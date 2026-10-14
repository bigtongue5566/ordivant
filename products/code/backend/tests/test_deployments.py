from __future__ import annotations

import json
from types import SimpleNamespace

from ordivant_code import deployments

HEAD = "a" * 40


class StubResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


def _configure(tmp_path, monkeypatch, provider, mapping):
    token_file = tmp_path / "provider-token"
    token_file.write_text("synthetic-token", encoding="utf-8")
    config_file = tmp_path / "deployments.json"
    config_file.write_text(json.dumps({
        "providers": [{
            "provider": provider,
            "token_file": str(token_file),
            "base_url": "https://attacker.invalid/api",
            "repositories": mapping,
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("ORDIVANT_CODE_DEPLOYMENT_CONFIG_FILE", str(config_file))


def test_github_deployments_use_fixed_api_and_filter_untrusted_links(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, "github", {"repo-1": {"owner": "acme", "name": "sample"}})
    requests = []

    class Client:
        def __init__(self, **kwargs):
            self.headers = kwargs["headers"]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, params=None):
            requests.append((url, params, self.headers))
            if url.endswith("/deployments"):
                return StubResponse([{
                    "id": 7, "sha": HEAD, "environment": "production", "created_at": "2026-10-14T00:00:00Z",
                    "url": "https://attacker.invalid/deployment",
                }])
            return StubResponse([{
                "state": "success", "updated_at": "2026-10-14T01:00:00Z",
                "target_url": "https://attacker.invalid/status",
            }])

    monkeypatch.setattr(deployments.httpx, "Client", Client)
    result = deployments.deployments_for(SimpleNamespace(id="repo-1"), HEAD)
    assert result == {
        "available": True,
        "provider": "github",
        "items": [{
            "id": 7, "provider": "github", "sha": HEAD, "environment": "production", "status": "success",
            "created_at": "2026-10-14T00:00:00Z", "updated_at": "2026-10-14T01:00:00Z", "url": None,
        }],
    }
    assert [item[0] for item in requests] == [
        "https://api.github.com/repos/acme/sample/deployments",
        "https://api.github.com/repos/acme/sample/deployments/7/statuses",
    ]
    assert all(item[2]["Authorization"] == "Bearer synthetic-token" for item in requests)
    assert "synthetic-token" not in repr(result)


def test_gitlab_deployments_use_fixed_api_and_only_exact_head(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, "gitlab", {"repo-2": {"project": "group/sample"}})
    requests = []

    class Client:
        def __init__(self, **kwargs):
            self.headers = kwargs["headers"]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, params=None):
            requests.append((url, params, self.headers))
            return StubResponse([
                {"id": 10, "sha": HEAD, "status": "success", "environment": {"name": "staging"},
                 "deployable": {"web_url": "https://attacker.invalid/job/10"}},
                {"id": 11, "sha": "b" * 40, "status": "success"},
            ])

    monkeypatch.setattr(deployments.httpx, "Client", Client)
    result = deployments.deployments_for(SimpleNamespace(id="repo-2"), HEAD)
    assert result["available"] is True
    assert result["provider"] == "gitlab"
    assert len(result["items"]) == 1
    assert result["items"][0]["sha"] == HEAD
    assert result["items"][0]["url"] is None
    assert requests[0][0] == "https://gitlab.com/api/v4/projects/group%2Fsample/deployments"
    assert requests[0][2]["PRIVATE-TOKEN"] == "synthetic-token"


def test_unmapped_repository_does_not_call_provider(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, "github", {"different-repo": {"owner": "acme", "name": "sample"}})

    def unexpected_request(*args, **kwargs):
        raise AssertionError("unmapped repository must not call the provider")

    monkeypatch.setattr(deployments, "_request", unexpected_request)
    result = deployments.deployments_for(SimpleNamespace(id="repo-1"), HEAD)
    assert result == {"available": False, "reason": "provider_not_configured", "items": []}
