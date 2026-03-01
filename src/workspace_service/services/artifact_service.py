"""Artifact business logic: upload, download, delete."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import structlog

from workspace_service.config import Settings
from workspace_service.exceptions import (
    ArtifactNotFoundError,
    ArtifactTooLargeError,
    ValidationError,
    WorkspaceNotFoundError,
)
from workspace_service.models.domain import ArtifactDomain
from workspace_service.repositories.base import (
    ArtifactRepository,
    ArtifactStore,
    WorkspaceRepository,
)

logger = structlog.get_logger()


class ArtifactService:
    def __init__(
        self,
        workspace_repo: WorkspaceRepository,
        artifact_repo: ArtifactRepository,
        artifact_store: ArtifactStore,
        settings: Settings,
    ) -> None:
        self._workspace_repo = workspace_repo
        self._artifact_repo = artifact_repo
        self._artifact_store = artifact_store
        self._settings = settings

    async def upload_artifact(
        self,
        *,
        workspace_id: str,
        session_id: str,
        task_id: str | None = None,
        step_id: str | None = None,
        artifact_type: str,
        artifact_name: str | None = None,
        content_type: str | None = None,
        content_base64: str | None = None,
        messages: list[dict[str, object]] | None = None,
    ) -> ArtifactDomain:
        # Verify workspace exists
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        # Resolve content
        if artifact_type == "session_history":
            if messages is None:
                raise ValidationError("messages required for session_history artifact")
            content = json.dumps(messages).encode("utf-8")
            content_type = content_type or "application/json"
        elif content_base64:
            content = base64.b64decode(content_base64)
        else:
            raise ValidationError("contentBase64 required for non-history artifacts")

        # Size check
        if len(content) > self._settings.max_artifact_size_bytes:
            raise ArtifactTooLargeError(len(content), self._settings.max_artifact_size_bytes)

        artifact_id = str(uuid.uuid4())
        s3_key = f"{workspace_id}/{session_id}/{artifact_id}"

        # Collect old session_history artifacts before writing the replacement
        old_history: list[ArtifactDomain] = []
        if artifact_type == "session_history":
            existing = await self._artifact_repo.list_by_session(workspace_id, session_id)
            old_history = [a for a in existing if a.artifact_type == "session_history"]

        # Create metadata first
        now = datetime.now(UTC)
        artifact = ArtifactDomain(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            session_id=session_id,
            task_id=task_id,
            step_id=step_id,
            artifact_type=artifact_type,
            artifact_name=artifact_name,
            content_type=content_type,
            s3_key=s3_key,
            size_bytes=len(content),
            created_at=now,
        )
        await self._artifact_repo.create(artifact)

        # Upload content to S3; cleanup metadata on failure
        try:
            ct = content_type or "application/octet-stream"
            await self._artifact_store.upload(s3_key, content, ct)
        except Exception:
            await self._artifact_repo.delete(workspace_id, artifact_id)
            raise

        # Only now remove prior session_history records (new snapshot is durable)
        for old in old_history:
            if old.s3_key:
                await self._artifact_store.delete(old.s3_key)
            await self._artifact_repo.delete(workspace_id, old.artifact_id)

        await self._workspace_repo.update_last_active(workspace_id)
        logger.info("artifact_uploaded", artifact_id=artifact_id, workspace_id=workspace_id)
        return artifact

    async def download_artifact(self, workspace_id: str, artifact_id: str) -> tuple[bytes, str]:
        artifact = await self._artifact_repo.get(workspace_id, artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id)

        if not artifact.s3_key:
            raise ArtifactNotFoundError(artifact_id)

        content = await self._artifact_store.download(artifact.s3_key)
        return content, artifact.content_type or "application/octet-stream"

    async def list_artifacts(self, workspace_id: str) -> list[ArtifactDomain]:
        return await self._artifact_repo.list_by_workspace(workspace_id)

    async def list_session_artifacts(
        self, workspace_id: str, session_id: str
    ) -> list[ArtifactDomain]:
        return await self._artifact_repo.list_by_session(workspace_id, session_id)
