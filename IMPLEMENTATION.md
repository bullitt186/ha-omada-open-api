st# OAuth2 Implementation Summary

## Overview
Complete OAuth2 Client Credentials authentication flow implemented for the Omada Open API integration, following Home Assistant best practices and coding standards.

## Implemented Features

### 1. Config Flow (config_flow.py)
Multi-step configuration flow with the following steps:

#### Step 1: Controller Type Selection
- Choose between Cloud Controller or Local/Self-Hosted Controller
- Sets up proper routing for subsequent steps

#### Step 2a: Cloud Controller - Region Selection
- Select region (US, EU, or Asia-Pacific)
- Automatically sets the correct regional API endpoint

#### Step 2b: Local Controller - URL Input
- Enter custom controller URL (domain or IP)
- Validates URL format (http/https required)

#### Step 3: OAuth2 Credentials
- Input Omada ID, Client ID, and Client Secret
- Automatically fetches OAuth2 access token using Client Credentials grant
- Stores access token, refresh token, and expiration time
- Error handling for connection and authentication failures

#### Step 4: Site Selection
- Retrieves all available sites from the controller
- Multi-select dropdown to choose which sites to monitor
- Validates that at least one site is selected

#### Step 5: Reauth Flow
- Triggered when refresh token expires (after 14 days)
- User re-enters Client ID and Client Secret
- Automatically refreshes tokens without reconfiguring sites

### 2. API Client (api.py)
Robust API client with automatic token management:

#### Features:
- **Automatic Token Refresh**: Checks token expiration before every API call
- **5-Minute Buffer**: Refreshes tokens 5 minutes before expiry to prevent race conditions
- **Thread-Safe**: Uses asyncio.Lock to prevent concurrent refresh attempts
- **Token Lifecycle**:
  - Access Token: Valid for 2 hours
  - Refresh Token: Valid for 14 days
- **Error Handling**: Raises `OmadaApiAuthError` for authentication failures

#### Methods:
- `_ensure_valid_token()`: Checks and refreshes token as needed
- `_refresh_access_token()`: Performs token refresh using refresh_token grant
- `get_sites()`: Fetches all sites with automatic token refresh and retry on 401

### 3. Integration Setup (__init__.py)
Proper integration lifecycle management:

#### Features:
- Creates API client from stored configuration
- Tests connection by fetching sites during setup
- Triggers reauth flow if tokens are invalid (`ConfigEntryAuthFailed`)
- Stores API client in `hass.data[DOMAIN]` for entity platforms
- Proper cleanup on unload

### 4. Constants (const.py)
Centralized configuration:

#### Regional Endpoints:
- **US**: use1-omada-northbound.tplinkcloud.com
- **EU**: euw1-omada-northbound.tplinkcloud.com
- **Asia-Pacific**: aps1-omada-northbound.tplinkcloud.com

#### Token Configuration:
- Access token lifetime: 7200 seconds (2 hours)
- Refresh token lifetime: 1,209,600 seconds (14 days)
- Token expiry buffer: 300 seconds (5 minutes)

### 5. UI Strings (strings.json)
Complete translation strings for all config flow steps:

- User-friendly labels and descriptions
- Error messages for common failures
- Abort messages for special cases
- Placeholders and suggestions for input fields

## OAuth2 Flow Details

### Client Credentials Grant
The implementation uses the **Client Credentials** OAuth2 flow:

```
1. User provides: Omada ID, Client ID, Client Secret
2. Integration requests token from /openapi/authorize/token
3. API returns: access_token, refresh_token, expires_in
4. Integration calculates expiration time and stores all tokens
```

### Token Refresh Flow
Automatic token refresh happens transparently:

```
1. Before API call, check if token expires within 5 minutes
2. If yes, use refresh_token to get new access_token
3. Update stored tokens with new values
4. Proceed with original API call
```

### Reauth Flow
When refresh token expires (14 days):

```
1. API returns 401 Unauthorized
2. Integration raises ConfigEntryAuthFailed
3. Home Assistant triggers reauth notification
4. User clicks notification and re-enters credentials
5. Integration gets new tokens and resumes normal operation
```

## Architecture Decisions

### 1. Client Credentials vs Authorization Code
- **Chosen**: Client Credentials
- **Reason**: Simpler flow, no user login required, suitable for API-to-API communication
- **Trade-off**: Requires storing credentials, but tokens auto-refresh

### 2. Local Controller Support
- **Primary Focus**: Self-hosted controllers with custom URLs
- **Cloud Support**: Also supports TP-Link cloud regional endpoints
- **Flexibility**: Users choose deployment type during setup

### 3. Automatic Token Refresh
- **Chosen**: Automatic refresh with 5-minute buffer
- **Reason**: Best user experience, no manual intervention
- **Fallback**: Reauth flow when refresh token expires

### 4. Site Selection
- **Chosen**: Multi-select during config flow
- **Reason**: Users may not want to monitor all sites
- **Future**: Could add options flow to modify site selection

## File Structure
```
custom_components/omada_open_api/
├── __init__.py          # Integration setup/teardown
├── api.py               # API client with token management
├── config_flow.py       # Multi-step OAuth2 config flow
├── const.py             # Constants and endpoints
├── manifest.json        # Integration metadata
└── strings.json         # UI translations
```

## Code Quality
All code passes:
- ✅ Ruff linting (no errors)
- ✅ Ruff formatting
- ✅ Full type hints (Python 3.11+)
- ✅ Home Assistant coding standards
- ✅ Async/await patterns
- ✅ Proper error handling
- ✅ Type-checking blocks for imports

## Next Steps

### 1. Create Platform Entities
- Sensors for device counts, bandwidth, uptime
- Binary sensors for device online/offline status
- Device trackers for connected clients
- Switches for PoE control, guest network toggle

### 2. Implement DataUpdateCoordinator
- Centralized data fetching for all entities
- Configurable polling interval (recommended 30-60 seconds)
- Proper error handling and recovery

### 3. Write Tests
- Unit tests for config flow steps
- Integration tests for setup/unload
- Mock API responses for testing
- Test token refresh and reauth flows

### 4. Documentation
- User guide for obtaining OAuth2 credentials
- Setup instructions for cloud and local controllers
- Troubleshooting guide

### 5. Optional Enhancements
- Options flow for modifying site selection
- Service actions for device control
- Diagnostic sensors for controller health
- Support for multiple controllers

## References
- [Home Assistant Config Flow Documentation](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- [Omada Open API Documentation](https://use1-omada-northbound.tplinkcloud.com/doc.html#/home)
- [Home Assistant Coding Standards](https://developers.home-assistant.io/docs/development_guidelines)
