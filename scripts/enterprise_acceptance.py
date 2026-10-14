"""SCIM and real TLS SMTP acceptance, restricted to the synthetic QA stack on 8096.

Run --prepare with the backend uv environment, then use the QA Compose override
under .cache/collaboration-qa/enterprise before running acceptance without arguments.
All credentials and mail links remain inside ignored QA files or process memory.
"""
from __future__ import annotations
import argparse
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import httpx

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.cache/collaboration-qa'
DATA = QA / 'enterprise'
BASE = 'http://127.0.0.1:8096'
PROJECT = 'ordivant-collaboration-qa-20261014'


def prepare():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'inbox').mkdir(exist_ok=True)
    if not (DATA / 'scim-token').exists():
        (DATA / 'scim-token').write_text(secrets.token_urlsafe(48), encoding='utf-8')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'smtp-sink')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('smtp-sink')]), critical=False).sign(key, hashes.SHA256()))
    (DATA / 'smtp.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (DATA / 'smtp.key').write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    # Fixed project/service names and no host ports; this sink cannot contact real mail servers.
    (DATA / 'compose.yaml').write_text('''services:
  smtp-sink:
    image: python:3.12-slim-bookworm
    restart: unless-stopped
    command: [python, /sink.py]
    security_opt: [no-new-privileges:true]
    volumes:
      - ${ORDIVANT_QA_ROOT}/scripts/qa_smtp_sink.py:/sink.py:ro
      - ${ORDIVANT_QA_ROOT}/.cache/collaboration-qa/enterprise:/qa
  identity-api:
    environment:
      ORDIVANT_SCIM_TOKEN_FILE: /qa/scim-token
      ORDIVANT_SMTP_HOST: smtp-sink
      ORDIVANT_SMTP_PORT: '8025'
      ORDIVANT_SMTP_SENDER: qa-noreply@example.com
      ORDIVANT_SMTP_STARTTLS: 'true'
      SSL_CERT_FILE: /qa/smtp.pem
    volumes:
      - ${ORDIVANT_QA_ROOT}/.cache/collaboration-qa/enterprise:/qa:ro
''', encoding='utf-8')
    print('ENTERPRISE_QA_PREPARED credentials_not_emitted=true')


def run():
    context = json.loads((QA / 'context.json').read_text(encoding='utf-8'))
    if context.get('base_url') != BASE or not context.get('run_id'):
        raise RuntimeError('Only the isolated synthetic QA project is allowed')
    admin = context['users']['admin']
    checks = []
    with httpx.Client(base_url=BASE, timeout=20, trust_env=False,
                      cookies={admin['cookie_name']: admin['cookie_value']}) as client:
        def request(method, path, *, expected=200, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != expected:
                raise RuntimeError(f'{method} {path.split("?")[0]} HTTP {response.status_code}, expected {expected}')
            checks.append(f'{method} {path.split("?")[0]} -> {expected}')
            return response
        browser = {'Origin': BASE, 'X-CSRF-Token': admin['csrf_token']}
        scim = {'Authorization': 'Bearer ' + (DATA / 'scim-token').read_text(encoding='utf-8').strip()}
        me = request('GET', '/auth-api/me').json()
        if context['run_id'] not in me['user']['email']:
            raise RuntimeError('The administrator is not the saved synthetic QA account')
        current = request('GET', '/auth-api/enterprise').json()
        if not current['scim_enabled'] or not current['mail_transport_ready']:
            raise RuntimeError('QA enterprise transport is not configured')
        ident = secrets.token_hex(5)
        email = f'qa-enterprise-{ident}@example.com'
        provisioned = request('POST', '/api/scim/v2/Users', headers=scim, expected=201,
            json={'userName': f'qa-scim-{ident}@example.com', 'active': True}).json()
        group_name = f'qa-group-{ident}'
        group = request('POST', '/api/scim/v2/Groups', headers=scim, expected=201,
            json={'displayName': group_name, 'members': []}).json()
        baseline = {'audit_retention_days': current['audit_retention_days'], 'scim_group_mappings': current['scim_group_mappings']}
        granted = {**baseline, 'scim_group_mappings': {**baseline['scim_group_mappings'], group_name:
            {'work': {'role': 'worker', 'scope_ids': [context['work']['project_id']]}}}}
        try:
            for _ in range(3):
                request('PATCH', f'/api/scim/v2/Groups/{group["id"]}', headers=scim,
                    json={'Operations': [{'op': 'replace', 'path': 'members', 'value': []}]})
                request('PUT', '/auth-api/enterprise', headers=browser, json=granted)
                barrier = Barrier(2)
                def mutate(index):
                    barrier.wait(timeout=10)
                    if index == 0:
                        request('PATCH', f'/api/scim/v2/Groups/{group["id"]}', headers=scim,
                            json={'Operations': [{'op': 'replace', 'path': 'members', 'value': [{'value': provisioned['id']}]}]})
                    else:
                        request('PUT', '/auth-api/enterprise', headers=browser, json=baseline)
                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(mutate, [0, 1]))
                users = request('GET', '/auth-api/users').json()['users']
                user = next(item for item in users if item['email'] == f'qa-scim-{ident}@example.com')
                if user['permissions'] or user['permissions_source'] != 'scim':
                    raise RuntimeError('Concurrent SCIM group and policy edits retained revoked grants')
        finally:
            request('PUT', '/auth-api/enterprise', headers=browser, json=baseline)
            request('DELETE', f'/api/scim/v2/Groups/{group["id"]}', headers=scim, expected=204)
        checks.append('PostgreSQL concurrent SCIM membership and policy edits preserve revoked grants')
        request('PATCH', f'/api/scim/v2/Users/{provisioned["id"]}', headers=scim,
            json={'Operations': [{'op': 'replace', 'path': 'active', 'value': False}]})
        request('DELETE', f'/api/scim/v2/Users/{provisioned["id"]}', headers=scim, expected=204)
        request('GET', '/api/scim/v2/Users', expected=401)
        invitation = request('POST', '/auth-api/invitations', expected=201, headers=browser,
            json={'email': email, 'name': 'Synthetic mail recipient', 'role': 'member', 'permissions': {}}).json()
        if not invitation.get('mail_queued'):
            raise RuntimeError('Invitation was not queued')
        def wait_mail(subject):
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                for path in (DATA / 'inbox').glob('*.json'):
                    item = json.loads(path.read_text(encoding='utf-8'))
                    if item['to'] == email and subject in item['subject']:
                        return item
                time.sleep(1)
            raise RuntimeError('Expected synthetic SMTP receipt was not delivered')
        received = wait_mail('invitation')
        link = next(line.strip() for line in received['body'].splitlines() if line.startswith(BASE))
        parsed = urlsplit(link)
        params = parse_qs(parsed.fragment)
        if parsed.query or params.get('code') != [invitation['invitation_code']]:
            raise RuntimeError('Mail link must use the fragment for its one-time code')
        checks.append('real STARTTLS invitation delivery and fragment link')
        password = secrets.token_urlsafe(32) + 'Aa8!'
        with httpx.Client(base_url=BASE, timeout=15, trust_env=False) as member:
            response = member.post('/auth-api/accept-invitation', headers={'Origin': BASE},
                json={'invitation_code': invitation['invitation_code'], 'password': password})
            if response.status_code != 201:
                raise RuntimeError('Synthetic mail invitation could not be accepted')
            old_session = dict(member.cookies)
            for address in [email, f'qa-absent-{ident}@example.com']:
                response = member.post('/auth-api/request-recovery', headers={'Origin': BASE}, json={'email': address})
                if response.status_code != 200 or response.json() != {'accepted': True}:
                    raise RuntimeError('Recovery mail response disclosed account existence')
            recovered_mail = wait_mail('recovery')
            link = next(line.strip() for line in recovered_mail['body'].splitlines() if line.startswith(BASE))
            code = parse_qs(urlsplit(link).fragment)['code'][0]
            response = member.post('/auth-api/recover', headers={'Origin': BASE},
                json={'email': email, 'recovery_code': code, 'new_password': secrets.token_urlsafe(32) + 'Aa8!'})
            if response.status_code != 200:
                raise RuntimeError('Synthetic emailed recovery could not be completed')
            replay = member.post('/auth-api/recover', headers={'Origin': BASE},
                json={'email': email, 'recovery_code': code, 'new_password': password})
            if replay.status_code != 401:
                raise RuntimeError('Recovery mail credential was reusable')
            with httpx.Client(base_url=BASE, cookies=old_session, timeout=15, trust_env=False) as stale:
                if stale.get('/auth-api/me').status_code != 401:
                    raise RuntimeError('Recovery did not revoke the previous session')
        checks.append('real recovery mail, uniform response, one-use code and old-session revocation')
        export = request('GET', '/auth-api/audit/export?limit=100')
        if scim['Authorization'][7:] in export.text or invitation['invitation_code'] in export.text or code in export.text:
            raise RuntimeError('Credential leaked into audit export')
        request('POST', '/auth-api/audit/retention', expected=403, headers={'Origin': BASE})
    report = {'status': 'passed', 'base_url': BASE, 'compose_project': PROJECT, 'checks': checks}
    (QA / 'enterprise-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f'ENTERPRISE_ACCEPTANCE_PASSED checks={len(checks)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    try:
        prepare() if args.prepare else run()
    except Exception as error:
        # Paths/statuses are safe; exception internals from transports could contain credentials.
        print(f'ENTERPRISE_ACCEPTANCE_FAILED type={type(error).__name__}')
        raise SystemExit(1) from None
