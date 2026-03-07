"""Tests for SessionClient — best-effort session metadata fetching."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from workspace_service.clients.session_client import SessionClient


def _mock_response(status_code: int, json_data: dict | None = None) -> httpx.Response:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


@pytest.mark.unit
class TestSessionClient:
    async def test_get_session_success(self) -> None:
        """Should return session data on 200 response."""
        mock_http = AsyncMock()
        resp_data = {"sessionId": "s-1", "name": "My session", "autoNamed": True}
        mock_http.get = AsyncMock(return_value=_mock_response(200, resp_data))
        client = SessionClient(mock_http)
        result = await client.get_session("s-1")

        assert result["name"] == "My session"
        assert result["autoNamed"] is True
        mock_http.get.assert_called_once_with("/sessions/s-1")

    async def test_get_session_not_found(self) -> None:
        """Should return empty dict on 404 response."""
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_mock_response(404, {"code": "SESSION_NOT_FOUND"}))
        client = SessionClient(mock_http)
        result = await client.get_session("nonexistent")

        assert result == {}

    async def test_get_session_network_error(self) -> None:
        """Should return empty dict on network failure."""
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client = SessionClient(mock_http)
        result = await client.get_session("s-1")

        assert result == {}

    async def test_get_session_server_error(self) -> None:
        """Should return empty dict on 500 response."""
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=_mock_response(500))
        client = SessionClient(mock_http)
        result = await client.get_session("s-1")

        assert result == {}
