"""OpenBell Guard command-line entry point.

P4-04 intentionally implements only the thin CLI skeleton:

- parse ``--bundle`` and ``--output``;
- verify that the bundle path is an existing directory;
- verify that output can be created and written outside the input bundle;
- emit a small CLI smoke summary.

It does not read telemetry file contents, mask inputs, compute metrics, or
create the final ``analysis.json``. Those behaviors belong to later Phase 4
steps and must keep using this entry point.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXIT_CODES = {
    "ok": 0,
    "input_error": 2,
    "security_block": 3,
    "limit_exceeded": 4,
    "output_validation_error": 5,
}

CLI_STAGE = "P4-04"
SUMMARY_FILENAME = "openbell-cli-summary.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_openbell.py",
        description=(
            "Prepare an OpenBell Guard run directory. P4-04 validates only the "
            "CLI entry point and paths; telemetry analysis is implemented later."
        ),
    )
    parser.add_argument(
        "--bundle",
        required=True,
        help="Path to a synthetic or anonymized incident bundle directory.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory where OpenBell Guard should write generated outputs.",
    )
    return parser


def issue_payload(*, exit_code: int, issue_code: str, message: str, argument: str) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "fatal",
        "exit_code": exit_code,
        "issues": [
            {
                "issue_code": issue_code,
                "severity": "fatal",
                "argument": argument,
                "message": message,
            }
        ],
    }


def write_stderr_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)


def validate_bundle_path(bundle_path: Path) -> dict[str, Any] | None:
    if not bundle_path.exists():
        return issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="CLI001_BUNDLE_NOT_FOUND",
            message="The --bundle path does not exist.",
            argument="bundle",
        )
    if not bundle_path.is_dir():
        return issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="CLI002_BUNDLE_NOT_DIRECTORY",
            message="The --bundle path must be a directory.",
            argument="bundle",
        )
    return None


def path_overlaps_bundle(*, bundle_path: Path, output_path: Path) -> bool:
    bundle_resolved = bundle_path.resolve(strict=False)
    output_resolved = output_path.resolve(strict=False)
    return output_resolved == bundle_resolved or bundle_resolved in output_resolved.parents


def validate_and_prepare_output(*, bundle_path: Path, output_path: Path) -> dict[str, Any] | None:
    if path_overlaps_bundle(bundle_path=bundle_path, output_path=output_path):
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI011_OUTPUT_OVERLAPS_BUNDLE",
            message="The --output directory must not be the bundle directory or a child of it.",
            argument="output",
        )

    if output_path.exists() and not output_path.is_dir():
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI010_OUTPUT_NOT_DIRECTORY",
            message="The --output path exists but is not a directory.",
            argument="output",
        )

    try:
        output_path.mkdir(parents=True, exist_ok=True)
        probe_path = output_path / ".openbell_write_probe"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI012_OUTPUT_WRITE_FAILED",
            message="The --output directory could not be created or written.",
            argument="output",
        )

    return None


def success_payload(*, bundle_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "cli_ready",
        "exit_code": EXIT_CODES["ok"],
        "bundle": {
            "name": bundle_path.name,
            "path_kind": "directory",
            "raw_telemetry_files_read": False,
        },
        "outputs": {
            "summary_file": SUMMARY_FILENAME,
            "analysis_json_created": False,
            "sanitization_report_created": False,
        },
        "implemented_scope": [
            "parse --bundle and --output",
            "validate bundle directory existence",
            "create writable output directory",
        ],
        "deferred_scope": [
            "bundle file validation",
            "secret masking",
            "telemetry parsing",
            "metric calculation",
            "analysis.json generation",
        ],
        "exit_code_skeleton": EXIT_CODES,
    }


def write_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI013_SUMMARY_WRITE_FAILED",
            message="The CLI summary file could not be written.",
            argument="output",
        )
    return None


def run(bundle_arg: str, output_arg: str) -> int:
    bundle_path = Path(bundle_arg)
    output_path = Path(output_arg)

    issue = validate_bundle_path(bundle_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    issue = validate_and_prepare_output(bundle_path=bundle_path, output_path=output_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    payload = success_payload(bundle_path=bundle_path)
    issue = write_summary(output_path=output_path, payload=payload)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return EXIT_CODES["ok"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.bundle, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
