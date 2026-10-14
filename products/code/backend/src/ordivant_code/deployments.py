from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from .errors import DomainError
from .models import Repository

_PROVIDER_BASES = {
    "github": "https://api.github.com",
    "gitlab": "https://gitlab.com/api/v4",
}


def _read_config() -> dict | None:
    path_value = os.getenv("ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE")
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainError(503, "deployment_config_unavailable", "Deployment provider configuration could not be read") from error
    if not isinstance(value, dict) or not isinstance(value.get("providers"), list):
        raise DomainError(503, "deployment_config_invalid", "Deployment provider configuration is invalid")
    return value


def _token(token_file: str) -> str:
    path = Path(token_file).expanduser()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise DomainError(503, "deployment_provider_unavailable", "Deployment provider credentials are unavailable") from error
    if not value or len(value) > 8192 or "\n" in value:
        raise DomainError(503, "deployment_provider_unavailable", "Deployment provider credentials are unavailable")
    return value


def _safe_link(value, provider: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    allowed_host = "github.com" if provider == "github" else "gitlab.com"
    if parsed.scheme != "https" or parsed.hostname != allowed_host or parsed.username or parsed.password:
        return None
    return value


def _provider_config(config: dict, repository: Repository) -> tuple[str, dict] | None:
    matches = []
    for item in config["providers"]:
        if not isinstance(item, dict) or item.get("provider") not in _PROVIDER_BASES:
            continue
        repositories = item.get("repositories")
        mapping = repositories.get(repository.id) if isinstance(repositories, dict) else None
        if mapping is not None:
            matches.append((item["provider"], item, mapping))
    if len(matches) > 1:
        raise DomainError(503, "deployment_config_ambiguous", "More than one deployment provider is configured for this repository")
    if not matches:
        return None
    provider, item, mapping = matches[0]
    if not isinstance(mapping, dict) or not isinstance(item.get("token_file"), str):
        raise DomainError(503, "deployment_config_invalid", "Deployment provider configuration is invalid")
    return provider, {"item": item, "mapping": mapping}


def _request(provider: str, token: str, endpoint: str, params: dict | None = None):
    headers = {"Accept": "application/json"}
    if provider == "github":
        headers.update({"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"})
    else:
        headers["PRIVATE-TOKEN"] = token
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False, headers=headers) as client:
            response = client.get(_PROVIDER_BASES[provider] + endpoint, params=params)
    except httpx.HTTPError:
        return None, {"available": False, "reason": "provider_unavailable"}
    if response.status_code >= 400:
        return None, {"available": False, "reason": f"provider_http_{response.status_code}"}
    try:
        return response.json(), None
    except ValueError:
        return None, {"available": False, "reason": "invalid_provider_response"}


def _github_deployments(token: str, mapping: dict, head_sha: str) -> tuple[list[dict] | None, dict | None]:
    owner, name = mapping.get("owner"), mapping.get("name")
    if not isinstance(owner, str) or not owner or not isinstance(name, str) or not name:
        return None, {"available": False, "reason": "invalid_provider_mapping"}
    root = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
    raw, error = _request("github", token, f"{root}/deployments", {"sha": head_sha, "per_page": 50})
    if error:
        return None, error
    if not isinstance(raw, list):
        return None, {"available": False, "reason": "invalid_provider_response"}
    result = []
    for item in raw:
        if not isinstance(item, dict) or str(item.get("sha") or "").casefold() != head_sha.casefold():
            continue
        deployment_id = item.get("id")
        if not isinstance(deployment_id, int):
            continue
        statuses, error = _request("github", token, f"{root}/deployments/{deployment_id}/statuses", {"per_page": 20})
        if error:
            return None, error
        if not isinstance(statuses, list):
            return None, {"available": False, "reason": "invalid_provider_response"}
        latest = statuses[0] if statuses and isinstance(statuses[0], dict) else {}
        result.append({
            "id": deployment_id,
            "provider": "github",
            "sha": head_sha,
            "environment": str(item.get("environment") or "")[:120],
            "status": str(latest.get("state") or "unknown"),
            "created_at": item.get("created_at"),
            "updated_at": latest.get("updated_at"),
            "url": _safe_link(latest.get("target_url") or item.get("url"), "github"),
        })
    return result, None


def _gitlab_deployments(token: str, mapping: dict, head_sha: str) -> tuple[list[dict] | None, dict | None]:
    project = mapping.get("project")
    if not isinstance(project, (str, int)) or not str(project):
        return None, {"available": False, "reason": "invalid_provider_mapping"}
    raw, error = _request("gitlab", token, f"/projects/{quote(str(project), safe='')}/deployments", {"sha": head_sha, "per_page": 50})
    if error:
        return None, error
    if not isinstance(raw, list):
        return None, {"available": False, "reason": "invalid_provider_response"}
    result = []
    for item in raw:
        if not isinstance(item, dict) or str(item.get("sha") or "").casefold() != head_sha.casefold():
            continue
        environment = item.get("environment") or {}
        result.append({
            "id": item.get("id"),
            "provider": "gitlab",
            "sha": head_sha,
            "environment": str(environment.get("name") or "")[:120] if isinstance(environment, dict) else "",
            "status": str(item.get("status") or "unknown"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "url": _safe_link(item.get("deployable", {}).get("web_url") if isinstance(item.get("deployable"), dict) else item.get("url"), "gitlab"),
        })
    return result, None


def deployments_for(repository: Repository, head_sha: str) -> dict:
    config = _read_config()
    if config is None:
        return {"available": False, "reason": "provider_not_configured", "items": []}
    selected = _provider_config(config, repository)
    if selected is None:
        return {"available": False, "reason": "provider_not_configured", "items": []}
    provider, values = selected
    try:
        token = _token(values["item"]["token_file"])
    except DomainError:
        return {"available": False, "reason": "provider_credentials_unavailable", "items": []}
    if provider == "github":
        items, error = _github_deployments(token, values["mapping"], head_sha)
    else:
        items, error = _gitlab_deployments(token, values["mapping"], head_sha)
    if error:
        return {**error, "items": []}
    return {"available": True, "provider": provider, "items": items or []}
