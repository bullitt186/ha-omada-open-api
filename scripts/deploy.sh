#!/usr/bin/env bash
# Deploy the integration to the HA host and reload all config entries via API.
#
# Usage:
#   bash scripts/deploy.sh
#   HA_HOST=homeassistant.stahmer.lan HA_TOKEN=<token> bash scripts/deploy.sh
#
# Environment variables (in priority order):
#   HA_HOST   — hostname or IP of the HA instance (default: homeassistant.stahmer.lan)
#   HA_TOKEN  — long-lived access token (falls back to $HASS_TOKEN from .claude/settings.json)
set -euo pipefail

HA_HOST="${HA_HOST:-homeassistant.stahmer.lan}"
HA_TOKEN="${HA_TOKEN:-${HASS_TOKEN:-}}"
REMOTE_USER="${REMOTE_USER:-bullitt}"
REMOTE_PATH="/config/custom_components/omada_open_api"
ENTRY_DOMAIN="omada_open_api"

echo "🚀 Deploying omada_open_api → ${REMOTE_USER}@${HA_HOST}:${REMOTE_PATH}"

# Copy integration files to HA host
rsync -az --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  custom_components/omada_open_api/ \
  "${REMOTE_USER}@${HA_HOST}:${REMOTE_PATH}/"

echo "✅ Files synced."

if [ -z "$HA_TOKEN" ]; then
  echo "⚠️  HA_TOKEN / HASS_TOKEN not set — skipping API reload."
  echo "   Set HASS_TOKEN in .claude/settings.json or export HA_TOKEN=<token>"
  exit 0
fi

HA_API="http://${HA_HOST}:8123/api"

echo "🔄 Reloading config entries for domain '${ENTRY_DOMAIN}'..."

# Fetch all entry IDs for this integration domain
ENTRIES=$(curl -sf \
  -H "Authorization: Bearer ${HA_TOKEN}" \
  -H "Content-Type: application/json" \
  "${HA_API}/config/config_entries/entry?domain=${ENTRY_DOMAIN}" \
  | python3 -c "
import json, sys
entries = json.load(sys.stdin)
for e in entries:
    print(e['entry_id'])
")

if [ -z "$ENTRIES" ]; then
  echo "⚠️  No config entries found for '${ENTRY_DOMAIN}' — is the integration set up in HA?"
  exit 0
fi

for entry_id in $ENTRIES; do
  curl -sf -X POST \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    "${HA_API}/config/config_entries/${entry_id}/reload" > /dev/null
  echo "  ✅ Reloaded entry ${entry_id}"
done

echo ""
echo "🎉 Deploy complete. Verify entities at http://${HA_HOST}:8123"
