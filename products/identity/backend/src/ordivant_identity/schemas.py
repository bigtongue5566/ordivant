from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_serializer, field_validator, model_serializer, model_validator


class ProductPermission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    scope_ids: list[str] = Field(default_factory=list, max_length=1000)

    @field_validator("scope_ids")
    @classmethod
    def valid_scope_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 160 for value in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("scope_ids must contain unique non-empty ids")
        return cleaned


class Permissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work: ProductPermission | None = None
    knowledge: ProductPermission | None = None
    code: ProductPermission | None = None

    @field_validator("work")
    @classmethod
    def work_role(cls, value: ProductPermission | None) -> ProductPermission | None:
        return _validate_role(value, {"manager", "worker", "reviewer"})

    @field_validator("knowledge")
    @classmethod
    def knowledge_role(cls, value: ProductPermission | None) -> ProductPermission | None:
        return _validate_role(value, {"manager", "writer", "reader"})

    @field_validator("code")
    @classmethod
    def code_role(cls, value: ProductPermission | None) -> ProductPermission | None:
        return _validate_role(value, {"manager", "writer", "reader"})


def _validate_role(value: ProductPermission | None, allowed: set[str]) -> ProductPermission | None:
    if value is not None and value.role not in allowed:
        raise ValueError("role is invalid for this product")
    return value


def permissions_data(value: Permissions | dict | None) -> dict:
    parsed = value if isinstance(value, Permissions) else Permissions.model_validate(value or {})
    return parsed.model_dump(mode="json", exclude_none=True)


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("password is too long")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()


class SetupRequest(Credentials):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)

    @field_validator("new_password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("password is too long")
        return value


class RecoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    recovery_code: str = Field(min_length=12, max_length=160)
    new_password: str = Field(min_length=12, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()

    @field_validator("new_password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("password is too long")
        return value


class AcceptInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_code: str = Field(min_length=32, max_length=160)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1024:
            raise ValueError("password is too long")
        return value


class InvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    name: str = Field(min_length=1, max_length=160)
    role: Literal["admin", "member"]
    permissions: Permissions = Field(default_factory=Permissions)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    permissions: Permissions | None = None
    expected_permissions: Permissions | None = None

    @model_validator(mode="after")
    def validate_permission_snapshot(self):
        if "expected_permissions" in self.model_fields_set and (self.expected_permissions is None or self.permissions is None):
            raise ValueError("expected_permissions requires a non-null permissions update")
        return self

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Literal["admin", "member"]
    active: bool
    permissions: Permissions
    credential_type: Literal["local", "sso"] = "local"
    permissions_source: Literal["manual", "sso", "scim"] = "manual"

    @field_serializer("permissions")
    def serialize_permissions(self, value: Permissions) -> dict:
        return value.model_dump(mode="json", exclude_none=True)


class AuthenticationOut(BaseModel):
    method: Literal["password", "oidc"]
    provider_name: str | None = None


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: str
    authentication: AuthenticationOut = Field(default_factory=lambda: AuthenticationOut(method="password"))
    recovery_codes: list[str] | None = None

    @model_serializer(mode="wrap")
    def omit_absent_recovery_codes(self, handler):
        data = handler(self)
        if self.recovery_codes is None:
            data.pop("recovery_codes", None)
        return data


class IntrospectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_token: str = Field(min_length=32, max_length=160)


class AccessTokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    products: list[Literal["work", "knowledge", "code"]] = Field(min_length=1, max_length=3)
    expires_in_days: int = Field(default=30, ge=1, le=365)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("products")
    @classmethod
    def unique_products(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class AccessTokenIntrospectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: SecretStr = Field(min_length=20, max_length=512)
    product: Literal["work", "knowledge", "code"]


class OIDCStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    return_to: Literal["/work", "/knowledge", "/code"] = "/work"


class SSOGroupMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: str = Field(min_length=1, max_length=256)
    permissions: Permissions

    @field_validator("group")
    @classmethod
    def clean_group(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("group is required")
        return cleaned


class SSOSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    enabled: bool = False
    display_name: str = Field(default="企業帳號", min_length=1, max_length=160)
    issuer_url: str = Field(default="", max_length=512)
    client_id: str = Field(default="", max_length=512)
    client_secret: str = Field(default="", max_length=4096, repr=False)
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"], min_length=1, max_length=32)
    allowed_email_domains: list[str] = Field(default_factory=list, max_length=100)
    email_claim: str = Field(default="email", min_length=1, max_length=128)
    require_email_verified: bool = True
    groups_claim: str = Field(default="groups", min_length=1, max_length=128)
    provisioning: Literal["invited_only", "jit"] = "invited_only"
    default_permissions: Permissions = Field(default_factory=Permissions)
    group_mappings: list[SSOGroupMapping] = Field(default_factory=list, max_length=500)
    login_policy: Literal["password_and_sso", "sso_only"] = "password_and_sso"
    required_acr: list[str] = Field(default_factory=list, max_length=20)
    required_amr: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("required_acr", "required_amr")
    @classmethod
    def validate_authentication_claims(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 256 for value in values):
            raise ValueError("Authentication requirements must use exact claim values")
        return list(dict.fromkeys(value.strip() for value in values))

    @field_validator("display_name", "issuer_url", "client_id", "email_claim", "groups_claim")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 128 for value in normalized) or "openid" not in normalized:
            raise ValueError("scopes must include openid and contain valid scope names")
        return normalized

    @field_validator("allowed_email_domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().casefold().rstrip(".") for value in values))
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if any(not value or "*" in value or len(value) > 253 or not re.fullmatch(rf"{label}(?:\.{label})+", value) for value in normalized):
            raise ValueError("allowed email domains must be exact DNS domain names")
        return normalized

    @field_validator("group_mappings")
    @classmethod
    def unique_groups(cls, values: list[SSOGroupMapping]) -> list[SSOGroupMapping]:
        names = [value.group for value in values]
        if len(names) != len(set(names)):
            raise ValueError("group mappings must use unique group names")
        return values

    @model_validator(mode="after")
    def reject_wildcard_scopes(self):
        if (self.required_acr or self.required_amr) and self.login_policy != "sso_only":
            raise ValueError("Authentication assurance requirements need SSO-only member login")
        permission_sets = [self.default_permissions, *(mapping.permissions for mapping in self.group_mappings)]
        for permissions in permission_sets:
            for product in (permissions.work, permissions.knowledge, permissions.code):
                if product is not None and any(scope in {"*", "**"} for scope in product.scope_ids):
                    raise ValueError("SSO permission mappings require exact resource IDs")
        return self


class SsoLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=36)
    subject: str = Field(min_length=1, max_length=512)
    managed_permissions: bool = False

    @field_validator("user_id", "subject")
    @classmethod
    def trim_link_fields(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned
