# Uniview Next — Home Assistant Integration

A custom Home Assistant integration for **Uniview NVR and IP cameras** using the official **LightAPI (LAPI) v4** protocol.

> Developed and tested on **NVR302-16E2** with firmware `NVR-B3112.39.52.251216`.  
> May work on other Uniview NVR and IPC devices supporting LAPI v4.

---

## Features

- 📹 **Live streaming** (Main + Sub stream per channel, RTSP via NVR)
- 📸 **Snapshots** (static image per camera)
- 🔔 **Real-time alarm push** (motion, tamper, line crossing, intrusion, etc.)
- 🔁 **Automatic subscription refresh** (keeps alarm push alive indefinitely)
- 🔛 **Switches** to enable/disable detection per camera:
  - Motion Detection
  - Tamper Detection
  - Line Crossing (Smart)
  - Intrusion Detection (Smart)
  - Region Exit / Entrance (Smart)
- 💾 **HDD/storage sensors** (free space, status per disk)
- 🔘 **Reboot button** for the NVR
- 🔗 Supports **mixed camera brands** connected to Uniview NVR (Hikvision, etc.)

---

## Requirements

- Home Assistant 2023.6 or newer
- Uniview NVR or IPC with LAPI v4 support
- HTTP access to the NVR from the HA host (port 80 by default)
- `stream:` integration enabled in HA (for live video)

---

## Installation

### Manual

1. Copy the `custom_components/uniview_next` folder into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for **Uniview Next**.

### Via HACS (if published)

1. Add this repository as a custom repository in HACS.
2. Install **Uniview Next**.
3. Restart Home Assistant.

---

## Configuration

| Field | Description | Default |
|---|---|---|
| Host | IP address of the NVR | — |
| Port | HTTP port | 80 |
| Username | NVR admin username | admin |
| Password | NVR admin password | — |
| Use HTTPS | Enable HTTPS | off |
| Set notification host | Subscribe to real-time alarm push | on |

> **Set notification host** should be enabled for real-time alarm detection.  
> When enabled, the NVR will push alarm events directly to Home Assistant.  
> The integration automatically refreshes the subscription every 30 minutes.

---

## Alarm Push (How it works)

When **Set notification host** is enabled:

1. At startup, HA registers itself with the NVR via `POST /LAPI/V1.0/System/Event/Subscription`
2. The NVR pushes alarm events to `http://<ha_ip>:<port>/LAPI/V1.0/System/Event/Notification/Alarm`
3. HA fires a `uniview_next_event` event on the event bus for each alarm
4. Binary sensors update instantly when alarms arrive

**Supported alarm types:**

| AlarmType | Sensor |
|---|---|
| MotionAlarmOn / Off | Motion Detection |
| TamperAlarmOn / Off | Tampering |
| VideoLossAlarmOn / Off | Video Loss |
| CrossLineAlarmOn / Off | Line Crossing |
| IntrusionAlarmOn / Off | Intrusion Detection |
| LeaveZoneAlarmOn / Off | Region Exit |
| AccessZoneAlarmOn / Off | Region Entrance |

---

## Known Limitations

- **H.265 streams** may not play as live video in HA (only snapshot shown). Workaround: change camera codec to H.264 in NVR settings, or use the Sub stream.
- **Hikvision cameras** connected to Uniview NVR work for streaming (NVR proxies the stream) but alarm detection depends on NVR configuration.
- Smart detection switches (CrossLine, Intrusion, etc.) require the camera to support those features.

---

## Entities Created

For each connected camera channel:

| Entity | Type | Description |
|---|---|---|
| `camera.<name>_main_stream` | Camera | Main stream (RTSP) |
| `camera.<name>_sub_stream` | Camera | Sub stream (RTSP) |
| `binary_sensor.<name>_motion_detection` | Binary sensor | Motion alarm state |
| `binary_sensor.<name>_tampering` | Binary sensor | Tamper alarm state |
| `binary_sensor.<name>_video_loss` | Binary sensor | Video loss state |
| `binary_sensor.<name>_line_crossing` | Binary sensor | Line crossing alarm |
| `binary_sensor.<name>_intrusion_detection` | Binary sensor | Intrusion alarm |
| `binary_sensor.<name>_region_exit` | Binary sensor | Leave zone alarm |
| `binary_sensor.<name>_region_entrance` | Binary sensor | Access zone alarm |
| `switch.<name>_motion_detection_switch` | Switch | Enable/disable motion |
| `switch.<name>_tampering_switch` | Switch | Enable/disable tamper |
| `switch.<name>_line_crossing_switch` | Switch | Enable/disable line crossing |
| `switch.<name>_intrusion_detection_switch` | Switch | Enable/disable intrusion |
| `switch.<name>_region_exit_switch` | Switch | Enable/disable leave zone |
| `switch.<name>_region_entrance_switch` | Switch | Enable/disable access zone |

For the NVR device:

| Entity | Type | Description |
|---|---|---|
| `sensor.nvr_hdd_<n>_free_space` | Sensor | HDD free space (GB) |
| `button.nvr_reboot` | Button | Reboot the NVR |

---

## Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.uniview_next: debug
```

---

## Contributing

Pull requests welcome. Tested hardware:

- Uniview NVR302-16E2
- Uniview IPC2225SB-ADF40KM-I1
- Uniview IPC2225SB-ADF28KM-I1
- Uniview IPC3614LB-SF28-A
- Uniview IPC3634LB-ADZK-G
- Hikvision DS-2CV2041G2-IDW (via NVR proxy)
- Hikvision HWC-P120-D/W (via NVR proxy)

---

## License

MIT License — see [LICENSE](LICENSE) file.
