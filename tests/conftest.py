"""Shared fixtures for workspace service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from workspace_service.config import Settings
from workspace_service.dependencies import get_artifact_service, get_workspace_service
from workspace_service.repositories.memory import (
    InMemoryArtifactRepository,
    InMemoryArtifactStore,
    InMemoryWorkspaceRepository,
)
from workspace_service.routes import artifacts, health, workspaces
from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.workspace_service import WorkspaceService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        max_artifact_size_bytes=1048576,  # 1 MB for tests
    )


@pytest.fixture
def workspace_repo() -> InMemoryWorkspaceRepository:
    return InMemoryWorkspaceRepository()


@pytest.fixture
def artifact_repo() -> InMemoryArtifactRepository:
    return InMemoryArtifactRepository()


@pytest.fixture
def artifact_store() -> InMemoryArtifactStore:
    return InMemoryArtifactStore()


@pytest.fixture
def workspace_service(
    workspace_repo: InMemoryWorkspaceRepository,
    artifact_repo: InMemoryArtifactRepository,
    artifact_store: InMemoryArtifactStore,
) -> WorkspaceService:
    return WorkspaceService(workspace_repo, artifact_repo, artifact_store)


@pytest.fixture
def artifact_service(
    workspace_repo: InMemoryWorkspaceRepository,
    artifact_repo: InMemoryArtifactRepository,
    artifact_store: InMemoryArtifactStore,
    settings: Settings,
) -> ArtifactService:
    return ArtifactService(workspace_repo, artifact_repo, artifact_store, settings)


@pytest.fixture
async def client(
    workspace_service: WorkspaceService,
    artifact_service: ArtifactService,
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(health.router)
    app.include_router(workspaces.router)
    app.include_router(artifacts.router)

    app.dependency_overrides[get_workspace_service] = lambda: workspace_service
    app.dependency_overrides[get_artifact_service] = lambda: artifact_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
