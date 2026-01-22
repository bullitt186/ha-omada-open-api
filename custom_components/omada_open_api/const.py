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

# Update intervals
SCAN_INTERVAL = 60  # seconds
