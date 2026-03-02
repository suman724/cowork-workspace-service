"""Service-tier tests for DynamoDB artifact repository.

Requires: docker run -p 8000:8000 amazon/dynamodb-local
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from workspace_service.models.domain import ArtifactDomain
from workspace_service.repositories.dynamo_artifact import DynamoArtifactRepository


def _make_artifact(
    artifact_id: str = "art-1",
    workspace_id: str = "ws-1",
    session_id: str = "sess-1",
    artifact_type: str = "session_history",
    **overrides: object,
) -> ArtifactDomain:
    now = datetime.now(UTC)
    defaults = {
        "artifact_id": artifact_id,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "artifact_type": artifact_type,
        "created_at": now,
    }
    defaults.update(overrides)
    return ArtifactDomain(**defaults)  # type: ignore[arg-type]


@pytest.mark.service
@pytest.mark.asyncio
class TestArtifactRepoCRUD:
    async def test_create_and_get_artifact(self, artifact_repo: DynamoArtifactRepository) -> None:
        """Create an artifact and retrieve it by composite key."""
        art = _make_artifact(
            s3_key="ws-1/art-1",
            artifact_name="session_history.json",
            content_type="application/json",
            size_bytes=1024,
        )
        await artifact_repo.create(art)

        result = await artifact_repo.get("ws-1", "art-1")
        assert result is not None
        assert result.artifact_id == "art-1"
        assert result.workspace_id == "ws-1"
        assert result.session_id == "sess-1"
        assert result.artifact_type == "session_history"
        assert result.s3_key == "ws-1/art-1"

    async def test_get_nonexistent_returns_none(
        self, artifact_repo: DynamoArtifactRepository
    ) -> None:
        """Getting a non-existent artifact returns None."""
        result = await artifact_repo.get("ws-1", "nonexistent")
        assert result is None

    async def test_delete_artifact(self, artifact_repo: DynamoArtifactRepository) -> None:
        """Delete an artifact."""
        art = _make_artifact()
        await artifact_repo.create(art)
        await artifact_repo.delete("ws-1", "art-1")

        result = await artifact_repo.get("ws-1", "art-1")
        assert result is None


@pytest.mark.service
@pytest.mark.asyncio
class TestArtifactRepoGSI:
    async def test_list_by_session_and_type(self, artifact_repo: DynamoArtifactRepository) -> None:
        """List artifacts for a session via GSI."""
        # Create 2 artifacts for the same session
        art1 = _make_artifact(artifact_id="art-1", artifact_type="session_history")
        art2 = _make_artifact(artifact_id="art-2", artifact_type="tool_output")
        await artifact_repo.create(art1)
        await artifact_repo.create(art2)

        # Different session — should not appear
        other = _make_artifact(artifact_id="art-other", session_id="sess-2")
        await artifact_repo.create(other)

        results = await artifact_repo.list_by_session("ws-1", "sess-1")
        assert len(results) == 2
        art_ids = {a.artifact_id for a in results}
        assert art_ids == {"art-1", "art-2"}

    async def test_list_by_workspace(self, artifact_repo: DynamoArtifactRepository) -> None:
        """List all artifacts for a workspace."""
        art1 = _make_artifact(artifact_id="art-1")
        art2 = _make_artifact(artifact_id="art-2", session_id="sess-2")
        await artifact_repo.create(art1)
        await artifact_repo.create(art2)

        results = await artifact_repo.list_by_workspace("ws-1")
        assert len(results) == 2

    async def test_delete_by_workspace(self, artifact_repo: DynamoArtifactRepository) -> None:
        """Delete all artifacts for a workspace."""
        art1 = _make_artifact(artifact_id="art-1")
        art2 = _make_artifact(artifact_id="art-2")
        await artifact_repo.create(art1)
        await artifact_repo.create(art2)

        await artifact_repo.delete_by_workspace("ws-1")

        results = await artifact_repo.list_by_workspace("ws-1")
        assert len(results) == 0
