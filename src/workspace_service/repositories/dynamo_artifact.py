"""DynamoDB artifact metadata repository.

Table: {env}-artifacts
  PK: workspaceId
  SK: artifactId
  GSI: sessionId-type-index (PK=sessionId, SK=artifactType)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from workspace_service.models.domain import ArtifactDomain


class DynamoArtifactRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def create(self, artifact: ArtifactDomain) -> None:
        item = _to_item(artifact)
        await self._table.put_item(Item=item)

    async def get(self, workspace_id: str, artifact_id: str) -> ArtifactDomain | None:
        resp = await self._table.get_item(
            Key={"workspaceId": workspace_id, "artifactId": artifact_id}
        )
        item = resp.get("Item")
        return _from_item(item) if item else None

    async def list_by_workspace(self, workspace_id: str) -> list[ArtifactDomain]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": "workspaceId = :wid",
            "ExpressionAttributeValues": {":wid": workspace_id},
        }
        while True:
            resp = await self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return [_from_item(item) for item in items]

    async def list_by_session(self, workspace_id: str, session_id: str) -> list[ArtifactDomain]:
        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {
            "IndexName": "sessionId-type-index",
            "KeyConditionExpression": "sessionId = :sid",
            "ExpressionAttributeValues": {":sid": session_id},
        }
        while True:
            resp = await self._table.query(**kwargs)
            items.extend(
                item for item in resp.get("Items", []) if item.get("workspaceId") == workspace_id
            )
            last_key = resp.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
        return [_from_item(item) for item in items]

    async def delete(self, workspace_id: str, artifact_id: str) -> None:
        await self._table.delete_item(Key={"workspaceId": workspace_id, "artifactId": artifact_id})

    async def delete_by_workspace(self, workspace_id: str) -> None:
        items = await self.list_by_workspace(workspace_id)
        for artifact in items:
            await self.delete(workspace_id, artifact.artifact_id)


def _to_item(a: ArtifactDomain) -> dict[str, Any]:
    item: dict[str, Any] = {
        "workspaceId": a.workspace_id,
        "artifactId": a.artifact_id,
        "sessionId": a.session_id,
        "artifactType": a.artifact_type,
        "createdAt": a.created_at.isoformat(),
        "updatedAt": (a.updated_at or a.created_at).isoformat(),
    }
    if a.task_id is not None:
        item["taskId"] = a.task_id
    if a.step_id is not None:
        item["stepId"] = a.step_id
    if a.artifact_name is not None:
        item["artifactName"] = a.artifact_name
    if a.content_type is not None:
        item["contentType"] = a.content_type
    if a.s3_key is not None:
        item["s3Key"] = a.s3_key
    if a.size_bytes is not None:
        item["sizeBytes"] = a.size_bytes
    return item


def _from_item(item: dict[str, Any]) -> ArtifactDomain:
    return ArtifactDomain(
        artifact_id=item["artifactId"],
        workspace_id=item["workspaceId"],
        session_id=item["sessionId"],
        task_id=item.get("taskId"),
        step_id=item.get("stepId"),
        artifact_type=item["artifactType"],
        artifact_name=item.get("artifactName"),
        content_type=item.get("contentType"),
        s3_key=item.get("s3Key"),
        size_bytes=item.get("sizeBytes"),
        created_at=datetime.fromisoformat(item["createdAt"]),
        updated_at=datetime.fromisoformat(item["updatedAt"]) if item.get("updatedAt") else None,
    )
