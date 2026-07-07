"""Representation of a single IoTaWatt sensor channel."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


class Sensor:
    """A single IoTaWatt input or output channel."""

    def __init__(
        self,
        channel: str,
        base_name: str,
        suffix: str | None,
        io_type: str,
        unit: str,
        value: float | None,
        begin: str | None,
        mac_addr: str,
        fromStart: bool = False,
    ) -> None:
        """Initialize the sensor."""
        self._channel = channel
        self._base_name = base_name
        self._suffix = suffix
        self._type = io_type
        self._unit = unit
        self._value: float | None = value
        self._begin: str | None = begin
        self._sensor_id: str = ""
        self._fromStart = fromStart

        self.hub_mac_address = mac_addr

        self.setSensorID(mac_addr)

    def getChannel(self) -> str:
        """Return the channel identifier."""
        return self._channel

    def setChannel(self, channel: str) -> None:
        """Set the channel identifier."""
        self._channel = channel

    def getSensorID(self) -> str:
        """Return the unique sensor ID."""
        return self._sensor_id

    def setSensorID(self, hub_mac_address: str) -> None:
        """Compute and set the sensor ID from the hub MAC and name."""
        self._sensor_id = f"{hub_mac_address}_{self._type}_{self.getName()}"

    def getSourceName(self) -> str:
        """Return the source name (base name + optional suffix)."""
        return self._base_name + (self._suffix if self._suffix is not None else "")

    def getName(self) -> str:
        """Return the display name for this sensor."""
        return self.getSourceName() + (
            "_last" if self._suffix == ".wh" and not self._fromStart else ""
        )

    def getBaseName(self) -> str:
        """Return the base name (without suffix)."""
        return self._base_name

    def setBaseName(self, base_name: str) -> None:
        """Set the base name."""
        self._base_name = base_name

    def getSuffix(self) -> str | None:
        """Return the sensor suffix."""
        return self._suffix

    def setSuffix(self, suffix: str | None) -> None:
        """Set the sensor suffix."""
        self._suffix = suffix

    def getType(self) -> str:
        """Return the I/O type ("Input" or "Output")."""
        return self._type

    def setType(self, io_type: str) -> None:
        """Set the I/O type."""
        self._type = io_type

    def getUnit(self) -> str:
        """Return the unit of measurement."""
        return self._unit

    def setUnit(self, unit: str) -> None:
        """Set the unit of measurement."""
        self._unit = unit

    def getValue(self) -> float | None:
        """Return the most recent value."""
        return self._value

    def setValue(self, value: float | None) -> None:
        """Set the most recent value."""
        self._value = value

    def getBegin(self) -> str | None:
        """Return the begin timestamp of the most recent sample window."""
        return self._begin

    def setBegin(self, begin: str | None) -> None:
        """Set the begin timestamp of the most recent sample window."""
        self._begin = begin

    def getFromStart(self) -> bool:
        """Return whether the sensor reports values from the start of the period."""
        return self._fromStart

    def setFromStart(self, fromStart: bool) -> None:
        """Set whether the sensor reports values from the start of the period."""
        self._fromStart = fromStart
