"""HTTP client for the Session Service — fetches session metadata for enrichment."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class SessionClient:
    """Lightweight client to fetch session details from the Session Service.

    Used to enrich workspace session summaries with human-readable names.
    All methods are best-effort — failures are logged and return defaults.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch session details from GET /sessions/{id}.

        Returns the response JSON dict on success, or an empty dict on failure.
        """
        try:
            response = await self._client.get(f"/sessions/{session_id}")
            if response.status_code == 200:
                return response.json()  # type: ignore[no-any-return]
        except Exception:
            logger.warning(
                "session_client.get_session_failed",
                session_id=session_id,
                exc_info=True,
            )
        return {}

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
