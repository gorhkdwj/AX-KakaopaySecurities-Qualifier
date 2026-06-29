"""Validate OpenBell Guard generated outputs.

This thin CLI wrapper reuses the P4-15 output validation functions from
``run_openbell.py``. It validates an already generated output directory before
later workflow steps use ``analysis.json`` to create a human-readable report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import run_openbell


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_bundle.py",
        description=(
            "Validate OpenBell Guard output files. P4-15 checks analysis.json "
            "schema, evidence references, confirmed_fact evidence, claim markers, "
            "and sensitive residue in generated outputs."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory produced by run_openbell.py.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary, issue = run_openbell.validate_output_directory(output_path=Path(args.output), write_report=True)
    if issue is not None:
        run_openbell.write_stderr_json(issue)
        return int(issue["exit_code"])
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return run_openbell.EXIT_CODES["ok"]


if __name__ == "__main__":
    raise SystemExit(main())
