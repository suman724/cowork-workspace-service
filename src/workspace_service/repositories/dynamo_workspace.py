"""DynamoDB workspace repository.

Table: {env}-workspaces
  PK: workspaceId
  GSI: tenantId-userId-index (PK=tenantId, SK=userId)
  GSI: localpath-lookup-index (PK=localPathKey)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from workspace_service.models.domain import WorkspaceDomain


class DynamoWorkspaceRepository:
    def __init__(self, table: Any) -> None:
        self._table = table

    async def create(self, workspace: WorkspaceDomain) -> None:
        item = _to_item(workspace)
        await self._table.put_item(Item=item)

    async def get(self, workspace_id: str) -> WorkspaceDomain | None:
        resp = await self._table.get_item(Key={"workspaceId": workspace_id})
        item = resp.get("Item")
        return _from_item(item) if item else None

    async def get_by_local_path_key(self, local_path_key: str) -> WorkspaceDomain | None:
        resp = await self._table.query(
            IndexName="localpath-lookup-index",
            KeyConditionExpression="localPathKey = :lpk",
            ExpressionAttributeValues={":lpk": local_path_key},
            Limit=1,
        )
        items = resp.get("Items", [])
        return _from_item(items[0]) if items else None

    async def list_by_tenant_user(self, tenant_id: str, user_id: str) -> list[WorkspaceDomain]:
        resp = await self._table.query(
            IndexName="tenantId-userId-index",
            KeyConditionExpression="tenantId = :tid AND userId = :uid",
            ExpressionAttributeValues={":tid": tenant_id, ":uid": user_id},
        )
        return [_from_item(item) for item in resp.get("Items", [])]

    async def update_last_active(self, workspace_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._table.update_item(
            Key={"workspaceId": workspace_id},
            UpdateExpression="SET lastActiveAt = :la, updatedAt = :ua",
            ExpressionAttributeValues={":la": now, ":ua": now},
        )

    async def delete(self, workspace_id: str) -> None:
        await self._table.delete_item(Key={"workspaceId": workspace_id})


def _to_item(ws: WorkspaceDomain) -> dict[str, Any]:
    item: dict[str, Any] = {
        "workspaceId": ws.workspace_id,
        "workspaceScope": ws.workspace_scope,
        "tenantId": ws.tenant_id,
        "userId": ws.user_id,
        "createdAt": ws.created_at.isoformat(),
        "lastActiveAt": ws.last_active_at.isoformat(),
        "updatedAt": (ws.updated_at or ws.created_at).isoformat(),
    }
    if ws.local_path is not None:
        item["localPath"] = ws.local_path
    if ws.local_path_key is not None:
        item["localPathKey"] = ws.local_path_key
    if ws.ttl is not None:
        item["ttl"] = ws.ttl
    return item


def _from_item(item: dict[str, Any]) -> WorkspaceDomain:
    return WorkspaceDomain(
        workspace_id=item["workspaceId"],
        workspace_scope=item["workspaceScope"],
        tenant_id=item["tenantId"],
        user_id=item["userId"],
        local_path=item.get("localPath"),
        local_path_key=item.get("localPathKey"),
        created_at=datetime.fromisoformat(item["createdAt"]),
        last_active_at=datetime.fromisoformat(item["lastActiveAt"]),
        updated_at=datetime.fromisoformat(item["updatedAt"]) if item.get("updatedAt") else None,
        ttl=item.get("ttl"),
    )
