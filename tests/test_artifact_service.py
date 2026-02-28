"""Tests for ArtifactService."""

from __future__ import annotations

import base64

import pytest

from workspace_service.exceptions import (
    ArtifactNotFoundError,
    ArtifactTooLargeError,
    ValidationError,
    WorkspaceNotFoundError,
)
from workspace_service.repositories.memory import (
    InMemoryArtifactRepository,
    InMemoryArtifactStore,
)
from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.workspace_service import WorkspaceService


@pytest.mark.unit
class TestUploadArtifact:
    async def test_upload_tool_output(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        content = base64.b64encode(b"hello world").decode()
        artifact = await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="tool_output",
            artifact_name="output.txt",
            content_type="text/plain",
            content_base64=content,
        )
        assert artifact.artifact_id
        assert artifact.s3_key
        assert artifact.size_bytes == 11

    async def test_upload_session_history(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        messages = [{"messageId": "m1", "role": "user", "content": "hello"}]
        artifact = await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="session_history",
            messages=messages,
        )
        assert artifact.artifact_type == "session_history"

    async def test_session_history_overwrite(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        msgs1 = [{"messageId": "m1", "role": "user", "content": "v1"}]
        a1 = await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="session_history",
            messages=msgs1,
        )
        msgs2 = [{"messageId": "m1", "role": "user", "content": "v2"}]
        a2 = await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="session_history",
            messages=msgs2,
        )
        assert a1.artifact_id != a2.artifact_id
        # Old one should be deleted
        with pytest.raises(ArtifactNotFoundError):
            await artifact_service.download_artifact(ws.workspace_id, a1.artifact_id)

    async def test_upload_workspace_not_found(self, artifact_service: ArtifactService) -> None:
        with pytest.raises(WorkspaceNotFoundError):
            await artifact_service.upload_artifact(
                workspace_id="nonexistent",
                session_id="sess-1",
                artifact_type="tool_output",
                content_base64=base64.b64encode(b"data").decode(),
            )

    async def test_upload_too_large(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        large = base64.b64encode(b"x" * 2_000_000).decode()
        with pytest.raises(ArtifactTooLargeError):
            await artifact_service.upload_artifact(
                workspace_id=ws.workspace_id,
                session_id="sess-1",
                artifact_type="tool_output",
                content_base64=large,
            )

    async def test_upload_missing_content(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        with pytest.raises(ValidationError, match="contentBase64 required"):
            await artifact_service.upload_artifact(
                workspace_id=ws.workspace_id,
                session_id="sess-1",
                artifact_type="tool_output",
            )

    async def test_upload_session_history_missing_messages(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        with pytest.raises(ValidationError, match="messages required"):
            await artifact_service.upload_artifact(
                workspace_id=ws.workspace_id,
                session_id="sess-1",
                artifact_type="session_history",
            )


@pytest.mark.unit
class TestDownloadArtifact:
    async def test_download(
        self, workspace_service: WorkspaceService, artifact_service: ArtifactService
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        content_bytes = b"hello download"
        content_b64 = base64.b64encode(content_bytes).decode()
        artifact = await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="tool_output",
            content_type="text/plain",
            content_base64=content_b64,
        )
        data, ct = await artifact_service.download_artifact(ws.workspace_id, artifact.artifact_id)
        assert data == content_bytes
        assert ct == "text/plain"

    async def test_download_not_found(self, artifact_service: ArtifactService) -> None:
        with pytest.raises(ArtifactNotFoundError):
            await artifact_service.download_artifact("ws-1", "nonexistent")


@pytest.mark.unit
class TestDeleteCascade:
    async def test_workspace_delete_cascades_artifacts(
        self,
        workspace_service: WorkspaceService,
        artifact_service: ArtifactService,
        artifact_store: InMemoryArtifactStore,
        artifact_repo: InMemoryArtifactRepository,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        content = base64.b64encode(b"data").decode()
        await artifact_service.upload_artifact(
            workspace_id=ws.workspace_id,
            session_id="sess-1",
            artifact_type="tool_output",
            content_base64=content,
        )
        assert len(artifact_store._objects) == 1
        assert len(artifact_repo._artifacts) == 1

        await workspace_service.delete_workspace(ws.workspace_id)

        assert len(artifact_store._objects) == 0
        assert len(artifact_repo._artifacts) == 0
