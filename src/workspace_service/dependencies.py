"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Request

from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.file_service import WorkspaceFileService
from workspace_service.services.workspace_service import WorkspaceService


def get_workspace_service(request: Request) -> WorkspaceService:
    return request.app.state.workspace_service  # type: ignore[no-any-return]


def get_artifact_service(request: Request) -> ArtifactService:
    return request.app.state.artifact_service  # type: ignore[no-any-return]


def get_file_service(request: Request) -> WorkspaceFileService:
    return request.app.state.file_service  # type: ignore[no-any-return]
