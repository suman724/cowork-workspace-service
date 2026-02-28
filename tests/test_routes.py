"""Tests for HTTP endpoints."""

from __future__ import annotations

import base64

import pytest
from httpx import AsyncClient


@pytest.mark.unit
class TestHealthRoutes:
    async def test_health(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_ready(self, client: AsyncClient) -> None:
        resp = await client.get("/ready")
        assert resp.status_code == 200


@pytest.mark.unit
class TestWorkspaceRoutes:
    async def test_create_workspace(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "workspaceId" in data
        assert data["workspaceScope"] == "general"

    async def test_list_workspaces(self, client: AsyncClient) -> None:
        await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        resp = await client.get("/workspaces", params={"tenantId": "t1", "userId": "u1"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_workspace(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = create_resp.json()["workspaceId"]
        resp = await client.get(f"/workspaces/{ws_id}")
        assert resp.status_code == 200
        assert resp.json()["workspaceId"] == ws_id

    async def test_delete_workspace(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = create_resp.json()["workspaceId"]
        resp = await client.delete(f"/workspaces/{ws_id}")
        assert resp.status_code == 204


@pytest.mark.unit
class TestArtifactRoutes:
    async def test_upload_and_download(self, client: AsyncClient) -> None:
        # Create workspace first
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        # Upload
        content = base64.b64encode(b"test content").decode()
        upload_resp = await client.post(
            f"/workspaces/{ws_id}/artifacts",
            json={
                "sessionId": "sess-1",
                "artifactType": "tool_output",
                "artifactName": "output.txt",
                "contentType": "text/plain",
                "contentBase64": content,
            },
        )
        assert upload_resp.status_code == 201
        artifact_id = upload_resp.json()["artifactId"]

        # Download
        dl_resp = await client.get(f"/workspaces/{ws_id}/artifacts/{artifact_id}")
        assert dl_resp.status_code == 200
        assert dl_resp.content == b"test content"

    async def test_list_artifacts(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        content = base64.b64encode(b"data").decode()
        await client.post(
            f"/workspaces/{ws_id}/artifacts",
            json={
                "sessionId": "sess-1",
                "artifactType": "tool_output",
                "contentBase64": content,
            },
        )

        resp = await client.get(f"/workspaces/{ws_id}/artifacts")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
