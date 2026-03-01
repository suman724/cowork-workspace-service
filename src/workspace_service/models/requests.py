"""API request models for input validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateWorkspaceRequest(BaseModel):
    """POST /workspaces request body."""

    tenant_id: str = Field(alias="tenantId", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    workspace_scope: str = Field(alias="workspaceScope", min_length=1)
    local_path: str | None = Field(alias="localPath", default=None)


class UploadArtifactRequest(BaseModel):
    """POST /workspaces/{id}/artifacts request body."""

    session_id: str = Field(alias="sessionId", min_length=1)
    task_id: str | None = Field(alias="taskId", default=None)
    step_id: str | None = Field(alias="stepId", default=None)
    artifact_type: str = Field(alias="artifactType", min_length=1)
    artifact_name: str | None = Field(alias="artifactName", default=None)
    content_type: str | None = Field(alias="contentType", default=None)
    content_base64: str | None = Field(alias="contentBase64", default=None)
    messages: list[dict[str, Any]] | None = None
