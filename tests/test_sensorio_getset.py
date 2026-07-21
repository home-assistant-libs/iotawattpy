"""Tests for the Sensor data class getters and setters."""

from __future__ import annotations

import pytest

from iotawattpy.sensor import Sensor


@pytest.fixture
def sensor() -> Sensor:
    return Sensor("", "myname", "", "Input", "Watts", 102, "2021-01-01", "deadbeef")


def test_get_name(sensor: Sensor) -> None:
    assert sensor.getName() == "myname"


def test_sensor_id_reflects_mutations(sensor: Sensor) -> None:
    """The sensor ID stays consistent with name-affecting mutations."""
    assert sensor.getSensorID() == "deadbeef_Input_myname"

    sensor.setSuffix(".wh")
    sensor.setLifetime(True)
    assert sensor.getSensorID() == "deadbeef_Input_myname.wh_lifetime"

    sensor.setLifetime(False)
    assert sensor.getSensorID() == "deadbeef_Input_myname.wh_last"

    sensor.setFromStart(True)
    assert sensor.getSensorID() == "deadbeef_Input_myname.wh"

    sensor.setSensorID("cafe0001")
    assert sensor.getSensorID() == "cafe0001_Input_myname.wh"
    assert sensor.hub_mac_address == "cafe0001"
