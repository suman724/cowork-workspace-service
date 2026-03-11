"""Workspace file operations for cloud-scoped workspaces."""

from __future__ import annotations

import posixpath
import re

import structlog

from workspace_service.config import Settings
from workspace_service.exceptions import (
    ArtifactTooLargeError,
    ValidationError,
    WorkspaceNotFoundError,
)
from workspace_service.models.domain import WorkspaceDomain
from workspace_service.repositories.base import ArtifactStore, WorkspaceRepository

logger = structlog.get_logger()

# Reject path components that could escape the workspace prefix
_TRAVERSAL_PATTERN = re.compile(r"(^|/)\.\.(/|$)")


def _validate_file_path(file_path: str) -> str:
    """Validate and normalize a workspace file path.

    Prevents directory traversal and rejects empty/absolute paths.
    Returns the normalized path.
    """
    if not file_path or file_path.isspace():
        raise ValidationError("File path must not be empty")
    if file_path.startswith("/"):
        raise ValidationError("File path must be relative")
    if _TRAVERSAL_PATTERN.search(file_path):
        raise ValidationError("File path must not contain '..' components")

    # Normalize: collapse redundant separators, resolve single dots
    normalized = posixpath.normpath(file_path)
    if normalized.startswith(".."):
        raise ValidationError("File path must not escape workspace directory")
    return normalized


class WorkspaceFileService:
    """Manage workspace files in S3 for cloud-scoped workspaces."""

    def __init__(
        self,
        workspace_repo: WorkspaceRepository,
        artifact_store: ArtifactStore,
        settings: Settings,
    ) -> None:
        self._workspace_repo = workspace_repo
        self._artifact_store = artifact_store
        self._settings = settings

    async def _resolve_cloud_workspace(self, workspace_id: str) -> WorkspaceDomain:
        """Get workspace and verify it's cloud-scoped with a prefix."""
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        if not workspace.s3_workspace_prefix:
            raise ValidationError("File operations are only supported for cloud workspaces")
        return workspace

    async def upload_file(
        self,
        workspace_id: str,
        file_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str | int]:
        """Upload a file to the workspace."""
        workspace = await self._resolve_cloud_workspace(workspace_id)
        normalized = _validate_file_path(file_path)

        if len(content) > self._settings.max_artifact_size_bytes:
            raise ArtifactTooLargeError(len(content), self._settings.max_artifact_size_bytes)

        s3_key = f"{workspace.s3_workspace_prefix}{normalized}"
        await self._artifact_store.upload(s3_key, content, content_type)
        await self._workspace_repo.update_last_active(workspace_id)

        logger.info(
            "workspace_file_uploaded",
            workspace_id=workspace_id,
            path=normalized,
            size=len(content),
        )
        return {"path": normalized, "size": len(content)}

    async def download_file(
        self,
        workspace_id: str,
        file_path: str,
    ) -> tuple[bytes, str]:
        """Download a file from the workspace. Returns (content, content_type)."""
        workspace = await self._resolve_cloud_workspace(workspace_id)
        normalized = _validate_file_path(file_path)
        s3_key = f"{workspace.s3_workspace_prefix}{normalized}"

        from workspace_service.exceptions import ArtifactNotFoundError

        try:
            content = await self._artifact_store.download(s3_key)
        except Exception as exc:
            raise ArtifactNotFoundError(file_path) from exc

        return content, "application/octet-stream"

    async def list_files(
        self,
        workspace_id: str,
    ) -> list[dict[str, str | int]]:
        """List all files in the workspace."""
        workspace = await self._resolve_cloud_workspace(workspace_id)
        prefix = workspace.s3_workspace_prefix
        if prefix is None:  # pragma: no cover — guaranteed by _resolve_cloud_workspace
            raise ValidationError("Workspace has no S3 prefix")

        files = await self._artifact_store.list_prefix(prefix)
        # Strip the workspace prefix to return relative paths
        result: list[dict[str, str | int]] = []
        for entry in files:
            relative = entry["key"][len(prefix) :]
            if relative:  # skip the prefix-only entry if any
                result.append({"path": relative, "size": entry["size"]})
        return result

    async def delete_file(
        self,
        workspace_id: str,
        file_path: str,
    ) -> None:
        """Delete a file from the workspace."""
        workspace = await self._resolve_cloud_workspace(workspace_id)
        normalized = _validate_file_path(file_path)
        s3_key = f"{workspace.s3_workspace_prefix}{normalized}"
        await self._artifact_store.delete(s3_key)
        logger.info(
            "workspace_file_deleted",
            workspace_id=workspace_id,
            path=normalized,
        )
