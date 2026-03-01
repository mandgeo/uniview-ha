"""Switch platform for Uniview Next — enable/disable alarm detection per channel."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ALARM_EVENTS, DOMAIN, MANUFACTURER
from .coordinator import UnivewCoordinator
from .isapi import UnivewDevice, UnivewError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UnivewCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for ch in coordinator.channels:
        ch_id = int(ch.get("ID", 0))
        ch_name = coordinator.get_channel_name(ch_id)
        for event_key, event_info in ALARM_EVENTS.items():
            if event_info.get("can_toggle", False):
                entities.append(
                    UnivewDetectionSwitch(
                        coordinator, entry, ch_id, ch_name, event_key, event_info
                    )
                )
    async_add_entities(entities, update_before_add=True)


class UnivewDetectionSwitch(SwitchEntity):
    """Switch to enable/disable an alarm detection type on a channel.

    Reads initial state from device on first update.
    Maps to the correct LAPI endpoint based on endpoint_type:
      motion_grid → /Alarm/MotionDetection/Areas/Grid        {"Enabled": bool}
      tamper      → /Alarm/TamperDetection/Rule              {"Enabled": bool, ...}
      smart       → /Smart/<smart_key>/Rule                   {"Enabled": bool}
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnivewCoordinator,
        entry: ConfigEntry,
        channel_id: int,
        channel_name: str,
        event_key: str,
        event_info: dict,
    ) -> None:
        self._coordinator = coordinator
        self._device: UnivewDevice = coordinator.device
        self._channel_id = channel_id
        self._event_key = event_key
        self._event_info = event_info
        self._is_on: bool | None = None  # None = unknown until first update

        serial = entry.data.get("serial", entry.entry_id)
        dev_info = coordinator.device_info_data

        self._attr_unique_id = f"{serial}_switch_ch{channel_id}_{event_key}"
        self._attr_name = f"{event_info['label']} Switch"
        self._attr_icon = event_info["icon"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_ch{channel_id}")},
            name=f"{entry.title} — {channel_name}",
            manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
            model=dev_info.get("DeviceModel", ""),
            sw_version=dev_info.get("FirmwareVersion", ""),
            via_device=(DOMAIN, serial),
        )

    @property
    def is_on(self) -> bool | None:
        return self._is_on

    @property
    def available(self) -> bool:
        return self._is_on is not None

    async def async_update(self) -> None:
        """Read current enabled state from device."""
        try:
            self._is_on = await self._get_enabled()
        except UnivewError as err:
            _LOGGER.debug(
                "Switch read ch%s %s: %s", self._channel_id, self._event_key, err
            )
            # Keep previous value; don't set to None (would mark unavailable)

    async def _get_enabled(self) -> bool:
        ep = self._event_info["endpoint_type"]
        ch = self._channel_id
        if ep == "motion_grid":
            return await self._device.get_motion_enabled(ch)
        if ep == "tamper":
            return await self._device.get_tamper_enabled(ch)
        if ep == "smart":
            return await self._device.get_smart_enabled(ch, self._event_info["smart_key"])
        return False

    async def _set_enabled(self, enabled: bool) -> None:
        ep = self._event_info["endpoint_type"]
        ch = self._channel_id
        if ep == "motion_grid":
            await self._device.set_motion_enabled(ch, enabled)
        elif ep == "tamper":
            await self._device.set_tamper_enabled(ch, enabled)
        elif ep == "smart":
            await self._device.set_smart_enabled(ch, self._event_info["smart_key"], enabled)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._set_enabled(True)
            self._is_on = True
            self.async_write_ha_state()
        except UnivewError as err:
            _LOGGER.error("Enable %s ch%s: %s", self._event_key, self._channel_id, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._set_enabled(False)
            self._is_on = False
            self.async_write_ha_state()
        except UnivewError as err:
            _LOGGER.error("Disable %s ch%s: %s", self._event_key, self._channel_id, err)
