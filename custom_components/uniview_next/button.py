"""Button platform for Uniview Next — device reboot.

PUT /LAPI/V1.0/System/Reboot  (Content-Length: 0)
Applicable to IPC and NVR.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER
from .coordinator import UnivewCoordinator
from .isapi import UnivewError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnivewCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UnivewRebootButton(coordinator, entry)])


class UnivewRebootButton(ButtonEntity):
    """Button to reboot the Uniview NVR/IPC."""

    _attr_has_entity_name = True
    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"

    def __init__(self, coordinator: UnivewCoordinator, entry: ConfigEntry) -> None:
        serial = entry.data.get("serial", entry.entry_id)
        dev_info = coordinator.device_info_data

        self._coordinator = coordinator
        self._attr_unique_id = f"{serial}_reboot"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=entry.title,
            manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
            model=dev_info.get("DeviceModel", ""),
            sw_version=dev_info.get("FirmwareVersion", ""),
        )

    async def async_press(self) -> None:
        """Send reboot command to device via LAPI."""
        try:
            await self._coordinator.device.reboot()
            _LOGGER.info("Uniview device reboot initiated")
        except UnivewError as err:
            _LOGGER.error("Reboot failed: %s", err)
