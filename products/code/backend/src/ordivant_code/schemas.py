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
