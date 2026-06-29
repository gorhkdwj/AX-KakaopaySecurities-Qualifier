"""OpenBell Guard command-line entry point.

P4-08 implements the shared CLI, bundle preflight gate, sanitizer,
line-oriented telemetry parser, and 60-second bucket preparation:

- parse ``--bundle`` and ``--output``;
- verify that the bundle is an existing, non-symlink directory;
- reject unsupported top-level files, directories, and symlinks;
- enforce fixed file and bundle byte limits;
- verify UTF-8/UTF-8-BOM readability;
- validate the ``incident.json`` contract and optional ``service-map.json``.
- create a masked working copy and ``sanitization-report.md``.
- parse sanitized ``logs.jsonl`` and ``metrics.csv`` rows into a record summary.
- assign accepted in-window rows to UTC 60-second service-path buckets.

It still does not compute metrics or create the final ``analysis.json``. Those
behaviors belong to later Phase 4 steps and must keep using this entry point.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from datetime import datetime, timezone
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

CLI_STAGE = "P4-08"
SUMMARY_FILENAME = "openbell-cli-summary.json"
SANITIZED_BUNDLE_DIR = "sanitized-bundle"
SANITIZATION_REPORT = "sanitization-report.md"
RECORD_SUMMARY_FILENAME = "record-summary.json"
BUCKET_SUMMARY_FILENAME = "bucket-summary.json"
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
LOG_RECORD_LIMIT = 100_000
METRIC_RECORD_LIMIT = 50_000
JSONL_RECORD_BYTE_LIMIT = 1 * MIB
INCIDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
LOG_REQUIRED_FIELDS = frozenset({"event_time", "service_name", "service_path", "status"})
LOG_OPTIONAL_FIELDS = frozenset(
    {
        "observed_time",
        "latency_ms",
        "dependency_type",
        "trace_id",
        "log_type",
        "severity",
        "message",
    }
)
LOG_ALLOWED_FIELDS = LOG_REQUIRED_FIELDS | LOG_OPTIONAL_FIELDS
LOG_STATUS_VALUES = frozenset({"ok", "error", "timeout", "rejected"})
LOG_SEVERITY_VALUES = frozenset({"debug", "info", "warning", "error", "critical"})
CSV_REQUIRED_COLUMNS = ("timestamp", "service_name", "metric_name", "value", "unit")
CSV_OPTIONAL_COLUMNS = ("service_path", "dependency_type")
CSV_ALLOWED_COLUMNS = frozenset(CSV_REQUIRED_COLUMNS + CSV_OPTIONAL_COLUMNS)
METRIC_UNIT_BY_NAME = {
    "request_count": "count",
    "error_count": "count",
    "latency_sample_ms": "ms",
    "ingestion_lag_sample_ms": "ms",
    "cpu_utilization_pct": "percent",
    "memory_utilization_pct": "percent",
}
COUNT_METRIC_NAMES = frozenset({"request_count", "error_count"})
NONNEGATIVE_SAMPLE_METRIC_NAMES = frozenset({"latency_sample_ms", "ingestion_lag_sample_ms"})
PERCENT_METRIC_NAMES = frozenset({"cpu_utilization_pct", "memory_utilization_pct"})
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
SENSITIVE_PATTERNS = (
    {
        "type": "PRIVATE_KEY",
        "pattern": re.compile(
            r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----[\s\S]*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----"
        ),
        "replacement": "[REDACTED:PRIVATE_KEY]",
    },
    {
        "type": "BEARER_TOKEN",
        "pattern": re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+"),
        "replacement": "Authorization: [REDACTED:BEARER_TOKEN]",
    },
    {
        "type": "JWT",
        "pattern": re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "replacement": "[REDACTED:JWT]",
    },
    {
        "type": "SECRET",
        "pattern": re.compile(
            r"(?i)\b(api_key|access_token|secret|password|passwd|session_token|cookie)\b\s*[:=]\s*[\"']?([^\s,\"';}]+)"
        ),
        "replacement": "[REDACTED:SECRET]",
    },
    {
        "type": "EMAIL",
        "pattern": re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
        "replacement": "[REDACTED:EMAIL]",
    },
    {
        "type": "PHONE",
        "pattern": re.compile(r"(?<!\d)(?:\+82[- ]?|0)(?:10|2|[3-6][1-5])[- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
        "replacement": "[REDACTED:PHONE]",
    },
    {
        "type": "ACCOUNT",
        "pattern": re.compile(r"(?i)(account(?:_no|_number)?|계좌(?:번호)?)\s*[:=]?\s*\d(?:[- ]?\d){7,15}"),
        "replacement": "[REDACTED:ACCOUNT]",
    },
)
SENSITIVE_TYPES = tuple(rule["type"] for rule in SENSITIVE_PATTERNS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_openbell.py",
        description=(
            "Prepare an OpenBell Guard run directory. P4-08 validates the CLI, "
            "paths, bundle file contract, byte limits, incident metadata, and "
            "creates a masked working copy, telemetry record summary, and bucket summary; "
            "metric calculation is implemented later."
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
            "baseline_window": {
                "start": baseline_start.isoformat(),
                "end": baseline_end.isoformat(),
            },
            "incident_window": {
                "start": incident_start.isoformat(),
                "end": incident_end.isoformat(),
            },
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
    service_path_by_name: dict[str, str] = {}
    dependency_type_by_name: dict[str, str] = {}
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
        service_path_by_name[service_name] = str(service_path)
        dependency_type_by_name[service_name] = str(dependency_type)
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

    return (
        {
            "provided": True,
            "service_count": len(services),
            "service_path_by_name": service_path_by_name,
            "dependency_type_by_name": dependency_type_by_name,
        },
        None,
    )


def validate_bundle_preflight(
    bundle_path: Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None, dict[str, Any] | None]:
    try:
        entries = list(bundle_path.iterdir())
    except OSError:
        return None, None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP003_UNSUPPORTED_ENTRY",
            message="The --bundle directory could not be listed.",
            argument="bundle",
        )

    file_paths: dict[str, Path] = {}
    for entry in entries:
        if entry.name not in ALLOWED_BUNDLE_FILES or entry.is_symlink() or not entry.is_file():
            return None, None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP003_UNSUPPORTED_ENTRY",
                message="The bundle contains an unsupported file, directory, or symbolic link.",
                argument="bundle",
                source_file=entry.name,
            )
        file_paths[entry.name] = entry

    if "incident.json" not in file_paths:
        return None, None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP001_MISSING_INCIDENT",
            message="incident.json is required.",
            argument="bundle",
            source_file="incident.json",
        )
    if "logs.jsonl" not in file_paths and "metrics.csv" not in file_paths:
        return None, None, issue_payload(
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
            return None, None, issue_payload(
                exit_code=EXIT_CODES["input_error"],
                issue_code="INP003_UNSUPPORTED_ENTRY",
                message="A bundle file could not be inspected.",
                argument="bundle",
                source_file=file_name,
            )
        if file_sizes[file_name] > FILE_BYTE_LIMITS[file_name]:
            return None, None, issue_payload(
                exit_code=EXIT_CODES["limit_exceeded"],
                issue_code="LIM001_FILE_BYTES",
                message="A bundle file exceeds its supported byte limit.",
                argument="bundle",
                source_file=file_name,
            )

    total_bytes = sum(file_sizes.values())
    if total_bytes > BUNDLE_BYTE_LIMIT:
        return None, None, issue_payload(
            exit_code=EXIT_CODES["limit_exceeded"],
            issue_code="LIM004_BUNDLE_BYTES",
            message="The bundle exceeds its supported total byte limit.",
            argument="bundle",
        )

    decoded_files: dict[str, str] = {}
    for file_name, path in sorted(file_paths.items()):
        text, issue = read_utf8_text(path, file_name)
        if issue is not None:
            return None, None, issue
        assert text is not None
        decoded_files[file_name] = text

    incident_payload, issue = load_json_object(decoded_files["incident.json"], "incident.json")
    if issue is not None:
        return None, None, issue
    assert incident_payload is not None
    incident_summary, issue = validate_incident(incident_payload)
    if issue is not None:
        return None, None, issue
    assert incident_summary is not None

    service_map_summary = {"provided": False, "service_count": 0}
    if "service-map.json" in decoded_files:
        service_map_payload, issue = load_json_object(decoded_files["service-map.json"], "service-map.json")
        if issue is not None:
            return None, None, issue
        assert service_map_payload is not None
        service_map_summary, issue = validate_service_map(service_map_payload)
        if issue is not None:
            return None, None, issue
        assert service_map_summary is not None

    return (
        {
            "files": [{"name": file_name, "bytes": file_sizes[file_name]} for file_name in sorted(file_sizes)],
            "total_bytes": total_bytes,
            "incident": incident_summary,
            "service_map": service_map_summary,
        },
        decoded_files,
        None,
    )


def is_redacted_placeholder_match(match_text: str) -> bool:
    return "[REDACTED:" in match_text


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def find_sensitive_matches(
    text: str, *, source_file: str = "<memory>", include_redacted: bool = True
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rule in SENSITIVE_PATTERNS:
        pattern = rule["pattern"]
        assert isinstance(pattern, re.Pattern)
        secret_type = str(rule["type"])
        for match in pattern.finditer(text):
            if not include_redacted and is_redacted_placeholder_match(match.group(0)):
                continue
            matches.append(
                {
                    "type": secret_type,
                    "source_file": source_file,
                    "line": line_number_for_offset(text, match.start()),
                }
            )
    return matches


def replace_sensitive_match(secret_type: str, replacement: str, match: re.Match[str]) -> str:
    match_text = match.group(0)
    if is_redacted_placeholder_match(match_text):
        return match_text

    if secret_type == "SECRET":
        value_start, value_end = match.span(2)
        relative_start = value_start - match.start()
        relative_end = value_end - match.start()
        return f"{match_text[:relative_start]}{replacement}{match_text[relative_end:]}"

    if secret_type == "ACCOUNT":
        digit_match = re.search(r"\d", match_text)
        if digit_match is None:
            return match_text
        return f"{match_text[: digit_match.start()]}{replacement}"

    return replacement


def sanitize_text(text: str, *, source_file: str) -> tuple[str, list[dict[str, Any]]]:
    sanitized = text
    findings: list[dict[str, Any]] = []

    for rule in SENSITIVE_PATTERNS:
        secret_type = str(rule["type"])
        replacement = str(rule["replacement"])
        pattern = rule["pattern"]
        assert isinstance(pattern, re.Pattern)

        for match in pattern.finditer(sanitized):
            if is_redacted_placeholder_match(match.group(0)):
                continue
            findings.append(
                {
                    "type": secret_type,
                    "source_file": source_file,
                    "line": line_number_for_offset(sanitized, match.start()),
                }
            )

        sanitized = pattern.sub(lambda match: replace_sensitive_match(secret_type, replacement, match), sanitized)

    return sanitized, findings


def summarize_sanitization(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = []
    for secret_type in SENSITIVE_TYPES:
        typed_findings = [finding for finding in findings if finding["type"] == secret_type]
        locations = sorted({f"{finding['source_file']}:L{finding['line']}" for finding in typed_findings})
        by_type.append({"type": secret_type, "count": len(typed_findings), "locations": locations})
    return {
        "status": "success",
        "total_redactions": len(findings),
        "by_type": by_type,
        "masked_bundle_dir": SANITIZED_BUNDLE_DIR,
        "report_file": SANITIZATION_REPORT,
    }


def render_sanitization_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Sanitization Report",
        "",
        f"- stage: {CLI_STAGE}",
        f"- status: {summary['status']}",
        f"- total_redactions: {summary['total_redactions']}",
        "- note: 원값, 원값 일부, 해시와 절대경로는 기록하지 않습니다.",
        "",
        "| Type | Count | Locations |",
        "|---|---:|---|",
    ]
    for item in summary["by_type"]:
        locations = ", ".join(item["locations"]) if item["locations"] else "-"
        lines.append(f"| {item['type']} | {item['count']} | {locations} |")
    return "\n".join(lines) + "\n"


def sanitize_bundle(
    *, decoded_files: dict[str, str], output_path: Path
) -> tuple[dict[str, Any] | None, dict[str, str] | None, dict[str, Any] | None]:
    try:
        sanitized_files: dict[str, str] = {}
        findings: list[dict[str, Any]] = []
        for file_name, text in sorted(decoded_files.items()):
            sanitized_text, file_findings = sanitize_text(text, source_file=file_name)
            sanitized_files[file_name] = sanitized_text
            findings.extend(file_findings)

        residues: list[dict[str, Any]] = []
        for file_name, sanitized_text in sorted(sanitized_files.items()):
            residues.extend(find_sensitive_matches(sanitized_text, source_file=file_name, include_redacted=False))
        if residues:
            first_residue = residues[0]
            return None, None, issue_payload(
                exit_code=EXIT_CODES["security_block"],
                issue_code="SEC002_SENSITIVE_RESIDUE",
                message="Sensitive pattern residue remained after masking.",
                argument="bundle",
                source_file=str(first_residue["source_file"]),
            )

        sanitized_dir = output_path / SANITIZED_BUNDLE_DIR
        sanitized_dir.mkdir(parents=True, exist_ok=True)
        for file_name, sanitized_text in sanitized_files.items():
            (sanitized_dir / file_name).write_text(sanitized_text, encoding="utf-8", newline="")

        summary = summarize_sanitization(findings)
        (output_path / SANITIZATION_REPORT).write_text(render_sanitization_report(summary), encoding="utf-8")
    except OSError:
        return None, None, issue_payload(
            exit_code=EXIT_CODES["security_block"],
            issue_code="SEC001_SANITIZER_FAILURE",
            message="The sanitizer could not create the masked working copy or report.",
            argument="output",
        )

    return summary, sanitized_files, None


def empty_record_counts() -> dict[str, int]:
    return {
        "physical_record_count": 0,
        "accepted_record_count": 0,
        "rejected_record_count": 0,
        "outside_analysis_window_count": 0,
        "field_dropped_count": 0,
    }


def add_record_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] += value


def record_issue(
    *,
    issue_code: str,
    source_file: str,
    location: str,
    message: str,
    field: str | None = None,
    severity: str = "warning",
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "issue_code": issue_code,
        "severity": severity,
        "source_file": source_file,
        "source_location": location,
        "message": message,
    }
    if field is not None:
        issue["field"] = field
    return issue


def parse_row_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def is_finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def is_valid_trimmed_string(value: Any, *, max_length: int) -> bool:
    return isinstance(value, str) and 1 <= len(value.strip()) <= max_length


def analysis_window_type(timestamp: datetime, incident_summary: dict[str, Any]) -> str | None:
    baseline_window = incident_summary["baseline_window"]
    incident_window = incident_summary["incident_window"]
    baseline_start = parse_row_datetime(baseline_window["start"])
    baseline_end = parse_row_datetime(baseline_window["end"])
    incident_start = parse_row_datetime(incident_window["start"])
    incident_end = parse_row_datetime(incident_window["end"])
    assert baseline_start is not None
    assert baseline_end is not None
    assert incident_start is not None
    assert incident_end is not None
    if baseline_start <= timestamp < baseline_end:
        return "baseline"
    if incident_start <= timestamp < incident_end:
        return "incident"
    return None


def is_in_analysis_window(timestamp: datetime, incident_summary: dict[str, Any]) -> bool:
    return analysis_window_type(timestamp, incident_summary) is not None


def utc_bucket_start(timestamp: datetime) -> datetime:
    return timestamp.astimezone(timezone.utc).replace(second=0, microsecond=0)


def isoformat_utc(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def isoformat_local(timestamp: datetime, timezone_name: str) -> str:
    return timestamp.astimezone(ZoneInfo(timezone_name)).isoformat()


def parse_logs_jsonl(text: str, incident_summary: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    counts = empty_record_counts()
    issues: list[dict[str, Any]] = []
    accepted_in_window_count = 0
    normalized_records: list[dict[str, Any]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        counts["physical_record_count"] += 1
        if counts["physical_record_count"] > LOG_RECORD_LIMIT:
            return None, issue_payload(
                exit_code=EXIT_CODES["limit_exceeded"],
                issue_code="LIM002_RECORD_COUNT",
                message="logs.jsonl exceeds its supported record count.",
                argument="bundle",
                source_file="logs.jsonl",
            )
        if len(line.encode("utf-8")) > JSONL_RECORD_BYTE_LIMIT:
            return None, issue_payload(
                exit_code=EXIT_CODES["limit_exceeded"],
                issue_code="LIM003_RECORD_BYTES",
                message="A logs.jsonl record exceeds its supported byte limit.",
                argument="bundle",
                source_file=f"logs.jsonl:L{line_number}",
            )

        location = f"logs.jsonl:L{line_number}"
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC001_SYNTAX",
                    source_file="logs.jsonl",
                    location=location,
                    message="The JSONL row is not valid JSON.",
                    severity="degraded",
                )
            )
            continue
        if not isinstance(payload, dict):
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC001_SYNTAX",
                    source_file="logs.jsonl",
                    location=location,
                    message="The JSONL row must be an object.",
                    severity="degraded",
                )
            )
            continue

        missing_required = sorted(field for field in LOG_REQUIRED_FIELDS if field not in payload)
        if missing_required:
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC002_REQUIRED_FIELD",
                    source_file="logs.jsonl",
                    location=location,
                    field=missing_required[0],
                    message="A required logs.jsonl field is missing.",
                    severity="degraded",
                )
            )
            continue

        event_time = parse_row_datetime(payload.get("event_time"))
        if event_time is None:
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC003_TYPE",
                    source_file="logs.jsonl",
                    location=location,
                    field="event_time",
                    message="event_time must be an ISO 8601 timestamp with an explicit offset.",
                    severity="degraded",
                )
            )
            continue
        if not is_valid_trimmed_string(payload.get("service_name"), max_length=128):
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC003_TYPE",
                    source_file="logs.jsonl",
                    location=location,
                    field="service_name",
                    message="service_name must be a non-empty string up to 128 characters after trimming.",
                    severity="degraded",
                )
            )
            continue
        if payload.get("service_path") not in STANDARD_SERVICE_PATHS:
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC004_ENUM",
                    source_file="logs.jsonl",
                    location=location,
                    field="service_path",
                    message="service_path must be one of the standard service path codes.",
                    severity="degraded",
                )
            )
            continue
        if payload.get("status") not in LOG_STATUS_VALUES:
            counts["rejected_record_count"] += 1
            issues.append(
                record_issue(
                    issue_code="REC004_ENUM",
                    source_file="logs.jsonl",
                    location=location,
                    field="status",
                    message="status must be ok, error, timeout, or rejected.",
                    severity="degraded",
                )
            )
            continue

        counts["accepted_record_count"] += 1
        assert isinstance(payload["service_name"], str)
        assert isinstance(payload["service_path"], str)
        assert isinstance(payload["status"], str)
        service_name = payload["service_name"].strip()
        service_path = payload["service_path"]
        status = payload["status"]
        parsed_observed_time: datetime | None = None
        latency_value: float | None = None
        dependency_type_value: str | None = None

        for field in sorted(set(payload) - LOG_ALLOWED_FIELDS):
            issues.append(
                record_issue(
                    issue_code="WRN001_UNKNOWN_FIELD",
                    source_file="logs.jsonl",
                    location=location,
                    field=field,
                    message="An unknown logs.jsonl field was ignored.",
                )
            )

        observed_time = payload.get("observed_time")
        if observed_time is not None:
            parsed_observed_time = parse_row_datetime(observed_time)
            if parsed_observed_time is None or parsed_observed_time < event_time:
                parsed_observed_time = None
                counts["field_dropped_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="FLD001_OPTIONAL_DROPPED",
                        source_file="logs.jsonl",
                        location=location,
                        field="observed_time",
                        message="observed_time was present but invalid, so the field was dropped.",
                        severity="degraded",
                    )
                )

        latency_ms = payload.get("latency_ms")
        if latency_ms is not None:
            if not is_finite_number(latency_ms) or float(latency_ms) < 0:
                counts["field_dropped_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="FLD001_OPTIONAL_DROPPED",
                        source_file="logs.jsonl",
                        location=location,
                        field="latency_ms",
                        message="latency_ms was present but invalid, so the field was dropped.",
                        severity="degraded",
                    )
                )
            else:
                latency_value = float(latency_ms)

        dependency_type = payload.get("dependency_type")
        if dependency_type is not None:
            if dependency_type not in STANDARD_DEPENDENCY_TYPES:
                counts["field_dropped_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="FLD001_OPTIONAL_DROPPED",
                        source_file="logs.jsonl",
                        location=location,
                        field="dependency_type",
                        message="dependency_type was present but invalid, so the field was dropped.",
                        severity="degraded",
                    )
                )
            else:
                assert isinstance(dependency_type, str)
                dependency_type_value = dependency_type

        for field, max_length in (("trace_id", 128), ("log_type", 64)):
            if field in payload and payload[field] is not None and not is_valid_trimmed_string(
                payload[field], max_length=max_length
            ):
                counts["field_dropped_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="FLD001_OPTIONAL_DROPPED",
                        source_file="logs.jsonl",
                        location=location,
                        field=field,
                        message=f"{field} was present but invalid, so the field was dropped.",
                        severity="degraded",
                    )
                )

        severity = payload.get("severity")
        if severity is not None and severity not in LOG_SEVERITY_VALUES:
            counts["field_dropped_count"] += 1
            issues.append(
                record_issue(
                    issue_code="FLD001_OPTIONAL_DROPPED",
                    source_file="logs.jsonl",
                    location=location,
                    field="severity",
                    message="severity was present but invalid, so the field was dropped.",
                    severity="degraded",
                )
            )

        message = payload.get("message")
        if message is not None and not isinstance(message, str):
            counts["field_dropped_count"] += 1
            issues.append(
                record_issue(
                    issue_code="FLD001_OPTIONAL_DROPPED",
                    source_file="logs.jsonl",
                    location=location,
                    field="message",
                    message="message was present but invalid, so the field was dropped.",
                    severity="degraded",
                )
            )

        window_type = analysis_window_type(event_time, incident_summary)
        if window_type is not None:
            accepted_in_window_count += 1
            normalized_records.append(
                {
                    "source_type": "log",
                    "source_file": "logs.jsonl",
                    "source_location": location,
                    "event_time": event_time,
                    "observed_time": parsed_observed_time,
                    "service_name": service_name,
                    "service_path": service_path,
                    "dependency_type": dependency_type_value,
                    "status": status,
                    "latency_ms": latency_value,
                    "window_type": window_type,
                }
            )
        else:
            counts["outside_analysis_window_count"] += 1
            issues.append(
                record_issue(
                    issue_code="TIM001_OUTSIDE_WINDOW",
                    source_file="logs.jsonl",
                    location=location,
                    field="event_time",
                    message="The accepted row is outside both analysis windows and was excluded from aggregation.",
                )
            )

    return {
        "counts": counts,
        "issues": issues,
        "accepted_in_window_count": accepted_in_window_count,
        "normalized_records": normalized_records,
    }, None


def parse_metric_number(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def is_integer_value(value: float) -> bool:
    return value >= 0 and value.is_integer()


def csv_header_issue(message: str) -> dict[str, Any]:
    return issue_payload(
        exit_code=EXIT_CODES["input_error"],
        issue_code="INP005_SCHEMA",
        message=message,
        argument="bundle",
        source_file="metrics.csv",
    )


def parse_metrics_csv(
    text: str, incident_summary: dict[str, Any], service_map_summary: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    counts = empty_record_counts()
    issues: list[dict[str, Any]] = []
    accepted_in_window_count = 0
    normalized_records: list[dict[str, Any]] = []

    stream = io.StringIO(text)
    reader = csv.DictReader(stream, strict=True)
    fieldnames = reader.fieldnames
    if not fieldnames:
        return None, csv_header_issue("metrics.csv must include a header row.")
    if len(fieldnames) != len(set(fieldnames)):
        return None, csv_header_issue("metrics.csv header names must be unique.")
    for column in CSV_REQUIRED_COLUMNS:
        if column not in fieldnames:
            return None, csv_header_issue("metrics.csv is missing a required column.")

    for column in sorted(set(fieldnames) - CSV_ALLOWED_COLUMNS):
        issues.append(
            record_issue(
                issue_code="WRN001_UNKNOWN_FIELD",
                source_file="metrics.csv",
                location="metrics.csv:R0",
                field=column,
                message="An unknown metrics.csv column was ignored.",
            )
        )

    service_path_by_name = service_map_summary.get("service_path_by_name", {})
    if not isinstance(service_path_by_name, dict):
        service_path_by_name = {}

    try:
        for row_number, row in enumerate(reader, start=1):
            counts["physical_record_count"] += 1
            if counts["physical_record_count"] > METRIC_RECORD_LIMIT:
                return None, issue_payload(
                    exit_code=EXIT_CODES["limit_exceeded"],
                    issue_code="LIM002_RECORD_COUNT",
                    message="metrics.csv exceeds its supported record count.",
                    argument="bundle",
                    source_file="metrics.csv",
                )

            location = f"metrics.csv:R{row_number}"
            if None in row:
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC001_SYNTAX",
                        source_file="metrics.csv",
                        location=location,
                        message="The CSV row has more columns than the header.",
                        severity="degraded",
                    )
                )
                continue

            missing_required = [
                column for column in CSV_REQUIRED_COLUMNS if row.get(column) is None or row.get(column) == ""
            ]
            if missing_required:
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC002_REQUIRED_FIELD",
                        source_file="metrics.csv",
                        location=location,
                        field=missing_required[0],
                        message="A required metrics.csv field is missing.",
                        severity="degraded",
                    )
                )
                continue

            timestamp = parse_row_datetime(row.get("timestamp"))
            if timestamp is None:
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC003_TYPE",
                        source_file="metrics.csv",
                        location=location,
                        field="timestamp",
                        message="timestamp must be an ISO 8601 timestamp with an explicit offset.",
                        severity="degraded",
                    )
                )
                continue
            service_name = row.get("service_name")
            if not is_valid_trimmed_string(service_name, max_length=128):
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC003_TYPE",
                        source_file="metrics.csv",
                        location=location,
                        field="service_name",
                        message="service_name must be a non-empty string up to 128 characters after trimming.",
                        severity="degraded",
                    )
                )
                continue
            assert isinstance(service_name, str)
            service_name = service_name.strip()

            service_path = (row.get("service_path") or "").strip()
            if not service_path:
                mapped_service_path = service_path_by_name.get(service_name)
                service_path = mapped_service_path if isinstance(mapped_service_path, str) else ""
            if service_path not in STANDARD_SERVICE_PATHS:
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC004_ENUM",
                        source_file="metrics.csv",
                        location=location,
                        field="service_path",
                        message="service_path must be present directly or resolvable from service-map.json.",
                        severity="degraded",
                    )
                )
                continue

            metric_name = row.get("metric_name")
            unit = row.get("unit")
            if metric_name not in METRIC_UNIT_BY_NAME or unit != METRIC_UNIT_BY_NAME.get(str(metric_name)):
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC004_ENUM",
                        source_file="metrics.csv",
                        location=location,
                        field="metric_name",
                        message="metric_name and unit must match the standard metric table.",
                        severity="degraded",
                    )
                )
                continue

            value = parse_metric_number(row.get("value"))
            if value is None:
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC005_RANGE",
                        source_file="metrics.csv",
                        location=location,
                        field="value",
                        message="value must be a finite number.",
                        severity="degraded",
                    )
                )
                continue
            if metric_name in COUNT_METRIC_NAMES:
                if not is_integer_value(value) or timestamp.second != 0 or timestamp.microsecond != 0:
                    counts["rejected_record_count"] += 1
                    issues.append(
                        record_issue(
                            issue_code="REC005_RANGE",
                            source_file="metrics.csv",
                            location=location,
                            field="value",
                            message="request_count and error_count must be non-negative integers on minute boundaries.",
                            severity="degraded",
                        )
                    )
                    continue
            elif metric_name in NONNEGATIVE_SAMPLE_METRIC_NAMES:
                if value < 0:
                    counts["rejected_record_count"] += 1
                    issues.append(
                        record_issue(
                            issue_code="REC005_RANGE",
                            source_file="metrics.csv",
                            location=location,
                            field="value",
                            message="Latency and ingestion lag metric values must be non-negative.",
                            severity="degraded",
                        )
                    )
                    continue
            elif metric_name in PERCENT_METRIC_NAMES and (value < 0 or value > 100):
                counts["rejected_record_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="REC005_RANGE",
                        source_file="metrics.csv",
                        location=location,
                        field="value",
                        message="CPU and memory percent metric values must be between 0 and 100 inclusive.",
                        severity="degraded",
                    )
                )
                continue

            dependency_type = row.get("dependency_type")
            dependency_type_value: str | None = None
            if dependency_type:
                dependency_type = dependency_type.strip()
                if dependency_type not in STANDARD_DEPENDENCY_TYPES:
                    counts["field_dropped_count"] += 1
                    issues.append(
                        record_issue(
                            issue_code="FLD001_OPTIONAL_DROPPED",
                            source_file="metrics.csv",
                            location=location,
                            field="dependency_type",
                            message="dependency_type was present but invalid, so the field was dropped.",
                            severity="degraded",
                        )
                    )
                else:
                    dependency_type_value = dependency_type

            counts["accepted_record_count"] += 1
            window_type = analysis_window_type(timestamp, incident_summary)
            if window_type is not None:
                accepted_in_window_count += 1
                normalized_records.append(
                    {
                        "source_type": "metric",
                        "source_file": "metrics.csv",
                        "source_location": location,
                        "timestamp": timestamp,
                        "service_name": service_name,
                        "service_path": service_path,
                        "dependency_type": dependency_type_value,
                        "metric_name": metric_name,
                        "value": value,
                        "unit": unit,
                        "window_type": window_type,
                    }
                )
            else:
                counts["outside_analysis_window_count"] += 1
                issues.append(
                    record_issue(
                        issue_code="TIM001_OUTSIDE_WINDOW",
                        source_file="metrics.csv",
                        location=location,
                        field="timestamp",
                        message="The accepted row is outside both analysis windows and was excluded from aggregation.",
                    )
                )
    except csv.Error:
        counts["rejected_record_count"] += 1
        issues.append(
            record_issue(
                issue_code="REC001_SYNTAX",
                source_file="metrics.csv",
                location=f"metrics.csv:R{counts['physical_record_count'] + 1}",
                message="The CSV parser could not read a row.",
                severity="degraded",
            )
        )

    return {
        "counts": counts,
        "issues": issues,
        "accepted_in_window_count": accepted_in_window_count,
        "normalized_records": normalized_records,
    }, None


def summarize_issues(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        issue_code = str(issue["issue_code"])
        counts[issue_code] = counts.get(issue_code, 0) + 1
    return dict(sorted(counts.items()))


def build_record_summary(
    *,
    logs_result: dict[str, Any] | None,
    metrics_result: dict[str, Any] | None,
) -> dict[str, Any]:
    total_counts = empty_record_counts()
    by_source: dict[str, dict[str, int]] = {}
    all_issues: list[dict[str, Any]] = []
    logs_in_window = 0
    metrics_in_window = 0

    if logs_result is not None:
        by_source["logs.jsonl"] = logs_result["counts"]
        add_record_counts(total_counts, logs_result["counts"])
        all_issues.extend(logs_result["issues"])
        logs_in_window = int(logs_result["accepted_in_window_count"])
    if metrics_result is not None:
        by_source["metrics.csv"] = metrics_result["counts"]
        add_record_counts(total_counts, metrics_result["counts"])
        all_issues.extend(metrics_result["issues"])
        metrics_in_window = int(metrics_result["accepted_in_window_count"])

    if logs_in_window > 0:
        primary_telemetry = "logs.jsonl"
    elif metrics_in_window > 0:
        primary_telemetry = "metrics.csv"
    else:
        primary_telemetry = None

    degraded_issue_prefixes = ("REC", "FLD", "MET")
    degraded = any(str(issue["issue_code"]).startswith(degraded_issue_prefixes) for issue in all_issues)
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "status": "degraded" if degraded else "success",
        "primary_telemetry": primary_telemetry,
        "record_counts": {
            "m_id": "M-014",
            "total": total_counts,
            "by_source": by_source,
        },
        "accepted_in_window": {
            "total": logs_in_window + metrics_in_window,
            "logs.jsonl": logs_in_window,
            "metrics.csv": metrics_in_window,
        },
        "issue_counts": summarize_issues(all_issues),
        "issues": all_issues,
        "raw_excerpts_emitted": False,
    }


def build_bucket_summary(
    *,
    logs_result: dict[str, Any] | None,
    metrics_result: dict[str, Any] | None,
    incident_summary: dict[str, Any],
) -> dict[str, Any]:
    timezone_name = str(incident_summary["timezone"])
    bucket_groups: dict[tuple[str, str], dict[str, Any]] = {}

    normalized_records: list[dict[str, Any]] = []
    if logs_result is not None:
        normalized_records.extend(logs_result["normalized_records"])
    if metrics_result is not None:
        normalized_records.extend(metrics_result["normalized_records"])

    for record in normalized_records:
        timestamp = record["event_time"] if record["source_type"] == "log" else record["timestamp"]
        assert isinstance(timestamp, datetime)
        bucket_start = utc_bucket_start(timestamp)
        bucket_start_utc = isoformat_utc(bucket_start)
        service_path = str(record["service_path"])
        key = (service_path, bucket_start_utc)

        if key not in bucket_groups:
            bucket_groups[key] = {
                "service_path": service_path,
                "bucket_start_utc": bucket_start_utc,
                "bucket_start_local": isoformat_local(bucket_start, timezone_name),
                "bucket_size_seconds": 60,
                "window_type": record["window_type"],
                "source_counts": {"logs.jsonl": 0, "metrics.csv": 0},
                "source_locations": [],
            }
        bucket = bucket_groups[key]
        if bucket["window_type"] != record["window_type"]:
            bucket["window_type"] = "mixed"
        source_file = str(record["source_file"])
        bucket["source_counts"][source_file] += 1
        bucket["source_locations"].append(record["source_location"])

    buckets = [bucket_groups[key] for key in sorted(bucket_groups)]
    for bucket in buckets:
        bucket["source_locations"] = sorted(bucket["source_locations"])

    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "status": "success",
        "bucket_size_seconds": 60,
        "time_basis": "UTC",
        "display_timezone": timezone_name,
        "sort_order": ["service_path", "bucket_start_utc"],
        "bucket_count": len(buckets),
        "buckets": buckets,
        "raw_excerpts_emitted": False,
    }


def parse_telemetry_records(
    *, sanitized_files: dict[str, str], preflight_summary: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    incident_summary = preflight_summary["incident"]
    service_map_summary = preflight_summary["service_map"]

    logs_result = None
    metrics_result = None
    if "logs.jsonl" in sanitized_files:
        logs_result, issue = parse_logs_jsonl(sanitized_files["logs.jsonl"], incident_summary)
        if issue is not None:
            return None, None, issue
    if "metrics.csv" in sanitized_files:
        metrics_result, issue = parse_metrics_csv(sanitized_files["metrics.csv"], incident_summary, service_map_summary)
        if issue is not None:
            return None, None, issue

    summary = build_record_summary(logs_result=logs_result, metrics_result=metrics_result)
    if int(summary["accepted_in_window"]["total"]) == 0:
        return None, None, issue_payload(
            exit_code=EXIT_CODES["input_error"],
            issue_code="INP008_NO_VALID_RECORD",
            message="No valid telemetry records remain inside the baseline or incident windows.",
            argument="bundle",
        )
    bucket_summary = build_bucket_summary(
        logs_result=logs_result,
        metrics_result=metrics_result,
        incident_summary=incident_summary,
    )
    return summary, bucket_summary, None


def write_bucket_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / BUCKET_SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI015_BUCKET_SUMMARY_WRITE_FAILED",
            message="The bucket summary file could not be written.",
            argument="output",
        )
    return None


def write_record_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / RECORD_SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI014_RECORD_SUMMARY_WRITE_FAILED",
            message="The record summary file could not be written.",
            argument="output",
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


def success_payload(
    *,
    bundle_path: Path,
    preflight_summary: dict[str, Any],
    sanitization_summary: dict[str, Any],
    record_summary: dict[str, Any],
    bucket_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "buckets_prepared_ready",
        "exit_code": EXIT_CODES["ok"],
        "bundle": {
            "name": bundle_path.name,
            "path_kind": "directory",
            "preflight": preflight_summary,
            "raw_telemetry_records_parsed": False,
            "sanitized_telemetry_records_parsed": True,
            "raw_excerpts_emitted": False,
        },
        "outputs": {
            "summary_file": SUMMARY_FILENAME,
            "sanitized_bundle_dir": SANITIZED_BUNDLE_DIR,
            "record_summary_file": RECORD_SUMMARY_FILENAME,
            "record_summary_created": True,
            "bucket_summary_file": BUCKET_SUMMARY_FILENAME,
            "bucket_summary_created": True,
            "analysis_json_created": False,
            "sanitization_report_created": True,
            "sanitization_report_file": SANITIZATION_REPORT,
        },
        "sanitization": sanitization_summary,
        "telemetry": {
            "parse_status": record_summary["status"],
            "primary_telemetry": record_summary["primary_telemetry"],
            "record_counts": record_summary["record_counts"],
            "accepted_in_window": record_summary["accepted_in_window"],
            "issue_counts": record_summary["issue_counts"],
            "raw_excerpts_emitted": False,
        },
        "buckets": {
            "bucket_summary_file": BUCKET_SUMMARY_FILENAME,
            "bucket_size_seconds": bucket_summary["bucket_size_seconds"],
            "time_basis": bucket_summary["time_basis"],
            "display_timezone": bucket_summary["display_timezone"],
            "bucket_count": bucket_summary["bucket_count"],
            "sort_order": bucket_summary["sort_order"],
            "raw_excerpts_emitted": False,
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
            "detect and redact seven sensitive-info pattern categories",
            "write masked working copy",
            "write sanitization-report.md without raw values",
            "rescan masked working copy for sensitive residue",
            "parse sanitized logs.jsonl rows",
            "parse sanitized metrics.csv rows",
            "write M-014 record-summary.json without raw excerpts",
            "assign accepted in-window rows to UTC 60-second buckets",
            "write bucket-summary.json without raw excerpts",
        ],
        "deferred_scope": [
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

    preflight_summary, decoded_files, issue = validate_bundle_preflight(bundle_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert preflight_summary is not None
    assert decoded_files is not None

    issue = validate_and_prepare_output(bundle_path=bundle_path, output_path=output_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    sanitization_summary, sanitized_files, issue = sanitize_bundle(decoded_files=decoded_files, output_path=output_path)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert sanitization_summary is not None
    assert sanitized_files is not None

    record_summary, bucket_summary, issue = parse_telemetry_records(
        sanitized_files=sanitized_files,
        preflight_summary=preflight_summary,
    )
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert record_summary is not None
    assert bucket_summary is not None

    issue = write_record_summary(output_path=output_path, payload=record_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_bucket_summary(output_path=output_path, payload=bucket_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    payload = success_payload(
        bundle_path=bundle_path,
        preflight_summary=preflight_summary,
        sanitization_summary=sanitization_summary,
        record_summary=record_summary,
        bucket_summary=bucket_summary,
    )
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
