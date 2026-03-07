"""FastAPI application factory for the Workspace Service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aioboto3
import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workspace_service.clients.session_client import SessionClient
from workspace_service.config import Settings
from workspace_service.exceptions import ServiceError
from workspace_service.middleware import RequestIdMiddleware
from workspace_service.repositories.dynamo_artifact import DynamoArtifactRepository
from workspace_service.repositories.dynamo_workspace import DynamoWorkspaceRepository
from workspace_service.repositories.s3_store import S3ArtifactStore
from workspace_service.routes import artifacts, health, workspaces
from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.workspace_service import WorkspaceService

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()

    log_level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )

    session = aioboto3.Session()
    boto_kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        boto_kwargs["endpoint_url"] = settings.aws_endpoint_url

    async with (
        session.resource("dynamodb", **boto_kwargs) as dynamodb,
        session.client("s3", **boto_kwargs) as s3_client,
    ):
        ws_table = await dynamodb.Table(settings.workspaces_table)
        art_table = await dynamodb.Table(settings.artifacts_table)

        workspace_repo = DynamoWorkspaceRepository(ws_table)
        artifact_repo = DynamoArtifactRepository(art_table)
        artifact_store = S3ArtifactStore(s3_client, settings.s3_bucket)

        # Session Service client for enriching session summaries with names
        session_http = httpx.AsyncClient(base_url=settings.session_service_url, timeout=10.0)
        session_client = SessionClient(session_http)

        app.state.workspace_service = WorkspaceService(
            workspace_repo, artifact_repo, artifact_store, session_client=session_client
        )
        app.state.artifact_service = ArtifactService(
            workspace_repo, artifact_repo, artifact_store, settings
        )

        logger.info("workspace_service_started", env=settings.env)
        yield
        await session_client.close()
        logger.info("workspace_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cowork Workspace Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(artifacts.router)

    app.add_exception_handler(ServiceError, _service_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)

    return app


async def _service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    se = (
        exc
        if isinstance(exc, ServiceError)
        else ServiceError("Unknown", code="INTERNAL_ERROR", status_code=500)
    )
    body: dict[str, Any] = {
        "code": se.code,
        "message": se.message,
        "retryable": se.status_code >= 500,
    }
    return JSONResponse(status_code=se.status_code, content=body)


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "Internal server error", "retryable": True},
    )


app = create_app()
