"""Workspace CRUD endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from starlette.responses import Response

from workspace_service.dependencies import get_workspace_service
from workspace_service.models.requests import CreateWorkspaceRequest
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


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    service: WorkspaceService = Depends(get_workspace_service),
) -> Response:
    await service.delete_workspace(workspace_id)
    return Response(status_code=204)
