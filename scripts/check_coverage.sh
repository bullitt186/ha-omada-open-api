#!/usr/bin/env bash
# Pre-commit hook: fail if code coverage drops below the stored baseline.
# The baseline is kept in .coverage-threshold (a single integer).
set -euo pipefail

THRESHOLD_FILE=".coverage-threshold"

# Run pytest with coverage and capture the total percentage.
output=$(pytest tests/ -x -q \
    --cov=custom_components.omada_open_api \
    --cov-report=term-missing 2>&1) || {
    echo "$output"
    echo ""
    echo "❌ Tests failed — commit blocked."
    exit 1
}

# Extract "TOTAL ... NN%" from the coverage summary line.
current=$(echo "$output" | grep '^TOTAL' | awk '{print $NF}' | tr -d '%')

if [ -z "$current" ]; then
    echo "$output"
    echo ""
    echo "⚠️  Could not parse coverage percentage — letting commit through."
    exit 0
fi

# Read the stored baseline (default 0 if file missing).
if [ -f "$THRESHOLD_FILE" ]; then
    baseline=$(cat "$THRESHOLD_FILE" | tr -d '[:space:]')
else
    baseline=0
fi

echo "Coverage: ${current}% (baseline: ${baseline}%)"

if [ "$current" -lt "$baseline" ]; then
    echo ""
    echo "❌ Coverage dropped from ${baseline}% to ${current}% — commit blocked."
    echo "   Add tests to restore coverage, or update ${THRESHOLD_FILE} if intentional."
    exit 1
fi

# Update baseline if coverage increased.
if [ "$current" -gt "$baseline" ]; then
    echo "$current" > "$THRESHOLD_FILE"
    git add "$THRESHOLD_FILE"
    echo "✅ Baseline updated: ${baseline}% → ${current}%"
else
    echo "✅ Coverage unchanged."
fi
