"""SCIM 2 Users/Groups; provisioning never acquires platform administrator rights."""
from __future__ import annotations

import json
import re
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, EmailStr, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .api import _audit, _now, _iso, _revoke_personal_access_tokens, get_db
from .enterprise_models import EnterprisePolicy, ScimResource
from .models import User, AuthSession
from .schemas import permissions_data
from .security import constant_time_equal, new_secret

router = APIRouter()
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"


class ScimError(Exception):
    def __init__(self, status: int, detail: str, kind: str = "invalidValue"):
        self.status, self.detail, self.kind = status, detail, kind


async def scim_error_handler(_request: Request, error: ScimError):
    return JSONResponse(status_code=error.status, media_type="application/scim+json", content={
        "schemas": [ERROR_SCHEMA], "status": str(error.status), "detail": error.detail, "scimType": error.kind})


def authorize(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    token = request.app.state.settings.scim_token
    if not token or not authorization or not authorization.startswith("Bearer ") or not constant_time_equal(token, authorization[7:]):
        raise ScimError(401, "Provisioning authentication is required")
    lock_provisioning(db)


def lock_provisioning(db: Session) -> None:
    # Group changes and administrator policy edits must recompute the same snapshot.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(719306143)"))


def resource(db: Session, kind: str, ident: str) -> ScimResource:
    row = db.get(ScimResource, ident)
    if not row or row.kind != kind:
        raise ScimError(404, "Resource not found")
    return row


def render(db: Session, row: ScimResource, request: Request) -> dict:
    result = {"schemas": [USER_SCHEMA if row.kind == "Users" else GROUP_SCHEMA], "id": row.id,
        "meta": {"resourceType": "User" if row.kind == "Users" else "Group", "created": _iso(row.created_at),
            "lastModified": _iso(row.updated_at), "location": str(request.base_url).rstrip("/") + f"/api/scim/v2/{row.kind}/{row.id}"}}
    if row.external_id is not None:
        result["externalId"] = row.external_id
    if row.kind == "Users":
        user = db.get(User, row.user_id)
        result.update(userName=user.email, displayName=user.name, name={"formatted": user.name}, active=user.active,
                      emails=[{"value": user.email, "primary": True, "type": "work"}])
    else:
        result.update(displayName=row.display_name, members=[{"value": ident} for ident in row.members])
    return result


def text_value(value, name: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ScimError(400, f"Invalid {name}")
    return value.strip()


def recompute(db: Session) -> None:
    from .sso import _merge_permissions
    policy = db.get(EnterprisePolicy, 1)
    mapping = (policy.values if policy else {}).get("scim_group_mappings", {})
    groups = db.scalars(select(ScimResource).where(ScimResource.kind == "Groups")).all()
    for row in db.scalars(select(ScimResource).where(ScimResource.kind == "Users")):
        user = db.get(User, row.user_id)
        if not user or user.role == "admin":
            continue
        grants = {}
        for group in groups:
            if row.id in group.members:
                grants = _merge_permissions(grants, mapping.get(group.display_name, {}))
        if user.permissions != grants:
            user.permissions = grants
            db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=_now()))
        user.permissions_source = "scim"


def apply(db: Session, row: ScimResource, body: dict, *, replace: bool = False) -> None:
    if len(json.dumps(body)) > 131072 or "password" in body or any(key.startswith("urn:") for key in body):
        raise ScimError(400, "Unsupported provisioning attributes")
    permitted = {"schemas", "id", "meta", "externalId", "displayName"} | (
        {"name", "active", "emails", "userName"} if row.kind == "Users" else {"members"})
    if set(body) - permitted:
        raise ScimError(400, "Unsupported provisioning attributes")
    if "externalId" in body:
        row.external_id = text_value(body["externalId"], "externalId") if body["externalId"] is not None else None
    if row.kind == "Users":
        if "members" in body:
            raise ScimError(400, "Users cannot carry group membership")
        user = db.get(User, row.user_id)
        if "userName" in body:
            try:
                email = str(TypeAdapter(EmailStr).validate_python(body["userName"])).casefold()
            except ValidationError:
                raise ScimError(400, "userName must be an email address")
            other = db.scalar(select(User).where(User.normalized_email == email, User.id != user.id))
            if other:
                raise ScimError(409, "userName already exists", "uniqueness")
            user.email = user.normalized_email = email
        name = body.get("displayName", (body.get("name") or {}).get("formatted") if isinstance(body.get("name"), dict) else None)
        if name is not None:
            user.name = text_value(name, "displayName", 160)
        if "active" in body:
            if type(body["active"]) is not bool:
                raise ScimError(400, "active must be a boolean")
            user.active = body["active"]
            if not body["active"]:
                _revoke_personal_access_tokens(db, user.id, _now())
        if "emails" in body:
            emails = body["emails"]
            if not isinstance(emails, list) or len(emails) > 20 or any(not isinstance(item, dict) or not isinstance(item.get("value"), str) or item["value"].casefold() != user.email for item in emails):
                raise ScimError(400, "emails must match userName")
        user.updated_at = _now()
        db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=_now()))
    else:
        if "displayName" in body:
            row.display_name = text_value(body["displayName"], "displayName", 160)
        if "members" in body or replace:
            members = body.get("members", [])
            if not isinstance(members, list) or len(members) > 1000:
                raise ScimError(400, "Invalid members")
            ids = []
            for member in members:
                if not isinstance(member, dict):
                    raise ScimError(400, "Invalid member")
                ident = text_value(member.get("value"), "member", 36)
                resource(db, "Users", ident)
                ids.append(ident)
            row.members = list(dict.fromkeys(ids))
    row.updated_at = _now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ScimError(409, "Resource already exists", "uniqueness")


def commit(db: Session, action: str, row: ScimResource) -> None:
    recompute(db)
    _audit(db, action, user_id=row.user_id, details={"resource_id": row.id, "resource_type": row.kind})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ScimError(409, "Resource already exists", "uniqueness")


@router.get("/ServiceProviderConfig", dependencies=[Depends(authorize)])
def config():
    return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"], "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0}, "filter": {"supported": True, "maxResults": 100},
        "changePassword": {"supported": False}, "sort": {"supported": False}, "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token", "description": "Dedicated provisioning token", "primary": True}]}


@router.get("/ResourceTypes", dependencies=[Depends(authorize)])
def resource_types():
    rows = [{"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"], "id": name[:-1], "name": name[:-1], "endpoint": "/" + name,
             "schema": schema} for name, schema in [("Users", USER_SCHEMA), ("Groups", GROUP_SCHEMA)]]
    return {"schemas": [LIST_SCHEMA], "totalResults": 2, "startIndex": 1, "itemsPerPage": 2, "Resources": rows}


@router.get("/{kind}", dependencies=[Depends(authorize)])
def list_resources(kind: str, request: Request, db: Session = Depends(get_db), filter: str | None = Query(default=None),
                   startIndex: int = Query(default=1, ge=1), count: int = Query(default=100, ge=0, le=100)):
    if kind not in {"Users", "Groups"}:
        raise ScimError(404, "Resource type not found")
    rows = db.scalars(select(ScimResource).where(ScimResource.kind == kind).order_by(ScimResource.id)).all()
    rendered = [render(db, row, request) for row in rows]
    if filter:
        match = re.fullmatch(r'(userName|externalId|id|displayName)\s+eq\s+("(?:[^"\\]|\\.)*")', filter, re.I)
        if not match:
            raise ScimError(400, "Only single attribute equality filters are supported", "invalidFilter")
        attribute = {"username": "userName", "externalid": "externalId", "id": "id", "displayname": "displayName"}[match[1].lower()]
        expected = json.loads(match[2])
        normalize = str.casefold if attribute in {"userName", "displayName"} else str
        rendered = [row for row in rendered if normalize(str(row.get(attribute, ""))) == normalize(expected)]
    return {"schemas": [LIST_SCHEMA], "totalResults": len(rendered), "startIndex": startIndex,
            "itemsPerPage": len(rendered[startIndex-1:startIndex-1+count]), "Resources": rendered[startIndex-1:startIndex-1+count]}


@router.get("/{kind}/{ident}", dependencies=[Depends(authorize)])
def get_resource(kind: str, ident: str, request: Request, db: Session = Depends(get_db)):
    return render(db, resource(db, kind, ident), request)


@router.post("/{kind}", status_code=201, dependencies=[Depends(authorize)])
def create_resource(kind: str, body: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    if kind not in {"Users", "Groups"}:
        raise ScimError(404, "Resource type not found")
    now = _now()
    row = ScimResource(id=str(uuid4()), kind=kind, display_name="", members=[], created_at=now, updated_at=now)
    if kind == "Users":
        from .api import _new_user
        email = text_value(body.get("userName"), "userName", 320)
        if db.scalar(select(User.id).where(User.normalized_email == email.casefold())):
            raise ScimError(409, "Existing accounts require administrator linking; provisioning cannot adopt them", "uniqueness")
        user = _new_user(email=email, name=email, role="member", password=new_secret(), permissions={})
        user.password_hash = "!external-provisioning-only"
        user.credential_type = "sso"
        user.permissions_source = "scim"
        db.add(user)
        db.flush()
        row.user_id = user.id
    else:
        text_value(body.get("displayName"), "displayName", 160)
    db.add(row)
    apply(db, row, body, replace=True)
    commit(db, "scim.created", row)
    result = render(db, row, request)
    response.headers["Location"] = result["meta"]["location"]
    return result


@router.put("/{kind}/{ident}", dependencies=[Depends(authorize)])
def replace_resource(kind: str, ident: str, body: dict, request: Request, db: Session = Depends(get_db)):
    row = resource(db, kind, ident)
    if kind == "Users" and "userName" not in body or kind == "Groups" and "displayName" not in body:
        raise ScimError(400, "Required replacement attribute is missing")
    apply(db, row, body, replace=True)
    commit(db, "scim.replaced", row)
    return render(db, row, request)


@router.patch("/{kind}/{ident}", dependencies=[Depends(authorize)])
def patch_resource(kind: str, ident: str, body: dict, request: Request, db: Session = Depends(get_db)):
    row = resource(db, kind, ident)
    operations = body.get("Operations", [])
    if not isinstance(operations, list) or not operations or len(operations) > 100:
        raise ScimError(400, "Invalid patch operations")
    for operation in operations:
        if not isinstance(operation, dict):
            raise ScimError(400, "Invalid patch operation")
        op, path, value = str(operation.get("op", "")).lower(), operation.get("path"), operation.get("value")
        if op not in {"add", "replace", "remove"}:
            raise ScimError(400, "Unsupported patch operation")
        if path is not None and not isinstance(path, str):
            raise ScimError(400, "Invalid patch path", "invalidPath")
        member_match = re.fullmatch(r'members\[value\s+eq\s+"([^"]+)"\]', path or "", re.I)
        if kind == "Groups" and (path == "members" or member_match):
            members = list(row.members)
            if op == "remove":
                members = [ident for ident in members if ident != member_match[1]] if member_match else []
            else:
                if not isinstance(value, list):
                    raise ScimError(400, "Invalid members")
                added = [item.get("value") for item in value if isinstance(item, dict)]
                if len(added) != len(value):
                    raise ScimError(400, "Invalid members")
                members = added if op == "replace" else members + added
            apply(db, row, {"members": [{"value": ident} for ident in members]})
        elif path is None and isinstance(value, dict) and op != "remove":
            apply(db, row, value)
        elif path in {"userName", "displayName", "active", "name", "emails", "externalId"} and op != "remove":
            apply(db, row, {path: value})
        elif path == "externalId" and op == "remove":
            apply(db, row, {"externalId": None})
        else:
            raise ScimError(400, "Unsupported patch path", "invalidPath")
    commit(db, "scim.patched", row)
    return render(db, row, request)


@router.delete("/{kind}/{ident}", status_code=204, dependencies=[Depends(authorize)])
def delete_resource(kind: str, ident: str, db: Session = Depends(get_db)):
    row = resource(db, kind, ident)
    if kind == "Users":
        apply(db, row, {"active": False})
        db.get(User, row.user_id).permissions = {}
        for group in db.scalars(select(ScimResource).where(ScimResource.kind == "Groups")):
            group.members = [value for value in group.members if value != row.id]
    db.delete(row)
    db.flush()
    commit(db, "scim.deleted", row)
    return Response(status_code=204)
