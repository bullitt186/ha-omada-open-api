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

# Controller types
CONTROLLER_TYPE_CLOUD = "cloud"
CONTROLLER_TYPE_LOCAL = "local"

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

# Update intervals
SCAN_INTERVAL = 60  # seconds

# Device types
DEVICE_TYPE_AP = "ap"
DEVICE_TYPE_GATEWAY = "gateway"
DEVICE_TYPE_SWITCH = "switch"

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
