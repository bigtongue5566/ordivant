"""No-LLM Knowledge authoring round trip and PostgreSQL tree races in synthetic QA."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import base64
import hashlib
import json
import httpx

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.cache/collaboration-qa'
BASE = 'http://127.0.0.1:8096'


def run():
    saved = json.loads((QA / 'context.json').read_text(encoding='utf-8'))
    if saved.get('base_url') != BASE or not saved.get('run_id'):
        raise RuntimeError('Only the isolated synthetic QA URL is allowed')
    admin = saved['users']['admin']
    prefix = '/knowledge-api'
    checks = []
    clients = [httpx.Client(base_url=BASE, timeout=30, trust_env=False, cookies={admin['cookie_name']: admin['cookie_value']},
        headers={'Origin': BASE, 'X-CSRF-Token': admin['csrf_token']}),
        httpx.Client(base_url=BASE, timeout=30, trust_env=False, headers={'Authorization': 'Bearer ' + saved['agents']['knowledge']['token'], 'Origin': BASE})]
    def request(client, method, path, body=None, expected=200):
        result = client.request(method, prefix + path, json=body, headers={'Idempotency-Key': uuid4().hex} if method != 'GET' else {})
        if result.status_code != expected:
            code = result.json().get('detail', {}).get('code', 'unknown') if result.headers.get('content-type', '').startswith('application/json') else 'non-json'
            raise RuntimeError(f'{method} {path} HTTP {result.status_code} code {code}')
        return result
    ident = uuid4().hex[:10]
    space = saved['knowledge']['space_id']
    def create(title, parent=None, client=None):
        return request(client or clients[0], 'POST', '/documents', {'space_id': space, 'title': f'P0 {ident} {title}',
            'body': 'Published original paragraph.', 'parent_id': parent}, 201).json()['document']
    try:
        for client in clients:
            request(client, 'GET', '/me')
        template = request(clients[0], 'POST', f'/spaces/{space}/templates',
            {'name': f'P0 {ident} checklist', 'description': 'Synthetic acceptance', 'body': '# Checklist\n\n- [ ] Review'}, 201).json()
        assert any(item['id'] == template['id'] for item in request(clients[1], 'GET', f'/spaces/{space}/templates').json())
        parent = create('Parent')
        child = create('Child', parent['id'], clients[1])
        request(clients[0], 'PATCH', f'/documents/{parent["id"]}/organization', {'parent_id': child['id']}, 409)
        comment = request(clients[1], 'POST', f'/documents/{child["id"]}/comments', {
            'body': '<script>not executable</script> Please review', 'anchor': {'version': 1, 'quote': 'original paragraph', 'start': 10, 'end': 28}}, 201).json()
        request(clients[0], 'POST', f'/documents/{child["id"]}/comments', {'body': 'Human response', 'parent_id': comment['id']}, 201)
        request(clients[0], 'PATCH', f'/document-comments/{comment["id"]}', {'resolved': True})
        request(clients[0], 'POST', f'/documents/{child["id"]}/versions', {'expected_version': 1, 'title': child['title'],
            'body': 'Second published paragraph.', 'change_summary': 'Synthetic update'}, 201)
        diff = request(clients[1], 'GET', f'/documents/{child["id"]}/diff?from_version=1&to_version=2').json()
        assert '-Published original paragraph.' in diff['diff']
        restored = request(clients[0], 'POST', f'/documents/{child["id"]}/restore', {'version': 1, 'expected_current_version': 2}, 201).json()
        assert restored['version'] == 3 and restored['body'] == 'Published original paragraph.'
        request(clients[1], 'POST', f'/documents/{child["id"]}/restore', {'version': 1, 'expected_current_version': 2}, 409)
        checks.append('human/Agent templates, tree, anchored comments, reply, resolve, immutable diff and restore conflict')
        content = b'QA scoped immutable attachment\n' * 75000  # >1 MiB checks actual reverse proxy body limit.
        uploaded = request(clients[0], 'POST', f'/collaboration/document/{child["id"]}/attachments',
            {'filename': 'qa-notes.txt', 'content_base64': base64.b64encode(content).decode()}, 201).json()
        downloaded = request(clients[1], 'GET', f'/collaboration/attachments/{uploaded["id"]}/download')
        assert hashlib.sha256(downloaded.content).hexdigest() == uploaded['sha256']
        checks.append('large attachment survives reverse proxy and authorized human/Agent round trip with exact hash')
        # Distinct principals are required: one actor's authorization row lock must not hide a tree race.
        a, b = create('Race A'), create('Race B')
        barrier = Barrier(2)
        def move(index):
            barrier.wait(timeout=10)
            target, new_parent = (a, b) if index == 0 else (b, a)
            response = clients[index].patch(prefix + f'/documents/{target["id"]}/organization',
                json={'parent_id': new_parent['id']}, headers={'Idempotency-Key': uuid4().hex})
            return response.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(move, [0, 1]))
        assert sorted(statuses) == [200, 409], statuses
        checks.append('PostgreSQL simultaneous reciprocal moves: exactly one succeeds, no cycle')
        archive_parent = create('Archive race')
        barrier = Barrier(2)
        def archive_or_create(index):
            barrier.wait(timeout=10)
            if index == 0:
                result = clients[0].patch(prefix + f'/documents/{archive_parent["id"]}/organization',
                    json={'archived': True}, headers={'Idempotency-Key': uuid4().hex})
            else:
                result = clients[1].post(prefix + '/documents', json={'space_id': space, 'title': f'P0 {ident} racing child',
                    'body': 'Child must not disappear', 'parent_id': archive_parent['id']}, headers={'Idempotency-Key': uuid4().hex})
            return result.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(archive_or_create, [0, 1]))
        assert statuses in [[200, 409], [409, 201]], statuses
        checks.append('PostgreSQL concurrent archive/create cannot leave an active child under archived parent')
        report = {'status': 'passed', 'base_url': BASE, 'checks': checks, 'document_id': child['id'], 'space_id': space}
        (QA / 'knowledge-authoring-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'KNOWLEDGE_AUTHORING_ACCEPTANCE_PASSED checks={len(checks)}')
    finally:
        for client in clients:
            client.close()


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print(f'KNOWLEDGE_AUTHORING_ACCEPTANCE_FAILED type={type(error).__name__}')
        raise SystemExit(1) from None
