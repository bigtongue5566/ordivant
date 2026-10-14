from __future__ import annotations

import os
import re
import json
import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url


_COOKIE_NAME = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str = field(repr=False)
    mode: str
    cookie_name: str
    service_secret: str = field(repr=False)
    auth_origins: tuple[str, ...]
    cookie_secure: bool
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    throttle_limit: int = 5
    throttle_window_seconds: int = 900
    throttle_lock_seconds: int = 900
    auth_trusted_proxy_hosts: tuple[str, ...] = ()
    sso_http_hosts: tuple[str, ...] = ()
    sso_allowed_endpoint_hosts: tuple[str, ...] = ()
    sso_backchannel_overrides: dict[str, str] = field(default_factory=dict, repr=False)
    sso_public_origin: str | None = None
    sso_ca_bundle: str | None = None
    scim_token: str | None = field(default=None, repr=False)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    smtp_sender: str | None = None
    smtp_starttls: bool = True
    mail_public_origin: str | None = None


def _read_configured_secret() -> str:
    path = os.getenv("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE", "").strip()
    if not path:
        raise RuntimeError("ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE is required")
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError("Identity service token file is unavailable") from exc
    if len(value.encode("utf-8")) < 32:
        raise RuntimeError("Identity service token must contain at least 32 bytes")
    return value


def _read_database_url(data_dir: Path) -> str:
    value = os.getenv("ORDIVANT_IDENTITY_DATABASE_URL", "").strip()
    path = os.getenv("ORDIVANT_IDENTITY_DATABASE_URL_FILE", "").strip()
    if path:
        try:
            value = Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError("Identity database URL file is unavailable") from exc
    if not value:
        value = f"sqlite:///{(data_dir / 'identity.sqlite3').as_posix()}"
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def _parse_origins(raw: str, *, secure: bool, mode: str) -> tuple[str, ...]:
    origins = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not origins or "*" in origins:
        raise RuntimeError("ORDIVANT_AUTH_ORIGINS must list exact trusted browser origins")
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or origin != f"{parsed.scheme}://{parsed.netloc}"
        ):
            raise RuntimeError("ORDIVANT_AUTH_ORIGINS contains an invalid origin")
        is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not secure and (parsed.scheme != "http" or not is_loopback):
            raise RuntimeError("Insecure auth cookies are allowed only for loopback origins")
        if mode == "production" and parsed.scheme != "https" and not (not secure and is_loopback):
            raise RuntimeError("Production identity service requires HTTPS browser origins outside loopback")
    return origins


def get_settings() -> Settings:
    mode = os.getenv("ORDIVANT_MODE", "").strip().lower()
    if mode not in {"development", "production"}:
        raise RuntimeError("ORDIVANT_MODE must be explicitly set to development or production")

    cookie_name = os.getenv("ORDIVANT_AUTH_COOKIE_NAME", "").strip()
    if not _COOKIE_NAME.fullmatch(cookie_name):
        raise RuntimeError("ORDIVANT_AUTH_COOKIE_NAME must be an explicit unique cookie name")

    secure_value = os.getenv("ORDIVANT_AUTH_COOKIE_SECURE", "").strip().lower()
    if secure_value not in {"true", "false"}:
        raise RuntimeError("ORDIVANT_AUTH_COOKIE_SECURE must be explicitly set to true or false")
    cookie_secure = secure_value == "true"

    data_dir = Path(os.getenv("ORDIVANT_IDENTITY_DATA_DIR", "/data")).expanduser().resolve()
    origins = _parse_origins(os.getenv("ORDIVANT_AUTH_ORIGINS", ""), secure=cookie_secure, mode=mode)
    sso_http_hosts = _parse_host_list(os.getenv("ORDIVANT_SSO_HTTP_HOSTS", ""))
    sso_endpoint_hosts = _parse_host_list(os.getenv("ORDIVANT_SSO_ALLOWED_ENDPOINT_HOSTS", ""))
    trusted_proxy_hosts = _parse_proxy_host_list(os.getenv("ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS", ""))
    public_origin = os.getenv("ORDIVANT_SSO_PUBLIC_ORIGIN", "").strip() or None
    if public_origin is not None and public_origin not in origins:
        raise RuntimeError("ORDIVANT_SSO_PUBLIC_ORIGIN must match an exact trusted auth origin")
    ca_bundle = os.getenv("ORDIVANT_SSO_CA_BUNDLE", "").strip() or None
    if ca_bundle is not None and not Path(ca_bundle).expanduser().is_file():
        raise RuntimeError("ORDIVANT_SSO_CA_BUNDLE must point to a readable CA bundle file")
    overrides_raw = os.getenv("ORDIVANT_SSO_BACKCHANNEL_OVERRIDES", "").strip()
    try:
        overrides_value = json.loads(overrides_raw) if overrides_raw else {}
    except ValueError as exc:
        raise RuntimeError("ORDIVANT_SSO_BACKCHANNEL_OVERRIDES must be a JSON object") from exc
    if not isinstance(overrides_value, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in overrides_value.items()
    ):
        raise RuntimeError("ORDIVANT_SSO_BACKCHANNEL_OVERRIDES must map issuer URL prefixes to URL prefixes")
    overrides: dict[str, str] = {}
    for public_prefix, internal_prefix in overrides_value.items():
        for prefix in (public_prefix, internal_prefix):
            parsed = urlsplit(prefix)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or prefix != f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            ):
                raise RuntimeError("SSO backchannel override contains an invalid URL prefix")
        if urlsplit(internal_prefix).scheme == "http" and urlsplit(internal_prefix).hostname not in sso_http_hosts:
            raise RuntimeError("HTTP backchannel override targets must be listed in ORDIVANT_SSO_HTTP_HOSTS")
        overrides[public_prefix.rstrip("/")] = internal_prefix.rstrip("/")
    database_url = _read_database_url(data_dir)
    if mode == "production" and make_url(database_url).get_backend_name() != "postgresql":
        raise RuntimeError("Production identity service requires PostgreSQL")
    return Settings(
        data_dir=data_dir,
        database_url=database_url,
        mode=mode,
        cookie_name=cookie_name,
        service_secret=_read_configured_secret(),
        auth_origins=origins,
        cookie_secure=cookie_secure,
        auth_trusted_proxy_hosts=trusted_proxy_hosts,
        sso_http_hosts=sso_http_hosts,
        sso_allowed_endpoint_hosts=sso_endpoint_hosts,
        sso_backchannel_overrides=overrides,
        sso_public_origin=public_origin,
        sso_ca_bundle=str(Path(ca_bundle).expanduser().resolve()) if ca_bundle else None,
        scim_token=_optional_secret("ORDIVANT_SCIM_TOKEN_FILE", minimum=32),
        smtp_host=os.getenv("ORDIVANT_SMTP_HOST", "").strip() or None,
        smtp_port=int(os.getenv("ORDIVANT_SMTP_PORT", "587")),
        smtp_username=os.getenv("ORDIVANT_SMTP_USERNAME", "").strip() or None,
        smtp_password=_optional_secret("ORDIVANT_SMTP_PASSWORD_FILE"),
        smtp_sender=os.getenv("ORDIVANT_SMTP_SENDER", "").strip() or None,
        smtp_starttls=os.getenv("ORDIVANT_SMTP_STARTTLS", "true").lower() == "true",
        mail_public_origin=public_origin or origins[0],
    )


def _optional_secret(variable: str, minimum: int = 1) -> str | None:
    path = os.getenv(variable, "").strip()
    if not path:
        return None
    try:
        secret = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"{variable} points to an unavailable secret file") from exc
    if len(secret.encode()) < minimum:
        raise RuntimeError(f"{variable} secret is too short")
    return secret


def _parse_host_list(raw: str) -> tuple[str, ...]:
    hosts = tuple(item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip())
    if any(not host or "/" in host or "@" in host or "*" in host or ":" in host for host in hosts):
        raise RuntimeError("SSO host allowlists must contain exact hostnames")
    return tuple(dict.fromkeys(hosts))


def _parse_proxy_host_list(raw: str) -> tuple[str, ...]:
    hosts: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            host = str(ipaddress.ip_address(value))
        except ValueError:
            host = value.casefold().rstrip(".")
            if (
                not host
                or len(host) > 253
                or any(not label or len(label) > 63 for label in host.split("."))
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) for label in host.split("."))
            ):
                raise RuntimeError("ORDIVANT_AUTH_TRUSTED_PROXY_HOSTS must contain exact hostnames or IP addresses")
        hosts.append(host)
    return tuple(dict.fromkeys(hosts))
