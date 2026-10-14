from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import socket
import stat
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api import (
    SessionContext,
    _audit,
    _check_csrf,
    _clear_cookie,
    _client_host,
    _new_recovery_codes,
    _new_session,
    _new_user,
    _now,
    _require_admin,
    _session_json,
    _settings,
    _set_cookie,
    current_session,
    get_db,
)
from .config import Settings
from .errors import DomainError
from .models import (
    AuthSession,
    BackchannelLogoutReplay,
    IdentityAuditEvent,
    IdentityLink,
    Invitation,
    OIDCFlow,
    SSORateBucket,
    SSOConfiguration,
    SetupMarker,
    User,
)
from .schemas import OIDCStartRequest, SSOSettingsRequest, SsoLinkRequest, permissions_data
from .security import constant_time_equal, keyed_hash, new_secret, session_hash


router = APIRouter()
_DEFAULT_SETTINGS: dict = {
    "enabled": False,
    "display_name": "企業帳號",
    "issuer_url": "",
    "client_id": "",
    "scopes": ["openid", "profile", "email"],
    "allowed_email_domains": [],
    "email_claim": "email",
    "require_email_verified": True,
    "groups_claim": "groups",
    "provisioning": "invited_only",
    "default_permissions": {},
    "group_mappings": [],
    "login_policy": "password_and_sso",
    "required_acr": [],
    "required_amr": [],
}
_ALLOWED_ALGORITHMS = {"RS256", "ES256"}
_GOOGLE_ENDPOINT_HOSTS = {"oauth2.googleapis.com", "www.googleapis.com"}
_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
_CALLBACK_ERRORS = {
    "invalid_state",
    "configuration_changed",
    "sso_error",
    "sso_disabled",
    "account_link_required",
    "invitation_required",
    "email_domain_not_allowed",
    "email_unverified",
}


class SSOFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def ensure_sso_key(data_dir) -> None:
    path = data_dir / "sso.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, stat.S_IRUSR | stat.S_IWUSR)
    except FileExistsError:
        key = path.read_bytes()
        if len(key) != 32:
            raise RuntimeError("SSO encryption key is invalid")
        return
    key = os.urandom(32)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _sso_key(settings: Settings) -> bytes:
    path = settings.data_dir / "sso.key"
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise DomainError(503, "sso_key_unavailable", "Enterprise identity encryption is unavailable") from exc
    if len(key) != 32:
        raise DomainError(503, "sso_key_unavailable", "Enterprise identity encryption is unavailable")
    return key


def _encrypt(settings: Settings, plaintext: str, purpose: bytes) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_sso_key(settings)).encrypt(nonce, plaintext.encode("utf-8"), purpose)
    return "v1." + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")


def _decrypt(settings: Settings, value: str, purpose: bytes) -> str:
    try:
        encoded = value.removeprefix("v1.")
        combined = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        return AESGCM(_sso_key(settings)).decrypt(combined[:12], combined[12:], purpose).decode("utf-8")
    except Exception as exc:
        raise DomainError(503, "sso_key_unavailable", "Enterprise identity encryption is unavailable") from exc


def _config(db: Session) -> tuple[SSOConfiguration | None, dict, int]:
    row = db.get(SSOConfiguration, 1)
    values = dict(_DEFAULT_SETTINGS)
    if row is not None:
        values.update(row.settings_json or {})
    return row, values, row.revision if row else 0


def _public_origin(settings: Settings) -> str:
    origin = settings.sso_public_origin or (settings.auth_origins[0] if settings.auth_origins else "")
    if origin not in settings.auth_origins:
        raise DomainError(503, "sso_origin_unavailable", "Enterprise sign-in origin is not configured")
    return origin


def _callback_uri(settings: Settings) -> str:
    return _public_origin(settings) + "/auth-api/oidc/callback"


def _binding_cookie_name(settings: Settings) -> str:
    return settings.cookie_name[:108] + "_oidc_binding"


def _sso_public(row: SSOConfiguration | None, values: dict, settings: Settings) -> dict:
    return {
        "enabled": bool(values.get("enabled", False)),
        "display_name": values.get("display_name", _DEFAULT_SETTINGS["display_name"]),
        "login_policy": values.get("login_policy", "password_and_sso"),
        "configured": bool(
            values.get("enabled")
            and values.get("issuer_url")
            and values.get("client_id")
            and row is not None
            and row.client_secret_ciphertext
        ),
        "public_origin": _public_origin(settings),
    }


def _trimmed_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.netloc
    ):
        raise SSOFailure("discovery_invalid")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SSOFailure("discovery_invalid") from exc
    if port is not None and not 1 <= port <= 65535:
        raise SSOFailure("discovery_invalid")
    return value


def _host(url: str) -> str:
    parsed = urlsplit(url)
    return (parsed.hostname or "").casefold().rstrip(".")


def _is_loopback_host(host: str) -> bool:
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_public_url(url: str, settings: Settings, *, endpoint_hosts: set[str]) -> None:
    _trimmed_url(url)
    parsed = urlsplit(url)
    host = _host(url)
    allowed = {item.casefold().rstrip(".") for item in endpoint_hosts}
    if allowed and host not in allowed:
        raise SSOFailure("discovery_invalid")
    trusted_http = {item.casefold().rstrip(".") for item in settings.sso_http_hosts}
    explicitly_trusted = host in trusted_http or host in {
        item.casefold().rstrip(".") for item in settings.sso_allowed_endpoint_hosts
    }
    try:
        address = ipaddress.ip_address(host)
        if address.is_link_local or address.is_unspecified or address.is_multicast:
            raise SSOFailure("discovery_invalid")
        if (address.is_private or address.is_reserved) and not explicitly_trusted and not address.is_loopback:
            raise SSOFailure("discovery_invalid")
    except ValueError:
        if host in {"metadata", "metadata.google.internal", "instance-data.ec2.internal"} and not explicitly_trusted:
            raise SSOFailure("discovery_invalid")
        if not explicitly_trusted and not _is_loopback_host(host):
            try:
                resolved = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            except OSError as exc:
                raise SSOFailure("discovery_invalid") from exc
            if not resolved:
                raise SSOFailure("discovery_invalid")
            for result in resolved:
                resolved_ip = ipaddress.ip_address(result[4][0])
                if resolved_ip.is_private or resolved_ip.is_link_local or resolved_ip.is_unspecified or resolved_ip.is_reserved:
                    raise SSOFailure("discovery_invalid")
    if parsed.scheme == "http" and not _is_loopback_host(host) and host not in trusted_http:
        raise SSOFailure("discovery_invalid")


def _rewrite_backchannel(url: str, settings: Settings) -> tuple[str, str | None]:
    for public_prefix in sorted(settings.sso_backchannel_overrides, key=len, reverse=True):
        internal_prefix = settings.sso_backchannel_overrides[public_prefix]
        if url == public_prefix or url.startswith(public_prefix + "/"):
            rewritten = internal_prefix + url[len(public_prefix) :]
            _validate_public_url(rewritten, settings, endpoint_hosts=set())
            return rewritten, urlsplit(public_prefix).netloc
    return url, None


def _bounded_json_request(
    method: str,
    url: str,
    settings: Settings,
    *,
    endpoint_hosts: set[str],
    data: dict | None = None,
    authorization: str | None = None,
    max_bytes: int = 1_048_576,
) -> dict:
    _validate_public_url(url, settings, endpoint_hosts=endpoint_hosts)
    request_url, public_host = _rewrite_backchannel(url, settings)
    headers = {"Accept": "application/json"}
    if public_host:
        headers["Host"] = public_host
    if authorization:
        headers["Authorization"] = authorization
    try:
        with httpx.Client(
            timeout=httpx.Timeout(8.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
            verify=settings.sso_ca_bundle or True,
        ) as client:
            with client.stream(method, request_url, headers=headers, data=data) as response:
                if response.is_redirect or response.status_code != 200:
                    raise SSOFailure("provider_unavailable")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"application/json", "application/jwk-set+json"}:
                    raise SSOFailure("provider_unavailable")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise SSOFailure("provider_unavailable")
    except SSOFailure:
        raise
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise SSOFailure("provider_unavailable") from exc
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SSOFailure("provider_unavailable") from exc
    if not isinstance(parsed, dict):
        raise SSOFailure("provider_unavailable")
    return parsed


def _discovery(values: dict, settings: Settings) -> tuple[dict, list[str]]:
    issuer = values.get("issuer_url", "")
    _trimmed_url(issuer)
    host = _host(issuer)
    issuer_hosts = {host}
    endpoint_hosts = issuer_hosts | {item.casefold().rstrip(".") for item in settings.sso_allowed_endpoint_hosts}
    if issuer.startswith("https://") and host == "accounts.google.com":
        endpoint_hosts |= _GOOGLE_ENDPOINT_HOSTS
    well_known = issuer.rstrip("/") + "/.well-known/openid-configuration"
    document = _bounded_json_request("GET", well_known, settings, endpoint_hosts=endpoint_hosts)
    if document.get("issuer") != issuer:
        raise SSOFailure("discovery_invalid")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        value = document.get(key)
        if not isinstance(value, str):
            raise SSOFailure("discovery_invalid")
        _validate_public_url(value, settings, endpoint_hosts=endpoint_hosts)
    advertised = document.get("id_token_signing_alg_values_supported", ["RS256"])
    if not isinstance(advertised, list) or any(not isinstance(item, str) for item in advertised):
        raise SSOFailure("discovery_invalid")
    supported = sorted(_ALLOWED_ALGORITHMS.intersection(advertised))
    if not supported:
        raise SSOFailure("discovery_invalid")
    return document, supported


def _client_auth(document: dict, client_id: str, client_secret: str) -> tuple[str | None, bool]:
    methods = document.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
    if not isinstance(methods, list) or any(not isinstance(item, str) for item in methods):
        raise SSOFailure("discovery_invalid")
    if "client_secret_basic" in methods:
        from urllib.parse import quote_plus

        pair = f"{quote_plus(client_id, safe='~')}:{quote_plus(client_secret, safe='~')}".encode("ascii")
        return "Basic " + base64.b64encode(pair).decode("ascii"), False
    if "client_secret_post" in methods:
        return None, True
    raise SSOFailure("discovery_invalid")


def _jwks(document: dict, settings: Settings, values: dict) -> list[dict]:
    endpoint_hosts = {_host(values["issuer_url"])} | {
        item.casefold().rstrip(".") for item in settings.sso_allowed_endpoint_hosts
    }
    if values["issuer_url"].startswith("https://") and _host(values["issuer_url"]) == "accounts.google.com":
        endpoint_hosts |= _GOOGLE_ENDPOINT_HOSTS
    jwks = _bounded_json_request("GET", document["jwks_uri"], settings, endpoint_hosts=endpoint_hosts)
    keys = jwks.get("keys")
    if not isinstance(keys, list) or len(keys) > 100 or any(not isinstance(key, dict) for key in keys):
        raise SSOFailure("jwks_invalid")
    return keys


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _new_flow_value(settings: Settings, purpose: str, value: str) -> str:
    return keyed_hash(settings.service_secret, f"oidc-{purpose}", value)


def _rate_limit(db: Session, settings: Settings, action: str, address: str, *, limit: int = 20) -> None:
    now = _now()
    bucket = keyed_hash(settings.service_secret, f"sso-{action}", address)
    values = {"bucket_hash": bucket, "requests": 1, "window_started_at": now}
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        statement = sqlite_insert(SSORateBucket).values(**values)
    elif db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = pg_insert(SSORateBucket).values(**values)
    else:
        raise RuntimeError("Unsupported identity database")
    expired = SSORateBucket.window_started_at <= now - timedelta(minutes=15)
    statement = statement.on_conflict_do_update(
        index_elements=[SSORateBucket.bucket_hash],
        set_={
            "requests": case((expired, 1), else_=SSORateBucket.requests + 1),
            "window_started_at": case((expired, now), else_=SSORateBucket.window_started_at),
        },
    ).returning(SSORateBucket.requests)
    request_count = db.scalar(statement)
    if request_count is not None and request_count > limit:
        db.commit()
        raise DomainError(429, "sso_throttled", "Enterprise sign-in is temporarily rate limited")


def _settings_response(row: SSOConfiguration | None, values: dict, settings: Settings) -> dict:
    return {
        "revision": row.revision if row else 0,
        **values,
        "client_secret_configured": bool(row and row.client_secret_ciphertext),
        "redirect_uri": _callback_uri(settings),
        "backchannel_logout_uri": _public_origin(settings) + "/auth-api/oidc/backchannel-logout",
    }


def _merge_permissions(base: dict, additional: dict) -> dict:
    result = dict(base)
    priorities = {
        "work": {"worker": 1, "reviewer": 2, "manager": 3},
        "knowledge": {"reader": 1, "writer": 2, "manager": 3},
        "code": {"reader": 1, "writer": 2, "manager": 3},
    }
    for product in ("work", "knowledge", "code"):
        left = result.get(product)
        right = additional.get(product)
        if not right:
            continue
        if not left:
            result[product] = {"role": right["role"], "scope_ids": list(right.get("scope_ids", []))}
            continue
        role = right["role"] if priorities[product][right["role"]] > priorities[product][left["role"]] else left["role"]
        scopes = list(dict.fromkeys([*left.get("scope_ids", []), *right.get("scope_ids", [])]))
        result[product] = {"role": role, "scope_ids": scopes}
    return result


def _permissions_from_claims(values: dict, claims: dict) -> dict:
    merged = permissions_data(values.get("default_permissions", {}))
    group_claim = claims.get(values.get("groups_claim", "groups"), [])
    if isinstance(group_claim, str):
        groups = {group_claim}
    elif isinstance(group_claim, list) and all(isinstance(item, str) for item in group_claim):
        groups = set(group_claim)
    else:
        groups = set()
    for mapping in values.get("group_mappings", []):
        if mapping.get("group") in groups:
            merged = _merge_permissions(merged, permissions_data(mapping.get("permissions", {})))
    return permissions_data(merged)


def _claims_email(values: dict, claims: dict) -> tuple[str, str]:
    email = claims.get(values.get("email_claim", "email"))
    if not isinstance(email, str):
        raise SSOFailure("email_unverified")
    try:
        normalized = str(TypeAdapter(EmailStr).validate_python(email.strip())).casefold()
    except (ValidationError, ValueError) as exc:
        raise SSOFailure("email_unverified") from exc
    domain = normalized.rpartition("@")[2]
    if domain not in values.get("allowed_email_domains", []):
        raise SSOFailure("email_domain_not_allowed")
    verified = claims.get("email_verified") is True
    if values.get("issuer_url") == "https://accounts.google.com" and claims.get("email_verified") == "true":
        verified = True
    if values.get("require_email_verified", True) and not verified:
        raise SSOFailure("email_unverified")
    return email.strip(), normalized


def _verify_signed_token(
    token: str,
    keys: list[dict],
    values: dict,
    supported_algs: list[str],
    *,
    expected_nonce_hash: str | None = None,
    settings: Settings,
    logout: bool = False,
) -> dict:
    if len(token) > 65536:
        raise SSOFailure("sso_error")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise SSOFailure("sso_error") from exc
    algorithm = header.get("alg")
    if algorithm not in _ALLOWED_ALGORITHMS or algorithm not in supported_algs:
        raise SSOFailure("sso_error")
    if logout and header.get("typ") not in {None, "logout+jwt", "JWT"}:
        raise SSOFailure("sso_error")
    kid = header.get("kid")
    candidates: list[dict] = []
    for key in keys:
        if kid is not None and key.get("kid") != kid:
            continue
        if algorithm == "RS256" and key.get("kty") != "RSA":
            continue
        if algorithm == "ES256" and (key.get("kty") != "EC" or key.get("crv") != "P-256"):
            continue
        if key.get("use") not in {None, "sig"}:
            continue
        if key.get("alg") not in {None, algorithm}:
            continue
        candidates.append(key)
    if len(candidates) != 1:
        raise SSOFailure("sso_error")
    required_claims = ["iss", "aud", "iat", "jti"] if logout else ["iss", "sub", "aud", "exp", "iat"]
    try:
        signing_key = jwt.PyJWK.from_dict(candidates[0], algorithm=algorithm).key
        google_issuer = values["issuer_url"] == "https://accounts.google.com"
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=values["client_id"],
            issuer=None if google_issuer else values["issuer_url"],
            leeway=60,
            options={"require": required_claims, "verify_iat": True, "verify_iss": not google_issuer},
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise SSOFailure("sso_error") from exc
    audience = claims.get("aud")
    accepted_issuers = (
        {"https://accounts.google.com", "accounts.google.com"}
        if values["issuer_url"] == "https://accounts.google.com"
        else {values["issuer_url"]}
    )
    token_issuer = claims.get("iss")
    if not isinstance(token_issuer, str) or token_issuer not in accepted_issuers:
        raise SSOFailure("sso_error")
    if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != values["client_id"]:
        raise SSOFailure("sso_error")
    if "azp" in claims and claims["azp"] != values["client_id"]:
        raise SSOFailure("sso_error")
    if logout:
        events = claims.get("events")
        sid = claims.get("sid")
        subject = claims.get("sub")
        now = time.time()
        try:
            issued_at = float(claims["iat"])
        except (TypeError, ValueError, OverflowError) as exc:
            raise SSOFailure("sso_error") from exc
        if (
            "nonce" in claims
            or now - issued_at > 300
            or not isinstance(claims.get("jti"), str)
            or not claims["jti"]
            or len(claims["jti"]) > 512
            or (sid is not None and (not isinstance(sid, str) or not sid or len(sid) > 512))
            or (subject is not None and (not isinstance(subject, str) or not subject.strip() or len(subject) > 512))
        ):
            raise SSOFailure("sso_error")
        if subject is None and sid is None:
            raise SSOFailure("sso_error")
        if not isinstance(events, dict) or events.get(_LOGOUT_EVENT) != {}:
            raise SSOFailure("sso_error")
    else:
        if not isinstance(claims.get("sub"), str) or not claims["sub"].strip() or len(claims["sub"]) > 512:
            raise SSOFailure("sso_error")
        if expected_nonce_hash is not None:
            nonce = claims.get("nonce")
            if not isinstance(nonce, str) or not constant_time_equal(
                expected_nonce_hash, keyed_hash(settings.service_secret, "oidc-nonce", nonce)
            ):
                raise SSOFailure("sso_error")
    return claims


def _safe_redirect(settings: Settings, return_to: str, error: str | None = None) -> RedirectResponse:
    if return_to not in {"/work", "/knowledge", "/code"}:
        return_to = "/work"
    target = _public_origin(settings) + return_to
    if error in _CALLBACK_ERRORS:
        target += "?" + urlencode({"auth_error": error})
    return RedirectResponse(target, status_code=303)


def _clear_binding(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=_binding_cookie_name(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth-api/oidc",
    )


def _admin(ctx: SessionContext, settings: Settings, csrf: str | None) -> None:
    _check_csrf(ctx, settings, csrf)
    _require_admin(ctx)


def _validate_issuer(value: str, settings: Settings) -> None:
    if not value:
        return
    try:
        _trimmed_url(value)
        _validate_public_url(value, settings, endpoint_hosts=set())
    except SSOFailure as exc:
        raise DomainError(422, "invalid_issuer", "Issuer URL is invalid or points to an untrusted network target") from exc


def _require_enabled(db: Session, settings: Settings) -> tuple[SSOConfiguration, dict, int, str]:
    row, values, revision = _config(db)
    if not values.get("enabled") or row is None or not row.client_secret_ciphertext:
        raise DomainError(409, "sso_disabled", "Enterprise sign-in is not enabled")
    if db.get(SetupMarker, 1) is None:
        raise DomainError(409, "setup_required", "Initial administrator setup must finish first")
    try:
        secret = _decrypt(settings, row.client_secret_ciphertext, b"ordivant-sso-client-secret-v1")
    except DomainError:
        raise
    return row, values, revision, secret


def _audit_failure(db: Session, code: str) -> None:
    safe_code = code if code in _CALLBACK_ERRORS else "sso_error"
    _audit(db, "sso.login_failure", details={"code": safe_code})
    db.commit()


def _verify_authentication_assurance(values: dict, claims: dict) -> None:
    acr = values.get("required_acr", [])
    amr = values.get("required_amr", [])
    if acr and claims.get("acr") not in acr:
        raise SSOFailure("sso_error")
    methods = claims.get("amr", [])
    if amr and (not isinstance(methods, list) or not all(isinstance(item, str) for item in methods) or not set(amr).issubset(methods)):
        raise SSOFailure("sso_error")


def _effective_name(claims: dict, email: str) -> str:
    raw_name = claims.get("name") or claims.get("preferred_username") or email
    if not isinstance(raw_name, str):
        raw_name = email
    cleaned = "".join(char for char in raw_name.strip() if ord(char) >= 32 and ord(char) != 127)[:160].strip()
    return cleaned or email


def _revoke_user_sessions(db: Session, user_id: str, now: datetime) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def _consume_member_invitation(db: Session, normalized_email: str, now: datetime) -> Invitation:
    invitation = db.scalar(
        select(Invitation)
        .where(
            Invitation.normalized_email == normalized_email,
            Invitation.consumed_at.is_(None),
            Invitation.expires_at > now,
        )
        .order_by(Invitation.created_at.desc())
    )
    if invitation is None or invitation.role != "member":
        raise SSOFailure("invitation_required")
    consumed = db.execute(
        update(Invitation)
        .where(Invitation.id == invitation.id, Invitation.consumed_at.is_(None), Invitation.expires_at > now)
        .execution_options(synchronize_session=False)
        .values(consumed_at=now)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise SSOFailure("invitation_required")
    return invitation


def _provision_or_sync(
    db: Session,
    settings: Settings,
    values: dict,
    issuer: str,
    claims: dict,
) -> tuple[User, bool]:
    email, normalized_email = _claims_email(values, claims)
    subject = claims["sub"]
    now = _now()
    link = db.scalar(select(IdentityLink).where(IdentityLink.issuer == issuer, IdentityLink.subject == subject))
    permissions_changed = False
    if link is not None:
        user = db.get(User, link.user_id)
        if user is None or not user.active:
            raise SSOFailure("sso_disabled")
        if link.initial_email_checked_at is None:
            if normalized_email != user.normalized_email:
                raise SSOFailure("account_link_required")
            link.initial_email_checked_at = now
        if link.managed_permissions and user.permissions_source == "sso":
            fresh_permissions = _permissions_from_claims(values, claims)
            permissions_changed = fresh_permissions != (user.permissions or {})
            if permissions_changed:
                user.permissions = fresh_permissions
                user.updated_at = now
                _revoke_user_sessions(db, user.id, now)
        return user, permissions_changed

    existing = db.scalar(select(User).where(User.normalized_email == normalized_email))
    if existing is not None:
        raise SSOFailure("account_link_required")

    if values.get("provisioning") == "invited_only":
        invitation = _consume_member_invitation(db, normalized_email, now)
        user = _new_user(
            email=invitation.email,
            name=invitation.name,
            role="member",
            password=new_secret(),
            permissions=invitation.permissions,
        )
        user.credential_type = "sso"
        user.permissions_source = "manual"
        managed_permissions = False
    else:
        permissions = _permissions_from_claims(values, claims)
        user = _new_user(
            email=email,
            name=_effective_name(claims, email),
            role="member",
            password=new_secret(),
            permissions=permissions,
        )
        user.credential_type = "sso"
        user.permissions_source = "sso"
        managed_permissions = True
    db.add(user)
    db.flush()
    db.add(
        IdentityLink(
            id=str(uuid4()),
            user_id=user.id,
            issuer=issuer,
            subject=subject,
            managed_permissions=managed_permissions,
            initial_email_checked_at=now,
            created_at=now,
        )
    )
    return user, permissions_changed


@router.get("/sso/settings")
def get_sso_settings(
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    _require_admin(ctx)
    row, values, _revision = _config(db)
    result = _settings_response(row, values, _settings(request))
    db.commit()
    return result


@router.put("/sso/settings")
def put_sso_settings(
    body: SSOSettingsRequest,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _admin(ctx, settings, x_csrf_token)
    current, previous, revision = _config(db)
    if body.revision != revision:
        raise DomainError(409, "revision_conflict", "SSO settings changed; reload before saving")
    _validate_issuer(body.issuer_url, settings)
    values = body.model_dump(mode="json", exclude={"revision", "client_secret"}, exclude_none=True)
    if values["enabled"] and db.get(SetupMarker, 1) is None:
        raise DomainError(409, "setup_required", "Initial administrator setup must finish first")
    if values["enabled"] and (not values["issuer_url"] or not values["client_id"] or not values["allowed_email_domains"]):
        raise DomainError(409, "sso_not_configured", "Issuer, client ID and allowed email domains are required")
    if values["login_policy"] == "sso_only" and not values["enabled"]:
        raise DomainError(409, "sso_not_configured", "SSO-only login requires enabled enterprise sign-in")

    provider_changed = bool(
        previous.get("issuer_url") != values["issuer_url"] or previous.get("client_id") != values["client_id"]
    )
    secret = body.client_secret
    if provider_changed and current is not None and current.client_secret_ciphertext and not secret:
        raise DomainError(409, "client_secret_required", "Changing the issuer or client ID requires a replacement secret")
    if values["enabled"] and not secret and not (current and current.client_secret_ciphertext and not provider_changed):
        raise DomainError(409, "sso_not_configured", "A client secret is required to enable enterprise sign-in")
    encrypted_secret = (
        _encrypt(settings, secret, b"ordivant-sso-client-secret-v1")
        if secret
        else current.client_secret_ciphertext if current else None
    )
    secret_changed = bool(secret)

    next_revision = revision + 1
    now = _now()
    try:
        if current is None:
            db.add(
                SSOConfiguration(
                    id=1,
                    revision=next_revision,
                    settings_json=values,
                    client_secret_ciphertext=encrypted_secret,
                    updated_by=ctx.user.id,
                    updated_at=now,
                )
            )
            db.flush()
        else:
            changed = db.execute(
                update(SSOConfiguration)
                .where(SSOConfiguration.id == 1, SSOConfiguration.revision == body.revision)
                .values(
                    revision=next_revision,
                    settings_json=values,
                    client_secret_ciphertext=encrypted_secret,
                    updated_by=ctx.user.id,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                db.rollback()
                raise DomainError(409, "revision_conflict", "SSO settings changed; reload before saving")
            db.flush()
        policy_changed = any(
            previous.get(field) != values.get(field)
            for field in ("enabled", "allowed_email_domains", "default_permissions", "group_mappings", "provisioning", "login_policy", "issuer_url", "client_id", "required_acr", "required_amr")
        )
        if policy_changed:
            db.execute(
                update(AuthSession)
                .where(AuthSession.authentication_method == "oidc", AuthSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
        if values["login_policy"] == "sso_only" and previous.get("login_policy") != "sso_only":
            db.execute(
                update(AuthSession)
                .where(
                    AuthSession.authentication_method == "password",
                    AuthSession.revoked_at.is_(None),
                    AuthSession.user_id.in_(select(User.id).where(User.role != "admin")),
                )
                .values(revoked_at=now)
            )
        _audit(
            db,
            "sso.settings_changed",
            actor_id=ctx.user.id,
            details={
                "revision": next_revision,
                "enabled": values["enabled"],
                "client_secret_updated": secret_changed,
                "changed_fields": sorted(
                    [field for field in values if previous.get(field) != values.get(field)]
                    + (["client_secret"] if secret_changed else [])
                ),
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError(409, "revision_conflict", "SSO settings changed; reload before saving") from exc
    row, stored, _ = _config(db)
    return _settings_response(row, stored, settings)


@router.post("/sso/test")
def test_sso_connection(
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _admin(ctx, settings, x_csrf_token)
    row, values, _revision = _config(db)
    try:
        if not values.get("issuer_url") or not values.get("client_id"):
            raise SSOFailure("discovery_invalid")
        document, supported = _discovery(values, settings)
        keys = _jwks(document, settings, values)
        _client_auth(document, values["client_id"], "validation-only")
        if not any(key.get("kty") == "RSA" for key in keys) and not any(key.get("kty") == "EC" and key.get("crv") == "P-256" for key in keys):
            raise SSOFailure("jwks_invalid")
    except SSOFailure as exc:
        _audit(db, "sso.connection_test_failure", actor_id=ctx.user.id, details={"code": "sso_test_failed"})
        db.commit()
        raise DomainError(502, "sso_test_failed", "The identity provider discovery or signing keys could not be validated") from exc
    _audit(db, "sso.connection_test_success", actor_id=ctx.user.id, details={"issuer": values["issuer_url"]})
    db.commit()
    return {
        "status": "ok",
        "issuer": values["issuer_url"],
        "authorization_endpoint": document["authorization_endpoint"],
        "redirect_uri": _callback_uri(settings),
        "supported_algs": supported,
    }


@router.post("/oidc/start")
def oidc_start(
    body: OIDCStartRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    settings = _settings(request)
    if request.headers.get("origin") != _public_origin(settings):
        raise DomainError(403, "sso_origin_mismatch", "Enterprise sign-in must start from the canonical application origin")
    client_host = _client_host(request)
    _rate_limit(db, settings, "start", client_host)
    row, values, revision, _client_secret = _require_enabled(db, settings)
    try:
        document, _supported = _discovery(values, settings)
    except SSOFailure as exc:
        _audit(db, "sso.login_failure", details={"code": "sso_error"})
        db.commit()
        raise DomainError(503, "sso_provider_unavailable", "The enterprise identity provider is unavailable") from exc

    state = new_secret()
    nonce = new_secret()
    verifier = new_secret() + new_secret()
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    browser_binding = new_secret()
    now = _now()
    db.execute(delete(OIDCFlow).where(OIDCFlow.expires_at <= now))
    flow = OIDCFlow(
        id=str(uuid4()),
        state_hash=_new_flow_value(settings, "state", state),
        browser_binding_hash=_new_flow_value(settings, "binding", browser_binding),
        nonce_hash=keyed_hash(settings.service_secret, "oidc-nonce", nonce),
        pkce_verifier_ciphertext=_encrypt(settings, verifier, b"ordivant-oidc-pkce-v1"),
        return_to=body.return_to,
        config_revision=revision,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        consumed_at=None,
    )
    db.add(flow)
    db.commit()
    params = urlencode(
        {
            "client_id": values["client_id"],
            "redirect_uri": _callback_uri(settings),
            "response_type": "code",
            "scope": " ".join(values["scopes"]),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **({"acr_values": " ".join(values["required_acr"]), "claims": json.dumps({"id_token": {"acr": {"essential": True, "values": values["required_acr"]}}})} if values.get("required_acr") else {}),
        }
    )
    response.set_cookie(
        key=_binding_cookie_name(settings),
        value=browser_binding,
        max_age=300,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/auth-api/oidc",
    )
    return {"authorization_url": document["authorization_endpoint"] + "?" + params}


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = _settings(request)
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    provider_error = request.query_params.get("error")
    browser_binding = request.cookies.get(_binding_cookie_name(settings), "")
    callback_error = "invalid_state"
    return_to = "/work"
    auth_session = None
    raw_handle = None
    try:
        client_host = _client_host(request)
        _rate_limit(db, settings, "callback", client_host, limit=30)
        db.commit()
        if not state or len(state) > 256 or not browser_binding or len(browser_binding) > 256:
            raise SSOFailure("invalid_state")
        state_hash = _new_flow_value(settings, "state", state)
        binding_hash = _new_flow_value(settings, "binding", browser_binding)
        flow = db.scalar(select(OIDCFlow).where(OIDCFlow.state_hash == state_hash))
        if flow is None or not hmac.compare_digest(flow.browser_binding_hash, binding_hash) or _now() >= _aware(flow.expires_at):
            raise SSOFailure("invalid_state")
        return_to = flow.return_to if flow.return_to in {"/work", "/knowledge", "/code"} else "/work"
        consumed = db.execute(
            update(OIDCFlow)
            .where(
                OIDCFlow.id == flow.id,
                OIDCFlow.browser_binding_hash == binding_hash,
                OIDCFlow.consumed_at.is_(None),
                OIDCFlow.expires_at > _now(),
            )
            .execution_options(synchronize_session=False)
            .values(consumed_at=_now())
        )
        if consumed.rowcount != 1:
            db.rollback()
            raise SSOFailure("invalid_state")
        db.commit()
        _row, values, current_revision = _config(db)
        if flow.config_revision != current_revision:
            raise SSOFailure("configuration_changed")
        if provider_error or not code or len(code) > 4096:
            raise SSOFailure("sso_error")
        row, values, _revision, client_secret = _require_enabled(db, settings)
        document, supported = _discovery(values, settings)
        verifier = _decrypt(settings, flow.pkce_verifier_ciphertext, b"ordivant-oidc-pkce-v1")
        client_auth, secret_in_post = _client_auth(document, values["client_id"], client_secret)
        token_request = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _callback_uri(settings),
            "client_id": values["client_id"],
            "code_verifier": verifier,
        }
        if secret_in_post:
            token_request["client_secret"] = client_secret
        token_response = _bounded_json_request(
            "POST",
            document["token_endpoint"],
            settings,
            endpoint_hosts={_host(values["issuer_url"])}
            | set(settings.sso_allowed_endpoint_hosts)
            | (_GOOGLE_ENDPOINT_HOSTS if _host(values["issuer_url"]) == "accounts.google.com" else set()),
            data=token_request,
            authorization=client_auth,
            max_bytes=65536,
        )
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str):
            raise SSOFailure("sso_error")
        signing_keys = _jwks(document, settings, values)
        claims = _verify_signed_token(
            id_token,
            signing_keys,
            values,
            supported,
            expected_nonce_hash=flow.nonce_hash,
            settings=settings,
        )
        _verify_authentication_assurance(values, claims)
        user, _permissions_changed = _provision_or_sync(db, settings, values, values["issuer_url"], claims)
        if not user.active:
            raise SSOFailure("sso_disabled")
        sid = claims.get("sid")
        if not isinstance(sid, str) or len(sid) > 512:
            sid = None
        auth_session, raw_handle = _new_session(
            db,
            user,
            settings,
            authentication_method="oidc",
            provider_name=values["display_name"],
            oidc_issuer=values["issuer_url"],
            oidc_subject=claims["sub"],
            oidc_sid=sid,
        )
        _audit(db, "sso.login_success", actor_id=user.id, user_id=user.id, details={"provider": values["display_name"]})
        db.commit()
        callback_error = ""
    except SSOFailure as exc:
        callback_error = exc.code if exc.code in _CALLBACK_ERRORS else "sso_error"
        auth_session = None
        raw_handle = None
        db.rollback()
        _audit_failure(db, callback_error)
    except IntegrityError:
        callback_error = "invitation_required"
        auth_session = None
        raw_handle = None
        db.rollback()
        _audit_failure(db, callback_error)
    except Exception:
        callback_error = "sso_error"
        auth_session = None
        raw_handle = None
        db.rollback()
        _audit_failure(db, callback_error)

    redirect = _safe_redirect(settings, return_to, callback_error or None)
    if auth_session is not None and raw_handle is not None:
        _set_cookie(redirect, raw_handle, settings)
    _clear_binding(redirect, settings)
    return redirect


@router.post("/oidc/backchannel-logout")
async def backchannel_logout(request: Request, db: Session = Depends(get_db)) -> dict:
    settings = _settings(request)
    client_host = _client_host(request)
    try:
        _rate_limit(db, settings, "logout", client_host, limit=60)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/x-www-form-urlencoded":
            raise SSOFailure("sso_error")
        if int(request.headers.get("content-length", "0") or "0") > 65536:
            raise SSOFailure("sso_error")
        body = await request.body()
        if len(body) > 65536:
            raise SSOFailure("sso_error")
        from urllib.parse import parse_qs

        form = parse_qs(body.decode("utf-8", "strict"), keep_blank_values=True, max_num_fields=8)
        logout_token_values = form.get("logout_token", [])
        if len(logout_token_values) != 1 or not logout_token_values[0]:
            raise SSOFailure("sso_error")
        logout_token = logout_token_values[0]
        _row, values, _revision = _config(db)
        if not values.get("issuer_url") or not values.get("client_id"):
            raise SSOFailure("sso_error")
        document, supported = _discovery(values, settings)
        claims = _verify_signed_token(
            logout_token,
            _jwks(document, settings, values),
            values,
            supported,
            settings=settings,
            logout=True,
        )
        issued = int(claims["iat"])
        replay_expiry = int(claims.get("exp", issued + 300))
        issuer = claims["iss"]
        jti_hash = keyed_hash(settings.service_secret, "logout-jti", claims["jti"])
        now = _now()
        db.execute(delete(BackchannelLogoutReplay).where(BackchannelLogoutReplay.expires_at <= now))
        replay = BackchannelLogoutReplay(
            id=str(uuid4()),
            issuer=issuer,
            jti_hash=jti_hash,
            expires_at=datetime.fromtimestamp(replay_expiry, tz=timezone.utc) + timedelta(seconds=60),
            received_at=now,
        )
        db.add(replay)
        db.flush()
        conditions = [AuthSession.authentication_method == "oidc", AuthSession.oidc_issuer == issuer]
        if claims.get("sub") is not None:
            conditions.append(AuthSession.oidc_subject == claims["sub"])
        if claims.get("sid") is not None:
            conditions.append(AuthSession.oidc_sid == claims["sid"])
        changed = db.execute(
            update(AuthSession)
            .where(*conditions, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        _audit(
            db,
            "sso.backchannel_logout",
            details={"sessions_revoked": max(changed.rowcount or 0, 0)},
        )
        db.commit()
        return {"ok": True}
    except (SSOFailure, UnicodeDecodeError, ValueError, IntegrityError) as exc:
        db.rollback()
        _audit(db, "sso.backchannel_logout_failure", details={"code": "sso_error"})
        db.commit()
        raise DomainError(400, "invalid_logout_token", "Back-channel logout token is invalid") from exc


@router.get("/sso/links")
def get_sso_links(
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    _require_admin(ctx)
    links = db.scalars(select(IdentityLink).order_by(IdentityLink.created_at.desc())).all()
    response = {
        "links": [
            {
                "id": link.id,
                "user_id": link.user_id,
                "issuer": link.issuer,
                "subject": link.subject,
                "managed_permissions": link.managed_permissions,
            }
            for link in links
        ]
    }
    db.commit()
    return response


@router.post("/sso/links", status_code=201)
def create_sso_link(
    body: SsoLinkRequest,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _admin(ctx, settings, x_csrf_token)
    _row, values, _revision = _config(db)
    if not values.get("issuer_url"):
        raise DomainError(409, "sso_not_configured", "Configure an issuer before linking accounts")
    user = db.get(User, body.user_id)
    if user is None:
        raise DomainError(404, "user_not_found", "User not found")
    if user.permissions_source == "scim" and body.managed_permissions:
        raise DomainError(409, "scim_managed_user", "Provisioning groups manage this account's permissions; link with managed_permissions disabled")
    if db.scalar(select(IdentityLink.id).where(IdentityLink.issuer == values["issuer_url"], IdentityLink.subject == body.subject)):
        raise DomainError(409, "sso_link_conflict", "That enterprise subject is already linked")
    now = _now()
    link = IdentityLink(
        id=str(uuid4()),
        user_id=user.id,
        issuer=values["issuer_url"],
        subject=body.subject,
        managed_permissions=body.managed_permissions,
        initial_email_checked_at=None,
        created_by=ctx.user.id,
        created_at=now,
    )
    db.add(link)
    if body.managed_permissions:
        user.permissions_source = "sso"
        user.updated_at = now
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError(409, "sso_link_conflict", "That user already has a link for this issuer") from exc
    _revoke_user_sessions(db, user.id, now)
    _audit(db, "sso.link_created", actor_id=ctx.user.id, user_id=user.id, details={"link_id": link.id})
    db.commit()
    return {
        "id": link.id,
        "user_id": link.user_id,
        "issuer": link.issuer,
        "subject": link.subject,
        "managed_permissions": link.managed_permissions,
    }


@router.delete("/sso/links/{link_id}")
def delete_sso_link(
    link_id: str,
    request: Request,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> dict:
    settings = _settings(request)
    _admin(ctx, settings, x_csrf_token)
    link = db.get(IdentityLink, link_id)
    if link is None:
        raise DomainError(404, "sso_link_not_found", "Enterprise account link not found")
    now = _now()
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == link.user_id,
            AuthSession.authentication_method == "oidc",
            AuthSession.oidc_issuer == link.issuer,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    _audit(db, "sso.link_deleted", actor_id=ctx.user.id, user_id=link.user_id, details={"link_id": link.id})
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.get("/audit")
def get_identity_audit(
    limit: int = 100,
    ctx: SessionContext = Depends(current_session),
    db: Session = Depends(get_db),
) -> dict:
    _require_admin(ctx)
    if not 1 <= limit <= 200:
        raise DomainError(422, "invalid_limit", "Audit limit must be between 1 and 200")
    rows = db.scalars(select(IdentityAuditEvent).order_by(IdentityAuditEvent.created_at.desc()).limit(limit)).all()
    result = {
        "events": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
                "actor_id": row.actor_id,
                "user_id": row.user_id,
                "action": row.action,
                "details": row.details or {},
            }
            for row in rows
        ]
    }
    db.commit()
    return result


def __all__():
    return ["router", "ensure_sso_key"]
