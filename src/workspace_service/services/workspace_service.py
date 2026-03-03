"""Workspace business logic."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog

from workspace_service.exceptions import ValidationError, WorkspaceNotFoundError
from workspace_service.models.domain import ArtifactDomain, WorkspaceDomain
from workspace_service.repositories.base import (
    ArtifactRepository,
    ArtifactStore,
    WorkspaceRepository,
)

logger = structlog.get_logger()


class WorkspaceService:
    def __init__(
        self,
        workspace_repo: WorkspaceRepository,
        artifact_repo: ArtifactRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self._workspace_repo = workspace_repo
        self._artifact_repo = artifact_repo
        self._artifact_store = artifact_store

    async def create_workspace(
        self,
        *,
        tenant_id: str,
        user_id: str,
        workspace_scope: str,
        local_path: str | None = None,
    ) -> WorkspaceDomain:
        # Local scope requires a local_path for idempotent resolution
        if workspace_scope == "local" and not local_path:
            raise ValidationError("localPath is required for local workspace scope")

        # For local scope, check idempotency via local_path_key
        if workspace_scope == "local" and local_path:
            local_path_key = f"{tenant_id}#{user_id}#{local_path}"
            existing = await self._workspace_repo.get_by_local_path_key(local_path_key)
            if existing:
                await self._workspace_repo.update_last_active(existing.workspace_id)
                logger.info(
                    "workspace_reused",
                    workspace_id=existing.workspace_id,
                    local_path_key=local_path_key,
                )
                return existing
        else:
            local_path_key = None

        now = datetime.now(UTC)
        workspace = WorkspaceDomain(
            workspace_id=str(uuid.uuid4()),
            workspace_scope=workspace_scope,
            tenant_id=tenant_id,
            user_id=user_id,
            local_path=local_path,
            local_path_key=local_path_key,
            created_at=now,
            last_active_at=now,
        )
        await self._workspace_repo.create(workspace)
        logger.info("workspace_created", workspace_id=workspace.workspace_id, scope=workspace_scope)
        return workspace

    async def get_workspace(self, workspace_id: str) -> WorkspaceDomain:
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        return workspace

    async def list_workspaces(self, tenant_id: str, user_id: str) -> list[WorkspaceDomain]:
        return await self._workspace_repo.list_by_tenant_user(tenant_id, user_id)

    async def delete_workspace(self, workspace_id: str) -> None:
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        # Cascade: collect artifacts, delete metadata first, then S3 objects.
        # Metadata-first ordering means a partial failure leaves orphaned S3
        # objects (harmless) rather than metadata pointing to missing S3 keys.
        artifacts = await self._artifact_repo.list_by_workspace(workspace_id)
        s3_keys: list[str] = []
        for artifact in artifacts:
            if artifact.s3_key:
                s3_keys.append(artifact.s3_key)
            await self._artifact_repo.delete(workspace_id, artifact.artifact_id)

        # Best-effort S3 cleanup — log but do not raise on individual failures
        for key in s3_keys:
            try:
                await self._artifact_store.delete(key)
            except Exception:
                logger.warning("s3_delete_failed", s3_key=key, workspace_id=workspace_id)

        # Delete workspace record
        await self._workspace_repo.delete(workspace_id)
        logger.info("workspace_deleted", workspace_id=workspace_id)

    async def delete_session_history(self, workspace_id: str, session_id: str) -> None:
        """Delete all artifacts for a session within a workspace."""
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        artifacts = await self._artifact_repo.list_by_session(workspace_id, session_id)

        # Delete metadata first, collect S3 keys for best-effort cleanup
        s3_keys: list[str] = []
        for artifact in artifacts:
            if artifact.s3_key:
                s3_keys.append(artifact.s3_key)
            await self._artifact_repo.delete(workspace_id, artifact.artifact_id)

        # Best-effort S3 cleanup — log but do not raise on individual failures
        for key in s3_keys:
            try:
                await self._artifact_store.delete(key)
            except Exception:
                logger.warning(
                    "s3_delete_failed",
                    s3_key=key,
                    workspace_id=workspace_id,
                    session_id=session_id,
                )

        logger.info(
            "session_history_deleted",
            workspace_id=workspace_id,
            session_id=session_id,
            artifact_count=len(artifacts),
        )

    async def list_workspace_sessions(
        self,
        workspace_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], bool]:
        """List sessions in a workspace, aggregated from artifact metadata.

        Returns a tuple of (sessions_page, has_more).
        """
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)

        artifacts = await self._artifact_repo.list_by_workspace(workspace_id)
        sessions = self._aggregate_sessions(artifacts)

        # Sort by lastTaskAt descending (most recent first)
        sessions.sort(key=lambda s: s["lastTaskAt"], reverse=True)

        # Paginate
        page = sessions[offset : offset + limit]
        has_more = offset + limit < len(sessions)
        return page, has_more

    @staticmethod
    def _aggregate_sessions(artifacts: list[ArtifactDomain]) -> list[dict[str, Any]]:
        """Group artifacts by sessionId and compute summary fields."""
        groups: dict[str, list[ArtifactDomain]] = defaultdict(list)
        for artifact in artifacts:
            groups[artifact.session_id].append(artifact)

        sessions: list[dict[str, Any]] = []
        for session_id, session_artifacts in groups.items():
            created_at = min(a.created_at for a in session_artifacts)
            last_task_at = max(a.created_at for a in session_artifacts)
            task_ids = {a.task_id for a in session_artifacts if a.task_id is not None}
            sessions.append(
                {
                    "sessionId": session_id,
                    "createdAt": created_at.isoformat(),
                    "lastTaskAt": last_task_at.isoformat(),
                    "taskCount": len(task_ids),
                }
            )
        return sessions

    async def list_session_artifacts(
        self, workspace_id: str, session_id: str
    ) -> list[dict[str, str]]:
        """Get session summary (artifact list for a session under a workspace)."""
        workspace = await self._workspace_repo.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(workspace_id)
        artifacts = await self._artifact_repo.list_by_session(workspace_id, session_id)
        return [
            {
                "artifactId": a.artifact_id,
                "artifactType": a.artifact_type,
                "createdAt": a.created_at.isoformat(),
            }
            for a in artifacts
        ]
