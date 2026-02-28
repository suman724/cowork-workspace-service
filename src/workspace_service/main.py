"""FastAPI application factory for the Workspace Service."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import aioboto3
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from workspace_service.config import Settings
from workspace_service.exceptions import ServiceError
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

        app.state.workspace_service = WorkspaceService(
            workspace_repo, artifact_repo, artifact_store
        )
        app.state.artifact_service = ArtifactService(
            workspace_repo, artifact_repo, artifact_store, settings
        )

        logger.info("workspace_service_started", env=settings.env)
        yield
        logger.info("workspace_service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cowork Workspace Service",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(artifacts.router)

    app.add_exception_handler(ServiceError, _service_error_handler)

    return app


async def _service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)  # noqa: S101
    body: dict[str, Any] = {
        "code": exc.code,
        "message": exc.message,
        "retryable": exc.status_code >= 500,
    }
    return JSONResponse(status_code=exc.status_code, content=body)


app = create_app()
