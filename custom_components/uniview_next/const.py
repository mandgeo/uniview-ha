"""Constants for Uniview Next integration."""

DOMAIN = "uniview_next"
MANUFACTURER = "Uniview"

# LightAPI base path
LAPI_BASE = "/LAPI/V1.0"

# Polling interval in seconds
SCAN_INTERVAL_SECONDS = 30

DEFAULT_PORT = 80
DEFAULT_HTTPS_PORT = 443

# Seconds after which a smart sensor auto-resets if no Off event received
AUTO_OFF_SECONDS = 30

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
        "auto_off": False,
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
        "auto_off": False,
    },
    "VideoLoss": {
        "label": "Video Loss",
        "icon": "mdi:video-off",
        "device_class": "problem",
        "endpoint_type": "video_loss",
        "smart_key": None,
        "alarm_type_on": "VideoLossAlarmOn",
        "alarm_type_off": "VideoLossAlarmOff",
        "can_toggle": False,
        "auto_off": False,
    },
    "CrossLineDetection": {
        "label": "Line Crossing",
        "icon": "mdi:vector-line",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "CrossLineDetection",
        "alarm_type_on": "LineDetectorCrossed",
        "alarm_type_off": None,
        "can_toggle": True,
        "auto_off": True,
    },
    "IntrusionDetection": {
        "label": "Intrusion Detection",
        "icon": "mdi:shield-alert",
        "device_class": "motion",
        "endpoint_type": "smart",
        "smart_key": "IntrusionDetection",
        "alarm_type_on": "FieldDetectorObjectsInside",
        "alarm_type_off": "FieldDetectorObjectsOutside",
        "can_toggle": True,
        "auto_off": True,
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
        "auto_off": False,
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
        "auto_off": False,
    },
}

# Config flow keys
CONF_USE_HTTPS = "use_https"
CONF_SET_NOTIFICATION_HOST = "set_notification_host"

# HA event fired when push alarm is received from device
EVENT_UNIVIEW_ALARM = "uniview_next_event"
