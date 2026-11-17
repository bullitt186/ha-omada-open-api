#!/usr/bin/env bash
# Claude Code Stop hook: run the fast quality check before an agent stops.
#
# Reads the hook input (JSON) from stdin. Exits 0 when there is nothing to
# check or every check passes. Exits 2 with a short summary on stderr when a
# check fails, which makes Claude Code continue working on the findings.
# Mutation testing and Pylint are not part of this check; `make check` and
# `make mutate` cover them.
set -uo pipefail

input=$(cat)

# A Stop hook that already sent the agent back must not loop forever.
if printf '%s' "$input" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}" || exit 0

if [ -z "$(git status --porcelain 2>/dev/null)" ]; then
    exit 0
fi

# The checks need the project venv (`make install` or the devcontainer). A
# host-side .venv can point to a Python that exists only in the devcontainer;
# then the check is skipped instead of reporting false failures.
if ! .venv/bin/python -c "import homeassistant" >/dev/null 2>&1; then
    echo "Fast check skipped: no working .venv in $PWD (run make install)." >&2
    exit 0
fi

failed=()
log=$(mktemp)
trap 'rm -f "$log"' EXIT

run_check() {
    local name=$1 exe=".venv/bin/$2"
    shift 2
    if ! "$exe" "$@" >"$log" 2>&1; then
        failed+=("$name")
        {
            echo "--- $name failed:"
            tail -n 25 "$log"
        } >&2
    fi
}

run_check "ruff check" ruff check custom_components/ tests/
run_check "ruff format" ruff format --check custom_components/ tests/
run_check "mypy" mypy --config-file pyproject.toml custom_components/omada_open_api/
run_check "pytest" pytest tests/ -x -q --tb=short -n auto

if [ ${#failed[@]} -gt 0 ]; then
    echo "Fast check failed: ${failed[*]}. Fix the findings before stopping." >&2
    exit 2
fi
exit 0
