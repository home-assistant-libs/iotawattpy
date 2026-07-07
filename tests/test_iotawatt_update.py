"""Tests for Iotawatt.update() against a mocked device."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from iotawattpy.iotawatt import Iotawatt

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

HOST = "192.0.2.1"

STATUS_WIFI = {"wifi": {"mac": "de:ad:be:ef:00:01"}}
STATUS_INPUTS_OUTPUTS = {
    "inputs": [{"channel": 0, "Watts": "123"}],
    "outputs": [],
}
SHOW_SERIES = {"series": [{"name": "Main", "unit": "Watts"}]}

CURRENT_RESULT = [[123.4]]
INTEGRATED_RESULT: list[list[str | float]] = [["2024-09-02T00:00:00", 4567]]


@pytest.fixture
async def websession() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def _mock_device(integrated_result: list[list[str | float]]) -> None:
    """Mock the device HTTP endpoints."""
    respx.get(f"http://{HOST}/status", params={"wifi": "yes"}).respond(json=STATUS_WIFI)
    respx.get(
        f"http://{HOST}/status", params={"inputs": "yes", "outputs": "yes"}
    ).respond(json=STATUS_INPUTS_OUTPUTS)

    def query(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("show") == "series":
            return httpx.Response(200, json=SHOW_SERIES)
        if params["select"].startswith("[time.iso"):
            return httpx.Response(200, json=integrated_result)
        return httpx.Response(200, json=CURRENT_RESULT)

    respx.get(f"http://{HOST}/query").mock(side_effect=query)


@respx.mock
async def test_update(websession: httpx.AsyncClient) -> None:
    """A normal update populates current and integrated sensor values."""
    _mock_device(INTEGRATED_RESULT)
    iotawatt = Iotawatt(
        "test", HOST, websession, integratedInterval="d", includeNonTotalSensors=False
    )

    await iotawatt.update()

    sensors = iotawatt.getSensors()["sensors"]
    assert sensors["input_0"].getValue() == 123.4
    assert sensors["input_0_total_energy"].getValue() == 4567
    assert sensors["input_0_total_energy"].getBegin() == "2024-09-02T00:00:00"


@respx.mock
async def test_update_empty_integrated_result(websession: httpx.AsyncClient) -> None:
    """An empty integrated query result is skipped instead of raising.

    The device returns [] for a zero-length interval, e.g. when queried
    with begin=d within the first seconds after midnight.
    """
    _mock_device([])
    iotawatt = Iotawatt(
        "test", HOST, websession, integratedInterval="d", includeNonTotalSensors=False
    )

    await iotawatt.update()

    sensors = iotawatt.getSensors()["sensors"]
    assert sensors["input_0"].getValue() == 123.4
    assert sensors["input_0_total_energy"].getValue() is None
    assert sensors["input_0_total_energy"].getBegin() is None
