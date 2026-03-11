"""Workspace file CRUD endpoints for cloud-scoped workspaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response

from workspace_service.dependencies import get_file_service
from workspace_service.exceptions import ArtifactTooLargeError
from workspace_service.services.file_service import WorkspaceFileService

router = APIRouter(prefix="/workspaces/{workspace_id}/files", tags=["files"])


@router.post("", status_code=201)
async def upload_file(
    workspace_id: str,
    file: UploadFile,
    path: str,
    service: WorkspaceFileService = Depends(get_file_service),
) -> dict[str, Any]:
    # Stream the upload with early-exit size check to avoid loading
    # arbitrarily large files into memory before rejecting them.
    max_size = service._settings.max_artifact_size_bytes
    chunk_size = 256 * 1024  # 256 KB chunks
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise ArtifactTooLargeError(total, max_size)
        chunks.append(chunk)
    content = b"".join(chunks)
    content_type = file.content_type or "application/octet-stream"
    result = await service.upload_file(workspace_id, path, content, content_type)
    return result


@router.get("")
async def list_files(
    workspace_id: str,
    service: WorkspaceFileService = Depends(get_file_service),
) -> list[dict[str, Any]]:
    return await service.list_files(workspace_id)


@router.get("/{file_path:path}")
async def download_file(
    workspace_id: str,
    file_path: str,
    service: WorkspaceFileService = Depends(get_file_service),
) -> Response:
    content, content_type = await service.download_file(workspace_id, file_path)
    return Response(content=content, media_type=content_type)


@router.delete("/{file_path:path}", status_code=204)
async def delete_file(
    workspace_id: str,
    file_path: str,
    service: WorkspaceFileService = Depends(get_file_service),
) -> Response:
    await service.delete_file(workspace_id, file_path)
    return Response(status_code=204)
