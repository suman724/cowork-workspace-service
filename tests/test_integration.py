"""Integration tests for workspace service against LocalStack DynamoDB + S3.

Requires: LocalStack running on http://localhost:4566 (make run-infra from project root).
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import aioboto3
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from workspace_service.config import Settings
from workspace_service.dependencies import get_artifact_service, get_workspace_service
from workspace_service.exceptions import ServiceError
from workspace_service.repositories.dynamo_artifact import DynamoArtifactRepository
from workspace_service.repositories.dynamo_workspace import DynamoWorkspaceRepository
from workspace_service.repositories.s3_store import S3ArtifactStore
from workspace_service.routes import artifacts, health, workspaces
from workspace_service.services.artifact_service import ArtifactService
from workspace_service.services.workspace_service import WorkspaceService

LOCALSTACK_URL = "http://localhost:4566"
AWS_REGION = "us-east-1"
BOTO_KWARGS = {
    "region_name": AWS_REGION,
    "endpoint_url": LOCALSTACK_URL,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}


def _create_workspace_request(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tenantId": "t1",
        "userId": "u1",
        "workspaceScope": "general",
    }
    base.update(overrides)
    return base


def _upload_artifact_request(**overrides: Any) -> dict[str, Any]:
    content = overrides.pop("raw_content", b"hello world")
    base: dict[str, Any] = {
        "sessionId": "sess-1",
        "artifactType": "tool_output",
        "artifactName": "output.txt",
        "contentType": "text/plain",
        "contentBase64": base64.b64encode(content).decode(),
    }
    base.update(overrides)
    return base


@pytest.fixture
async def integration_client() -> AsyncIterator[AsyncClient]:
    """Create DynamoDB tables + S3 bucket, wire into app, yield HTTP client, tear down."""
    suffix = uuid.uuid4().hex[:8]
    ws_table_name = f"test-workspaces-{suffix}"
    art_table_name = f"test-artifacts-{suffix}"
    bucket_name = f"test-artifacts-{suffix}"

    boto_session = aioboto3.Session()
    async with (
        boto_session.resource("dynamodb", **BOTO_KWARGS) as dynamodb,
        boto_session.client("s3", **BOTO_KWARGS) as s3_client,
    ):
        # Create workspaces table
        ws_table = await dynamodb.create_table(
            TableName=ws_table_name,
            AttributeDefinitions=[
                {"AttributeName": "workspaceId", "AttributeType": "S"},
                {"AttributeName": "tenantId", "AttributeType": "S"},
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "localPathKey", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "workspaceId", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "tenantId-userId-index",
                    "KeySchema": [
                        {"AttributeName": "tenantId", "KeyType": "HASH"},
                        {"AttributeName": "userId", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "localpath-lookup-index",
                    "KeySchema": [
                        {"AttributeName": "localPathKey", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        await ws_table.wait_until_exists()

        # Create artifacts table
        art_table = await dynamodb.create_table(
            TableName=art_table_name,
            AttributeDefinitions=[
                {"AttributeName": "workspaceId", "AttributeType": "S"},
                {"AttributeName": "artifactId", "AttributeType": "S"},
                {"AttributeName": "sessionId", "AttributeType": "S"},
                {"AttributeName": "artifactType", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "workspaceId", "KeyType": "HASH"},
                {"AttributeName": "artifactId", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "sessionId-type-index",
                    "KeySchema": [
                        {"AttributeName": "sessionId", "KeyType": "HASH"},
                        {"AttributeName": "artifactType", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        await art_table.wait_until_exists()

        # Create S3 bucket
        await s3_client.create_bucket(Bucket=bucket_name)

        # Wire up services
        settings = Settings(
            env="test",
            aws_endpoint_url=LOCALSTACK_URL,
            aws_region=AWS_REGION,
            max_artifact_size_bytes=1048576,
        )
        workspace_repo = DynamoWorkspaceRepository(ws_table)
        artifact_repo = DynamoArtifactRepository(art_table)
        artifact_store = S3ArtifactStore(s3_client, bucket_name)

        ws_service = WorkspaceService(workspace_repo, artifact_repo, artifact_store)
        art_service = ArtifactService(workspace_repo, artifact_repo, artifact_store, settings)

        async def _service_error_handler(request: Request, exc: Exception) -> JSONResponse:
            se = (
                exc
                if isinstance(exc, ServiceError)
                else ServiceError("Unknown", code="INTERNAL_ERROR", status_code=500)
            )
            return JSONResponse(
                status_code=se.status_code,
                content={
                    "code": se.code,
                    "message": se.message,
                    "retryable": se.status_code >= 500,
                },
            )

        app = FastAPI()
        app.include_router(health.router)
        app.include_router(workspaces.router)
        app.include_router(artifacts.router)
        app.add_exception_handler(ServiceError, _service_error_handler)

        app.dependency_overrides[get_workspace_service] = lambda: ws_service
        app.dependency_overrides[get_artifact_service] = lambda: art_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

        # Teardown
        await ws_table.delete()
        await art_table.delete()
        # Empty and delete S3 bucket
        paginator = s3_client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                await s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
        await s3_client.delete_bucket(Bucket=bucket_name)


@pytest.mark.integration
class TestWorkspaceIntegration:
    async def test_create_workspace_general(self, integration_client: AsyncClient) -> None:
        resp = await integration_client.post(
            "/workspaces", json=_create_workspace_request()
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "workspaceId" in body
        assert body["workspaceScope"] == "general"
        assert "createdAt" in body

    async def test_create_workspace_local_idempotent(
        self, integration_client: AsyncClient
    ) -> None:
        unique_path = f"/projects/test-{uuid.uuid4().hex[:8]}"
        req = _create_workspace_request(workspaceScope="local", localPath=unique_path)

        resp1 = await integration_client.post("/workspaces", json=req)
        assert resp1.status_code == 201
        ws_id_1 = resp1.json()["workspaceId"]

        resp2 = await integration_client.post("/workspaces", json=req)
        assert resp2.status_code == 201
        ws_id_2 = resp2.json()["workspaceId"]

        assert ws_id_1 == ws_id_2

    async def test_get_workspace(self, integration_client: AsyncClient) -> None:
        create_resp = await integration_client.post(
            "/workspaces", json=_create_workspace_request()
        )
        ws_id = create_resp.json()["workspaceId"]

        resp = await integration_client.get(f"/workspaces/{ws_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["workspaceId"] == ws_id
        assert body["tenantId"] == "t1"
        assert body["userId"] == "u1"
        assert body["workspaceScope"] == "general"

    async def test_get_workspace_not_found(self, integration_client: AsyncClient) -> None:
        resp = await integration_client.get("/workspaces/nonexistent-id")
        assert resp.status_code == 404

    async def test_list_workspaces(self, integration_client: AsyncClient) -> None:
        unique_tenant = f"tenant-{uuid.uuid4().hex[:8]}"
        unique_user = f"user-{uuid.uuid4().hex[:8]}"

        for _ in range(3):
            await integration_client.post(
                "/workspaces",
                json=_create_workspace_request(tenantId=unique_tenant, userId=unique_user),
            )

        resp = await integration_client.get(
            "/workspaces", params={"tenantId": unique_tenant, "userId": unique_user}
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3
        assert all(ws["tenantId"] == unique_tenant for ws in items)

    async def test_delete_workspace(self, integration_client: AsyncClient) -> None:
        create_resp = await integration_client.post(
            "/workspaces", json=_create_workspace_request()
        )
        ws_id = create_resp.json()["workspaceId"]

        resp = await integration_client.delete(f"/workspaces/{ws_id}")
        assert resp.status_code == 204

        get_resp = await integration_client.get(f"/workspaces/{ws_id}")
        assert get_resp.status_code == 404


@pytest.mark.integration
class TestArtifactIntegration:
    async def _create_workspace(self, client: AsyncClient) -> str:
        resp = await client.post("/workspaces", json=_create_workspace_request())
        return resp.json()["workspaceId"]

    async def test_upload_and_download_artifact(
        self, integration_client: AsyncClient
    ) -> None:
        ws_id = await self._create_workspace(integration_client)
        content = b"integration test content"

        upload_resp = await integration_client.post(
            f"/workspaces/{ws_id}/artifacts",
            json=_upload_artifact_request(raw_content=content),
        )
        assert upload_resp.status_code == 201
        body = upload_resp.json()
        assert "artifactId" in body

        artifact_id = body["artifactId"]
        download_resp = await integration_client.get(
            f"/workspaces/{ws_id}/artifacts/{artifact_id}"
        )
        assert download_resp.status_code == 200
        assert download_resp.content == content

    async def test_upload_session_history(self, integration_client: AsyncClient) -> None:
        ws_id = await self._create_workspace(integration_client)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        upload_resp = await integration_client.post(
            f"/workspaces/{ws_id}/artifacts",
            json={
                "sessionId": "sess-hist-1",
                "artifactType": "session_history",
                "messages": messages,
            },
        )
        assert upload_resp.status_code == 201
        artifact_id = upload_resp.json()["artifactId"]

        download_resp = await integration_client.get(
            f"/workspaces/{ws_id}/artifacts/{artifact_id}"
        )
        assert download_resp.status_code == 200
        downloaded = json.loads(download_resp.content)
        assert downloaded == messages

    async def test_list_artifacts(self, integration_client: AsyncClient) -> None:
        ws_id = await self._create_workspace(integration_client)

        for i in range(3):
            await integration_client.post(
                f"/workspaces/{ws_id}/artifacts",
                json=_upload_artifact_request(
                    artifactName=f"file-{i}.txt",
                    raw_content=f"content {i}".encode(),
                ),
            )

        resp = await integration_client.get(f"/workspaces/{ws_id}/artifacts")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3

    async def test_delete_workspace_cascades_artifacts(
        self, integration_client: AsyncClient
    ) -> None:
        ws_id = await self._create_workspace(integration_client)

        for i in range(2):
            await integration_client.post(
                f"/workspaces/{ws_id}/artifacts",
                json=_upload_artifact_request(
                    artifactName=f"cascade-{i}.txt",
                    raw_content=f"cascade {i}".encode(),
                ),
            )

        resp = await integration_client.delete(f"/workspaces/{ws_id}")
        assert resp.status_code == 204

        get_resp = await integration_client.get(f"/workspaces/{ws_id}")
        assert get_resp.status_code == 404
