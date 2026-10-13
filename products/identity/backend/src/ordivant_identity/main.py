from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from . import models as _models  # noqa: F401
from .api import router
from .config import Settings, get_settings
from .db import Base, make_engine, session_factory
from .errors import DomainError
from .sso import ensure_sso_key, router as sso_router


def _migrate_legacy_columns(engine) -> None:
    additions = {
        "identity_users": {
            "credential_type": "VARCHAR(16) NOT NULL DEFAULT 'local'",
            "permissions_source": "VARCHAR(16) NOT NULL DEFAULT 'manual'",
        },
        "identity_sessions": {
            "authentication_method": "VARCHAR(16) NOT NULL DEFAULT 'password'",
            "provider_name": "VARCHAR(160)",
            "oidc_issuer": "VARCHAR(512)",
            "oidc_subject": "VARCHAR(512)",
            "oidc_sid": "VARCHAR(512)",
        },
    }
    inspector = inspect(engine)
    for table_name, columns in additions.items():
        if not inspector.has_table(table_name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        with engine.begin() as connection:
            for name, definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {definition}')


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_settings = settings or get_settings()
        ensure_sso_key(active_settings.data_dir)
        engine = make_engine(active_settings.database_url)
        Base.metadata.create_all(bind=engine)
        _migrate_legacy_columns(engine)
        application.state.settings = active_settings
        application.state.engine = engine
        application.state.session_factory = session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Ordivant Identity", version="0.2.0", lifespan=lifespan)
    application.include_router(router, prefix="/api/auth")
    application.include_router(sso_router, prefix="/api/auth")

    @application.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": {"code": error.code, "message": error.message}},
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
        safe_errors = [
            {"loc": item.get("loc", ()), "msg": item.get("msg", "Invalid value"), "type": item.get("type", "value_error")}
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    @application.middleware("http")
    async def auth_response_and_origin_policy(request: Request, call_next):
        is_auth = request.url.path.startswith("/api/auth/")
        origin_exempt = {
            "/api/auth/introspect",
            "/api/auth/oidc/backchannel-logout",
        }
        if is_auth and request.method in {"POST", "PATCH", "PUT", "DELETE"} and request.url.path not in origin_exempt:
            trusted_origins = (settings or getattr(request.app.state, "settings", None))
            allowed = trusted_origins.auth_origins if trusted_origins else ()
            if request.headers.get("origin") not in allowed:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": {"code": "origin_not_allowed", "message": "A trusted Origin is required"}},
                )
                response.headers["Cache-Control"] = "no-store"
                return response

        response = await call_next(request)
        if is_auth:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @application.get("/api/health")
    def health(request: Request):
        active_settings: Settings = request.app.state.settings
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "database": "unavailable", "mode": active_settings.mode},
            )
        backend = request.app.state.engine.dialect.name
        return {
            "status": "ok",
            "database": "postgresql" if backend == "postgresql" else "sqlite",
            "mode": active_settings.mode,
        }

    return application


app = create_app()
