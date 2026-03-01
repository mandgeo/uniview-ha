"""Binary sensor platform for Uniview Next — alarm events.

Each sensor represents a specific alarm type on a specific channel.

State updates happen two ways:
1. PUSH (fast, real-time): Device POSTs alarm push → HA webhook → event bus.
   Sensor listens for EVENT_UNIVIEW_ALARM and matches by ChannelID + AlarmType.
2. POLL (slow, fallback): Coordinator polls device every 30s.
   This only tells us if detection is *armed*, not if an alarm is currently active.
"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_EVENTS, DOMAIN, EVENT_UNIVIEW_ALARM, MANUFACTURER
from .coordinator import UnivewCoordinator

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
            entities.append(
                UnivewAlarmBinarySensor(coordinator, entry, ch_id, ch_name, event_key, event_info)
            )
    async_add_entities(entities)


class UnivewAlarmBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for a specific alarm type on a channel."""

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
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._event_key = event_key
        self._event_info = event_info
        self._is_on = False

        serial = entry.data.get("serial", entry.entry_id)
        dev_info = coordinator.device_info_data

        self._attr_unique_id = f"{serial}_ch{channel_id}_{event_key}"
        self._attr_name = event_info["label"]
        self._attr_icon = event_info["icon"]
        try:
            self._attr_device_class = BinarySensorDeviceClass(event_info["device_class"])
        except ValueError:
            self._attr_device_class = BinarySensorDeviceClass.MOTION

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_ch{channel_id}")},
            name=f"{entry.title} — {channel_name}",
            manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
            model=dev_info.get("DeviceModel", ""),
            sw_version=dev_info.get("FirmwareVersion", ""),
            via_device=(DOMAIN, serial),
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "channel_id": self._channel_id,
            "event_type": self._event_key,
            "alarm_type_on": self._event_info.get("alarm_type_on"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Coordinator poll update — does not change is_on (push is authoritative for that)."""
        # Polling tells us if detection is armed, not if alarm is currently firing.
        # We only update is_on from push events.
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_UNIVIEW_ALARM, self._handle_alarm_push)
        )

    @callback
    def _handle_alarm_push(self, event) -> None:
        """Handle alarm push from device.

        event.data structure (set by _handle_webhook in __init__.py):
          AlarmType:   "MotionAlarmOn" | "MotionAlarmOff" | ...
          ChannelID:   int (channel ID) or -1 if not a channel alarm
          Active:      bool (True if AlarmType ends with "AlarmOn")
        """
        data = event.data
        event_channel = data.get("ChannelID", -1)

        # Match by channel: accept if channel matches OR if channel is unknown (-1)
        if event_channel != -1 and event_channel != self._channel_id:
            return

        alarm_type = data.get("AlarmType", "")
        alarm_on = self._event_info.get("alarm_type_on", "")
        alarm_off = self._event_info.get("alarm_type_off", "")

        if alarm_type == alarm_on:
            self._is_on = True
            self.async_write_ha_state()
        elif alarm_type == alarm_off:
            self._is_on = False
            self.async_write_ha_state()
