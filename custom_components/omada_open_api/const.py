"""Constants for the Omada Open API integration."""

DOMAIN = "omada_open_api"

# Config flow constants
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_OMADA_ID = "omada_id"
CONF_REGION = "region"
CONF_API_URL = "api_url"
CONF_CONTROLLER_TYPE = "controller_type"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES = "token_expires"
CONF_TOKEN_EXPIRES_AT = "token_expires_at"
CONF_SELECTED_SITES = "selected_sites"
CONF_SELECTED_CLIENTS = "selected_clients"
CONF_SELECTED_APPLICATIONS = "selected_applications"
CONF_SSID_FILTER = "ssid_filter"
CONF_DISCONNECT_TIMEOUT = "disconnect_timeout"
DEFAULT_DISCONNECT_TIMEOUT = 0  # minutes; 0 = immediate (current behavior)

# Entity type toggles — all default True to preserve existing behavior
CONF_ENABLE_DEVICE_BANDWIDTH_SENSORS = "enable_device_bandwidth_sensors"
CONF_ENABLE_DEVICE_CLIENT_COUNT_SENSORS = "enable_device_client_count_sensors"
CONF_ENABLE_DEVICE_DIAGNOSTIC_SENSORS = "enable_device_diagnostic_sensors"
CONF_ENABLE_DEVICE_RADIO_UTILIZATION_SENSORS = "enable_device_radio_utilization_sensors"
CONF_ENABLE_CLIENT_BANDWIDTH_SENSORS = "enable_client_bandwidth_sensors"
CONF_ENABLE_CLIENT_SIGNAL_SENSORS = "enable_client_signal_sensors"
CONF_ENABLE_CLIENT_BLOCK_SWITCH = "enable_client_block_switch"
CONF_ENABLE_CLIENT_RECONNECT_BUTTON = "enable_client_reconnect_button"
CONF_ENABLE_THREAT_HEATMAP_SENSORS = "enable_threat_heatmap_sensors"

# Controller types
CONTROLLER_TYPE_CLOUD = "cloud"
CONTROLLER_TYPE_LOCAL = "local"
CONTROLLER_TYPE_FUSION = "fusion"

# Auth modes
AUTH_MODE_OPENAPI = "openapi"
AUTH_MODE_WEB_SESSION = "web_session"
CONF_AUTH_MODE = "auth_mode"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# API constants
DEFAULT_TIMEOUT = 30
TOKEN_EXPIRY_BUFFER = 300  # Refresh token 5 minutes before expiry
ACCESS_TOKEN_LIFETIME = 7200  # 2 hours in seconds
REFRESH_TOKEN_LIFETIME = 1209600  # 14 days in seconds

# Regional API endpoints
REGIONS = {
    "us": {
        "name": "United States",
        "api_url": "https://use1-omada-northbound.tplinkcloud.com",
    },
    "eu": {
        "name": "Europe",
        "api_url": "https://euw1-omada-northbound.tplinkcloud.com",
    },
    "ap": {
        "name": "Asia Pacific (Singapore)",
        "api_url": "https://aps1-omada-northbound.tplinkcloud.com",
    },
}

# API endpoints
API_AUTHORIZE_TOKEN = "/openapi/authorize/token"
API_SITES = "/openapi/v1/{omada_id}/sites"
API_DEVICES = "/openapi/v1/{omada_id}/sites/{site_id}/devices"
API_CLIENTS = "/openapi/v2/{omada_id}/sites/{site_id}/clients"

# Update intervals (seconds)
SCAN_INTERVAL = 60  # Default for all coordinators
CONF_DEVICE_SCAN_INTERVAL = "device_scan_interval"
CONF_CLIENT_SCAN_INTERVAL = "client_scan_interval"
CONF_APP_SCAN_INTERVAL = "app_scan_interval"
DEFAULT_DEVICE_SCAN_INTERVAL = 60
DEFAULT_CLIENT_SCAN_INTERVAL = 30
DEFAULT_APP_SCAN_INTERVAL = 300
DEFAULT_FIRMWARE_CHECK_INTERVAL = 1800  # 30 minutes
DEFAULT_RADIO_UTIL_INTERVAL = 300  # 5 minutes
UPGRADE_POLL_INTERVAL = 10  # Fast polling during firmware upgrades
UPGRADE_COOLDOWN_POLLS = 3  # Extra fast-poll cycles after upgrade finishes
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

# Device types
DEVICE_TYPE_AP = "ap"
DEVICE_TYPE_GATEWAY = "gateway"
DEVICE_TYPE_SWITCH = "switch"

# Device stats
CONF_STATS_SCAN_INTERVAL = "stats_scan_interval"
DEFAULT_STATS_SCAN_INTERVAL = 300

# Threat heatmap — windows hard-coded for v1 (named so options can be added later).
THREAT_HEATMAP_SOURCE = "omada_open_api.security.threat-management"
THREAT_HEATMAP_HOURLY_INTERVAL = 300  # 5 minutes
THREAT_HEATMAP_DAILY_INTERVAL = 900  # 15 minutes
THREAT_HEATMAP_WEEKLY_INTERVAL = 3600  # 60 minutes
THREAT_HEATMAP_MONTHLY_INTERVAL = 21600  # 6 hours
THREAT_HEATMAP_INTERVALS: dict[str, int] = {
    "hourly": THREAT_HEATMAP_HOURLY_INTERVAL,
    "daily": THREAT_HEATMAP_DAILY_INTERVAL,
    "weekly": THREAT_HEATMAP_WEEKLY_INTERVAL,
    "monthly": THREAT_HEATMAP_MONTHLY_INTERVAL,
}

# WAN link speed enum → Mbps
WAN_SPEED_MAP: dict[int, int] = {
    1: 10,
    2: 100,
    3: 1000,
    4: 2500,
    5: 10000,
}

# Device icons
ICON_ACCESS_POINT = "mdi:access-point"
ICON_GATEWAY = "mdi:router-network"
ICON_SWITCH = "mdi:switch"
ICON_CLIENTS = "mdi:account-multiple"
ICON_UPTIME = "mdi:clock-outline"
ICON_CPU = "mdi:cpu-64-bit"
ICON_MEMORY = "mdi:memory"
ICON_FIRMWARE = "mdi:chip"
ICON_STATUS = "mdi:check-network"
ICON_LINK = "mdi:ethernet"
ICON_TAG = "mdi:tag"
ICON_DEVICE_TYPE = "mdi:devices"
ICON_SERIAL = "mdi:barcode"
ICON_POE = "mdi:flash"
ICON_DOWNLOAD = "mdi:download-network"
ICON_UPLOAD = "mdi:upload-network"
ICON_SIGNAL = "mdi:signal"
ICON_POWER_SAVE = "mdi:leaf"
ICON_IP = "mdi:ip-network"
ICON_TEMPERATURE = "mdi:thermometer"
ICON_WIFI = "mdi:wifi"
ICON_WIFI_OFF = "mdi:wifi-off"
ICON_WIFI_COG = "mdi:wifi-cog"
ICON_THREAT_HEATMAP = "mdi:map-marker-radius"
