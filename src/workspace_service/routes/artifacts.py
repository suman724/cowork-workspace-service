"""Artifact upload/download endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from workspace_service.dependencies import get_artifact_service
from workspace_service.models.requests import UploadArtifactRequest
from workspace_service.services.artifact_service import ArtifactService

router = APIRouter(prefix="/workspaces/{workspace_id}/artifacts", tags=["artifacts"])


@router.post("", status_code=201)
async def upload_artifact(
    workspace_id: str,
    body: UploadArtifactRequest,
    service: ArtifactService = Depends(get_artifact_service),
) -> dict[str, Any]:
    artifact = await service.upload_artifact(
        workspace_id=workspace_id,
        session_id=body.session_id,
        task_id=body.task_id,
        step_id=body.step_id,
        artifact_type=body.artifact_type,
        artifact_name=body.artifact_name,
        content_type=body.content_type,
        content_base64=body.content_base64,
        messages=body.messages,
    )
    return {
        "artifactId": artifact.artifact_id,
        "artifactUri": f"s3://{artifact.s3_key}",
    }


@router.get("/{artifact_id}")
async def download_artifact(
    workspace_id: str,
    artifact_id: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> Response:
    content, content_type = await service.download_artifact(workspace_id, artifact_id)
    return Response(content=content, media_type=content_type)


@router.get("")
async def list_artifacts(
    workspace_id: str,
    service: ArtifactService = Depends(get_artifact_service),
) -> list[dict[str, Any]]:
    artifacts = await service.list_artifacts(workspace_id)
    return [
        {
            "artifactId": a.artifact_id,
            "workspaceId": a.workspace_id,
            "sessionId": a.session_id,
            "artifactType": a.artifact_type,
            "artifactName": a.artifact_name,
            "contentType": a.content_type,
            "sizeBytes": a.size_bytes,
            "createdAt": a.created_at.isoformat(),
        }
        for a in artifacts
    ]
