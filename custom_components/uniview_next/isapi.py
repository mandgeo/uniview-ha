"""Uniview LightAPI (LAPI) v4 client.

Reference: LightAPI_InterFace_v4_00_EN.docx

URL pattern:
  /LAPI/V1.0[/Channels/<ID>]/<service>/<resource>[?params]

Response envelope (always):
  {"Response": {"ResponseCode": 0, "ResponseString": "Succeed", "Data": {...}}}
  ResponseCode == 0 means success.

Push alarms:
  Device POSTs to subscriber:  /LAPI/V1.0/System/Event/Notification/Alarm
  Body: {"Reference":"...", "AlarmInfo": <AlarmInfo>, "RelatedObjects":{}}
  AlarmInfo.AlarmType examples: "MotionAlarmOn", "TamperAlarmOn", etc.
  AlarmInfo.AlarmSrcType: 8 = video channel;  AlarmInfo.AlarmSrcID = channel ID
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from httpx import DigestAuth

from .const import LAPI_BASE

_LOGGER = logging.getLogger(__name__)


class _UnivewTransport(httpx.AsyncHTTPTransport):
    """Normalize Uniview's non-standard HTTP 599 status code to 200.

    Some Uniview firmware versions return HTTP 599 as a success code.
    Standard HTTP stacks reject it on raise_for_status(), so we rewrite it.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        if response.status_code == 599:
            # Must read the body before rewriting response
            await response.aread()
            response = httpx.Response(
                status_code=200,
                headers=response.headers,
                content=response.content,
                extensions=response.extensions,
            )
        return response


class UnivewError(Exception):
    """Exception for Uniview LAPI errors."""


class UnivewDevice:
    """Represents a Uniview NVR or IP Camera device accessed via LightAPI."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_https: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_https = use_https
        self._session: httpx.AsyncClient | None = None
        scheme = "https" if use_https else "http"
        self.base_url = f"{scheme}://{host}:{port}"

    @property
    def session(self) -> httpx.AsyncClient:
        if self._session is None:
            self._session = httpx.AsyncClient(
                auth=DigestAuth(self.username, self.password),
                verify=False,
                timeout=10.0,
                transport=_UnivewTransport(verify=False),
            )
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.aclose()
            self._session = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{LAPI_BASE}{path}"

    def _parse_response(self, raw: dict | list | str, path: str) -> Any:
        """Unwrap LAPI response envelope and raise on error.

        Normal envelope: {"Response": {"ResponseCode": 0, "Data": {...}}}
        Some devices return the data directly without envelope.
        """
        _LOGGER.debug("LAPI response [%s]: %s", path, raw)

        if not isinstance(raw, dict):
            raise UnivewError(f"Non-dict response for {path}: {type(raw)}")

        # Standard envelope
        if "Response" in raw:
            resp = raw["Response"]
            code = resp.get("ResponseCode", -1)
            if code != 0:
                raise UnivewError(
                    f"LAPI [{code}] {path}: {resp.get('ResponseString', 'unknown error')}"
                )
            return resp.get("Data")

        # Some firmware returns data directly (no Response wrapper)
        # If it has common data keys, treat it as the data itself
        _LOGGER.debug("No Response wrapper for %s, treating as raw data", path)
        return raw

    async def _get(self, path: str) -> Any:
        url = self._url(path)
        try:
            _LOGGER.debug("LAPI GET %s", url)
            r = await self.session.get(url)
            _LOGGER.debug("LAPI GET %s → HTTP %s", path, r.status_code)
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                raise UnivewError(f"Non-JSON response for {path}: {r.text[:200]}")
            return self._parse_response(body, path)
        except httpx.HTTPStatusError as err:
            raise UnivewError(
                f"HTTP {err.response.status_code} GET {path}: {err.response.text[:200]}"
            ) from err
        except UnivewError:
            raise
        except Exception as err:
            raise UnivewError(f"GET {path}: {err}") from err

    async def _put(self, path: str, payload: dict) -> Any:
        url = self._url(path)
        try:
            _LOGGER.debug("LAPI PUT %s payload=%s", url, payload)
            r = await self.session.put(url, json=payload)
            _LOGGER.debug("LAPI PUT %s → HTTP %s", path, r.status_code)
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                # PUT responses sometimes have no body
                return None
            return self._parse_response(body, path)
        except httpx.HTTPStatusError as err:
            raise UnivewError(
                f"HTTP {err.response.status_code} PUT {path}: {err.response.text[:200]}"
            ) from err
        except UnivewError:
            raise
        except Exception as err:
            raise UnivewError(f"PUT {path}: {err}") from err

    async def _post(self, path: str, payload: dict) -> Any:
        url = self._url(path)
        try:
            _LOGGER.debug("LAPI POST %s payload=%s", url, payload)
            r = await self.session.post(url, json=payload)
            _LOGGER.debug("LAPI POST %s → HTTP %s", path, r.status_code)
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                return None
            return self._parse_response(body, path)
        except httpx.HTTPStatusError as err:
            raise UnivewError(
                f"HTTP {err.response.status_code} POST {path}: {err.response.text[:200]}"
            ) from err
        except UnivewError:
            raise
        except Exception as err:
            raise UnivewError(f"POST {path}: {err}") from err

    # ── System ───────────────────────────────────────────────────────────────

    async def get_device_info(self) -> dict[str, Any]:
        """GET /LAPI/V1.0/System/DeviceInfo
        Returns DeviceInfo: {ID, DeviceName, DeviceType, DeviceCode,
                             DeviceModel, SerialNumber, FirmwareVersion,
                             HardwareID, UbootVersion}
        Applicable to IPC and NVR.
        """
        data = await self._get("/System/DeviceInfo")
        return data if isinstance(data, dict) else {}

    async def reboot(self) -> None:
        """PUT /LAPI/V1.0/System/Reboot  (Content-Length: 0)"""
        url = self._url("/System/Reboot")
        try:
            await self.session.put(url, content=b"")
        except Exception as err:
            raise UnivewError(f"Reboot: {err}") from err

    # ── Channels ─────────────────────────────────────────────────────────────

    async def get_channels(self) -> list[dict[str, Any]]:
        """GET /LAPI/V1.0/Channels/System/DeviceInfos
        Returns DeviceInfoList: {"Nums": N, "DeviceInfos": [<DeviceInfo>, ...]}
        Each DeviceInfo: {ID, DeviceName, DeviceType, DeviceCode, DeviceModel,
                          SerialNumber, FirmwareVersion, ...}
        Applicable to NVR.
        """
        try:
            data = await self._get("/Channels/System/DeviceInfos")
            if not isinstance(data, dict):
                return []
            infos = data.get("DeviceInfos", [])
            return infos if isinstance(infos, list) else []
        except UnivewError as err:
            _LOGGER.debug("get_channels (DeviceInfos) failed: %s", err)
            return []

    async def get_channel_detail_infos(self) -> list[dict[str, Any]]:
        """GET /LAPI/V1.0/Channels/System/ChannelDetailInfos
        Returns: {"Nums": N, "DetailInfos": [<DetailInfo>, ...]}
        DetailInfo: {ID, Name, Status (0=Offline,1=Online,2=Idle),
                     IsPoEPort, PoEStatus, StreamNums, DeviceType,
                     AddressInfo, AccessProtocol, OffReason, Manufacturer,
                     DeviceModel, ...}
        Applicable to NVR.
        """
        try:
            data = await self._get("/Channels/System/ChannelDetailInfos")
            if not isinstance(data, dict):
                return []
            infos = data.get("DetailInfos", [])
            return infos if isinstance(infos, list) else []
        except UnivewError as err:
            _LOGGER.debug("get_channel_detail_infos failed: %s", err)
            return []

    # ── Media ─────────────────────────────────────────────────────────────────

    async def get_live_stream_url(self, channel_id: int, stream_id: int = 0) -> str | None:
        """GET /LAPI/V1.0/Channels/<ID>/Media/Video/Streams/<ID>/LiveStreamURL
        Returns: {"LoginName": "...", "PIN": "...", "URL": "rtsp://..."}
        URL example: rtsp://192.168.0.13:554/media/video1
        Applicable to IPC, NVR, VMS.
        """
        try:
            data = await self._get(
                f"/Channels/{channel_id}/Media/Video/Streams/{stream_id}/LiveStreamURL"
            )
            if isinstance(data, dict):
                return data.get("URL")
            return None
        except UnivewError as err:
            _LOGGER.debug("get_live_stream_url ch%s stream%s: %s", channel_id, stream_id, err)
            return None

    async def get_snapshot(self, channel_id: int, stream_id: int = 0) -> bytes:
        """GET /LAPI/V1.0/Channels/<ID>/Media/Video/Streams/<ID>/Snapshot
        Returns raw JPEG image bytes (Content-Type: image/jpeg).
        stream_id: 0=Main, 1=Sub, 2=Third
        Applicable to IPC and NVR.
        """
        url = f"{self.base_url}{LAPI_BASE}/Channels/{channel_id}/Media/Video/Streams/{stream_id}/Snapshot"
        try:
            r = await self.session.get(url)
            r.raise_for_status()
            return r.content
        except Exception as err:
            raise UnivewError(f"Snapshot ch{channel_id}: {err}") from err

    # ── Alarm - MotionDetection ───────────────────────────────────────────────

    async def get_motion_area_type(self, channel_id: int) -> dict[str, Any]:
        """GET /LAPI/V1.0/Channels/<ID>/Alarm/MotionDetection/AreaType
        Returns MotionDetectionAreaType: {"Type": 0|1}
          0 = Rectangular area, 1 = Grid area
        Applicable to IPC and NVR.
        NOTE: This endpoint does NOT have an Enable field.
              Enable/Disable is set per-area in Areas/Rectangle/<ID> or Areas/Grid.
        """
        data = await self._get(f"/Channels/{channel_id}/Alarm/MotionDetection/AreaType")
        return data if isinstance(data, dict) else {}

    async def get_motion_grid_areas(self, channel_id: int) -> dict[str, Any]:
        """GET /LAPI/V1.0/Channels/<ID>/Alarm/MotionDetection/Areas/Grid
        Returns MotionDetectionGridAreaInfo: {"Enabled": bool, "Sensitivity": int, "Grid": ...}
        Applicable to IPC and NVR.
        """
        data = await self._get(f"/Channels/{channel_id}/Alarm/MotionDetection/Areas/Grid")
        return data if isinstance(data, dict) else {}

    async def set_motion_grid_areas(self, channel_id: int, payload: dict) -> None:
        """PUT /LAPI/V1.0/Channels/<ID>/Alarm/MotionDetection/Areas/Grid"""
        await self._put(f"/Channels/{channel_id}/Alarm/MotionDetection/Areas/Grid", payload)

    async def get_motion_enabled(self, channel_id: int) -> bool:
        """Read motion detection enabled state from Grid areas (NVR/IPC compatible)."""
        try:
            data = await self.get_motion_grid_areas(channel_id)
            return bool(data.get("Enabled", False))
        except UnivewError:
            return False

    async def set_motion_enabled(self, channel_id: int, enabled: bool) -> None:
        """Enable/disable motion detection via MotionDetection/Areas/Grid."""
        try:
            current = await self.get_motion_grid_areas(channel_id)
        except UnivewError:
            current = {}
        current["Enabled"] = 1 if enabled else 0
        await self.set_motion_grid_areas(channel_id, current)

    # ── Alarm - TamperDetection ──────────────────────────────────────────────

    async def get_tamper_rule(self, channel_id: int) -> dict[str, Any]:
        """GET /LAPI/V1.0/Channels/<ID>/Alarm/TamperDetection/Rule
        Returns TamperDetectionRuleInfo: {"Enabled": bool, "Sensitivity": int, "Duration": int}
        Applicable to IPC and NVR.
        """
        data = await self._get(f"/Channels/{channel_id}/Alarm/TamperDetection/Rule")
        return data if isinstance(data, dict) else {}

    async def set_tamper_rule(self, channel_id: int, payload: dict) -> None:
        """PUT /LAPI/V1.0/Channels/<ID>/Alarm/TamperDetection/Rule"""
        await self._put(f"/Channels/{channel_id}/Alarm/TamperDetection/Rule", payload)

    async def get_tamper_enabled(self, channel_id: int) -> bool:
        try:
            data = await self.get_tamper_rule(channel_id)
            return bool(data.get("Enabled", False))
        except UnivewError:
            return False

    async def set_tamper_enabled(self, channel_id: int, enabled: bool) -> None:
        try:
            current = await self.get_tamper_rule(channel_id)
        except UnivewError:
            current = {}
        current["Enabled"] = 1 if enabled else 0
        await self.set_tamper_rule(channel_id, current)

    # ── Alarm - VideoLoss ────────────────────────────────────────────────────

    async def get_video_loss_rule(self, channel_id: int) -> dict[str, Any]:
        """GET /LAPI/V1.0/Channels/<ID>/Alarm/VideoLoss/Rule
        Returns VideoLossRuleInfo: {"Enabled": bool}
        Applicable to NVR.
        """
        data = await self._get(f"/Channels/{channel_id}/Alarm/VideoLoss/Rule")
        return data if isinstance(data, dict) else {}

    async def get_video_loss_enabled(self, channel_id: int) -> bool:
        try:
            data = await self.get_video_loss_rule(channel_id)
            return bool(data.get("Enabled", False))
        except UnivewError:
            return False

    # ── Smart Events ─────────────────────────────────────────────────────────
    # Pattern: GET/PUT /LAPI/V1.0/Channels/<ID>/Smart/<Type>/Rule
    # Supported types: CrossLineDetection, IntrusionDetection, LeaveZone, AccessZone
    # All Rule responses: {"Enabled": bool}

    async def get_smart_rule(self, channel_id: int, smart_type: str) -> dict[str, Any]:
        """GET /LAPI/V1.0/Channels/<ID>/Smart/<smart_type>/Rule
        smart_type: CrossLineDetection | IntrusionDetection | LeaveZone | AccessZone
        Returns: {"Enabled": bool}
        Applicable to IPC and NVR.
        """
        data = await self._get(f"/Channels/{channel_id}/Smart/{smart_type}/Rule")
        return data if isinstance(data, dict) else {}

    async def set_smart_rule(self, channel_id: int, smart_type: str, payload: dict) -> None:
        """PUT /LAPI/V1.0/Channels/<ID>/Smart/<smart_type>/Rule"""
        await self._put(f"/Channels/{channel_id}/Smart/{smart_type}/Rule", payload)

    async def get_smart_enabled(self, channel_id: int, smart_type: str) -> bool:
        try:
            data = await self.get_smart_rule(channel_id, smart_type)
            return bool(data.get("Enabled", False))
        except UnivewError:
            return False

    async def set_smart_enabled(self, channel_id: int, smart_type: str, enabled: bool) -> None:
        try:
            current = await self.get_smart_rule(channel_id, smart_type)
        except UnivewError:
            current = {}
        current["Enabled"] = 1 if enabled else 0
        await self.set_smart_rule(channel_id, smart_type, current)

    # ── Storage ───────────────────────────────────────────────────────────────

    async def get_hdd_status(self) -> list[dict[str, Any]]:
        """GET /LAPI/V1.0/Storage/Containers/DetailInfos
        Returns ContainerInfoList:
        {
          "LocalHDDNum": N,
          "LocalHDDList": [<ContainerInfo>, ...],
          "NASNum": N,
          "NASList": [<ExContainerInfo>, ...],
          ...
        }
        ContainerInfo: {ID, RemainCapacity(MB), TotalCapacity(MB),
                        Manufacturer, Status(0-7), Property(0-2),
                        FormatProgress, GroupID}
        Status values: 0=No HDD/idle, 1=Not formatted, 2=Formatting,
                       3=Healthy, 4=Sleep, 5=Abnormal, 6=Switching, 7=Unmounted
        Applicable to IPC, NVR, VMS.
        """
        try:
            data = await self._get("/Storage/Containers/DetailInfos")
            if not isinstance(data, dict):
                return []
            # Collect all storage containers from all lists
            all_hdds: list[dict] = []
            for key in [
                "LocalHDDList", "SDList", "ArrayList",
                "ExtendCabinet1HDDList", "ExtendCabinet2HDDList",
                "NASList", "eSATAList",
            ]:
                lst = data.get(key, [])
                if isinstance(lst, list):
                    all_hdds.extend(lst)
            return all_hdds
        except UnivewError as err:
            _LOGGER.debug("get_hdd_status failed: %s", err)
            return []

    # ── Event Subscription (Push Alarms) ─────────────────────────────────────

    async def subscribe_alarms(self, ha_ip: str, ha_port: int = 8123) -> dict[str, Any]:
        """POST /LAPI/V1.0/System/Event/Subscription
        Subscribe to push alarm notifications.
        Device will POST to ha_ip:ha_port/LAPI/V1.0/System/Event/Notification/Alarm
        Duration range: [30, 3600] seconds (per docs).
        Returns: {"ID": N, "Reference": "...", "CurrentTime": T, "TerminationTime": T}
        Applicable to IPC, NVR, VMS.
        """
        payload = {
            "AddressType": 0,   # IPv4
            "IPAddress": ha_ip,
            "Port": ha_port,
            "Duration": 3600,   # 1 hour; refresh via PUT before expiry
        }
        data = await self._post("/System/Event/Subscription", payload)
        return data if isinstance(data, dict) else {}

    async def refresh_alarm_subscription(self, sub_id: int) -> None:
        """PUT /LAPI/V1.0/System/Event/Subscription/<ID>
        Duration range: [30, 3600] s.
        """
        await self._put(f"/System/Event/Subscription/{sub_id}", {"Duration": 3600})

    async def cancel_alarm_subscription(self, sub_id: int) -> None:
        """DELETE /LAPI/V1.0/System/Event/Subscription/<ID>"""
        url = self._url(f"/System/Event/Subscription/{sub_id}")
        try:
            await self.session.delete(url)
        except Exception as err:
            _LOGGER.warning("Cancel subscription %s: %s", sub_id, err)

    # ── Alarm state polling (coordinator) ─────────────────────────────────────

    async def get_channel_alarm_states(self, channel_id: int) -> dict[str, Any]:
        """Poll all relevant alarm enabled states for a single channel."""
        results: dict[str, Any] = {}
        tasks = {
            "motion_enabled": self.get_motion_enabled(channel_id),
            "tamper_enabled": self.get_tamper_enabled(channel_id),
            "video_loss_enabled": self.get_video_loss_enabled(channel_id),
        }
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, val in zip(tasks.keys(), gathered):
            results[key] = False if isinstance(val, Exception) else val
        return results

    async def get_all_alarm_states(self, channel_ids: list[int]) -> dict[int, dict]:
        """Poll alarm states for all channels concurrently."""
        tasks = {ch: self.get_channel_alarm_states(ch) for ch in channel_ids}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        return {
            ch: (res if not isinstance(res, Exception) else {})
            for ch, res in zip(tasks.keys(), gathered)
        }
