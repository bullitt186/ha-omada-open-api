## What's New in v1.5.1

### Improvements

- Improved error diagnostics during setup: connection timeouts, DNS resolution failures, and connection refused errors now show specific, actionable guidance instead of a generic "cannot connect" message
- Enhanced error messages for authentication failures with clearer instructions on where to find the correct Omada ID
- Reduced log noise during expected connection errors (uses warning level instead of full stack traces)

### Bug Fixes

- Client coordinator now fetches all clients (including offline/blocked) so blocked clients remain available for control actions like unblocking via switch entities
