"""Run an isolated human PAT through Identity, REST, and each stdio MCP bridge.

Usage: uv run --no-sync --project backend python scripts/verify_personal_mcp.py
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]
UV = shutil.which("uv")
STARTUP_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class Product:
    name: str
    project_dir: Path
    app: str
    mcp_module: str
    api_env: str
    token_env: str
    data_env: str
    database_env: str
    list_tool: str
    list_path: str
    create_tool: str


PRODUCTS = (
    Product(
        "Work",
        ROOT / "backend",
        "ordivant.main:app",
        "ordivant.mcp_server",
        "ORDIVANT_API_URL",
        "ORDIVANT_API_TOKEN",
        "ORDIVANT_DATA_DIR",
        "ORDIVANT_DATABASE_URL",
        "list_projects",
        "/api/projects",
        "create_project",
    ),
    Product(
        "Knowledge",
        ROOT / "products" / "knowledge" / "backend",
        "ordivant_knowledge.main:app",
        "ordivant_knowledge.mcp_server",
        "ORDIVANT_KNOWLEDGE_API_URL",
        "ORDIVANT_KNOWLEDGE_API_TOKEN",
        "ORDIVANT_KNOWLEDGE_DATA_DIR",
        "ORDIVANT_KNOWLEDGE_DATABASE_URL",
        "list_spaces",
        "/api/spaces",
        "create_space",
    ),
    Product(
        "Code",
        ROOT / "products" / "code" / "backend",
        "ordivant_code.main:app",
        "ordivant_code.mcp_server",
        "ORDIVANT_CODE_API_URL",
        "ORDIVANT_CODE_API_TOKEN",
        "ORDIVANT_CODE_DATA_DIR",
        "ORDIVANT_CODE_DATABASE_URL",
        "list_code_projects",
        "/api/projects",
        "create_code_project",
    ),
)


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _safe_process_env(uv_cache: Path) -> dict[str, str]:
    allowed = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "HOME",
    )
    env = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    env.update(
        {
            "UV_CACHE_DIR": str(uv_cache),
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    expected: set[int] | None = None,
) -> tuple[int, Any]:
    request_headers = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=request_headers,
        method=method,
    )
    try:
        response = (opener or urllib.request.build_opener()).open(request, timeout=5)
    except urllib.error.HTTPError as exc:
        status = exc.code
        data = exc.read()
    else:
        with response:
            status = response.status
            data = response.read()
    if expected is not None and status not in expected:
        raise RuntimeError(f"HTTP {status} for {method} {urlsplit_path(url)}")
    if not data:
        return status, None
    try:
        return status, json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None


def urlsplit_path(url: str) -> str:
    return urlsplit(url).path


def _start_server(
    *,
    name: str,
    project_dir: Path,
    app: str,
    port: int,
    env: dict[str, str],
) -> subprocess.Popen[bytes]:
    if UV is None:
        raise RuntimeError("uv must be available on PATH")
    command = [
        UV,
        "run",
        "--no-sync",
        "--project",
        str(project_dir),
        "python",
        "-m",
        "uvicorn",
        app,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-access-log",
    ]
    try:
        return subprocess.Popen(
            command,
            cwd=project_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise RuntimeError(f"Could not start {name} API using its existing uv environment") from exc


def _wait_ready(name: str, process: subprocess.Popen[bytes], url: str) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} API exited during startup (code {process.returncode})")
        try:
            status, payload = _request(url, expected={200})
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return
        except (OSError, RuntimeError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"{name} API did not become ready within {STARTUP_TIMEOUT_SECONDS} seconds")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        else:
            import signal

            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
        process.wait(timeout=5)


def _response_object(result: Any, label: str) -> Any:
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool {label} returned an error")
    value = getattr(result, "structuredContent", None)
    if value is not None:
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        return value
    blocks = getattr(result, "content", ())
    text_blocks = [block.text for block in blocks if getattr(block, "type", None) == "text"]
    if len(text_blocks) == 1:
        try:
            return json.loads(text_blocks[0])
        except json.JSONDecodeError:
            return text_blocks[0]
    if text_blocks:
        return text_blocks
    raise RuntimeError(f"MCP tool {label} returned no result")


async def _mcp_calls(
    product: Product,
    base_url: str,
    token: str,
    env: dict[str, str],
    calls: list[tuple[str, dict[str, Any]]],
) -> list[Any]:
    if UV is None:
        raise RuntimeError("uv must be available on PATH")
    child_env = dict(env)
    child_env[product.api_env] = base_url
    child_env[product.token_env] = token
    server = StdioServerParameters(
        command=UV,
        args=[
            "run",
            "--no-sync",
            "--project",
            str(product.project_dir),
            "python",
            "-m",
            product.mcp_module,
        ],
        env=child_env,
        cwd=product.project_dir,
    )
    results: list[Any] = []
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        try:
            async with asyncio.timeout(30), stdio_client(server, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=10)) as client:
                    print(f"{product.name}: initializing MCP", flush=True)
                    await client.initialize()
                    for name, arguments in calls:
                        print(f"{product.name}: MCP {name}", flush=True)
                        result = await client.call_tool(name, arguments)
                        results.append(_response_object(result, name))
        except Exception as exc:
            raise RuntimeError(f"{product.name} stdio MCP roundtrip failed ({type(exc).__name__})") from None
    return results


async def _mcp_rejects_revoked_token(
    product: Product,
    base_url: str,
    token: str,
    env: dict[str, str],
) -> bool:
    child_env = dict(env)
    child_env[product.api_env] = base_url
    child_env[product.token_env] = token
    server = StdioServerParameters(
        command=UV or "uv",
        args=[
            "run",
            "--no-sync",
            "--project",
            str(product.project_dir),
            "python",
            "-m",
            product.mcp_module,
        ],
        env=child_env,
        cwd=product.project_dir,
    )
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        try:
            async with asyncio.timeout(30), stdio_client(server, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream, read_timeout_seconds=timedelta(seconds=10)) as client:
                    await client.initialize()
                    result = await client.call_tool("get_me", {})
                    return bool(getattr(result, "isError", False))
        except Exception as exc:
            raise RuntimeError(
                f"{product.name} stdio MCP revoke check failed ({type(exc).__name__})"
            ) from None


def _assert_human_identity(cookie_user: Any, token_user: Any, product: str) -> None:
    if not isinstance(cookie_user, dict) or not isinstance(token_user, dict):
        raise RuntimeError(f"{product} /api/me did not return principal objects")
    if cookie_user.get("kind") != "human" or token_user.get("kind") != "human":
        raise RuntimeError(f"{product} did not resolve the synthetic account as a human")
    if not cookie_user.get("id") or cookie_user.get("id") != token_user.get("id"):
        raise RuntimeError(f"{product} cookie and PAT resolved to different human principals")


def _mcp_error(result: Any, label: str) -> None:
    if not getattr(result, "isError", False):
        raise RuntimeError(f"Revoked PAT was accepted by MCP tool {label}")


def run() -> int:
    if UV is None:
        raise RuntimeError("uv must be available on PATH")
    cache_root = ROOT / ".cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    server_processes: list[subprocess.Popen[bytes]] = []
    results: list[str] = []

    with tempfile.TemporaryDirectory(prefix="personal-mcp-", dir=cache_root) as temporary:
        temp_root = Path(temporary)
        env = _safe_process_env(temp_root / "uv-cache")
        (temp_root / "uv-cache").mkdir()
        identity_port = _port()
        product_ports = {product.name: _port() for product in PRODUCTS}
        origins = ",".join(
            [f"http://127.0.0.1:{identity_port}"]
            + [f"http://127.0.0.1:{port}" for port in product_ports.values()]
        )
        cookie_name = f"ordivant_verify_{secrets.token_hex(10)}"
        service_secret = secrets.token_urlsafe(48)
        service_token_file = temp_root / "identity-service-token"
        service_token_file.write_text(service_secret, encoding="utf-8")
        identity_url = f"http://127.0.0.1:{identity_port}"

        identity_env = dict(env)
        identity_env.update(
            {
                "ORDIVANT_MODE": "development",
                "ORDIVANT_IDENTITY_DATA_DIR": str(temp_root / "identity-data"),
                "ORDIVANT_IDENTITY_DATABASE_URL": _sqlite_url(temp_root / "identity.sqlite3"),
                "ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE": str(service_token_file),
                "ORDIVANT_AUTH_COOKIE_NAME": cookie_name,
                "ORDIVANT_AUTH_COOKIE_SECURE": "false",
                "ORDIVANT_AUTH_ORIGINS": origins,
            }
        )
        (temp_root / "identity-data").mkdir()

        try:
            identity_process = _start_server(
                name="Identity",
                project_dir=ROOT / "products" / "identity" / "backend",
                app="ordivant_identity.main:app",
                port=identity_port,
                env=identity_env,
            )
            server_processes.append(identity_process)
            _wait_ready("Identity", identity_process, f"{identity_url}/api/health")
            print("Identity: ready", flush=True)

            product_envs: dict[str, dict[str, str]] = {}
            product_urls: dict[str, str] = {}
            for product in PRODUCTS:
                port = product_ports[product.name]
                base_url = f"http://127.0.0.1:{port}"
                product_dir = temp_root / f"{product.name.lower()}-data"
                product_dir.mkdir()
                product_env = dict(env)
                product_env.update(
                    {
                        "ORDIVANT_MODE": "development",
                        "ORDIVANT_AUTH_COOKIE_NAME": cookie_name,
                        "ORDIVANT_AUTH_COOKIE_SECURE": "false",
                        "ORDIVANT_AUTH_ORIGINS": origins,
                        "ORDIVANT_IDENTITY_URL": identity_url,
                        "ORDIVANT_IDENTITY_SERVICE_TOKEN_FILE": str(service_token_file),
                        product.data_env: str(product_dir),
                        product.database_env: _sqlite_url(product_dir / f"{product.name.lower()}.sqlite3"),
                        product.api_env: base_url,
                    }
                )
                process = _start_server(
                    name=product.name,
                    project_dir=product.project_dir,
                    app=product.app,
                    port=port,
                    env=product_env,
                )
                server_processes.append(process)
                _wait_ready(product.name, process, f"{base_url}/api/health")
                print(f"{product.name}: ready", flush=True)
                product_envs[product.name] = product_env
                product_urls[product.name] = base_url

            cookie_jar = http.cookiejar.CookieJar()
            cookie_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
            identity_origin = f"http://127.0.0.1:{identity_port}"
            synthetic_suffix = secrets.token_hex(5)
            _, setup = _request(
                f"{identity_url}/api/auth/setup",
                method="POST",
                body={
                    "name": "Synthetic MCP Verifier",
                    "email": f"mcp-verifier-{synthetic_suffix}@example.com",
                    "password": secrets.token_urlsafe(32),
                },
                headers={"Origin": identity_origin},
                opener=cookie_opener,
                expected={201},
            )
            if not isinstance(setup, dict) or not setup.get("user", {}).get("id"):
                raise RuntimeError("Identity setup did not create the synthetic administrator")
            print("Identity: synthetic account created", flush=True)
            csrf = setup.get("csrf_token")
            if not isinstance(csrf, str) or not csrf:
                raise RuntimeError("Identity setup did not return a CSRF token")

            _, minted = _request(
                f"{identity_url}/api/auth/access-tokens",
                method="POST",
                body={
                    "name": "Isolated MCP verification",
                    "products": ["work", "knowledge", "code"],
                    "expires_in_days": 1,
                },
                headers={"Origin": identity_origin, "X-CSRF-Token": csrf},
                opener=cookie_opener,
                expected={201},
            )
            if not isinstance(minted, dict) or not isinstance(minted.get("token"), str):
                raise RuntimeError("Identity did not issue a PAT for all three products")
            pat = minted["token"]
            token_id = minted.get("access_token", {}).get("id")
            if not token_id:
                raise RuntimeError("Identity did not return PAT metadata")
            print("Identity: personal token created", flush=True)

            for product in PRODUCTS:
                base_url = product_urls[product.name]
                api_origin = base_url
                _, cookie_me = _request(
                    f"{base_url}/api/me",
                    headers={"Origin": api_origin},
                    opener=cookie_opener,
                    expected={200},
                )
                pat_headers = {"Authorization": f"Bearer {pat}"}
                _, pat_me = _request(f"{base_url}/api/me", headers=pat_headers, expected={200})
                _assert_human_identity(cookie_me, pat_me, product.name)
                _, listed = _request(f"{base_url}{product.list_path}", headers=pat_headers, expected={200})
                if not isinstance(listed, list) or listed:
                    raise RuntimeError(f"{product.name} isolated list endpoint was not initially empty")

                request_id = f"verify-{secrets.token_hex(12)}"
                key = f"verify-{secrets.token_hex(5)}"
                if product.name == "Work":
                    key = key.upper()
                name = f"Synthetic {product.name} MCP {secrets.token_hex(3)}"
                create_args: dict[str, Any] = {
                    "key": key,
                    "name": name,
                    "description": "Temporary isolated end-to-end verification resource",
                    "request_id": request_id,
                }
                if product.name == "Work":
                    create_args.update({"team_id": None, "budget_usd": 0})

                values = asyncio.run(
                        _mcp_calls(
                            product,
                            base_url,
                            pat,
                            product_envs[product.name],
                            [
                                ("get_me", {}),
                                (product.list_tool, {}),
                                (product.create_tool, create_args),
                                (product.create_tool, create_args),
                            ],
                        )
                    )
                mcp_me, mcp_list, created, replayed = values
                _assert_human_identity(cookie_me, mcp_me, f"{product.name} MCP")
                if not isinstance(mcp_list, list) or mcp_list:
                    raise RuntimeError(f"{product.name} MCP list tool did not return the isolated empty list")
                if not isinstance(created, dict) or not created.get("id") or created.get("key") != key:
                    raise RuntimeError(f"{product.name} MCP create tool did not return its created resource")
                if not isinstance(replayed, dict) or replayed.get("id") != created["id"]:
                    raise RuntimeError(f"{product.name} MCP create did not replay idempotently")
                _, after_create = _request(
                    f"{base_url}{product.list_path}", headers=pat_headers, expected={200}
                )
                if not isinstance(after_create, list) or created["id"] not in {
                    row.get("id") for row in after_create if isinstance(row, dict)
                }:
                    raise RuntimeError(f"{product.name} REST list did not include the MCP-created resource")
                results.append(f"{product.name}: cookie/PAT principal, REST list, MCP tools, idempotent create")

            _request(
                f"{identity_url}/api/auth/access-tokens/{token_id}",
                method="DELETE",
                headers={"Origin": identity_origin, "X-CSRF-Token": csrf},
                opener=cookie_opener,
                expected={204},
            )
            for product in PRODUCTS:
                base_url = product_urls[product.name]
                status, _ = _request(
                    f"{base_url}/api/me",
                    headers={"Authorization": f"Bearer {pat}"},
                    expected={401},
                )
                if status != 401:
                    raise RuntimeError(f"{product.name} REST accepted a revoked PAT")
                mcp_rejected = asyncio.run(
                        _mcp_rejects_revoked_token(
                            product,
                            base_url,
                            pat,
                            product_envs[product.name],
                        )
                    )
                if not mcp_rejected:
                    raise RuntimeError(f"{product.name} MCP did not reject the revoked PAT")
                results.append(f"{product.name}: revoked PAT rejected by REST and MCP")

            _, cookie_after_revoke = _request(
                f"{identity_url}/api/auth/access-tokens",
                opener=cookie_opener,
                expected={200},
            )
            if not isinstance(cookie_after_revoke, dict):
                raise RuntimeError("Identity session stopped working after PAT revocation")
        finally:
            for process in reversed(server_processes):
                print("Stopping temporary API", flush=True)
                _stop_process(process)

    print("Personal MCP verification passed:")
    for item in results:
        print(f"- {item}")
    print(f"- Identity setup/PAT mint/revoke; all temporary data removed ({len(results)} checks)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"Personal MCP verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
