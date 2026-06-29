"""OpenBell Guard command-line entry point.

P4-05 implements the shared CLI plus the first bundle preflight gate:

- parse ``--bundle`` and ``--output``;
- verify that the bundle is an existing, non-symlink directory;
- reject unsupported top-level files, directories, and symlinks;
- enforce fixed file and bundle byte limits;
- verify UTF-8/UTF-8-BOM readability;
- validate the ``incident.json`` contract and optional ``service-map.json``.

It still does not mask inputs, parse telemetry records, compute metrics, or
create the final ``analysis.json``. Those behaviors belong to later Phase 4
steps and must keep using this entry point.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


EXIT_CODES = {
    "ok": 0,
    "input_error": 2,
    "security_block": 3,
    "limit_exceeded": 4,
    "output_validation_error": 5,
}

CLI_STAGE = "P4-05"
SUMMARY_FILENAME = "openbell-cli-summary.json"
SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "1.0.0"

MIB = 1024 * 1024
ALLOWED_BUNDLE_FILES = frozenset({"incident.json", "logs.jsonl", "metrics.csv", "service-map.json"})
FILE_BYTE_LIMITS = {
    "incident.json": 5 * MIB,
    "service-map.json": 5 * MIB,
    "logs.jsonl": 50 * MIB,
    "metrics.csv": 20 * MIB,
}
BUNDLE_BYTE_LIMIT = 80 * MIB
INCIDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STANDARD_SERVICE_PATHS = frozenset(
    {
        "auth_access",
        "market_data",
        "watchlist_info",
        "order_execution",
        "recurring_investment",
        "external_dependency",
    }
)
STANDARD_DEPENDENCY_TYPES = frozenset(
    {
        "internal",
        "exchange",
        "depository",
        "overseas_broker",
        "observability",
        "unknown",
    }
)
THRESHOLD_KEYS = frozenset(
    {
        "error_rate_pct_max",
        "p95_latency_ms_max",
        "p99_latency_ms_max",
        "ingestion_lag_p95_ms_max",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_openbell.py",
        description=(
            "Prepare an OpenBell Guard run directory. P4-05 validates the CLI, "
            "paths, bundle file contract, byte limits, and incident metadata; "
            "telemetry analysis is implemented later."
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


def issue_payload(
    *,
    exit_code: int,
    issue_code: str,
    message: str,
    argument: str,
    source_file: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "issue_code": issue_code,
        "severity": "fatal",
        "argument": argument,
        "message": message,
    }
    if source_file is not None:
        issue["source_file"] = source_file

    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "fatal",
        "exit_code": exit_code,
        "issues": [issue],
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
    if bundle_path.is_symlink():
        return issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP003_UNSUPPORTED_ENTRY",
            message="The --bundle directory must not be a symbolic link.",
            argument="bundle",
        )
    return None


def read_utf8_text(path: Path, source_file: str) -> tuple[str | None, dict[str, Any] | None]:
    try:
        return path.read_bytes().decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP004_ENCODING",
            message="The file must be readable as UTF-8 or UTF-8 with BOM.",
            argument="bundle",
            source_file=source_file,
        )
    except OSError:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP003_UNSUPPORTED_ENTRY",
            message="The file could not be read as a regular local file.",
            argument="bundle",
            source_file=source_file,
        )


def load_json_object(text: str, source_file: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="The JSON file is not valid JSON.",
            argument="bundle",
            source_file=source_file,
        )
    if not isinstance(payload, dict):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="The JSON file must contain a top-level object.",
            argument="bundle",
            source_file=source_file,
        )
    return payload, None


def parse_offset_datetime(value: Any, *, source_file: str) -> tuple[datetime | None, dict[str, Any] | None]:
    if not isinstance(value, str):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="Window timestamps must be ISO 8601 strings with an explicit offset.",
            argument="bundle",
            source_file=source_file,
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="Window timestamps must be valid ISO 8601 values.",
            argument="bundle",
            source_file=source_file,
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="Window timestamps must include an explicit UTC offset.",
            argument="bundle",
            source_file=source_file,
        )
    if parsed.second != 0 or parsed.microsecond != 0:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="Window timestamps must be aligned to minute boundaries.",
            argument="bundle",
            source_file=source_file,
        )
    return parsed, None


def validate_thresholds(thresholds: Any) -> dict[str, Any] | None:
    if thresholds is None:
        return None
    if not isinstance(thresholds, dict):
        return issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="incident.json thresholds must be an object when provided.",
            argument="bundle",
            source_file="incident.json",
        )
    for service_path, rule in thresholds.items():
        if service_path not in STANDARD_SERVICE_PATHS:
            return issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP005_SCHEMA",
                message="incident.json thresholds contain an unknown service_path.",
                argument="bundle",
                source_file="incident.json",
            )
        if not isinstance(rule, dict) or not rule:
            return issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP005_SCHEMA",
                message="Each thresholds service_path entry must be a non-empty object.",
                argument="bundle",
                source_file="incident.json",
            )
        for threshold_name, threshold_value in rule.items():
            if threshold_name not in THRESHOLD_KEYS:
                return issue_payload(
                    exit_code=EXIT_CODES["input_error"],
                    issue_code="INP005_SCHEMA",
                    message="incident.json thresholds contain an unknown threshold key.",
                    argument="bundle",
                    source_file="incident.json",
                )
            if isinstance(threshold_value, bool) or not isinstance(threshold_value, (int, float)):
                return issue_payload(
                    exit_code=EXIT_CODES["input_error"],
                    issue_code="INP005_SCHEMA",
                    message="Threshold values must be finite numbers.",
                    argument="bundle",
                    source_file="incident.json",
                )
            if not math.isfinite(float(threshold_value)):
                return issue_payload(
                    exit_code=EXIT_CODES["input_error"],
                    issue_code="INP005_SCHEMA",
                    message="Threshold values must be finite numbers.",
                    argument="bundle",
                    source_file="incident.json",
                )
            if threshold_name == "error_rate_pct_max":
                if float(threshold_value) < 0 or float(threshold_value) > 100:
                    return issue_payload(
                        exit_code=EXIT_CODES["input_error"],
                        issue_code="INP005_SCHEMA",
                        message="error_rate_pct_max must be between 0 and 100 inclusive.",
                        argument="bundle",
                        source_file="incident.json",
                    )
            elif float(threshold_value) < 0:
                return issue_payload(
                    exit_code=EXIT_CODES["input_error"],
                    issue_code="INP005_SCHEMA",
                    message="Latency and ingestion lag thresholds must be greater than or equal to 0.",
                    argument="bundle",
                    source_file="incident.json",
                )
    return None


def validate_incident(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("contract_version") != CONTRACT_VERSION:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="incident.json schema_version or contract_version is not supported.",
            argument="bundle",
            source_file="incident.json",
        )

    incident_id = payload.get("incident_id")
    if not isinstance(incident_id, str) or INCIDENT_ID_PATTERN.fullmatch(incident_id) is None:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="incident.json incident_id does not match the allowed pattern.",
            argument="bundle",
            source_file="incident.json",
        )

    timezone = payload.get("timezone")
    if not isinstance(timezone, str):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP006_TIMEZONE",
            message="incident.json timezone must be an IANA timezone string.",
            argument="bundle",
            source_file="incident.json",
        )
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP006_TIMEZONE",
            message="incident.json timezone could not be loaded as an IANA timezone.",
            argument="bundle",
            source_file="incident.json",
        )

    baseline_window = payload.get("baseline_window")
    incident_window = payload.get("incident_window")
    if not isinstance(baseline_window, dict) or not isinstance(incident_window, dict):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP005_SCHEMA",
            message="incident.json must include baseline_window and incident_window objects.",
            argument="bundle",
            source_file="incident.json",
        )

    baseline_start, issue = parse_offset_datetime(baseline_window.get("start"), source_file="incident.json")
    if issue is not None:
        return None, issue
    baseline_end, issue = parse_offset_datetime(baseline_window.get("end"), source_file="incident.json")
    if issue is not None:
        return None, issue
    incident_start, issue = parse_offset_datetime(incident_window.get("start"), source_file="incident.json")
    if issue is not None:
        return None, issue
    incident_end, issue = parse_offset_datetime(incident_window.get("end"), source_file="incident.json")
    if issue is not None:
        return None, issue

    assert baseline_start is not None
    assert baseline_end is not None
    assert incident_start is not None
    assert incident_end is not None

    baseline_seconds = int((baseline_end - baseline_start).total_seconds())
    incident_seconds = int((incident_end - incident_start).total_seconds())
    if baseline_seconds < 60:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="baseline_window must be at least 60 seconds and end after start.",
            argument="bundle",
            source_file="incident.json",
        )
    if incident_seconds < 120:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="incident_window must be at least 120 seconds and end after start.",
            argument="bundle",
            source_file="incident.json",
        )
    if baseline_end > incident_start:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP007_WINDOW",
            message="baseline_window must not overlap incident_window.",
            argument="bundle",
            source_file="incident.json",
        )

    issue = validate_thresholds(payload.get("thresholds"))
    if issue is not None:
        return None, issue

    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    return (
        {
            "incident_id": incident_id,
            "timezone": timezone,
            "baseline_window_seconds": baseline_seconds,
            "incident_window_seconds": incident_seconds,
            "threshold_service_paths": sorted(thresholds),
        },
        None,
    )


def validate_service_map(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    services = payload.get("services")
    if not isinstance(services, list):
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP009_SERVICE_MAP",
            message="service-map.json must include a services array.",
            argument="bundle",
            source_file="service-map.json",
        )

    seen_names: set[str] = set()
    dependency_refs: list[tuple[str, str]] = []
    for service in services:
        if not isinstance(service, dict):
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="Each service-map.json service must be an object.",
                argument="bundle",
                source_file="service-map.json",
            )
        service_name = service.get("service_name")
        service_path = service.get("service_path")
        dependency_type = service.get("dependency_type")
        if not isinstance(service_name, str) or not service_name.strip() or len(service_name.strip()) > 128:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="Each service-map.json service must have a 1 to 128 character service_name.",
                argument="bundle",
                source_file="service-map.json",
            )
        service_name = service_name.strip()
        if service_name in seen_names:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="service-map.json service_name values must be unique.",
                argument="bundle",
                source_file="service-map.json",
            )
        seen_names.add(service_name)
        if service_path not in STANDARD_SERVICE_PATHS:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="service-map.json contains an unknown service_path.",
                argument="bundle",
                source_file="service-map.json",
            )
        if dependency_type not in STANDARD_DEPENDENCY_TYPES:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="service-map.json contains an unknown dependency_type.",
                argument="bundle",
                source_file="service-map.json",
            )
        dependencies = service.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="service-map.json dependencies must be an array of service_name strings.",
                argument="bundle",
                source_file="service-map.json",
            )
        dependency_refs.extend((service_name, dependency_name) for dependency_name in dependencies)

    for service_name, dependency_name in dependency_refs:
        if dependency_name not in seen_names:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP009_SERVICE_MAP",
                message="service-map.json dependencies must reference services in the same file.",
                argument="bundle",
                source_file="service-map.json",
            )

    return {"provided": True, "service_count": len(services)}, None


def validate_bundle_preflight(bundle_path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        entries = list(bundle_path.iterdir())
    except OSError:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP003_UNSUPPORTED_ENTRY",
            message="The --bundle directory could not be listed.",
            argument="bundle",
        )

    file_paths: dict[str, Path] = {}
    for entry in entries:
        if entry.name not in ALLOWED_BUNDLE_FILES or entry.is_symlink() or not entry.is_file():
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP003_UNSUPPORTED_ENTRY",
                message="The bundle contains an unsupported file, directory, or symbolic link.",
                argument="bundle",
                source_file=entry.name,
            )
        file_paths[entry.name] = entry

    if "incident.json" not in file_paths:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP001_MISSING_INCIDENT",
            message="incident.json is required.",
            argument="bundle",
            source_file="incident.json",
        )
    if "logs.jsonl" not in file_paths and "metrics.csv" not in file_paths:
        return None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP002_NO_TELEMETRY",
            message="At least one of logs.jsonl or metrics.csv is required.",
            argument="bundle",
        )

    file_sizes: dict[str, int] = {}
    for file_name, path in file_paths.items():
        try:
            file_sizes[file_name] = path.stat().st_size
        except OSError:
            return None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP003_UNSUPPORTED_ENTRY",
                message="A bundle file could not be inspected.",
                argument="bundle",
                source_file=file_name,
            )
        if file_sizes[file_name] > FILE_BYTE_LIMITS[file_name]:
            return None, issue_payload(
                exit_code=EXIT_CODES["limit_exceeded"],
                issue_code="LIM001_FILE_BYTES",
                message="A bundle file exceeds its supported byte limit.",
                argument="bundle",
                source_file=file_name,
            )

    total_bytes = sum(file_sizes.values())
    if total_bytes > BUNDLE_BYTE_LIMIT:
        return None, issue_payload(
            exit_code=EXIT_CODES["limit_exceeded"],
            issue_code="LIM004_BUNDLE_BYTES",
            message="The bundle exceeds its supported total byte limit.",
            argument="bundle",
        )

    decoded_files: dict[str, str] = {}
    for file_name, path in sorted(file_paths.items()):
        text, issue = read_utf8_text(path, file_name)
        if issue is not None:
            return None, issue
        assert text is not None
        decoded_files[file_name] = text

    incident_payload, issue = load_json_object(decoded_files["incident.json"], "incident.json")
    if issue is not None:
        return None, issue
    assert incident_payload is not None
    incident_summary, issue = validate_incident(incident_payload)
    if issue is not None:
        return None, issue
    assert incident_summary is not None

    service_map_summary = {"provided": False, "service_count": 0}
    if "service-map.json" in decoded_files:
        service_map_payload, issue = load_json_object(decoded_files["service-map.json"], "service-map.json")
        if issue is not None:
            return None, issue
        assert service_map_payload is not None
        service_map_summary, issue = validate_service_map(service_map_payload)
        if issue is not None:
            return None, issue
        assert service_map_summary is not None

    return (
        {
            "files": [{"name": file_name, "bytes": file_sizes[file_name]} for file_name in sorted(file_sizes)],
            "total_bytes": total_bytes,
            "incident": incident_summary,
            "service_map": service_map_summary,
        },
        None,
    )


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


def success_payload(*, bundle_path: Path, preflight_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "bundle_preflight_ready",
        "exit_code": EXIT_CODES["ok"],
        "bundle": {
            "name": bundle_path.name,
            "path_kind": "directory",
            "preflight": preflight_summary,
            "raw_telemetry_records_parsed": False,
            "raw_excerpts_emitted": False,
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
            "validate allowed bundle files",
            "enforce file and bundle byte limits",
            "validate UTF-8 readability",
            "validate incident metadata and windows",
            "validate service-map structure when provided",
        ],
        "deferred_scope": [
            "secret masking",
            "telemetry record parsing",
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

    preflight_summary, issue = validate_bundle_preflight(bundle_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert preflight_summary is not None

    issue = validate_and_prepare_output(bundle_path=bundle_path, output_path=output_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    payload = success_payload(bundle_path=bundle_path, preflight_summary=preflight_summary)
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
