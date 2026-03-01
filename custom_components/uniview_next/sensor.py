"""Sensor platform for Uniview Next — HDD / storage status.

ContainerInfoList from /Storage/Containers/DetailInfos:
{
  "LocalHDDNum": N,
  "LocalHDDList": [<ContainerInfo>, ...],
  "NASNum": N,
  "NASList": [<ExContainerInfo>, ...],
  ...
}
ContainerInfo: {
  "ID": int,
  "RemainCapacity": int,   # MB
  "TotalCapacity": int,    # MB
  "Manufacturer": str,
  "Status": int,           # 0=No HDD, 1=Not formatted, 2=Formatting,
                           # 3=Healthy, 4=Sleep, 5=Abnormal, 6=Switching, 7=Unmounted
  "Property": int,         # 0=R/W, 1=Read-only, 2=Redundant
  "FormatProgress": int,   # % when Status=2
  "GroupID": int,
}
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnivewCoordinator

_LOGGER = logging.getLogger(__name__)

HDD_STATUS_MAP = {
    0: "no_hdd",
    1: "not_formatted",
    2: "formatting",
    3: "healthy",
    4: "sleep",
    5: "abnormal",
    6: "switching",
    7: "unmounted",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnivewCoordinator = hass.data[DOMAIN][entry.entry_id]

    hdd_list = (coordinator.data or {}).get("hdd_status", [])
    entities = [
        UnivewHddSensor(coordinator, entry, i, hdd)
        for i, hdd in enumerate(hdd_list)
    ]
    if entities:
        async_add_entities(entities)


class UnivewHddSensor(CoordinatorEntity, SensorEntity):
    """Sensor for one storage container (HDD/NAS/etc).

    native_value = remaining capacity in GB
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_icon = "mdi:harddisk"

    def __init__(
        self,
        coordinator: UnivewCoordinator,
        entry: ConfigEntry,
        hdd_index: int,
        hdd_data: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._hdd_index = hdd_index
        serial = entry.data.get("serial", entry.entry_id)
        dev_info = coordinator.device_info_data
        hdd_id = hdd_data.get("ID", hdd_index + 1)

        self._attr_unique_id = f"{serial}_hdd{hdd_id}"
        self._attr_name = f"HDD {hdd_id} Free Space"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=entry.title,
            manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
            model=dev_info.get("DeviceModel", ""),
            sw_version=dev_info.get("FirmwareVersion", ""),
        )

    def _get_hdd(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        hdd_list = data.get("hdd_status", [])
        if self._hdd_index < len(hdd_list):
            return hdd_list[self._hdd_index]
        return None

    @property
    def native_value(self) -> float | None:
        hdd = self._get_hdd()
        if hdd is None:
            return None
        mb = hdd.get("RemainCapacity")
        if mb is None:
            return None
        try:
            return round(float(mb) / 1024, 2)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        hdd = self._get_hdd()
        if hdd is None:
            return {}
        status_code = hdd.get("Status", -1)
        total_mb = hdd.get("TotalCapacity", 0)
        return {
            "hdd_id": hdd.get("ID"),
            "status": HDD_STATUS_MAP.get(status_code, f"unknown_{status_code}"),
            "total_capacity_gb": round(float(total_mb) / 1024, 2) if total_mb else None,
            "property": {0: "read_write", 1: "read_only", 2: "redundant"}.get(
                hdd.get("Property", 0), "unknown"
            ),
            "manufacturer": hdd.get("Manufacturer", ""),
            "group_id": hdd.get("GroupID"),
            "format_progress": hdd.get("FormatProgress"),
        }
