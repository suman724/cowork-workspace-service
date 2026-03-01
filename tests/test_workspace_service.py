"""Tests for WorkspaceService."""

from __future__ import annotations

import pytest

from workspace_service.exceptions import WorkspaceNotFoundError
from workspace_service.services.workspace_service import WorkspaceService


@pytest.mark.unit
class TestCreateWorkspace:
    async def test_creates_general_workspace(self, workspace_service: WorkspaceService) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        assert ws.workspace_id
        assert ws.workspace_scope == "general"
        assert ws.tenant_id == "t1"

    async def test_creates_local_workspace(self, workspace_service: WorkspaceService) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="local",
            local_path="/home/user/project",
        )
        assert ws.workspace_scope == "local"
        assert ws.local_path == "/home/user/project"
        assert ws.local_path_key == "t1#u1#/home/user/project"

    async def test_local_workspace_idempotency(self, workspace_service: WorkspaceService) -> None:
        ws1 = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="local",
            local_path="/home/user/project",
        )
        ws2 = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="local",
            local_path="/home/user/project",
        )
        assert ws1.workspace_id == ws2.workspace_id

    async def test_general_workspace_always_new(self, workspace_service: WorkspaceService) -> None:
        ws1 = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        ws2 = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        assert ws1.workspace_id != ws2.workspace_id


@pytest.mark.unit
class TestGetWorkspace:
    async def test_get_existing(self, workspace_service: WorkspaceService) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        result = await workspace_service.get_workspace(ws.workspace_id)
        assert result.workspace_id == ws.workspace_id

    async def test_get_not_found(self, workspace_service: WorkspaceService) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.get_workspace("nonexistent")


@pytest.mark.unit
class TestListWorkspaces:
    async def test_list_by_tenant_user(self, workspace_service: WorkspaceService) -> None:
        await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        await workspace_service.create_workspace(
            tenant_id="t1", user_id="u2", workspace_scope="general"
        )
        result = await workspace_service.list_workspaces("t1", "u1")
        assert len(result) == 2


@pytest.mark.unit
class TestDeleteWorkspace:
    async def test_delete_workspace(self, workspace_service: WorkspaceService) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        await workspace_service.delete_workspace(ws.workspace_id)
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.get_workspace(ws.workspace_id)

    async def test_delete_not_found(self, workspace_service: WorkspaceService) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.delete_workspace("nonexistent")
