"""Standalone CLI example for exercising the iotawattpy library."""

from __future__ import annotations

import argparse
import asyncio
import logging

import httpx

from iotawattpy.iotawatt import Iotawatt

logging.basicConfig(level="DEBUG")
LOGGER = logging.getLogger(__name__)


class Tester:
    def __init__(
        self, ip_addr: str, username: str | None, password: str | None
    ) -> None:
        self._ip_addr = ip_addr
        self._username = username
        self._password = password

    async def run(self) -> None:
        async with httpx.AsyncClient() as session:
            iotawatt = Iotawatt(
                "iotawatt",
                self._ip_addr,
                session,
                self._username,
                self._password,
            )
            try:
                await iotawatt.connect()
            except httpx.HTTPStatusError:
                LOGGER.exception("Connect failed")
                return

            while True:
                LOGGER.info("=" * 45)
                await iotawatt.update()
                LOGGER.info("=" * 45)
                await asyncio.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IoTaWatt tester")
    parser.add_argument("ip_address", help="IP address of the IoTaWatt")
    parser.add_argument("-u", "--username", default=None)
    parser.add_argument("-p", "--password", default=None)
    args = parser.parse_args()

    LOGGER.info("Started")
    asyncio.run(Tester(args.ip_address, args.username, args.password).run())


if __name__ == "__main__":
    main()
