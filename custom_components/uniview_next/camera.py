"""Camera platform for Uniview Next.

Stream URL: obtained via LAPI LiveStreamURL endpoint which returns an RTSP URL.
  GET /LAPI/V1.0/Channels/<ID>/Media/Video/Streams/<ID>/LiveStreamURL
  Response: {"LoginName": "...", "PIN": "...", "URL": "rtsp://192.168.x.x:554/..."}

Snapshot: JPEG bytes from LAPI endpoint (no JSON envelope — raw image).
  GET /LAPI/V1.0/Channels/<ID>/Media/Video/Streams/<ID>/Snapshot
  Response: Content-Type: image/jpeg  (raw bytes)

Stream IDs:
  0 = Main stream
  1 = Sub stream
  2 = Third stream

For IPC, channel ID is always 0.
For NVR, channel ID matches the channel number (1-based per DeviceInfos).
"""
from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
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

    entities = []
    for ch in coordinator.channels:
        ch_id = int(ch.get("ID", 0))
        ch_name = coordinator.get_channel_name(ch_id)
        # Main stream (0) and Sub stream (1)
        for stream_id, label in [(0, "Main"), (1, "Sub")]:
            entities.append(
                UnivewCamera(coordinator, entry, ch_id, ch_name, stream_id, label)
            )

    async_add_entities(entities)


class UnivewCamera(Camera):
    """Representation of a single Uniview camera stream.

    Uses LAPI LiveStreamURL for the RTSP stream source.
    Falls back to a constructed RTSP URL if the API call fails.
    """

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: UnivewCoordinator,
        entry: ConfigEntry,
        channel_id: int,
        channel_name: str,
        stream_id: int,
        stream_label: str,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._device = coordinator.device
        self._channel_id = channel_id
        self._stream_id = stream_id

        serial = entry.data.get("serial", entry.entry_id)
        dev_info = coordinator.device_info_data

        self._attr_unique_id = f"{serial}_cam_ch{channel_id}_stream{stream_id}"
        self._attr_name = f"{stream_label} Stream"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_ch{channel_id}")},
            name=f"{entry.title} — {channel_name}",
            manufacturer=dev_info.get("Manufacturer", MANUFACTURER),
            model=dev_info.get("DeviceModel", ""),
            sw_version=dev_info.get("FirmwareVersion", ""),
            via_device=(DOMAIN, serial),
        )

    async def stream_source(self) -> str | None:
        """Return RTSP stream URL via LAPI LiveStreamURL.

        Uniview RTSP URL format: rtsp://host:554/unicast/c<channel>/s<stream>/live
          c = channel ID (1-based)
          s = stream index (0=main, 1=sub, 2=third)
        """
        url = await self._device.get_live_stream_url(self._channel_id, self._stream_id)
        if url:
            # Inject credentials if not present
            if "://" in url and "@" not in url:
                scheme, rest = url.split("://", 1)
                url = f"{scheme}://{self._device.username}:{self._device.password}@{rest}"
            return url

        # Fallback: Uniview standard RTSP format
        # unicast/c<channel>/s<stream>/live  (channel is 1-based)
        return (
            f"rtsp://{self._device.username}:{self._device.password}"
            f"@{self._device.host}:554"
            f"/unicast/c{self._channel_id}/s{self._stream_id}/live"
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return JPEG snapshot via LAPI Snapshot endpoint."""
        try:
            return await self._device.get_snapshot(self._channel_id, self._stream_id)
        except UnivewError as err:
            _LOGGER.error(
                "Snapshot failed ch%s stream%s: %s", self._channel_id, self._stream_id, err
            )
            return None
