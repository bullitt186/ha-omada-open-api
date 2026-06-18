#!/usr/bin/env bash
# Deploy the integration to the devcontainer HA instance and restart HA so the
# new code is actually picked up.
#
# A config-entry *reload* is NOT enough: HA reuses the already-imported Python
# module from sys.modules and re-runs setup on it — it does not re-read the
# .py files from disk. Only a full HA restart re-imports the module, so a
# reload-only deploy can silently keep running the old code while looking
# like it succeeded.
#
# This script is ONLY for use inside the devcontainer (or when HA is running locally).
# It NEVER writes to any remote host.
#
# Usage (inside devcontainer):
#   bash scripts/deploy.sh
#
# Environment variables:
#   HA_URL    — HA base URL (default: http://localhost:8123)
#   HA_TOKEN  — long-lived access token (falls back to $HASS_TOKEN)
#   HA_CONFIG — path to HA config dir (default: /config)
set -euo pipefail

HA_URL="${HA_URL:-http://localhost:8123}"
HA_TOKEN="${HA_TOKEN:-${HASS_TOKEN:-}}"
HA_CONFIG="${HA_CONFIG:-/config}"
DEST="${HA_CONFIG}/custom_components/omada_open_api"

# Safety check: refuse to run if HA_URL points to anything other than localhost/127.0.0.1
# or the docker-compose service hostname 'homeassistant'.
if echo "$HA_URL" | grep -qvE '^https?://(localhost|127\.0\.0\.1|homeassistant)(:[0-9]+)?'; then
  echo "❌ ERROR: HA_URL='$HA_URL' does not point to a local HA instance."
  echo "   This script only deploys to the local devcontainer HA instance."
  echo "   Do NOT use this script to deploy to a remote/production HA host."
  exit 1
fi

# Safety check: /config must exist (we're inside the devcontainer)
if [ ! -d "$HA_CONFIG" ]; then
  echo "❌ ERROR: HA config directory '$HA_CONFIG' not found."
  echo "   Run this script inside the devcontainer where HA is running locally."
  exit 1
fi

echo "🚀 Deploying omada_open_api → ${DEST}"

# Copy integration files using local cp (no SSH, no rsync to remote)
rm -rf "${DEST}"
cp -r custom_components/omada_open_api "${DEST}"
find "${DEST}" -name "*.pyc" -delete
find "${DEST}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "✅ Files copied to ${DEST}"

if [ -z "$HA_TOKEN" ]; then
  echo "⚠️  HA_TOKEN / HASS_TOKEN not set — skipping restart."
  echo "   Set HASS_TOKEN in .claude/settings.json or export HA_TOKEN=<token>"
  exit 0
fi

HA_API="${HA_URL}/api"

echo "🔄 Restarting Home Assistant so the new code is re-imported..."

curl -sf -X POST \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "${HA_API}/services/homeassistant/restart" > /dev/null

echo "⏳ Waiting for HA to come back up..."

for _ in $(seq 1 30); do
  sleep 2
  if curl -sf -o /dev/null "${HA_URL}/"; then
    echo ""
    echo "🎉 Deploy complete. HA is back up at ${HA_URL}"
    exit 0
  fi
done

echo "⚠️  HA did not respond within 60s after restart — check manually."
exit 1
