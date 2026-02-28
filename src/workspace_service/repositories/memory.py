"""In-memory repositories for unit tests."""

from __future__ import annotations

from workspace_service.models.domain import ArtifactDomain, WorkspaceDomain


class InMemoryWorkspaceRepository:
    """Dict-backed workspace repository for testing."""

    def __init__(self) -> None:
        self._workspaces: dict[str, WorkspaceDomain] = {}
        self._local_path_index: dict[str, str] = {}  # local_path_key -> workspace_id

    async def create(self, workspace: WorkspaceDomain) -> None:
        self._workspaces[workspace.workspace_id] = workspace
        if workspace.local_path_key:
            self._local_path_index[workspace.local_path_key] = workspace.workspace_id

    async def get(self, workspace_id: str) -> WorkspaceDomain | None:
        return self._workspaces.get(workspace_id)

    async def get_by_local_path_key(self, local_path_key: str) -> WorkspaceDomain | None:
        ws_id = self._local_path_index.get(local_path_key)
        if ws_id:
            return self._workspaces.get(ws_id)
        return None

    async def list_by_tenant_user(self, tenant_id: str, user_id: str) -> list[WorkspaceDomain]:
        return [
            ws
            for ws in self._workspaces.values()
            if ws.tenant_id == tenant_id and ws.user_id == user_id
        ]

    async def update_last_active(self, workspace_id: str) -> None:
        from datetime import UTC, datetime

        ws = self._workspaces.get(workspace_id)
        if ws:
            ws.last_active_at = datetime.now(UTC)

    async def delete(self, workspace_id: str) -> None:
        ws = self._workspaces.pop(workspace_id, None)
        if ws and ws.local_path_key:
            self._local_path_index.pop(ws.local_path_key, None)


class InMemoryArtifactRepository:
    """Dict-backed artifact metadata repository for testing."""

    def __init__(self) -> None:
        self._artifacts: dict[str, ArtifactDomain] = {}  # keyed by f"{ws_id}#{artifact_id}"

    def _key(self, workspace_id: str, artifact_id: str) -> str:
        return f"{workspace_id}#{artifact_id}"

    async def create(self, artifact: ArtifactDomain) -> None:
        key = self._key(artifact.workspace_id, artifact.artifact_id)
        self._artifacts[key] = artifact

    async def get(self, workspace_id: str, artifact_id: str) -> ArtifactDomain | None:
        return self._artifacts.get(self._key(workspace_id, artifact_id))

    async def list_by_workspace(self, workspace_id: str) -> list[ArtifactDomain]:
        return [a for a in self._artifacts.values() if a.workspace_id == workspace_id]

    async def list_by_session(self, workspace_id: str, session_id: str) -> list[ArtifactDomain]:
        return [
            a
            for a in self._artifacts.values()
            if a.workspace_id == workspace_id and a.session_id == session_id
        ]

    async def delete(self, workspace_id: str, artifact_id: str) -> None:
        self._artifacts.pop(self._key(workspace_id, artifact_id), None)

    async def delete_by_workspace(self, workspace_id: str) -> None:
        keys_to_delete = [k for k, a in self._artifacts.items() if a.workspace_id == workspace_id]
        for key in keys_to_delete:
            del self._artifacts[key]


class InMemoryArtifactStore:
    """Dict-backed artifact content store for testing."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}  # s3_key -> (content, content_type)

    async def upload(self, s3_key: str, content: bytes, content_type: str) -> None:
        self._objects[s3_key] = (content, content_type)

    async def download(self, s3_key: str) -> bytes:
        item = self._objects.get(s3_key)
        if item is None:
            raise FileNotFoundError(f"Object not found: {s3_key}")
        return item[0]

    async def delete(self, s3_key: str) -> None:
        self._objects.pop(s3_key, None)

    async def delete_prefix(self, prefix: str) -> None:
        keys_to_delete = [k for k in self._objects if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._objects[key]
