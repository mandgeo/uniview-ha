"""Binary sensor platform for Uniview Next — alarm events.

State updates:
1. PUSH (real-time): Device POSTs alarm → HA HTTP view → event bus → sensor
2. POLL (fallback): Coordinator polls every 30s for armed/disarmed state

For smart events (camera-side AI) without an Off event (auto_off=True),
the sensor resets automatically after AUTO_OFF_SECONDS seconds.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ALARM_EVENTS, AUTO_OFF_SECONDS, DOMAIN, EVENT_UNIVIEW_ALARM, MANUFACTURER
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
                UnivewAlarmBinarySensor(
                    coordinator, entry, ch_id, event_key, event_info, ch_name
                )
            )
    async_add_entities(entities)


class UnivewAlarmBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for a specific alarm type on a channel.

    For events with auto_off=True (smart camera-side events that have no Off
    push), the sensor automatically resets to off after AUTO_OFF_SECONDS.
    The cancel handle is stored so any subsequent On event restarts the timer.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnivewCoordinator,
        entry: ConfigEntry,
        channel_id: int,
        event_key: str,
        event_info: dict,
        ch_name: str = "",
    ) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._event_key = event_key
        self._event_info = event_info
        self._is_on = False
        self._auto_off_cancel = None  # handle to cancel pending auto-off

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
            name=f"{entry.title} — {ch_name}",
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
            "auto_off": self._event_info.get("auto_off", False),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Coordinator poll — does not change is_on (push is authoritative)."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_UNIVIEW_ALARM, self._handle_alarm_push)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel pending auto-off timer when entity is removed."""
        self._cancel_auto_off()

    @callback
    def _cancel_auto_off(self) -> None:
        if self._auto_off_cancel is not None:
            self._auto_off_cancel()
            self._auto_off_cancel = None

    @callback
    def _schedule_auto_off(self) -> None:
        """Schedule automatic reset to off after AUTO_OFF_SECONDS."""
        self._cancel_auto_off()

        @callback
        def _do_auto_off(now=None) -> None:
            self._auto_off_cancel = None
            if self._is_on:
                _LOGGER.debug(
                    "Auto-off %s ch%s after %ss",
                    self._event_key, self._channel_id, AUTO_OFF_SECONDS,
                )
                self._is_on = False
                self.async_write_ha_state()

        self._auto_off_cancel = async_call_later(
            self.hass, AUTO_OFF_SECONDS, _do_auto_off
        )

    @callback
    def _handle_alarm_push(self, event) -> None:
        """Handle alarm push from device.

        event.data:
          AlarmType:  "MotionAlarmOn" | "FieldDetectorObjectsInside" | etc.
          ChannelID:  int (channel ID from NVR) or -1
          Active:     bool
        """
        data = event.data
        event_channel = data.get("ChannelID", -1)

        if event_channel != -1 and event_channel != self._channel_id:
            return

        alarm_type = data.get("AlarmType", "")
        alarm_on = self._event_info.get("alarm_type_on", "")
        alarm_off = self._event_info.get("alarm_type_off")
        auto_off = self._event_info.get("auto_off", False)

        if alarm_type == alarm_on:
            self._is_on = True
            self.async_write_ha_state()
            # Start auto-off timer if this event type has no Off push
            if auto_off:
                self._schedule_auto_off()

        elif alarm_off and alarm_type == alarm_off:
            self._cancel_auto_off()
            self._is_on = False
            self.async_write_ha_state()
