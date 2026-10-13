from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from .api import router
from .collaboration import router as collaboration_router
from .config import Settings, get_settings
from .db import Base, make_engine, session_factory
from .errors import DomainError
from . import models as _models  # noqa: F401
from . import identity as _identity  # noqa: F401


def create_app(database_url: str | None = None, *, mode: str | None = None) -> FastAPI:
    settings = get_settings()
    if mode is not None:
        if mode not in {"development", "production"}:
            raise RuntimeError("mode must be 'development' or 'production'")
        settings = replace(settings, mode=mode)
    engine = make_engine(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    application = FastAPI(title="Ordivant Knowledge", version="0.2.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.engine = engine
    application.state.session_factory = session_factory(engine)
    application.state.collaboration_connections = 0
    application.include_router(router)
    application.include_router(collaboration_router)

    @application.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, error: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": {"code": error.code, "message": error.message}},
        )

    return application


app = create_app()
