"""Constants for Uniview Next integration."""

DOMAIN = "uniview_next"
MANUFACTURER = "Uniview"

# LightAPI base path
LAPI_BASE = "/LAPI/V1.0"

# Polling interval in seconds
SCAN_INTERVAL_SECONDS = 30

DEFAULT_PORT = 80
DEFAULT_HTTPS_PORT = 443

# ── Alarm / Event definitions ─────────────────────────────────────────────────
#
# AlarmType strings pushed by device (from AlarmInfo.AlarmType in push payload):
#   "<EventName>AlarmOn"  / "<EventName>AlarmOff"
#
# endpoint_type:
#   "motion_grid"  → /Channels/<ID>/Alarm/MotionDetection/Areas/Grid  (Enabled field)
#   "tamper"       → /Channels/<ID>/Alarm/TamperDetection/Rule         (Enabled field)
#   "video_loss"   → /Channels/<ID>/Alarm/VideoLoss/Rule               (Enabled field)
#   "smart"        → /Channels/<ID>/Smart/<smart_key>/Rule             (Enabled field)
#
# smart_key: used for Smart endpoints (CrossLineDetection, IntrusionDetection,
#            LeaveZone, AccessZone)

ALARM_EVENTS: dict[str, dict] = {
    "MotionDetection": {
        "label": "Motion Detection",
        "icon": "mdi:motion-sensor",
        "device_class": "motion",
        "endpoint_type": "motion_grid",
        "smart_key": None,
        "alarm_type_on": "MotionAlarmOn",
        "alarm_type_off": "MotionAlarmOff",
        "can_toggle": True,
    },
    "TamperDetection": {
        "label": "Tampering",
        "icon": "mdi:camera-lock",
        "device_class": "tamper",
        "endpoint_type": "tamper",
        "smart_key": None,
        "alarm_type_on": "TamperAlarmOn",
        "alarm_type_off": "TamperAlarmOff",
        "can_toggle": True,
    },
    "VideoLoss": {
        "label": "Video Loss",
        "icon": "mdi:video-off",
        "device_class": "problem",
        "endpoint_type": "video_loss",
        "smart_key": None,
        "alarm_type_on": "VideoLossAlarmOn",
        "alarm_type_off": "VideoLossAlarmOff",
        "can_toggle": False,  # NVR-only, read-only for now
    },
    "CrossLineDetection": {
        "label": "Line Crossing",
        "icon": "mdi:vector-line",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "CrossLineDetection",
        "alarm_type_on": "CrossLineAlarmOn",
        "alarm_type_off": "CrossLineAlarmOff",
        "can_toggle": True,
    },
    "IntrusionDetection": {
        "label": "Intrusion Detection",
        "icon": "mdi:shield-alert",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "IntrusionDetection",
        "alarm_type_on": "IntrusionAlarmOn",
        "alarm_type_off": "IntrusionAlarmOff",
        "can_toggle": True,
    },
    "LeaveZone": {
        "label": "Region Exit",
        "icon": "mdi:map-marker-radius-outline",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "LeaveZone",
        "alarm_type_on": "LeaveZoneAlarmOn",
        "alarm_type_off": "LeaveZoneAlarmOff",
        "can_toggle": True,
    },
    "AccessZone": {
        "label": "Region Entrance",
        "icon": "mdi:map-marker-radius",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "AccessZone",
        "alarm_type_on": "AccessZoneAlarmOn",
        "alarm_type_off": "AccessZoneAlarmOff",
        "can_toggle": True,
    },
}

# Config flow keys
CONF_USE_HTTPS = "use_https"
CONF_SET_NOTIFICATION_HOST = "set_notification_host"

# HA event fired when push alarm is received from device
EVENT_UNIVIEW_ALARM = "uniview_next_event"
