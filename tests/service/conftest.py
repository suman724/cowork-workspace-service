"""Fixtures for DynamoDB Local service tests."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import aioboto3
import pytest

from workspace_service.repositories.dynamo_artifact import DynamoArtifactRepository
from workspace_service.repositories.dynamo_workspace import DynamoWorkspaceRepository

# DynamoDB Local must be running at this endpoint
DYNAMODB_ENDPOINT = "http://localhost:8000"


@pytest.fixture
async def workspace_table() -> AsyncIterator[Any]:
    """Create a temporary DynamoDB workspaces table."""
    table_name = f"test-workspaces-{uuid.uuid4().hex[:8]}"
    session = aioboto3.Session()
    async with session.resource(
        "dynamodb",
        endpoint_url=DYNAMODB_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    ) as dynamodb:
        table = await dynamodb.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "workspaceId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "workspaceId", "AttributeType": "S"},
                {"AttributeName": "tenantId", "AttributeType": "S"},
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "localPathKey", "AttributeType": "S"},
            ],
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
        await table.meta.client.get_waiter("table_exists").wait(TableName=table_name)
        yield table
        await table.delete()


@pytest.fixture
async def artifact_table() -> AsyncIterator[Any]:
    """Create a temporary DynamoDB artifacts table."""
    table_name = f"test-artifacts-{uuid.uuid4().hex[:8]}"
    session = aioboto3.Session()
    async with session.resource(
        "dynamodb",
        endpoint_url=DYNAMODB_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106
    ) as dynamodb:
        table = await dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "workspaceId", "KeyType": "HASH"},
                {"AttributeName": "artifactId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "workspaceId", "AttributeType": "S"},
                {"AttributeName": "artifactId", "AttributeType": "S"},
                {"AttributeName": "sessionId", "AttributeType": "S"},
                {"AttributeName": "artifactType", "AttributeType": "S"},
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
        await table.meta.client.get_waiter("table_exists").wait(TableName=table_name)
        yield table
        await table.delete()


@pytest.fixture
def workspace_repo(workspace_table: Any) -> DynamoWorkspaceRepository:
    return DynamoWorkspaceRepository(workspace_table)


@pytest.fixture
def artifact_repo(artifact_table: Any) -> DynamoArtifactRepository:
    return DynamoArtifactRepository(artifact_table)
