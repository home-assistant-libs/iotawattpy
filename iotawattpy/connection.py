"""HTTP connection helper for the IoTaWatt device."""

from __future__ import annotations

import logging

import httpx

LOGGER = logging.getLogger(__name__)


class Connection:
    """Thin async HTTP wrapper around an httpx client."""

    def __init__(self, websession: httpx.AsyncClient, host: str) -> None:
        """Initialize the connection helper."""
        self._host = host
        self._websession = websession

    async def get(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> httpx.Response:
        """Perform a GET request, optionally with digest auth."""
        auth = (
            httpx.DigestAuth(username, password or "") if username is not None else None
        )
        LOGGER.debug("URL: %s", url)
        try:
            return await self._websession.get(url, auth=auth)
        except httpx.HTTPError:
            LOGGER.debug("HTTP error while requesting %s", url, exc_info=True)
            raise
