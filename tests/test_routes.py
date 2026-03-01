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

    async def test_create_missing_tenant_id(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"userId": "u1", "workspaceScope": "general"},
        )
        assert resp.status_code == 422

    async def test_create_empty_workspace_scope(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": ""},
        )
        assert resp.status_code == 422

    async def test_delete_workspace(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = create_resp.json()["workspaceId"]
        resp = await client.delete(f"/workspaces/{ws_id}")
        assert resp.status_code == 204

    async def test_list_workspace_sessions(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        content = base64.b64encode(b"data").decode()
        for sess_id in ["sess-1", "sess-2"]:
            await client.post(
                f"/workspaces/{ws_id}/artifacts",
                json={
                    "sessionId": sess_id,
                    "artifactType": "tool_output",
                    "contentBase64": content,
                },
            )

        resp = await client.get(f"/workspaces/{ws_id}/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "sessions" in body
        assert len(body["sessions"]) == 2
        assert all("sessionId" in s for s in body["sessions"])
        assert all("createdAt" in s for s in body["sessions"])
        assert all("lastTaskAt" in s for s in body["sessions"])
        assert all("taskCount" in s for s in body["sessions"])

    async def test_list_workspace_sessions_pagination(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        content = base64.b64encode(b"data").decode()
        for i in range(3):
            await client.post(
                f"/workspaces/{ws_id}/artifacts",
                json={
                    "sessionId": f"sess-{i}",
                    "artifactType": "tool_output",
                    "contentBase64": content,
                },
            )

        # First page
        resp1 = await client.get(f"/workspaces/{ws_id}/sessions", params={"limit": 2})
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert len(body1["sessions"]) == 2
        assert "nextToken" in body1

        # Second page using nextToken
        resp2 = await client.get(
            f"/workspaces/{ws_id}/sessions",
            params={"limit": 2, "nextToken": body1["nextToken"]},
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["sessions"]) == 1
        assert "nextToken" not in body2

    async def test_list_workspace_sessions_not_found(self, client: AsyncClient) -> None:
        resp = await client.get("/workspaces/nonexistent/sessions")
        assert resp.status_code == 404

    async def test_get_session_history(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        # Upload a session_history artifact
        messages = [
            {
                "role": "user",
                "content": "Hello",
                "messageId": "m1",
                "sessionId": "s1",
                "taskId": "t1",
                "timestamp": "2026-03-01T00:00:00Z",
            },
            {
                "role": "assistant",
                "content": "Hi there",
                "messageId": "m2",
                "sessionId": "s1",
                "taskId": "t1",
                "timestamp": "2026-03-01T00:00:01Z",
            },
        ]
        upload_resp = await client.post(
            f"/workspaces/{ws_id}/artifacts",
            json={
                "sessionId": "sess-1",
                "artifactType": "session_history",
                "messages": messages,
            },
        )
        assert upload_resp.status_code == 201

        # Retrieve history via convenience endpoint
        resp = await client.get(f"/workspaces/{ws_id}/sessions/sess-1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["role"] == "user"
        assert data[0]["content"] == "Hello"
        assert data[1]["role"] == "assistant"
        assert data[1]["content"] == "Hi there"

    async def test_get_session_history_empty(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]

        # No history uploaded — should return empty list
        resp = await client.get(f"/workspaces/{ws_id}/sessions/sess-none/history")
        assert resp.status_code == 200
        assert resp.json() == []


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

    async def test_upload_missing_session_id(self, client: AsyncClient) -> None:
        ws_resp = await client.post(
            "/workspaces",
            json={"tenantId": "t1", "userId": "u1", "workspaceScope": "general"},
        )
        ws_id = ws_resp.json()["workspaceId"]
        resp = await client.post(
            f"/workspaces/{ws_id}/artifacts",
            json={"artifactType": "tool_output", "contentBase64": "dGVzdA=="},
        )
        assert resp.status_code == 422

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
