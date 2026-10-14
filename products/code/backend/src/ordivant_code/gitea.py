from __future__ import annotations

import base64
from urllib.parse import quote

import httpx

from .config import GiteaConfig
from .errors import DomainError


class GiteaClient:
    def __init__(self, config: GiteaConfig):
        self.config = config

    def request(self, method: str, endpoint: str, *, params=None, json_body=None):
        try:
            with httpx.Client(
                timeout=httpx.Timeout(20.0, connect=5.0),
                headers={"Authorization": f"token {self.config.token}", "Accept": "application/json"},
            ) as client:
                response = client.request(method, self.config.api_base + endpoint, params=params, json=json_body)
        except httpx.HTTPError as exc:
            raise DomainError(502, "gitea_unavailable", "Gitea could not complete the request") from exc
        if response.status_code >= 400:
            if response.status_code == 404:
                code = "gitea_resource_not_found"
                status = 404
            elif response.status_code in {405, 501}:
                code = "gitea_feature_unavailable"
                status = 501
            elif response.status_code in {409, 422}:
                code = "gitea_conflict"
                status = 409
            else:
                code = "gitea_upstream_error"
                status = 502
            raise DomainError(status, code, "Gitea rejected the request")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise DomainError(502, "gitea_invalid_response", "Gitea returned an invalid response") from exc

    def request_text(self, method: str, endpoint: str, *, params=None) -> str:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(30.0, connect=5.0),
                headers={"Authorization": f"token {self.config.token}", "Accept": "application/vnd.git.diff, text/plain"},
            ) as client:
                response = client.request(method, self.config.api_base + endpoint, params=params)
        except httpx.HTTPError as exc:
            raise DomainError(502, "gitea_unavailable", "Gitea could not complete the request") from exc
        if response.status_code >= 400:
            if response.status_code == 404:
                code, status = "gitea_resource_not_found", 404
            elif response.status_code in {405, 501}:
                code, status = "gitea_feature_unavailable", 501
            elif response.status_code in {409, 422}:
                code, status = "gitea_conflict", 409
            else:
                code, status = "gitea_upstream_error", 502
            raise DomainError(status, code, "Gitea rejected the request")
        return response.text

    @staticmethod
    def repo_path(owner: str, repo: str) -> str:
        return f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"

    def user(self) -> dict:
        return self.request("GET", "/user")

    def repository(self, owner: str, repo: str) -> dict:
        return self.request("GET", self.repo_path(owner, repo))

    def create_repository(self, *, name: str, description: str):
        return self.request(
            "POST",
            "/user/repos",
            json_body={"name": name, "description": description, "private": True, "auto_init": True, "default_branch": "main"},
        )

    def branch(self, owner: str, repo: str, name: str) -> dict:
        return self.request("GET", f"{self.repo_path(owner, repo)}/branches/{quote(name, safe='')}")

    def create_branch(self, owner: str, repo: str, name: str, from_branch: str):
        return self.request(
            "POST",
            f"{self.repo_path(owner, repo)}/branches",
            json_body={"new_branch_name": name, "old_branch_name": from_branch},
        )

    def file(self, owner: str, repo: str, path: str, ref: str) -> dict:
        endpoint = f"{self.repo_path(owner, repo)}/contents/{quote(path, safe='/')}"
        return self.request("GET", endpoint, params={"ref": ref})

    def commit_file(self, owner: str, repo: str, *, path: str, branch: str, content: str, message: str, sha: str | None):
        endpoint = f"{self.repo_path(owner, repo)}/contents/{quote(path, safe='/')}"
        data = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "branch": branch}
        if sha:
            data["sha"] = sha
            method = "PUT"
        else:
            method = "POST"
        return self.request(method, endpoint, json_body=data)

    def commits_for_path(self, owner: str, repo: str, path: str, branch: str):
        return self.request(
            "GET",
            f"{self.repo_path(owner, repo)}/commits",
            params={"path": path, "sha": branch, "limit": 100},
        )

    def statuses(self, owner: str, repo: str, sha: str):
        return self.request(
            "GET",
            f"{self.repo_path(owner, repo)}/commits/{quote(sha, safe='')}/statuses",
            params={"limit": 100},
        )

    def pulls(self, owner: str, repo: str):
        return self.request("GET", f"{self.repo_path(owner, repo)}/pulls", params={"state": "all", "limit": 100})

    def create_pull(self, owner: str, repo: str, *, head: str, base: str, title: str, body: str):
        return self.request(
            "POST",
            f"{self.repo_path(owner, repo)}/pulls",
            json_body={"head": head, "base": base, "title": title, "body": body},
        )

    def pull(self, owner: str, repo: str, number: int):
        return self.request("GET", f"{self.repo_path(owner, repo)}/pulls/{number}")

    def pull_diff(self, owner: str, repo: str, number: int) -> str:
        return self.request_text("GET", f"{self.repo_path(owner, repo)}/pulls/{number}.diff")

    def pull_reviews(self, owner: str, repo: str, number: int):
        return self.request("GET", f"{self.repo_path(owner, repo)}/pulls/{number}/reviews", params={"limit": 100})

    def pull_commits(self, owner: str, repo: str, number: int):
        return self.request("GET", f"{self.repo_path(owner, repo)}/pulls/{number}/commits", params={"limit": 100})

    def compare(self, owner: str, repo: str, base: str, head: str):
        base_head = f"{quote(base, safe='')}...{quote(head, safe='')}"
        return self.request("GET", f"{self.repo_path(owner, repo)}/compare/{base_head}")

    def branch_protections(self, owner: str, repo: str):
        return self.request("GET", f"{self.repo_path(owner, repo)}/branch_protections")

    def update_branch_protection(self, owner: str, repo: str, branch: str, *, exists: bool, data: dict):
        endpoint = f"{self.repo_path(owner, repo)}/branch_protections/{quote(branch, safe='')}"
        if exists:
            return self.request("PATCH", endpoint, json_body=data)
        return self.request("POST", f"{self.repo_path(owner, repo)}/branch_protections", json_body=data)

    def actions_runs(self, owner: str, repo: str, sha: str):
        return self.request("GET", f"{self.repo_path(owner, repo)}/actions/runs", params={"head_sha": sha, "limit": 50})

    def actions_jobs(self, owner: str, repo: str, run_id: int):
        return self.request("GET", f"{self.repo_path(owner, repo)}/actions/runs/{run_id}/jobs", params={"limit": 100})

    def actions_artifacts(self, owner: str, repo: str, run_id: int):
        return self.request("GET", f"{self.repo_path(owner, repo)}/actions/runs/{run_id}/artifacts", params={"limit": 100})

    def create_status(self, owner: str, repo: str, *, sha: str, context: str, state: str, description: str, target_url: str | None):
        return self.request(
            "POST",
            f"{self.repo_path(owner, repo)}/statuses/{quote(sha, safe='')}",
            json_body={"context": context, "state": state, "description": description, "target_url": target_url},
        )
