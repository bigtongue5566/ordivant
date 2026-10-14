from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(InputModel):
    product: Literal["work", "knowledge", "code", "external"]
    kind: Literal["task", "document_version", "pull_request", "test_report", "url"]
    uri: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=500)


class SpaceCreate(InputModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class DocumentCreate(InputModel):
    space_id: str = Field(min_length=1, max_length=80)
    parent_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(default="", max_length=4000)
    body: str = Field(min_length=1, max_length=2_000_000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    change_summary: str = Field(default="Initial version.", max_length=4000)
    source_refs: list[Reference] = Field(default_factory=list, max_length=200)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


class VersionPublish(InputModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=2_000_000)
    change_summary: str = Field(min_length=1, max_length=4000)
    source_refs: list[Reference] = Field(default_factory=list, max_length=200)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


class DraftUpdate(InputModel):
    update: str = Field(min_length=1, max_length=350_000)


class DraftPublish(InputModel):
    expected_revision: int = Field(ge=0)
    change_summary: str = Field(min_length=1, max_length=4000)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    source_refs: list[Reference] = Field(default_factory=list, max_length=200)


class DecisionCreate(InputModel):
    space_id: str = Field(min_length=1, max_length=80)
    document_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=100_000)
    source_refs: list[Reference] = Field(default_factory=list, max_length=200)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


class DocumentOrganizationPatch(InputModel):
    parent_id: str | None = Field(default=None, max_length=80)
    archived: bool | None = None


class CommentAnchor(InputModel):
    quote: str = Field(min_length=1, max_length=2000)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)
    version: int = Field(ge=1)


class DocumentCommentCreate(InputModel):
    body: str = Field(min_length=1, max_length=5000)
    anchor: CommentAnchor | None = None
    parent_id: str | None = Field(default=None, max_length=80)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("comment body must not be blank")
        return value


class DocumentCommentPatch(InputModel):
    resolved: bool


class SpaceTemplateCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=100_000)

    @field_validator("name", "body")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value


class DocumentRestore(InputModel):
    version: int = Field(ge=1)
    expected_current_version: int = Field(ge=1)
    change_summary: str = Field(default="", max_length=4000)


class LocalSessionCreate(InputModel):
    principal_id: str | None = Field(default=None, min_length=1, max_length=80)
