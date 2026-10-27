#!/usr/bin/env bash
# Fail if any integration module is below the per-module coverage minimum.
# The Platinum quality scale (test-coverage rule) requires >95% per module,
# not only in total. Reads the .coverage data of the preceding pytest run and
# compares exact percentages (coverage rounds 94.5% up to 95% by default).
set -euo pipefail

MIN="${MIN_MODULE_COVERAGE:-95}"

COVERAGE_CMD="coverage"
if [ -x ".venv/bin/coverage" ]; then
    COVERAGE_CMD=".venv/bin/coverage"
fi

$COVERAGE_CMD report --precision=2 | awk -v min="$MIN" '
    $1 ~ /\.py$/ {
        pct = $NF; sub(/%/, "", pct)
        if (pct + 0 < min + 0) { printf "❌ %s: %s%% < %s%%\n", $1, pct, min; bad = 1 }
    }
    END {
        if (bad) { print "Per-module coverage below minimum."; exit 1 }
        printf "✅ Every module has at least %s%% coverage.\n", min
    }'
