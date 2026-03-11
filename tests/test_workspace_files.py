"""Tests for cloud workspace file operations."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from workspace_service.repositories.memory import InMemoryArtifactStore
from workspace_service.services.file_service import (
    WorkspaceFileService,
    _validate_file_path,
)
from workspace_service.services.workspace_service import WorkspaceService


@pytest.mark.unit
class TestValidateFilePath:
    """Test file path validation and sanitization."""

    def test_simple_path(self) -> None:
        assert _validate_file_path("src/main.py") == "src/main.py"

    def test_trailing_slash_normalized(self) -> None:
        assert _validate_file_path("src/") == "src"

    def test_dot_slash_normalized(self) -> None:
        assert _validate_file_path("./src/main.py") == "src/main.py"

    def test_double_slash_normalized(self) -> None:
        assert _validate_file_path("src//main.py") == "src/main.py"

    def test_rejects_empty(self) -> None:
        with pytest.raises(Exception, match="must not be empty"):
            _validate_file_path("")

    def test_rejects_whitespace(self) -> None:
        with pytest.raises(Exception, match="must not be empty"):
            _validate_file_path("   ")

    def test_rejects_absolute(self) -> None:
        with pytest.raises(Exception, match="must be relative"):
            _validate_file_path("/etc/passwd")

    def test_rejects_traversal(self) -> None:
        with pytest.raises(Exception, match="must not contain"):
            _validate_file_path("../etc/passwd")

    def test_rejects_mid_traversal(self) -> None:
        with pytest.raises(Exception, match="must not contain"):
            _validate_file_path("src/../../etc/passwd")

    def test_rejects_nested_traversal(self) -> None:
        # "foo/../../bar" contains ".." so it's caught by the pattern check
        with pytest.raises(Exception, match="must not contain"):
            _validate_file_path("foo/../../bar")

    def test_rejects_null_byte(self) -> None:
        with pytest.raises(Exception, match="null bytes"):
            _validate_file_path("src/\x00evil.py")

    def test_rejects_dot_path(self) -> None:
        with pytest.raises(Exception, match="must not be empty"):
            _validate_file_path(".")


@pytest.mark.unit
class TestCloudWorkspaceCreation:
    """Test that cloud workspaces get s3_workspace_prefix."""

    async def test_cloud_workspace_gets_prefix(
        self,
        workspace_service: WorkspaceService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="cloud",
        )
        assert ws.s3_workspace_prefix is not None
        assert ws.s3_workspace_prefix == f"{ws.workspace_id}/workspace-files/"

    async def test_general_workspace_no_prefix(
        self,
        workspace_service: WorkspaceService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="general",
        )
        assert ws.s3_workspace_prefix is None

    async def test_local_workspace_no_prefix(
        self,
        workspace_service: WorkspaceService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1",
            user_id="u1",
            workspace_scope="local",
            local_path="/home/user/project",
        )
        assert ws.s3_workspace_prefix is None

    async def test_cloud_workspace_always_new(
        self,
        workspace_service: WorkspaceService,
    ) -> None:
        ws1 = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="cloud"
        )
        ws2 = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="cloud"
        )
        assert ws1.workspace_id != ws2.workspace_id


@pytest.mark.unit
class TestWorkspaceFileService:
    """Test file upload/download/list/delete operations."""

    async def _create_cloud_workspace(
        self,
        workspace_service: WorkspaceService,
    ) -> str:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="cloud"
        )
        return ws.workspace_id

    async def test_upload_and_download(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        await file_service.upload_file(ws_id, "src/main.py", b"print('hello')", "text/x-python")

        content, _ct = await file_service.download_file(ws_id, "src/main.py")
        assert content == b"print('hello')"

    async def test_list_files(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        await file_service.upload_file(ws_id, "a.txt", b"aaa")
        await file_service.upload_file(ws_id, "dir/b.txt", b"bbb")

        files = await file_service.list_files(ws_id)
        paths = sorted(f["path"] for f in files)
        assert paths == ["a.txt", "dir/b.txt"]

    async def test_list_files_empty(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        files = await file_service.list_files(ws_id)
        assert files == []

    async def test_delete_file(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        await file_service.upload_file(ws_id, "remove.txt", b"data")
        await file_service.delete_file(ws_id, "remove.txt")

        files = await file_service.list_files(ws_id)
        assert files == []

    async def test_download_nonexistent_file(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        with pytest.raises(Exception, match="not found"):
            await file_service.download_file(ws_id, "nonexistent.txt")

    async def test_upload_to_general_workspace_rejected(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="general"
        )
        with pytest.raises(Exception, match="cloud workspaces"):
            await file_service.upload_file(ws.workspace_id, "file.txt", b"data")

    async def test_upload_traversal_path_rejected(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        with pytest.raises(Exception, match="must not contain"):
            await file_service.upload_file(ws_id, "../etc/passwd", b"evil")

    async def test_upload_size_limit(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        # Test settings has 1 MB limit
        with pytest.raises(Exception, match="too large"):
            await file_service.upload_file(ws_id, "big.bin", b"x" * 1048577)

    async def test_workspace_not_found(
        self,
        file_service: WorkspaceFileService,
    ) -> None:
        with pytest.raises(Exception, match="not found"):
            await file_service.upload_file("nonexistent", "file.txt", b"data")

    async def test_overwrite_file(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
    ) -> None:
        ws_id = await self._create_cloud_workspace(workspace_service)
        await file_service.upload_file(ws_id, "file.txt", b"v1")
        await file_service.upload_file(ws_id, "file.txt", b"v2")

        content, _ = await file_service.download_file(ws_id, "file.txt")
        assert content == b"v2"


@pytest.mark.unit
class TestWorkspaceDeleteCascade:
    """Test that workspace deletion cleans up workspace files."""

    async def test_delete_cloud_workspace_cleans_files(
        self,
        workspace_service: WorkspaceService,
        file_service: WorkspaceFileService,
        artifact_store: InMemoryArtifactStore,
    ) -> None:
        ws = await workspace_service.create_workspace(
            tenant_id="t1", user_id="u1", workspace_scope="cloud"
        )
        await file_service.upload_file(ws.workspace_id, "a.txt", b"aaa")
        await file_service.upload_file(ws.workspace_id, "b.txt", b"bbb")

        # Files exist in store
        prefix = ws.s3_workspace_prefix
        assert prefix is not None
        files_before = await artifact_store.list_prefix(prefix)
        assert len(files_before) == 2

        # Delete workspace
        await workspace_service.delete_workspace(ws.workspace_id)

        # Files cleaned up
        files_after = await artifact_store.list_prefix(prefix)
        assert len(files_after) == 0


@pytest.mark.unit
class TestFileRoutes:
    """Test file HTTP endpoints."""

    async def _create_cloud_workspace(self, client: AsyncClient) -> str:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "cloud"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "s3WorkspacePrefix" in data
        return data["workspaceId"]

    async def test_upload_file(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        resp = await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "src/main.py"},
            files={"file": ("main.py", b"print('hello')", "text/x-python")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["path"] == "src/main.py"
        assert data["size"] == len(b"print('hello')")

    async def test_download_file(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "hello.txt"},
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        resp = await client.get(f"/workspaces/{ws_id}/files/hello.txt")
        assert resp.status_code == 200
        assert resp.content == b"hello world"

    async def test_list_files(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "a.txt"},
            files={"file": ("a.txt", b"aaa", "text/plain")},
        )
        await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "b.txt"},
            files={"file": ("b.txt", b"bbb", "text/plain")},
        )
        resp = await client.get(f"/workspaces/{ws_id}/files")
        assert resp.status_code == 200
        paths = sorted(f["path"] for f in resp.json())
        assert paths == ["a.txt", "b.txt"]

    async def test_delete_file(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "del.txt"},
            files={"file": ("del.txt", b"data", "text/plain")},
        )
        resp = await client.delete(f"/workspaces/{ws_id}/files/del.txt")
        assert resp.status_code == 204

        # Verify deleted
        list_resp = await client.get(f"/workspaces/{ws_id}/files")
        assert list_resp.json() == []

    async def test_upload_to_general_workspace_rejected(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = resp.json()["workspaceId"]
        resp = await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "file.txt"},
            files={"file": ("file.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_upload_traversal_rejected(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        resp = await client.post(
            f"/workspaces/{ws_id}/files",
            params={"path": "../etc/passwd"},
            files={"file": ("passwd", b"evil", "text/plain")},
        )
        assert resp.status_code == 400

    async def test_download_nonexistent(self, client: AsyncClient) -> None:
        ws_id = await self._create_cloud_workspace(client)
        resp = await client.get(f"/workspaces/{ws_id}/files/nonexistent.txt")
        assert resp.status_code == 404

    async def test_cloud_workspace_response_has_prefix(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "cloud"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "s3WorkspacePrefix" in data
        ws_id = data["workspaceId"]
        assert data["s3WorkspacePrefix"] == f"{ws_id}/workspace-files/"

    async def test_general_workspace_response_no_prefix(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        assert resp.status_code == 201
        assert "s3WorkspacePrefix" not in resp.json()

    async def test_workspace_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/workspaces/nonexistent/files")
        assert resp.status_code == 404
