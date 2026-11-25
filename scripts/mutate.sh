#!/usr/bin/env bash
# Mutation testing with mutmut (configured in pyproject.toml, [tool.mutmut]).
#
# Usage:
#   scripts/mutate.sh               mutate modules changed against origin/main
#   scripts/mutate.sh --all         mutate the whole integration (slow)
#   scripts/mutate.sh MODULE.py...  mutate the given integration modules
#
# MUTATE_BASE overrides the base ref of the incremental run. Uncommitted and
# untracked changes count as changed. Results are cached in mutants/; delete
# that directory to start over.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

PKG_DIR="custom_components/omada_open_api"
PKG="custom_components.omada_open_api"

PYTHON="python3"
if [ -x ".venv/bin/python" ] && .venv/bin/python -c "" >/dev/null 2>&1; then
    PYTHON=".venv/bin/python"
fi

# Runs mutmut, then reports. mutmut can crash while exiting after all results
# are saved (seen as a segmentation fault on macOS); the run counts as
# complete when no selected mutant is left unchecked.
run_mutmut() {
    local status=0
    "$PYTHON" -m mutmut run ${patterns[@]+"${patterns[@]}"} || status=$?
    # mutmut fails when the filter matches no mutant, for example in a module
    # whose only functions are decorated (mutmut skips those).
    if [ "$status" -ne 0 ] && [ ${#modules[@]} -gt 0 ] &&
        "$PYTHON" scripts/mutation_report.py --no-mutants "${modules[@]}"; then
        echo "mutmut generated no mutants for ${modules[*]}; nothing to mutate."
        exit 0
    fi
    "$PYTHON" scripts/mutation_report.py "${report_args[@]}" || {
        echo "mutmut did not finish (exit code $status)." >&2
        exit "$(( status == 0 ? 1 : status ))"
    }
    if [ "$status" -ne 0 ]; then
        echo "Note: mutmut exited with code $status after saving all results." >&2
    fi
}

modules=()
if [ "${1:-}" = "--all" ]; then
    patterns=()
    report_args=(--check-complete)
    run_mutmut
    exit 0
fi

if [ $# -gt 0 ]; then
    modules=("$@")
else
    base="${MUTATE_BASE:-origin/main}"
    merge_base=$(git merge-base "$base" HEAD)
    modules=()
    while IFS= read -r file; do
        [ -f "$file" ] && modules+=("$file")
    done < <(
        {
            git diff --name-only "$merge_base" -- "$PKG_DIR"
            git ls-files --others --exclude-standard -- "$PKG_DIR"
        } | grep '\.py$' | sort -u
    )
    if [ ${#modules[@]} -eq 0 ]; then
        echo "No integration modules changed against $base; nothing to mutate."
        exit 0
    fi
fi

# mutmut names mutants <module path>.<function>__mutmut_<n>; functions are
# prefixed with "x_" and methods with "xǁ". __init__.py has no module part.
patterns=()
for file in "${modules[@]}"; do
    case "$file" in
        "$PKG_DIR"/*.py) ;;
        *)
            echo "Not an integration module: $file" >&2
            exit 1
            ;;
    esac
    # mutmut only mutates code inside functions and methods.
    if ! grep -Eq '^[[:space:]]*(async[[:space:]]+)?def ' "$file"; then
        echo "Skipping $file: no functions to mutate."
        continue
    fi
    name=$(basename "$file" .py)
    if [ "$name" = "__init__" ]; then
        patterns+=("$PKG.x_*" "$PKG.xǁ*")
    else
        patterns+=("$PKG.$name.*")
    fi
done

if [ ${#patterns[@]} -eq 0 ]; then
    echo "Nothing to mutate."
    exit 0
fi

echo "Mutating: ${modules[*]}"
report_args=(--check-complete "${modules[@]}")
run_mutmut
echo "List surviving mutants with 'make mutate-results'; inspect one with"
echo "'mutmut show <name>'."
