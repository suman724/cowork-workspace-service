"""Service-tier tests for DynamoDB workspace repository.

Requires: LocalStack (port 4566) or DynamoDB Local (set AWS_ENDPOINT_URL)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from workspace_service.models.domain import WorkspaceDomain
from workspace_service.repositories.dynamo_workspace import DynamoWorkspaceRepository


def _make_workspace(
    workspace_id: str = "ws-1",
    tenant_id: str = "t1",
    user_id: str = "u1",
    **overrides: object,
) -> WorkspaceDomain:
    now = datetime.now(UTC)
    defaults = {
        "workspace_id": workspace_id,
        "workspace_scope": "general",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "created_at": now,
        "last_active_at": now,
    }
    defaults.update(overrides)
    return WorkspaceDomain(**defaults)  # type: ignore[arg-type]


@pytest.mark.service
@pytest.mark.asyncio
class TestWorkspaceRepoCRUD:
    async def test_create_and_get_workspace(
        self, workspace_repo: DynamoWorkspaceRepository
    ) -> None:
        """Create a workspace and retrieve it by ID."""
        ws = _make_workspace()
        await workspace_repo.create(ws)

        result = await workspace_repo.get("ws-1")
        assert result is not None
        assert result.workspace_id == "ws-1"
        assert result.workspace_scope == "general"
        assert result.tenant_id == "t1"
        assert result.user_id == "u1"

    async def test_get_nonexistent_returns_none(
        self, workspace_repo: DynamoWorkspaceRepository
    ) -> None:
        """Getting a non-existent workspace returns None."""
        result = await workspace_repo.get("nonexistent")
        assert result is None

    async def test_delete_workspace(self, workspace_repo: DynamoWorkspaceRepository) -> None:
        """Delete a workspace."""
        ws = _make_workspace()
        await workspace_repo.create(ws)
        await workspace_repo.delete("ws-1")

        result = await workspace_repo.get("ws-1")
        assert result is None


@pytest.mark.service
@pytest.mark.asyncio
class TestWorkspaceRepoGSI:
    async def test_resolve_by_local_path(self, workspace_repo: DynamoWorkspaceRepository) -> None:
        """Resolve a local workspace by localPathKey GSI."""
        ws = _make_workspace(
            workspace_scope="local",
            local_path="/home/user/project",
            local_path_key="t1#u1#/home/user/project",
        )
        await workspace_repo.create(ws)

        result = await workspace_repo.get_by_local_path_key("t1#u1#/home/user/project")
        assert result is not None
        assert result.workspace_id == "ws-1"
        assert result.local_path == "/home/user/project"

    async def test_list_workspaces_by_tenant(
        self, workspace_repo: DynamoWorkspaceRepository
    ) -> None:
        """List workspaces for a tenant-user pair via GSI."""
        for i in range(3):
            ws = _make_workspace(workspace_id=f"ws-{i}")
            await workspace_repo.create(ws)

        # Different user
        other = _make_workspace(workspace_id="ws-other", user_id="u2")
        await workspace_repo.create(other)

        results = await workspace_repo.list_by_tenant_user("t1", "u1")
        assert len(results) == 3
        ws_ids = {w.workspace_id for w in results}
        assert ws_ids == {"ws-0", "ws-1", "ws-2"}
