"""HTTP connection helper for the IoTaWatt device."""

from __future__ import annotations

import logging
from typing import Any

import httpx

GET = "get"
POST = "post"

LOGGER = logging.getLogger(__name__)


class Connection:
    """Thin async HTTP wrapper around an httpx client."""

    def __init__(self, websession: httpx.AsyncClient, host: str) -> None:
        """Initialize the connection helper."""
        self._host = host
        self._series: list[Any] = []
        self._websession = websession

    async def get(
        self,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> httpx.Response:
        """Perform a GET request, optionally with digest auth."""
        return await self.__open(url, username=username, password=password)

    async def __open(
        self,
        url: str,
        method: str = GET,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        auth: httpx.Auth | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> httpx.Response:
        """Perform the underlying HTTP request."""
        if username is not None and password is not None:
            auth = httpx.DigestAuth(username, password)

        LOGGER.debug("URL: %s", url)
        try:
            response: httpx.Response = await getattr(self._websession, method)(
                url, headers=headers, params=params, auth=auth
            )
        except httpx.HTTPError:
            LOGGER.debug("HTTP error while requesting %s", url)
            raise
        return response
