"""Tests for the Sensor data class getters and setters."""

from __future__ import annotations

import pytest

from iotawattpy.sensor import Sensor


@pytest.fixture(scope="session")
def sensor() -> Sensor:
    return Sensor("", "myname", "", "Input", "Watts", 102, "2021-01-01", "deadbeef")


def test_get_name(sensor: Sensor) -> None:
    assert sensor.getName() == "myname"
