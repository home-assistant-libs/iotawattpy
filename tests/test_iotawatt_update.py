"""Tests for Iotawatt.update() against a mocked device."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
STATUS_DATALOGS = {
    "datalogs": [
        {"id": "Current", "firstkey": 1750000000, "lastkey": 1751000000},
        {"id": "History", "firstkey": 1600000000, "lastkey": 1751000000},
    ]
}
SHOW_SERIES = {"series": [{"name": "Main", "unit": "Watts"}]}

CURRENT_RESULT = [[123.4]]
INTEGRATED_RESULT: list[list[str | float]] = [["2024-09-02T00:00:00", 4567]]
LIFETIME_RESULT: list[list[str | float]] = [["2020-09-13T14:26:40", 12345678.912]]


@pytest.fixture
async def websession() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def _mock_device(
    integrated_result: list[list[str | float]],
    datalogs: dict[str, Any] = STATUS_DATALOGS,
) -> list[dict[str, str]]:
    """Mock the device HTTP endpoints.

    Returns a list capturing the parameters of every integrated
    (time.iso) query the library performs.
    """
    respx.get(f"http://{HOST}/status", params={"wifi": "yes"}).respond(json=STATUS_WIFI)
    respx.get(
        f"http://{HOST}/status", params={"inputs": "yes", "outputs": "yes"}
    ).respond(json=STATUS_INPUTS_OUTPUTS)
    respx.get(f"http://{HOST}/status", params={"datalogs": "yes"}).respond(
        json=datalogs
    )

    integrated_queries: list[dict[str, str]] = []

    def query(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if params.get("show") == "series":
            return httpx.Response(200, json=SHOW_SERIES)
        if params["select"].startswith("[time.iso"):
            integrated_queries.append(dict(params))
            if params["begin"] == "d":
                return httpx.Response(200, json=integrated_result)
            return httpx.Response(200, json=LIFETIME_RESULT)
        return httpx.Response(200, json=CURRENT_RESULT)

    respx.get(f"http://{HOST}/query").mock(side_effect=query)
    return integrated_queries


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
    assert "input_0_lifetime_energy" not in sensors


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


@respx.mock
async def test_update_lifetime_sensors(websession: httpx.AsyncClient) -> None:
    """Lifetime sensors integrate since the datalog start."""
    integrated_queries = _mock_device(INTEGRATED_RESULT)
    iotawatt = Iotawatt(
        "test",
        HOST,
        websession,
        integratedInterval="d",
        includeNonTotalSensors=False,
        includeLifetimeSensors=True,
    )

    await iotawatt.update()

    sensors = iotawatt.getSensors()["sensors"]
    sensor = sensors["input_0_lifetime_energy"]
    assert sensor.getName() == "Main.wh_lifetime"
    assert sensor.getLifetime() is True
    assert sensor.getValue() == 12345678.912
    assert sensor.getBegin() == "2020-09-13T14:26:40"
    assert sensors["input_0_total_energy"].getValue() == 4567

    lifetime_query = next(q for q in integrated_queries if q["begin"] != "d")
    assert lifetime_query["begin"] == "1600000000"
    assert "Main.wh.d3" in lifetime_query["select"]


@respx.mock
async def test_update_lifetime_datalog_start_cached(
    websession: httpx.AsyncClient,
) -> None:
    """The datalog start is only fetched once across updates."""
    _mock_device(INTEGRATED_RESULT)
    iotawatt = Iotawatt(
        "test",
        HOST,
        websession,
        integratedInterval="d",
        includeNonTotalSensors=False,
        includeLifetimeSensors=True,
    )

    await iotawatt.update()
    await iotawatt.update()

    datalogs_route = respx.get(f"http://{HOST}/status", params={"datalogs": "yes"})
    assert datalogs_route.call_count == 1


@pytest.mark.parametrize(
    ("datalogs", "expected_begin"),
    [
        pytest.param(STATUS_DATALOGS, "1600000000", id="prefer-history"),
        pytest.param(
            {
                "datalogs": [
                    {"id": "Current", "firstkey": 1750000000},
                    {"id": "History", "firstkey": 0},
                ]
            },
            "1750000000",
            id="empty-history",
        ),
        pytest.param(
            {"datalogs": [{"id": "Current", "firstkey": 999999999}]},
            "2000-01-01",
            id="clock-not-set",
        ),
        pytest.param({"datalogs": []}, "2000-01-01", id="no-datalogs"),
    ],
)
@respx.mock
async def test_update_lifetime_begin_selection(
    websession: httpx.AsyncClient,
    datalogs: dict[str, Any],
    expected_begin: str,
) -> None:
    """The lifetime query begin is derived from the datalog status."""
    integrated_queries = _mock_device(INTEGRATED_RESULT, datalogs=datalogs)
    iotawatt = Iotawatt(
        "test",
        HOST,
        websession,
        integratedInterval="d",
        includeNonTotalSensors=False,
        includeLifetimeSensors=True,
    )

    await iotawatt.update()

    lifetime_query = next(q for q in integrated_queries if q["begin"] != "d")
    assert lifetime_query["begin"] == expected_begin
