from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectCreate(InputModel):
    key: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9][a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class LocalSessionInput(InputModel):
    name: str = Field(default="Local Developer", min_length=1, max_length=120)


class RepositoryCreate(InputModel):
    project_id: str
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    description: str = Field(default="", max_length=4000)
    private: Literal[True] = True

    @field_validator("name")
    @classmethod
    def repo_name_safe(cls, value: str) -> str:
        if value in {".", ".."} or ".." in value or value.endswith("."):
            raise ValueError("repository name is invalid")
        return value


class BranchCreate(InputModel):
    name: str = Field(min_length=1, max_length=255)
    from_branch: str = Field(default="main", min_length=1, max_length=255)


class FileCommit(InputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    branch: str = Field(min_length=1, max_length=255)
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=2_000_000)
    commit_message: str = Field(min_length=1, max_length=500)
    expected_sha: str | None = Field(default=None, min_length=40, max_length=64, pattern=r"^[a-fA-F0-9]+$")

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        if not value.strip() or value.startswith("/") or "\\" in value or "\x00" in value:
            raise ValueError("path must be a relative POSIX repository path")
        parts = value.split("/")
        if any(part in {"", ".", ".."} for part in parts) or any(part.lower() == ".git" for part in parts):
            raise ValueError("path contains a forbidden component")
        return value

    @field_validator("content")
    @classmethod
    def utf8_content(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("content cannot contain NUL")
        value.encode("utf-8", errors="strict")
        return value

    @field_validator("commit_message")
    @classmethod
    def nonblank_commit_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("commit message cannot be blank")
        return value


class CodeReference(InputModel):
    product: Literal["work", "knowledge", "code", "external"]
    kind: Literal["task", "document_version", "pull_request", "test_report", "url"]
    uri: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)


class PullRequestCreate(InputModel):
    head: str = Field(min_length=1, max_length=255)
    base: str = Field(default="main", min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=20000)
    source_refs: list[CodeReference] = Field(default_factory=list, max_length=50)


class PullRequestCommentCreate(InputModel):
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("body")
    @classmethod
    def safe_body(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("comment cannot contain NUL")
        value.encode("utf-8", errors="strict")
        return value


class PullRequestReviewCreate(InputModel):
    decision: Literal["approve", "request_changes", "comment"]
    comment: str = Field(default="", max_length=20000)
    expected_head_sha: str = Field(min_length=40, max_length=64, pattern=r"^[a-fA-F0-9]+$")

    @field_validator("comment")
    @classmethod
    def safe_review_comment(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("comment cannot contain NUL")
        value.encode("utf-8", errors="strict")
        return value


class PullRequestInlineCommentCreate(InputModel):
    head_sha: str = Field(min_length=40, max_length=64, pattern=r"^[a-fA-F0-9]+$")
    file_path: str = Field(min_length=1, max_length=1024)
    line: int = Field(ge=1, le=10_000_000)
    side: Literal["LEFT", "RIGHT"]
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("file_path")
    @classmethod
    def safe_inline_path(cls, value: str) -> str:
        if value.startswith("/") or "\\" in value or "\x00" in value or any(part in {"", ".", ".."} for part in value.split("/")) or any(part.lower() == ".git" for part in value.split("/")):
            raise ValueError("file_path must be a relative POSIX repository path")
        return value

    @field_validator("body")
    @classmethod
    def safe_inline_body(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("comment cannot contain NUL")
        value.encode("utf-8", errors="strict")
        return value


class PullRequestInlineReplyCreate(InputModel):
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("body")
    @classmethod
    def safe_inline_reply(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("comment cannot contain NUL")
        value.encode("utf-8", errors="strict")
        return value


class PullRequestInlineResolve(InputModel):
    resolved: bool


class BranchProtectionUpdate(InputModel):
    required_approvals: int | None = Field(default=None, ge=0, le=100)
    enable_status_check: bool | None = None
    status_check_contexts: list[str] | None = Field(default=None, max_length=100)
    block_on_outdated_branch: bool | None = None
    block_on_rejected_reviews: bool | None = None
    dismiss_stale_approvals: bool | None = None
    require_signed_commits: bool | None = None

    @field_validator("status_check_contexts")
    @classmethod
    def valid_status_contexts(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in item) for item in normalized):
            raise ValueError("status check contexts must be nonblank printable names")
        if len(set(normalized)) != len(normalized):
            raise ValueError("status check contexts must be unique")
        return normalized


class CheckCreate(InputModel):
    commit_sha: str = Field(min_length=40, max_length=64, pattern=r"^[a-fA-F0-9]+$")
    context: str = Field(min_length=1, max_length=255)
    state: Literal["pending", "success", "failure", "error"]
    description: str = Field(default="", max_length=500)
    target_url: str | None = Field(default=None, max_length=2000)

    @field_validator("target_url")
    @classmethod
    def safe_target_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError("target_url must be an http(s) URL without credentials")
        return value


class WebhookResult(BaseModel):
    received: bool
    duplicate: bool = False
