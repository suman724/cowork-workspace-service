"""Workspace CRUD endpoints."""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from starlette.responses import Response

from workspace_service.dependencies import get_artifact_service, get_workspace_service
from workspace_service.models.requests import CreateWorkspaceRequest
from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest,
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    workspace = await service.create_workspace(
        tenant_id=body.tenant_id,
        user_id=body.user_id,
        workspace_scope=body.workspace_scope,
        local_path=body.local_path,
    )
    return {
        "workspaceId": workspace.workspace_id,
        "workspaceScope": workspace.workspace_scope,
        "createdAt": workspace.created_at.isoformat(),
    }


@router.get("")
async def list_workspaces(
    tenant_id: str = Query(alias="tenantId"),
    user_id: str = Query(alias="userId"),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[dict[str, Any]]:
    workspaces = await service.list_workspaces(tenant_id, user_id)
    return [
        {
            "workspaceId": ws.workspace_id,
            "workspaceScope": ws.workspace_scope,
            "tenantId": ws.tenant_id,
            "userId": ws.user_id,
            "localPath": ws.local_path,
            "createdAt": ws.created_at.isoformat(),
            "lastActiveAt": ws.last_active_at.isoformat(),
        }
        for ws in workspaces
    ]


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    ws = await service.get_workspace(workspace_id)
    return {
        "workspaceId": ws.workspace_id,
        "workspaceScope": ws.workspace_scope,
        "tenantId": ws.tenant_id,
        "userId": ws.user_id,
        "localPath": ws.local_path,
        "createdAt": ws.created_at.isoformat(),
        "lastActiveAt": ws.last_active_at.isoformat(),
    }


@router.get("/{workspace_id}/sessions")
async def list_workspace_sessions(
    workspace_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    next_token: str | None = Query(default=None, alias="nextToken"),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, Any]:
    offset = _decode_token(next_token)
    sessions, has_more = await service.list_workspace_sessions(
        workspace_id, limit=limit, offset=offset
    )
    result: dict[str, Any] = {"sessions": sessions}
    if has_more:
        result["nextToken"] = _encode_token(offset + limit)
    return result


@router.get("/{workspace_id}/sessions/{session_id}/history")
async def get_session_history(
    workspace_id: str,
    session_id: str,
    artifact_service: ArtifactService = Depends(get_artifact_service),
) -> list[dict[str, Any]]:
    """Return conversation messages for a session.

    Finds the latest session_history artifact and returns its content.
    """
    artifacts = await artifact_service.list_session_artifacts(workspace_id, session_id)
    history_artifacts = [a for a in artifacts if a.artifact_type == "session_history"]
    if not history_artifacts:
        return []

    # Take the most recent session_history artifact
    history_artifacts.sort(key=lambda a: a.created_at, reverse=True)
    artifact = history_artifacts[0]

    content_bytes, _ = await artifact_service.download_artifact(workspace_id, artifact.artifact_id)
    messages: list[dict[str, Any]] = json.loads(content_bytes)
    return messages


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    await service.delete_workspace(workspace_id)
    return Response(status_code=204)


def _encode_token(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()


def _decode_token(token: str | None) -> int:
    if token is None:
        return 0
    try:
        data = json.loads(base64.urlsafe_b64decode(token))
        return int(data["offset"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return 0
