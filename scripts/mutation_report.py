#!/usr/bin/env python3
"""Summarize mutmut results per integration module.

Reads the ``mutants/**/*.py.meta`` files that ``mutmut run`` writes and prints
one row per module plus a total. The score follows mutmut's own badge formula:
killed and timed-out mutants divided by all checked, non-skipped mutants.
Mutants that were never checked are counted separately and left out of the
score, so the score of an incremental run covers only the modules it mutated.

Usage:
    python scripts/mutation_report.py [--markdown] [--json FILE]
        [--check-complete] [MODULE.py ...]

With --check-complete, the exit code is 1 when a given module still has
unchecked mutants, which means the mutmut run did not finish.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

MUTANTS_DIR = Path("mutants")
PACKAGE_DIR = Path("custom_components/omada_open_api")

# Exit codes mutmut stores per mutant, mapped to the status names it reports.
STATUS_BY_EXIT_CODE = {
    0: "survived",
    1: "killed",
    3: "killed",
    5: "no tests",
    33: "no tests",
    34: "skipped",
    36: "timeout",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
    255: "timeout",
    37: "killed",
}
COLUMNS = (
    "killed",
    "survived",
    "no tests",
    "timeout",
    "suspicious",
    "skipped",
    "not checked",
)


def status_counts(meta_path: Path) -> Counter[str]:
    """Count the mutants of one module by status."""
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    for exit_code in data.get("exit_code_by_key", {}).values():
        if exit_code is None:
            counts["not checked"] += 1
        else:
            counts[STATUS_BY_EXIT_CODE.get(exit_code, "suspicious")] += 1
    return counts


def score(counts: Counter[str]) -> float | None:
    """Return the mutation score in percent, or None without checked mutants."""
    tested = sum(counts.values()) - counts["skipped"] - counts["not checked"]
    if tested <= 0:
        return None
    return 100 * (counts["killed"] + counts["timeout"]) / tested


def collect(modules: list[str]) -> dict[str, Counter[str]]:
    """Collect status counts for the given module files, or for all modules."""
    if modules:
        metas = [MUTANTS_DIR / f"{module}.meta" for module in modules]
    else:
        metas = sorted((MUTANTS_DIR / PACKAGE_DIR).glob("*.py.meta"))
    result: dict[str, Counter[str]] = {}
    for meta in metas:
        if not meta.exists():
            continue
        counts = status_counts(meta)
        if counts:
            result[meta.name.removesuffix(".meta")] = counts
    return result


def render(rows: dict[str, Counter[str]], *, markdown: bool) -> str:
    """Render the per-module table and the total."""
    total: Counter[str] = Counter()
    for counts in rows.values():
        total.update(counts)
    header = ("module", *COLUMNS, "score")
    lines = []
    for name, counts in [*rows.items(), ("TOTAL", total)]:
        value = score(counts)
        cells = (
            name,
            *(str(counts[column]) for column in COLUMNS),
            "n/a" if value is None else f"{value:.1f}%",
        )
        lines.append(cells)
    if markdown:
        out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        out += ["| " + " | ".join(cells) + " |" for cells in lines]
        return "\n".join(out)
    widths = [max(len(row[i]) for row in [header, *lines]) for i in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        for row in [header, *lines]
    )


def main() -> int:
    """Print the report and optionally write the totals as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("modules", nargs="*", help="module paths, e.g. .../api.py")
    parser.add_argument("--markdown", action="store_true", help="render Markdown")
    parser.add_argument("--json", type=Path, help="write the totals to this file")
    parser.add_argument(
        "--check-complete",
        action="store_true",
        help="exit with 1 when a module has unchecked mutants",
    )
    args = parser.parse_args()

    rows = collect(args.modules)
    if not rows:
        sys.stdout.write("No mutation results found. Run mutmut first.\n")
        return 1 if args.check_complete else 0
    sys.stdout.write(render(rows, markdown=args.markdown) + "\n")
    if args.json:
        total: Counter[str] = Counter()
        for counts in rows.values():
            total.update(counts)
        args.json.write_text(
            json.dumps(
                {
                    "modules": {name: dict(counts) for name, counts in rows.items()},
                    "total": dict(total),
                    "score": score(total),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.check_complete and any(c["not checked"] for c in rows.values()):
        sys.stdout.write("Some mutants were not checked; the run did not finish.\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
