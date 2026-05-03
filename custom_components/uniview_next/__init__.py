"""Uniview Next — Home Assistant integration for Uniview NVR and IP cameras.

Uses Uniview LightAPI (LAPI) v4.
Documentation: LightAPI_InterFace_v4_00_EN.docx
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .dashboard import async_create_dashboard_if_missing

from .const import (
    CONF_SET_NOTIFICATION_HOST,
    CONF_USE_HTTPS,
    DOMAIN,
    EVENT_UNIVIEW_ALARM,
    MANUFACTURER,
)
from .coordinator import UnivewCoordinator
from .isapi import UnivewDevice, UnivewError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SENSOR,
]

# NVR pushes alarms to this exact path on the HA server
ALARM_PUSH_PATH = "/LAPI/V1.0/System/Event/Notification/Alarm"


class UnivewAlarmView(HomeAssistantView):
    """HTTP view that receives alarm push notifications from Uniview NVR.

    The NVR POSTs to: http://<ha_ip>:<ha_port>/LAPI/V1.0/System/Event/Notification/Alarm
    Body: {
        "Reference": "192.168.x.x:80/.../Subscribers/249",
        "AlarmInfo": {
            "AlarmType": "MotionAlarmOn",
            "AlarmLevel": 0,
            "TimeStamp": 1489040894,
            "AlarmSeq": 327,
            "AlarmSrcID": 1,       # channel ID when AlarmSrcType=8
            "AlarmSrcType": 8,     # 8=video channel
            "AlarmSrcName": "Camera1"
        }
    }
    """

    url = ALARM_PUSH_PATH
    name = "uniview_alarm_push"
    requires_auth = False  # NVR cannot authenticate to HA

    async def post(self, request: web.Request) -> web.Response:
        """Handle alarm push from NVR."""
        hass: HomeAssistant = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            body = {}

        _LOGGER.debug("Uniview alarm push received: %s", body)

        alarm_info = body.get("AlarmInfo", {})
        alarm_type = alarm_info.get("AlarmType", "")
        src_type = alarm_info.get("AlarmSrcType", -1)
        src_id = alarm_info.get("AlarmSrcID", -1)

        channel_id = int(src_id) if src_type == 8 and src_id != -1 else -1

        event_data = {
            "AlarmType": alarm_type,
            "ChannelID": channel_id,
            "AlarmSrcID": src_id,
            "AlarmSrcType": src_type,
            "AlarmSrcName": alarm_info.get("AlarmSrcName", ""),
            "TimeStamp": alarm_info.get("TimeStamp", 0),
            "AlarmSeq": alarm_info.get("AlarmSeq", 0),
            "Active": alarm_type.endswith("AlarmOn"),
            "Raw": body,
        }
        hass.bus.async_fire(EVENT_UNIVIEW_ALARM, event_data)

        return web.Response(status=200)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Uniview from a config entry."""
    device = UnivewDevice(
        host=entry.data[CONF_HOST],
        port=int(entry.data[CONF_PORT]),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        use_https=entry.data.get(CONF_USE_HTTPS, False),
    )

    coordinator = UnivewCoordinator(hass, device)

    try:
        await coordinator.async_setup()
    except UnivewError as err:
        _LOGGER.error("Failed to connect to Uniview device: %s", err)
        await device.close()
        return False

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register NVR/camera as HA device
    dev_info = coordinator.device_info_data
    serial = entry.data.get("serial", entry.entry_id)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, serial)},
        manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
        model=dev_info.get("DeviceModel", entry.data.get("model", "Uniview Device")),
        name=entry.title,
        sw_version=dev_info.get("FirmwareVersion", ""),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Generează dashboard Lovelace dacă nu există deja
    hass.async_create_task(
        async_create_dashboard_if_missing(hass, entry)
    )

    # Register HTTP view to receive alarm push from NVR.
    # NVR POSTs to: http://<ha_ip>:<port>/LAPI/V1.0/System/Event/Notification/Alarm
    # Only register once (shared across all entries)
    if not hass.data.get(DOMAIN + "_view_registered"):
        hass.http.register_view(UnivewAlarmView())
        hass.data[DOMAIN + "_view_registered"] = True
        _LOGGER.debug("Registered Uniview alarm push view at %s", ALARM_PUSH_PATH)

    # Subscribe device to push alarms to HA
    if entry.data.get(CONF_SET_NOTIFICATION_HOST, False):
        try:
            from homeassistant.helpers.network import get_url
            ha_url = get_url(hass, prefer_external=False)
            ha_ip = ha_url.split("://")[-1].split(":")[0].split("/")[0]
            url_after_scheme = ha_url.split("://")[-1]
            ha_port = 8123
            if ":" in url_after_scheme:
                port_part = url_after_scheme.split(":")[1].split("/")[0]
                try:
                    ha_port = int(port_part)
                except ValueError:
                    pass

            result = await device.subscribe_alarms(ha_ip, ha_port)
            sub_id = result.get("ID")
            if sub_id is not None:
                hass.data.setdefault(DOMAIN + "_subs", {})[entry.entry_id] = sub_id
                _LOGGER.info(
                    "Subscribed to Uniview alarm push (sub ID: %s). "
                    "NVR will POST alarms to %s:%s%s",
                    sub_id, ha_ip, ha_port, ALARM_PUSH_PATH,
                )

                # Refresh subscription every 30 min (duration is 3600s = 1h)
                async def _refresh_subscription(now=None) -> None:
                    current_sub_id = hass.data.get(DOMAIN + "_subs", {}).get(entry.entry_id)
                    if current_sub_id is None:
                        return
                    try:
                        await device.refresh_alarm_subscription(current_sub_id)
                        _LOGGER.debug("Refreshed Uniview alarm subscription %s", current_sub_id)
                    except UnivewError as err:
                        _LOGGER.warning(
                            "Failed to refresh subscription %s: %s — resubscribing",
                            current_sub_id, err,
                        )
                        # Subscription may have expired — create a new one
                        try:
                            new_result = await device.subscribe_alarms(ha_ip, ha_port)
                            new_id = new_result.get("ID")
                            if new_id is not None:
                                hass.data[DOMAIN + "_subs"][entry.entry_id] = new_id
                                _LOGGER.info("Resubscribed, new sub ID: %s", new_id)
                        except UnivewError as sub_err:
                            _LOGGER.error("Resubscribe failed: %s", sub_err)

                from homeassistant.helpers.event import async_track_time_interval
                from datetime import timedelta
                cancel_refresh = async_track_time_interval(
                    hass,
                    _refresh_subscription,
                    timedelta(minutes=30),
                )
                hass.data.setdefault(DOMAIN + "_refresh_cancels", {})[entry.entry_id] = cancel_refresh

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Could not subscribe to Uniview alarm push: %s. "
                "Alarms will not be pushed — only polling active.",
                err,
            )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cancel subscription refresh timer
    cancel_refresh = hass.data.get(DOMAIN + "_refresh_cancels", {}).pop(entry.entry_id, None)
    if cancel_refresh:
        cancel_refresh()

    # Cancel alarm subscription on NVR
    sub_id = hass.data.get(DOMAIN + "_subs", {}).pop(entry.entry_id, None)
    if sub_id is not None:
        coordinator: UnivewCoordinator = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            try:
                await coordinator.device.cancel_alarm_subscription(sub_id)
            except Exception:  # pylint: disable=broad-except
                pass

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.device.close()
    return unload_ok
