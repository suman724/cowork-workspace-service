"""Domain models for workspace and artifact entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkspaceDomain(BaseModel):
    """Internal workspace representation."""

    workspace_id: str
    workspace_scope: Literal["local", "general", "cloud"]
    tenant_id: str
    user_id: str
    local_path: str | None = None
    local_path_key: str | None = None  # {tenantId}#{userId}#{localPath} for GSI
    s3_workspace_prefix: str | None = None  # {workspaceId}/workspace-files/ for cloud scope
    created_at: datetime
    last_active_at: datetime
    updated_at: datetime | None = None
    ttl: int | None = None


class ArtifactDomain(BaseModel):
    """Internal artifact metadata representation."""

    artifact_id: str
    workspace_id: str
    session_id: str
    task_id: str | None = None
    step_id: str | None = None
    artifact_type: Literal["session_history", "tool_output", "file_diff"]
    artifact_name: str | None = None
    content_type: str | None = None
    s3_key: str | None = None
    size_bytes: int | None = None
    created_at: datetime
    updated_at: datetime | None = None
