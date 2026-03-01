"""DataUpdateCoordinator for Uniview Next."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL_SECONDS
from .isapi import UnivewDevice, UnivewError

_LOGGER = logging.getLogger(__name__)


class UnivewCoordinator(DataUpdateCoordinator):
    """Coordinator that periodically polls the Uniview device.

    Channels come from /Channels/System/ChannelDetailInfos (NVR)
    which includes Status (0=Offline, 1=Online, 2=Idle) and Name.
    For standalone IPC, channels falls back to a single virtual channel 0.

    Coordinator data structure:
    {
        "alarm_states": {
            <channel_id>: {
                "motion_enabled": bool,
                "tamper_enabled": bool,
                "video_loss_enabled": bool,
            },
            ...
        },
        "hdd_status": [<ContainerInfo>, ...],
    }
    """

    def __init__(self, hass: HomeAssistant, device: UnivewDevice) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.device = device
        self.channels: list[dict[str, Any]] = []
        self.device_info_data: dict[str, Any] = {}

    async def async_setup(self) -> None:
        """Initial setup: fetch device info and build channel list.

        Uses /Channels/System/ChannelDetailInfos which returns DetailInfo objects:
        {ID, Name, Status(0=Offline,1=Online,2=Idle), StreamNums, DeviceType,
         Manufacturer, DeviceModel, AddressInfo, ...}

        Falls back to /Channels/System/DeviceInfos if detail infos unavailable.
        Falls back to single channel 0 for standalone IPC.
        """
        self.device_info_data = await self.device.get_device_info()

        # Try ChannelDetailInfos first (most info-rich)
        channels = await self.device.get_channel_detail_infos()

        if not channels:
            # Fallback: DeviceInfos (less detail)
            channels = await self.device.get_channels()

        if channels:
            # Only include online channels (Status=1); include all if Status unknown
            self.channels = [
                ch for ch in channels
                if ch.get("Status", 1) in (1, None)  # 1=Online
                or "Status" not in ch
            ]
            if not self.channels:
                # All offline — still include them so user sees the device
                self.channels = channels
        else:
            # Standalone IPC — single virtual channel
            self.channels = [{"ID": 0, "Name": "Camera"}]

        _LOGGER.debug(
            "Uniview setup: device=%s, channels=%d",
            self.device_info_data.get("DeviceModel", "?"),
            len(self.channels),
        )

    def get_channel_ids(self) -> list[int]:
        return [int(ch.get("ID", i)) for i, ch in enumerate(self.channels)]

    def get_channel_name(self, channel_id: int) -> str:
        for ch in self.channels:
            if int(ch.get("ID", -1)) == channel_id:
                return ch.get("Name", ch.get("DeviceName", f"Camera {channel_id}"))
        return f"Camera {channel_id}"

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll device: alarm enable states + HDD status."""
        try:
            channel_ids = self.get_channel_ids()
            alarm_states = await self.device.get_all_alarm_states(channel_ids)
            hdd_status = await self.device.get_hdd_status()
            return {
                "alarm_states": alarm_states,
                "hdd_status": hdd_status,
            }
        except UnivewError as err:
            raise UpdateFailed(f"Uniview update error: {err}") from err
