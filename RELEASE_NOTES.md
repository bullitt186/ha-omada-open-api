## What's New in v1.8.0

### Features

- **Fusion Gateway support**: Added "Fusion Gateway (Built-in Controller)" as a third controller type in the setup flow. Fusion gateways use web-login authentication (username/password) instead of OAuth client credentials, and can now be monitored alongside traditional Omada controllers in the same Home Assistant instance.
- **Auth strategy architecture**: Introduced pluggable authentication via `OmadaAuthStrategy` pattern, supporting both `ClientCredentialsAuth` (traditional) and `WebSessionAuth` (Fusion) modes transparently.
- **v2-to-v1 client endpoint fallback**: The integration now gracefully handles Fusion firmware that returns error `-1600` on the v2 clients endpoint by permanently falling back to the v1 GET-based endpoint.
- **Single-site auto-detection**: Fusion gateways with a single site are auto-selected during setup, and a runtime fallback handles site ID changes after firmware updates.

### Improvements

- API client now accepts JSON responses regardless of Content-Type header, improving compatibility with Fusion firmware that omits the header.
- Config flow uses a dedicated session with unsafe cookie jar for IP-based controller URLs, fixing session persistence issues with self-signed certificates.
