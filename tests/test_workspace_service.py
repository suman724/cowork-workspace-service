"""Tests for WorkspaceService."""

from __future__ import annotations

import base64

import pytest

from workspace_service.exceptions import WorkspaceNotFoundError
from workspace_service.services.artifact_service import ArtifactService
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


@pytest.mark.unit
class TestListWorkspaceSessions:
    async def test_empty_workspace(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        sessions, has_more = await workspace_service.list_workspace_sessions(ws.workspace_id)
        assert sessions == []
        assert has_more is False

    async def test_aggregates_sessions(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        # Upload artifacts for two sessions with different task IDs
        for task_id in ["task-1", "task-2", "task-3"]:
            await artifact_service.upload_artifact(
                workspace_id=ws.workspace_id,
                session_id="sess-A",
                artifact_type="tool_output",
                content_base64=base64.b64encode(b"data").decode(),
                content_type="text/plain",
                task_id=task_id,
            )
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-B",
            artifact_type="tool_output",
            content_base64=base64.b64encode(b"data").decode(),
            content_type="text/plain",
            task_id="task-10",
        )

        sessions, has_more = await workspace_service.list_workspace_sessions(ws.workspace_id)
        assert len(sessions) == 2
        assert has_more is False

        by_id = {s["sessionId"]: s for s in sessions}
        assert by_id["sess-A"]["taskCount"] == 3
        assert by_id["sess-B"]["taskCount"] == 1

    async def test_sorted_by_recency(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        # Upload for sess-old first, then sess-new
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-old",
            artifact_type="tool_output",
            content_base64=base64.b64encode(b"old").decode(),
            content_type="text/plain",
        )
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-new",
            artifact_type="tool_output",
            content_base64=base64.b64encode(b"new").decode(),
            content_type="text/plain",
        )

        sessions, _ = await workspace_service.list_workspace_sessions(ws.workspace_id)
        assert sessions[0]["sessionId"] == "sess-new"
        assert sessions[1]["sessionId"] == "sess-old"

    async def test_pagination(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        for i in range(5):
            await artifact_service.upload_artifact(
                workspace_id=ws.workspace_id,
                session_id=f"sess-{i}",
                artifact_type="tool_output",
                content_base64=base64.b64encode(f"data-{i}".encode()).decode(),
                content_type="text/plain",
            )

        page1, has_more1 = await workspace_service.list_workspace_sessions(
            ws.workspace_id, limit=2, offset=0
        )
        assert len(page1) == 2
        assert has_more1 is True

        page2, has_more2 = await workspace_service.list_workspace_sessions(
            ws.workspace_id, limit=2, offset=2
        )
        assert len(page2) == 2
        assert has_more2 is True

        page3, has_more3 = await workspace_service.list_workspace_sessions(
            ws.workspace_id, limit=2, offset=4
        )
        assert len(page3) == 1
        assert has_more3 is False

    async def test_workspace_not_found(self, workspace_service: WorkspaceService) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.list_workspace_sessions("nonexistent")


@pytest.mark.unit
class TestDeleteSessionHistory:
    async def test_deletes_session_artifacts(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        # Upload artifacts for two sessions
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-keep",
            artifact_type="tool_output",
            content_base64=base64.b64encode(b"keep").decode(),
            content_type="text/plain",
        )
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-delete",
            artifact_type="tool_output",
            content_base64=base64.b64encode(b"delete1").decode(),
            content_type="text/plain",
        )
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-delete",
            artifact_type="session_history",
            messages=[{"role": "user", "content": "test"}],
        )

        await workspace_service.delete_session_history(ws.workspace_id, "sess-delete")

        sessions, _ = await workspace_service.list_workspace_sessions(ws.workspace_id)
        session_ids = [s["sessionId"] for s in sessions]
        assert "sess-keep" in session_ids
        assert "sess-delete" not in session_ids

    async def test_delete_nonexistent_session_is_noop(
        self,
        workspace_service: WorkspaceService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        # Should not raise — no artifacts to delete
        await workspace_service.delete_session_history(ws.workspace_id, "nonexistent-session")

    async def test_workspace_not_found(self, workspace_service: WorkspaceService) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.delete_session_history("nonexistent", "sess-1")
