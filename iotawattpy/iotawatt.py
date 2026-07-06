"""High-level interface to an IoTaWatt energy monitoring device."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import httpx

from .connection import Connection
from .sensor import Sensor

LOGGER = logging.getLogger(__name__)

_HTTP_UNAUTHORIZED = 401
_ROUND_SECONDS = 5


class Iotawatt:
    """Represent a physical IoTaWatt device and its connected sensors."""

    def __init__(
        self,
        device_name: str,
        ip: str,
        websession: httpx.AsyncClient,
        username: str | None = None,
        password: str | None = None,
        integratedInterval: str = "y",
        includeNonTotalSensors: bool = True,
    ) -> None:
        """Initialize the device wrapper.

        :param device_name: Friendly name for the device.
        :param ip: IP address or hostname of the IoTaWatt.
        :param websession: Shared httpx async client.
        :param username: Optional digest-auth username.
        :param password: Optional digest-auth password.
        :param integratedInterval: Period for integrated WattHour queries.
        :param includeNonTotalSensors: Whether to add per-period energy sensors.
        """
        self._device_name = device_name
        self._ip = ip
        self._connection = Connection(websession, self._ip)
        self._username = username
        self._password = password
        self._integratedInterval = integratedInterval
        self._includeNonTotalSensors = includeNonTotalSensors
        self._lastUpdateTime: datetime | None = None

        self._sensors: dict[str, dict[str, Sensor]] = {"sensors": {}}

        self._macAddress = ""
        self._getMACFlag = False

    async def connect(self) -> bool:
        """Test the connection and capture the device MAC address."""
        url = f"http://{self._ip}/status?wifi=yes"
        results = await self._connection.get(url, self._username, self._password)
        if results.status_code == httpx.codes.OK:
            jsonResults = results.json()
            self._macAddress = jsonResults["wifi"]["mac"].replace(":", "")
            LOGGER.debug("MAC: %s", self._macAddress)
            return True
        if results.status_code == _HTTP_UNAUTHORIZED:
            return False
        results.raise_for_status()
        return False

    def getSensors(self) -> dict[str, dict[str, Sensor]]:
        """Return the dict of known sensors."""
        return self._sensors

    async def update(
        self, timespan: int = 30, lastUpdate: datetime | None = None
    ) -> None:
        """Refresh sensor values from the device.

        Raises ``httpx.HTTPError`` if the device cannot be reached or rejects
        the request (e.g. an authentication failure surfaces as a 401).
        """
        if not self._getMACFlag:
            if not await self.connect():
                url = f"http://{self._ip}/status?wifi=yes"
                msg = "Authentication with the IoTaWatt device failed"
                raise httpx.HTTPStatusError(
                    msg,
                    request=httpx.Request("GET", url),
                    response=httpx.Response(httpx.codes.UNAUTHORIZED),
                )
            self._getMACFlag = True
        await self._refreshSensors(timespan, lastUpdate)

    def getLastUpdateTime(self) -> datetime | None:
        """Return the timestamp of the last successful update."""
        return self._lastUpdateTime

    async def _getInputsandOutputs(self) -> httpx.Response:
        """Fetch the inputs and outputs status from the device."""
        url = f"http://{self._ip}/status?inputs=yes&outputs=yes"
        response = await self._connection.get(url, self._username, self._password)
        response.raise_for_status()
        return response

    def _createOrUpdateSensor(
        self,
        sensors: dict[str, Sensor],
        entity: str,
        channel_nbr: str,
        base_name: str,
        io_type: str,
        unit: str,
        suffix: str | None = None,
        fromStart: bool = False,
    ) -> None:
        """Create or update a single sensor entry."""
        if entity not in sensors:
            LOGGER.debug("%s: Creating Channel sensor %s", io_type, entity)
            sensors[entity] = Sensor(
                channel_nbr,
                base_name,
                suffix,
                io_type,
                unit,
                None,
                None,
                self._macAddress,
                fromStart,
            )
        else:
            sensor = sensors[entity]
            sensor.setBaseName(base_name)
            sensor.setSuffix(suffix)
            sensor.setUnit(unit)
            sensor.setSensorID(self._macAddress)
            sensor.setFromStart(fromStart)

    def _createOrUpdateSensorSet(
        self,
        sensors: dict[str, Sensor],
        entity: str,
        channel_nbr: str,
        base_name: str,
        io_type: str,
        unit: str,
    ) -> None:
        """Create or update a power sensor and its derived energy sensors."""
        self._createOrUpdateSensor(
            sensors, entity, channel_nbr, base_name, io_type, unit
        )

        # Also add Energy sensors (the integral of Power) for all Power sensors
        if unit == "Watts":
            self._createOrUpdateSensor(
                sensors,
                entity + "_total_energy",
                channel_nbr,
                base_name,
                io_type,
                "WattHours",
                suffix=".wh",
                fromStart=True,
            )
            if self._includeNonTotalSensors:
                self._createOrUpdateSensor(
                    sensors,
                    entity + "_energy",
                    channel_nbr,
                    base_name,
                    io_type,
                    "WattHours",
                    suffix=".wh",
                )

    async def _refreshSensors(  # noqa: C901, PLR0912, PLR0915
        self, timespan: int, lastUpdate: datetime | None
    ) -> None:
        """Fetch the latest sensor values and update local state."""
        sensors = self._sensors["sensors"]

        response = await self._getInputsandOutputs()
        results: dict[str, Any] = response.json()
        LOGGER.debug("IOResults: %s", results)
        inputs = results["inputs"]
        outputs = results["outputs"]

        query_response = await self._getQueryShowSeries()
        query: dict[str, Any] = query_response.json()
        LOGGER.debug("Query: %s", query)

        self._removeStaleSensors(sensors, query)

        for i, input_entry in enumerate(inputs):
            channel_nbr = input_entry["channel"]
            LOGGER.debug(
                "In: Channel: %s - Name: %s", channel_nbr, query["series"][i]["name"]
            )
            self._createOrUpdateSensorSet(
                sensors,
                f"input_{channel_nbr}",
                channel_nbr,
                query["series"][i]["name"],
                "Input",
                query["series"][i]["unit"],
            )

        for output_entry in outputs:
            channel_name = str(output_entry["name"])
            LOGGER.debug("Out: Name: %s", channel_name)
            self._createOrUpdateSensorSet(
                sensors,
                f"output_{channel_name}",
                "N/A",
                channel_name,
                "Output",
                output_entry["units"],
            )

        # Bucket entities by query type based on unit
        current_query_entities: list[str] = []
        integrated_total_query_entities: list[str] = []
        integrated_query_entities: list[str] = []
        for entity, sensor in sensors.items():
            if sensor.getUnit() == "WattHours" and sensor.getFromStart():
                integrated_total_query_entities.append(entity)
            elif sensor.getUnit() == "WattHours":
                integrated_query_entities.append(entity)
            else:
                current_query_entities.append(entity)

        # Current (right-now) measurements
        current_query_names = [
            f"{sensors[entity].getSourceName()}.{sensors[entity].getUnit().lower()}"
            for entity in current_query_entities
        ]
        LOGGER.debug("Sen: %s", current_query_names)
        response = await self._getQuerySelectSeriesCurrent(
            current_query_names, timespan
        )
        values = response.json()
        LOGGER.debug("Val: %s", values)
        for idx, entity in enumerate(current_query_entities):
            sensors[entity].setValue(values[0][idx])

        # Integrated measurements since the beginning of the period
        integrated_total_query_names = [
            sensors[entity].getSourceName()
            for entity in integrated_total_query_entities
        ]
        LOGGER.debug("Sen: %s", integrated_total_query_names)
        integrate_response = await self._getQuerySelectSeriesIntegrate(
            integrated_total_query_names, self._integratedInterval
        )
        if integrate_response is not None:
            values = integrate_response.json()
            LOGGER.debug("Val: %s", values)
            for idx, entity in enumerate(integrated_total_query_entities):
                sensors[entity].setValue(values[0][idx + 1])
                sensors[entity].setBegin(values[0][0])

        # Integrated measurements since the previous query
        integrated_query_names = [
            sensors[entity].getSourceName() for entity in integrated_query_entities
        ]
        LOGGER.debug("Sen: %s", integrated_query_names)

        # The iotawatt only knows how to deal with either local timezone or UTC.
        # A local timezone different from the one set on the iotawatt would yield
        # incorrect results, so we use UTC.
        now = datetime.now(tz=UTC)

        # The iotawatt only supports rounded seconds; round to the nearest 5s.
        diff = now.second % _ROUND_SECONDS
        now -= timedelta(seconds=diff, microseconds=now.microsecond)

        if lastUpdate is None:
            lastUpdate = (
                now - timedelta(seconds=timespan)
                if self._lastUpdateTime is None
                else self._lastUpdateTime
            )
        LOGGER.debug(
            "Querying energy at %s for the past %ss",
            now.isoformat(),
            (now - lastUpdate).seconds,
        )
        if now == lastUpdate:
            LOGGER.warning(
                "Nothing to query, update() called too soon, must wait %ss", timespan
            )
            return
        integrate_response = await self._getQuerySelectSeriesIntegrate(
            integrated_query_names,
            lastUpdate.isoformat().split("+")[0] + "Z",
            now.isoformat().split("+")[0] + "Z",
            precision=".d3",
        )
        if integrate_response is not None:
            values = integrate_response.json()
            LOGGER.debug("Val: %s", values)
            for idx, entity in enumerate(integrated_query_entities):
                sensors[entity].setValue(values[0][idx + 1])
                sensors[entity].setBegin(values[0][0])

        self._lastUpdateTime = now

    @staticmethod
    def _removeStaleSensors(sensors: dict[str, Sensor], query: dict[str, Any]) -> None:
        """Drop sensors that no longer appear in the device series list."""
        series_names = {entry["name"] for entry in query["series"]}
        keys_to_remove = [
            entity
            for entity, sensor in sensors.items()
            if sensor.getBaseName() not in series_names
        ]
        for key in keys_to_remove:
            LOGGER.debug("Removing stale entity: %s", key)
            sensors.pop(key)

    async def _getQueryShowSeries(self) -> httpx.Response:
        """Fetch the available series from the device."""
        url = f"http://{self._ip}/query?show=series"
        LOGGER.debug("URL: %s", url)
        response = await self._connection.get(url, self._username, self._password)
        response.raise_for_status()
        return response

    async def _getQuerySelectSeriesCurrent(
        self, sensor_names: list[str], timespan: int
    ) -> httpx.Response:
        """Get current values using the Query API.

        :param sensor_names: List of sensor source names.
        :param timespan: Interval in seconds; result is averaged over the period.
        """
        strSeries = ",".join(sensor_names)
        url = (
            f"http://{self._ip}/query"
            f"?select=[{strSeries}]&begin=s-{timespan}s&end=s&group={timespan}s"
        )
        LOGGER.debug("Querying with URL %s", url)
        response = await self._connection.get(url, self._username, self._password)
        response.raise_for_status()
        return response

    async def _getQuerySelectSeriesIntegrate(
        self,
        sensor_names: list[str],
        start: str,
        end: str = "s",
        group: str = "all",
        precision: str = "",
    ) -> httpx.Response | None:
        """Get integrated (summed) values using the Query API.

        When ``group`` is ``"all"`` returns a sum; otherwise returns discrete
        values. Note that the iotawatt cannot return more than 100kB of data.

        :param sensor_names: List of sensor source names.
        :param start: Start time. ISO dates supported, plus relative codes:

            - ``y``: Jan 1 of the current year
            - ``M``: first day of the current month
            - ``w``: first day of the current week (weeks start on Sunday)
            - ``d``: the current day

            See https://docs.iotawatt.com/en/02_06_03/query.html#relative-time
        :param end: End time, same format as ``start``.
        :param group: Grouping interval (``"all"`` for a single sum).
        :param precision: Optional precision suffix (e.g. ``".d3"``).
        """
        if not sensor_names:
            return None
        strSeries = f"{precision},".join(sensor_names) + precision
        url = (
            f"http://{self._ip}/query"
            f"?select=[time.iso,{strSeries}]&begin={start}&end={end}&group={group}"
        )
        LOGGER.debug("Querying with URL %s", url)
        response = await self._connection.get(url, self._username, self._password)
        response.raise_for_status()
        return response
