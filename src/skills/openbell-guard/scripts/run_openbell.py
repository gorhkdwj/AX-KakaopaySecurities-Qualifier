"""OpenBell Guard command-line entry point.

P4-15 implements the shared CLI, bundle preflight gate, sanitizer,
line-oriented telemetry parser, 60-second bucket preparation, basic bucket
metrics, observability lag metrics, baseline-vs-incident comparisons, and
threshold-based state judgment with context metrics, evidence-backed claims,
the final machine-verifiable ``analysis.json``, and an output validator:

- parse ``--bundle`` and ``--output``;
- verify that the bundle is an existing, non-symlink directory;
- reject unsupported top-level files, directories, and symlinks;
- enforce fixed file and bundle byte limits;
- verify UTF-8/UTF-8-BOM readability;
- validate the ``incident.json`` contract and optional ``service-map.json``.
- create a masked working copy and ``sanitization-report.md``.
- parse sanitized ``logs.jsonl`` and ``metrics.csv`` rows into a record summary.
- assign accepted in-window rows to UTC 60-second service-path buckets.
- calculate M-001 through M-007 request, error, throughput, error-rate, and
  latency percentile metrics into ``metric-summary.json``.
- calculate M-008 through M-009 ingestion-lag metrics without emitting raw
  per-record values.
- calculate M-010 through M-013 baseline median, incident peak, absolute
  change, and percent change for comparable bucket metrics.
- calculate M-015 CPU and memory utilization median context metrics from
  metrics.csv without using them for outage threshold judgment.
- invalidate metrics fallback count buckets when error_count exceeds
  request_count and report MET001_COUNT_INCONSISTENT.
- judge bucket state, service-path state, outage start, recovery time, and
  successful run status into ``state-summary.json``.
- create evidence and claim summaries without raw excerpts.
- write ``analysis.json`` by merging metric, state, and evidence summaries
  without raw excerpts.
- validate ``analysis.json`` structure, evidence references, claim evidence,
  claim markers, and sensitive residue before reporting success.

It still does not create the human-readable Markdown report. That behavior
belongs to later Phase 4 steps and must keep using this entry point.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
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

CLI_STAGE = "P4-15"
SUMMARY_FILENAME = "openbell-cli-summary.json"
ANALYSIS_FILENAME = "analysis.json"
OUTPUT_VALIDATION_FILENAME = "output-validation.json"
SANITIZED_BUNDLE_DIR = "sanitized-bundle"
SANITIZATION_REPORT = "sanitization-report.md"
RECORD_SUMMARY_FILENAME = "record-summary.json"
BUCKET_SUMMARY_FILENAME = "bucket-summary.json"
METRIC_SUMMARY_FILENAME = "metric-summary.json"
STATE_SUMMARY_FILENAME = "state-summary.json"
EVIDENCE_SUMMARY_FILENAME = "evidence-summary.json"
SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "1.0.0"
CONTRACT_REFERENCE_RELATIVE_PATH = "src/skills/openbell-guard/references/metrics-validation-contract.md"
BASIC_METRIC_IDS = ("M-001", "M-002", "M-003", "M-004", "M-005", "M-006", "M-007")
OBSERVABILITY_METRIC_IDS = ("M-008", "M-009")
COMPARISON_METRIC_IDS = ("M-010", "M-011", "M-012", "M-013")
CONTEXT_METRIC_IDS = ("M-015",)
CALCULATED_METRIC_IDS = (
    BASIC_METRIC_IDS + OBSERVABILITY_METRIC_IDS + COMPARISON_METRIC_IDS + CONTEXT_METRIC_IDS
)
COMPARABLE_BUCKET_METRICS = (
    "request_count",
    "error_count",
    "throughput_rps",
    "error_rate_pct",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "ingestion_lag_p50_ms",
    "ingestion_lag_p95_ms",
    "ingestion_lag_p99_ms",
)
THRESHOLD_DEFINITIONS = {
    "error_rate_pct_max": {
        "metric_name": "error_rate_pct",
        "unit": "percent",
    },
    "p95_latency_ms_max": {
        "metric_name": "latency_p95_ms",
        "unit": "ms",
    },
    "p99_latency_ms_max": {
        "metric_name": "latency_p99_ms",
        "unit": "ms",
    },
    "ingestion_lag_p95_ms_max": {
        "metric_name": "ingestion_lag_p95_ms",
        "unit": "ms",
    },
}
ERROR_STATUSES = frozenset({"error", "timeout", "rejected"})
DECIMAL_3_PLACES = Decimal("0.001")

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
EVIDENCE_ID_PATTERN = re.compile(r"^E-\d{3}$")
CLAIM_ID_PATTERN = re.compile(r"^C-\d{3}$")
WINDOW_TYPE_VALUES = frozenset({"baseline", "incident"})
BUCKET_STATE_VALUES = frozenset({"healthy", "breach", "unknown"})
RUN_STATUS_VALUES = frozenset({"complete", "degraded", "fatal"})
CLAIM_TYPE_VALUES = frozenset({"confirmed_fact", "hypothesis", "unknown"})
CLAIM_CONFIDENCE_VALUES = frozenset({"high", "medium", "low", "unknown"})
EVIDENCE_SOURCE_TYPES = frozenset({"incident", "log", "metric", "service_map"})
BREACH_REASON_KEYS = frozenset({"metric", "value", "threshold", "operator"})
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
            "Prepare an OpenBell Guard run directory. P4-15 validates the CLI, "
            "paths, bundle file contract, byte limits, incident metadata, and "
            "creates a masked working copy, telemetry record summary, bucket summary, "
            "metric summary, threshold-based state summary, evidence summary, and "
            "validated analysis.json."
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
    normalized_thresholds = {
        str(service_path): {
            str(threshold_name): rounded_observation(float(threshold_value))
            for threshold_name, threshold_value in sorted(rule.items())
        }
        for service_path, rule in sorted(thresholds.items())
        if isinstance(rule, dict)
    }
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
            "thresholds": normalized_thresholds,
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


def decimal_from_number(value: int | float | Decimal) -> Decimal:
    return Decimal(str(value))


def round_decimal_3(value: int | float | Decimal) -> Decimal:
    rounded = decimal_from_number(value).quantize(DECIMAL_3_PLACES, rounding=ROUND_HALF_UP)
    if rounded == Decimal("-0.000"):
        return Decimal("0.000")
    return rounded


def rounded_float(value: int | float | Decimal) -> float:
    return float(round_decimal_3(value))


def rounded_observation(value: int | float | Decimal) -> int | float:
    rounded = round_decimal_3(value)
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def metric_value(
    *,
    m_id: str,
    value: int | float | None,
    unit: str,
    sample_count: int | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "m_id": m_id,
        "value": value,
        "unit": unit,
    }
    if sample_count is not None:
        payload["sample_count"] = sample_count
    if reason_code is not None:
        payload["reason_code"] = reason_code
    return payload


def context_metric_value(*, value: int | float | None, sample_count: int) -> dict[str, Any]:
    payload = metric_value(
        m_id="M-015",
        value=value,
        unit="percent",
        sample_count=sample_count,
        reason_code="missing_input" if sample_count == 0 else None,
    )
    payload["individual_values_emitted"] = False
    return payload


def nearest_rank_raw_value(samples: list[float], percentile: Decimal, minimum_sample_count: int) -> tuple[float | None, str | None]:
    if len(samples) < minimum_sample_count:
        return None, "insufficient_sample"
    sorted_samples = sorted(samples)
    rank = int(math.ceil(float(percentile * Decimal(len(sorted_samples)))))
    rank = max(1, min(rank, len(sorted_samples)))
    return float(sorted_samples[rank - 1]), None


def nearest_rank_value(samples: list[float], percentile: Decimal, minimum_sample_count: int) -> tuple[int | float | None, str | None]:
    raw_value, reason_code = nearest_rank_raw_value(samples, percentile, minimum_sample_count)
    if raw_value is None:
        return None, reason_code
    return rounded_observation(raw_value), None


def median_value(samples: list[int | float]) -> int | float | None:
    if not samples:
        return None
    sorted_samples = sorted(decimal_from_number(sample) for sample in samples)
    middle = len(sorted_samples) // 2
    if len(sorted_samples) % 2 == 1:
        return rounded_observation(sorted_samples[middle])
    return rounded_observation((sorted_samples[middle - 1] + sorted_samples[middle]) / Decimal(2))


def ingestion_lag_metric(
    *,
    sample_count: int,
    missing_input_count: int,
    invalid_optional_field_count: int,
    source: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "m_id": "M-008",
        "value": None,
        "unit": "ms",
        "sample_count": sample_count,
        "source": source,
        "individual_values_emitted": False,
    }
    if missing_input_count:
        payload["missing_input_count"] = missing_input_count
    if invalid_optional_field_count:
        payload["invalid_optional_field_count"] = invalid_optional_field_count
    if sample_count == 0:
        if invalid_optional_field_count and not missing_input_count:
            payload["reason_code"] = "invalid_optional_field"
        elif missing_input_count and not invalid_optional_field_count:
            payload["reason_code"] = "missing_input"
        elif missing_input_count or invalid_optional_field_count:
            payload["reason_code"] = "missing_or_invalid_input"
        else:
            payload["reason_code"] = "insufficient_sample"
    return payload


def comparison_metric_value(
    *,
    m_id: str,
    value: int | float | None,
    unit: str,
    sample_count: int | None = None,
    reason_code: str | None = None,
) -> dict[str, Any]:
    return metric_value(
        m_id=m_id,
        value=value,
        unit=unit,
        sample_count=sample_count,
        reason_code=reason_code,
    )


def build_comparison_metrics(bucket_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    metric_units: dict[tuple[str, str], str] = {}
    metric_m_ids: dict[tuple[str, str], str] = {}

    for bucket in bucket_metrics:
        window_type = bucket["window_type"]
        if window_type not in {"baseline", "incident"}:
            continue
        service_path = str(bucket["service_path"])
        metrics = bucket["metrics"]
        for metric_name in COMPARABLE_BUCKET_METRICS:
            metric = metrics.get(metric_name)
            if not isinstance(metric, dict):
                continue
            value = metric.get("value")
            if not is_finite_number(value):
                continue
            unit = str(metric["unit"])
            key = (service_path, metric_name)
            if key not in grouped:
                grouped[key] = {"baseline": [], "incident": []}
                metric_units[key] = unit
                metric_m_ids[key] = str(metric["m_id"])
            grouped[key][window_type].append(float(value))

    comparison_metrics: list[dict[str, Any]] = []
    for key in sorted(grouped):
        service_path, metric_name = key
        baseline_values = grouped[key]["baseline"]
        incident_values = grouped[key]["incident"]
        unit = metric_units[key]

        baseline_median = median_value(baseline_values)
        baseline_reason = None if baseline_median is not None else "insufficient_sample"
        incident_peak = rounded_observation(max(incident_values)) if incident_values else None

        if baseline_median is None or incident_peak is None:
            change_abs: int | float | None = None
            change_pct: int | float | None = None
            change_pct_reason = "insufficient_sample"
        else:
            baseline_decimal = decimal_from_number(baseline_median)
            incident_decimal = decimal_from_number(incident_peak)
            change_abs = rounded_observation(incident_decimal - baseline_decimal)
            if baseline_decimal == 0:
                change_pct = None
                change_pct_reason = "zero_denominator"
            else:
                change_pct = rounded_float((incident_decimal - baseline_decimal) / baseline_decimal * Decimal(100))
                change_pct_reason = None

        comparison_metrics.append(
            {
                "service_path": service_path,
                "metric_name": metric_name,
                "source_metric_m_id": metric_m_ids[key],
                "unit": unit,
                "metrics": {
                    "baseline_median": comparison_metric_value(
                        m_id="M-010",
                        value=baseline_median,
                        unit=unit,
                        sample_count=len(baseline_values),
                        reason_code=baseline_reason,
                    ),
                    "incident_peak": comparison_metric_value(
                        m_id="M-011",
                        value=incident_peak,
                        unit=unit,
                        sample_count=len(incident_values),
                        reason_code="insufficient_sample" if incident_peak is None else None,
                    ),
                    "change_abs": comparison_metric_value(
                        m_id="M-012",
                        value=change_abs,
                        unit=unit,
                    ),
                    "change_pct": comparison_metric_value(
                        m_id="M-013",
                        value=change_pct,
                        unit="percent",
                        reason_code=change_pct_reason,
                    ),
                },
            }
        )

    return comparison_metrics


def threshold_as_output(value: int | float | Decimal) -> int | float:
    return rounded_observation(value)


def evaluate_bucket_state(
    *,
    bucket: dict[str, Any],
    thresholds: dict[str, dict[str, int | float]],
    raw_threshold_values: dict[tuple[str, str], dict[str, float | None]],
) -> dict[str, Any]:
    service_path = str(bucket["service_path"])
    bucket_start_utc = str(bucket["bucket_start_utc"])
    service_thresholds = thresholds.get(service_path)
    state: dict[str, Any] = {
        "service_path": service_path,
        "window_type": bucket["window_type"],
        "bucket_start_utc": bucket_start_utc,
        "bucket_start_local": bucket["bucket_start_local"],
        "source_locations": bucket["source_locations"],
    }
    if not service_thresholds:
        state["bucket_state"] = "unknown"
        state["unknown_reasons"] = [
            {
                "reason_code": "threshold_missing",
                "message": "No threshold is configured for this service_path.",
            }
        ]
        return state

    threshold_values = raw_threshold_values.get((service_path, bucket_start_utc), {})
    metrics = bucket["metrics"]
    breach_reasons: list[dict[str, Any]] = []
    unknown_reasons: list[dict[str, Any]] = []

    for threshold_key in sorted(service_thresholds):
        definition = THRESHOLD_DEFINITIONS[threshold_key]
        metric_name = str(definition["metric_name"])
        metric = metrics.get(metric_name, {})
        raw_value = threshold_values.get(metric_name)
        threshold_value = decimal_from_number(service_thresholds[threshold_key])

        if raw_value is None:
            reason_code = "missing_input"
            if isinstance(metric, dict):
                reason_code = str(metric.get("reason_code") or reason_code)
            unknown_reasons.append(
                {
                    "metric": metric_name,
                    "threshold_key": threshold_key,
                    "threshold": threshold_as_output(threshold_value),
                    "operator": ">",
                    "reason_code": reason_code,
                }
            )
            continue

        raw_decimal = decimal_from_number(raw_value)
        if raw_decimal > threshold_value:
            breach_reasons.append(
                {
                    "metric": metric_name,
                    "threshold_key": threshold_key,
                    "value": threshold_as_output(raw_decimal),
                    "threshold": threshold_as_output(threshold_value),
                    "operator": ">",
                }
            )

    if breach_reasons:
        state["bucket_state"] = "breach"
        state["breach_reasons"] = breach_reasons
    elif unknown_reasons:
        state["bucket_state"] = "unknown"
        state["unknown_reasons"] = unknown_reasons
    else:
        state["bucket_state"] = "healthy"
    return state


def outage_duration_seconds(outage_start: str | None, recovery_time: str | None) -> int | None:
    if outage_start is None or recovery_time is None:
        return None
    parsed_start = parse_row_datetime(outage_start)
    parsed_recovery = parse_row_datetime(recovery_time)
    if parsed_start is None or parsed_recovery is None:
        return None
    return int((parsed_recovery - parsed_start).total_seconds())


def service_path_state(service_path: str, bucket_states: list[dict[str, Any]]) -> dict[str, Any]:
    all_buckets = [state for state in bucket_states if state["service_path"] == service_path]
    incident_buckets = [state for state in all_buckets if state["window_type"] == "incident"]
    outage_start: str | None = None
    recovery_time: str | None = None
    consecutive_breach = 0
    first_breach_start: str | None = None
    consecutive_healthy_after_outage = 0
    first_healthy_start: str | None = None

    for state in incident_buckets:
        bucket_state = state["bucket_state"]
        if outage_start is None:
            if bucket_state == "breach":
                consecutive_breach += 1
                if consecutive_breach == 1:
                    first_breach_start = str(state["bucket_start_utc"])
                if consecutive_breach == 2:
                    outage_start = first_breach_start
            else:
                consecutive_breach = 0
                first_breach_start = None
        else:
            if bucket_state == "healthy":
                consecutive_healthy_after_outage += 1
                if consecutive_healthy_after_outage == 1:
                    first_healthy_start = str(state["bucket_start_utc"])
                if consecutive_healthy_after_outage == 2 and recovery_time is None:
                    recovery_time = first_healthy_start
            else:
                consecutive_healthy_after_outage = 0
                first_healthy_start = None

    has_breach = any(state["bucket_state"] == "breach" for state in incident_buckets)
    has_unknown = any(state["bucket_state"] == "unknown" for state in all_buckets)
    all_healthy = bool(all_buckets) and all(state["bucket_state"] == "healthy" for state in all_buckets)

    if outage_start is not None:
        status = "outage_detected"
    elif has_breach:
        status = "degradation_observed"
    elif all_healthy:
        status = "healthy"
    elif has_unknown or not incident_buckets:
        status = "unknown"
    else:
        status = "unknown"

    return {
        "service_path": service_path,
        "status": status,
        "outage_start": outage_start,
        "recovery_time": recovery_time,
        "outage_duration_seconds": outage_duration_seconds(outage_start, recovery_time),
        "ongoing_at_window_end": outage_start is not None and recovery_time is None,
        "evaluated_bucket_count": len(all_buckets),
        "incident_bucket_count": len(incident_buckets),
        "breach_bucket_count": sum(1 for state in all_buckets if state["bucket_state"] == "breach"),
        "unknown_bucket_count": sum(1 for state in all_buckets if state["bucket_state"] == "unknown"),
        "healthy_bucket_count": sum(1 for state in all_buckets if state["bucket_state"] == "healthy"),
    }


def run_state_from_summaries(
    *,
    record_summary: dict[str, Any],
    metric_issue_counts: dict[str, int],
    service_paths: list[dict[str, Any]],
    bucket_states: list[dict[str, Any]],
) -> dict[str, Any]:
    limitations: list[dict[str, Any]] = []
    accepted = record_summary["accepted_in_window"]

    if int(accepted.get("logs.jsonl", 0)) == 0 or int(accepted.get("metrics.csv", 0)) == 0:
        limitations.append(
            {
                "reason_code": "single_telemetry_source",
                "message": "Both logs.jsonl and metrics.csv must have valid in-window rows for complete status.",
            }
        )
    if record_summary["status"] != "success":
        limitations.append(
            {
                "reason_code": "record_quality_degraded",
                "message": "Rejected rows or dropped optional fields were detected.",
            }
        )
    if metric_issue_counts:
        limitations.append(
            {
                "reason_code": "metric_quality_degraded",
                "message": "Metric aggregation issues were detected.",
            }
        )
    if any(path["status"] == "unknown" for path in service_paths):
        limitations.append(
            {
                "reason_code": "state_unknown",
                "message": "At least one service path has unknown state.",
            }
        )
    if any(state["bucket_state"] == "unknown" for state in bucket_states):
        limitations.append(
            {
                "reason_code": "threshold_or_sample_incomplete",
                "message": "At least one bucket could not be fully evaluated against configured thresholds.",
            }
        )

    issue_counts = dict(record_summary.get("issue_counts", {}))
    for issue_code, count in metric_issue_counts.items():
        issue_counts[issue_code] = int(issue_counts.get(issue_code, 0)) + int(count)
    return {
        "status": "degraded" if limitations else "complete",
        "exit_code": EXIT_CODES["ok"],
        "issue_counts": issue_counts,
        "limitations": limitations,
    }


def build_state_summary(
    *,
    incident_summary: dict[str, Any],
    record_summary: dict[str, Any],
    metric_issue_counts: dict[str, int],
    bucket_metrics: list[dict[str, Any]],
    raw_threshold_values: dict[tuple[str, str], dict[str, float | None]],
) -> dict[str, Any]:
    thresholds = incident_summary.get("thresholds", {})
    if not isinstance(thresholds, dict):
        thresholds = {}
    normalized_thresholds = {
        str(service_path): {
            str(threshold_key): float(threshold_value)
            for threshold_key, threshold_value in rule.items()
        }
        for service_path, rule in thresholds.items()
        if isinstance(rule, dict)
    }
    bucket_states = [
        evaluate_bucket_state(
            bucket=bucket,
            thresholds=normalized_thresholds,
            raw_threshold_values=raw_threshold_values,
        )
        for bucket in bucket_metrics
    ]
    service_paths = [
        service_path_state(service_path, bucket_states)
        for service_path in sorted({state["service_path"] for state in bucket_states})
    ]
    run_state = run_state_from_summaries(
        record_summary=record_summary,
        metric_issue_counts=metric_issue_counts,
        service_paths=service_paths,
        bucket_states=bucket_states,
    )

    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "status": run_state["status"],
        "contract_version": CONTRACT_VERSION,
        "run": run_state,
        "thresholds": normalized_thresholds,
        "service_paths": service_paths,
        "bucket_states": bucket_states,
        "bucket_state_counts": summarize_issues(
            [{"issue_code": state["bucket_state"]} for state in bucket_states]
        ),
        "path_status_counts": summarize_issues(
            [{"issue_code": path["status"]} for path in service_paths]
        ),
        "raw_excerpts_emitted": False,
    }


def next_evidence_id(evidence: list[dict[str, Any]]) -> str:
    return f"E-{len(evidence) + 1:03}"


def next_claim_id(claims: list[dict[str, Any]]) -> str:
    return f"C-{len(claims) + 1:03}"


def claim_with_marker(claim: dict[str, Any]) -> dict[str, Any]:
    claim["report_claim_marker"] = f"[{claim['claim_id']}]"
    return claim


def compact_source_locations(locations: list[str]) -> str:
    if not locations:
        return "unknown"
    parsed: list[tuple[str, str, int]] = []
    for location in sorted(locations):
        match = re.match(r"^(?P<file>[^:]+):(?P<prefix>[LR])(?P<number>\d+)$", location)
        if match is None:
            return ",".join(sorted(locations))
        parsed.append((match.group("file"), match.group("prefix"), int(match.group("number"))))

    files = {item[0] for item in parsed}
    prefixes = {item[1] for item in parsed}
    numbers = sorted(item[2] for item in parsed)
    if len(files) == 1 and len(prefixes) == 1:
        file_name = parsed[0][0]
        prefix = parsed[0][1]
        if len(numbers) == 1:
            return f"{file_name}:{prefix}{numbers[0]}"
        if numbers == list(range(numbers[0], numbers[-1] + 1)):
            return f"{file_name}:{prefix}{numbers[0]}-{prefix}{numbers[-1]}"
    return ",".join(sorted(locations))


def source_file_from_locations(locations: list[str]) -> str:
    if not locations:
        return "unknown"
    first = sorted(locations)[0]
    return first.split(":", 1)[0]


def source_type_from_file(source_file: str) -> str:
    if source_file == "logs.jsonl":
        return "log"
    if source_file == "metrics.csv":
        return "metric"
    if source_file == "service-map.json":
        return "service_map"
    return "incident"


def local_bucket_window(bucket_start_local: str) -> str:
    parsed_start = parse_row_datetime(bucket_start_local)
    if parsed_start is None:
        return f"[{bucket_start_local}, unknown)"
    parsed_end = parsed_start + timedelta(seconds=60)
    return f"[{parsed_start.isoformat()}, {parsed_end.isoformat()})"


def display_bucket_time(bucket_start_local: str) -> str:
    parsed = parse_row_datetime(bucket_start_local)
    if parsed is None:
        return bucket_start_local
    suffix = "KST" if parsed.utcoffset() == timedelta(hours=9) else parsed.tzname() or "local time"
    return f"{parsed.strftime('%H:%M')} {suffix}"


def metric_output_value(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    if value is None:
        return "null"
    return str(value)


def threshold_output_value(value: int | float) -> str:
    return str(float(value))


def add_evidence(
    evidence: list[dict[str, Any]],
    *,
    source_type: str,
    source_file: str,
    source_location: str,
    masked_excerpt: str,
    time_window: str | None = None,
) -> str:
    evidence_id = next_evidence_id(evidence)
    item: dict[str, Any] = {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_file": source_file,
        "source_location": source_location,
    }
    if time_window is not None:
        item["time_window"] = time_window
    if masked_excerpt:
        item["masked_excerpt"] = masked_excerpt[:300]
    evidence.append(item)
    return evidence_id


def build_threshold_evidence(
    *, evidence: list[dict[str, Any]], state_summary: dict[str, Any]
) -> dict[str, str]:
    refs: dict[str, str] = {}
    thresholds = state_summary.get("thresholds", {})
    if not isinstance(thresholds, dict):
        return refs
    for service_path in sorted(thresholds):
        service_thresholds = thresholds.get(service_path, {})
        if not isinstance(service_thresholds, dict):
            continue
        threshold_parts = [
            f"{key}={threshold_output_value(float(value))}"
            for key, value in sorted(service_thresholds.items())
        ]
        refs[str(service_path)] = add_evidence(
            evidence,
            source_type="incident",
            source_file="incident.json",
            source_location=f"incident.json:thresholds.{service_path}",
            masked_excerpt=f"{service_path} " + ", ".join(threshold_parts),
        )
    return refs


def build_bucket_evidence(
    *, evidence: list[dict[str, Any]], metric_summary: dict[str, Any]
) -> dict[tuple[str, str], str]:
    refs: dict[tuple[str, str], str] = {}
    for bucket in metric_summary.get("bucket_metrics", []):
        if bucket.get("window_type") != "incident":
            continue
        locations = list(bucket.get("source_locations", []))
        source_file = source_file_from_locations(locations)
        source_type = source_type_from_file(source_file)
        metrics = bucket.get("metrics", {})
        request_count = metric_output_value(metrics.get("request_count", {}))
        error_count = metric_output_value(metrics.get("error_count", {}))
        status_word = "status" if error_count == "1" else "statuses"
        excerpt = (
            f"{request_count} {bucket['service_path']} requests, "
            f"{error_count} error-or-timeout {status_word}"
        )
        refs[(str(bucket["service_path"]), str(bucket["bucket_start_utc"]))] = add_evidence(
            evidence,
            source_type=source_type,
            source_file=source_file,
            source_location=compact_source_locations(locations),
            time_window=local_bucket_window(str(bucket["bucket_start_local"])),
            masked_excerpt=excerpt,
        )
    return refs


def build_context_evidence(
    *, evidence: list[dict[str, Any]], metric_summary: dict[str, Any]
) -> dict[tuple[str, str], str]:
    refs: dict[tuple[str, str], str] = {}
    for context in metric_summary.get("context_metrics", []):
        if context.get("window_type") != "incident":
            continue
        locations = list(context.get("source_locations", []))
        metrics = context.get("metrics", {})
        cpu = metric_output_value(metrics.get("cpu_utilization_median_pct", {}))
        memory = metric_output_value(metrics.get("memory_utilization_median_pct", {}))
        refs[(str(context["service_path"]), str(context["bucket_start_utc"]))] = add_evidence(
            evidence,
            source_type="metric",
            source_file=source_file_from_locations(locations),
            source_location=compact_source_locations(locations),
            time_window=local_bucket_window(str(context["bucket_start_local"])),
            masked_excerpt=(
                f"M-015 context for {context['service_path']}: "
                f"cpu_utilization_median_pct={cpu}, memory_utilization_median_pct={memory}"
            ),
        )
    return refs


def build_service_map_evidence(
    *, evidence: list[dict[str, Any]], preflight_summary: dict[str, Any]
) -> dict[str, str]:
    refs: dict[str, str] = {}
    service_map = preflight_summary.get("service_map", {})
    if not isinstance(service_map, dict) or not service_map.get("provided"):
        return refs
    service_path_by_name = service_map.get("service_path_by_name", {})
    dependency_type_by_name = service_map.get("dependency_type_by_name", {})
    if not isinstance(service_path_by_name, dict) or not isinstance(dependency_type_by_name, dict):
        return refs
    for index, service_name in enumerate(sorted(service_path_by_name)):
        service_path = str(service_path_by_name[service_name])
        dependency_type = str(dependency_type_by_name.get(service_name, "unknown"))
        refs[service_path] = add_evidence(
            evidence,
            source_type="service_map",
            source_file="service-map.json",
            source_location=f"service-map.json:services[{index}]",
            masked_excerpt=f"{service_name} maps to {service_path} with {dependency_type} dependency_type",
        )
    return refs


def confidence_from_evidence(
    *,
    supporting_evidence_refs: list[str],
    contradicting_evidence_refs: list[str],
    missing_data: list[str],
    evidence_by_id: dict[str, dict[str, Any]],
) -> str:
    if not supporting_evidence_refs:
        return "unknown"
    source_types = {
        str(evidence_by_id[evidence_ref]["source_type"])
        for evidence_ref in supporting_evidence_refs
        if evidence_ref in evidence_by_id
    }
    has_direct = bool(source_types & {"log", "metric"})
    if {"log", "metric"}.issubset(source_types) and not contradicting_evidence_refs and not missing_data:
        return "high"
    if has_direct and not contradicting_evidence_refs:
        return "medium"
    return "low"


def build_evidence_claim_summary(
    *,
    preflight_summary: dict[str, Any],
    metric_summary: dict[str, Any],
    state_summary: dict[str, Any],
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    threshold_refs = build_threshold_evidence(evidence=evidence, state_summary=state_summary)
    bucket_refs = build_bucket_evidence(evidence=evidence, metric_summary=metric_summary)
    context_refs = build_context_evidence(evidence=evidence, metric_summary=metric_summary)
    service_map_refs = build_service_map_evidence(evidence=evidence, preflight_summary=preflight_summary)

    state_by_key = {
        (str(state["service_path"]), str(state["bucket_start_utc"])): state
        for state in state_summary.get("bucket_states", [])
    }
    metric_by_key = {
        (str(bucket["service_path"]), str(bucket["bucket_start_utc"])): bucket
        for bucket in metric_summary.get("bucket_metrics", [])
    }

    for key in sorted(bucket_refs):
        state = state_by_key.get(key)
        bucket = metric_by_key.get(key)
        if not state or not bucket:
            continue
        service_path, bucket_start_utc = key
        threshold_ref = threshold_refs.get(service_path)
        bucket_ref = bucket_refs[key]
        metrics = bucket.get("metrics", {})
        request_count = metric_output_value(metrics.get("request_count", {}))
        error_count = metric_output_value(metrics.get("error_count", {}))
        error_rate = metric_output_value(metrics.get("error_rate_pct", {}))
        evidence_refs = [ref for ref in [threshold_ref, bucket_ref] if ref]
        if state.get("bucket_state") == "breach":
            threshold_value = None
            breach_reasons = state.get("breach_reasons", [])
            if breach_reasons:
                threshold_value = threshold_output_value(float(breach_reasons[0]["threshold"]))
            claims.append(
                claim_with_marker(
                    {
                        "claim_id": next_claim_id(claims),
                        "claim_type": "confirmed_fact",
                        "statement": (
                            f"The {display_bucket_time(str(bucket['bucket_start_local']))} {service_path} bucket "
                            f"has request_count={request_count}, error_count={error_count}, "
                            f"and error_rate_pct={error_rate}, which exceeds the {threshold_value} threshold."
                        ),
                        "evidence_refs": evidence_refs,
                    }
                )
            )
        elif state.get("window_type") == "incident" and state.get("bucket_state") == "healthy":
            claims.append(
                claim_with_marker(
                    {
                        "claim_id": next_claim_id(claims),
                        "claim_type": "confirmed_fact",
                        "statement": (
                            f"The {display_bucket_time(str(bucket['bucket_start_local']))} {service_path} bucket "
                            f"has request_count={request_count}, error_count={error_count}, "
                            f"and error_rate_pct={error_rate}, so it does not breach the configured threshold."
                        ),
                        "evidence_refs": evidence_refs,
                    }
                )
            )

    for context_key in sorted(context_refs):
        context = next(
            (
                item
                for item in metric_summary.get("context_metrics", [])
                if (str(item["service_path"]), str(item["bucket_start_utc"])) == context_key
            ),
            None,
        )
        if not context:
            continue
        metrics = context.get("metrics", {})
        cpu = metric_output_value(metrics.get("cpu_utilization_median_pct", {}))
        memory = metric_output_value(metrics.get("memory_utilization_median_pct", {}))
        claims.append(
            claim_with_marker(
                {
                    "claim_id": next_claim_id(claims),
                    "claim_type": "confirmed_fact",
                    "statement": (
                        f"The {display_bucket_time(str(context['bucket_start_local']))} {context['service_path']} "
                        f"context metrics show cpu_utilization_median_pct={cpu} and "
                        f"memory_utilization_median_pct={memory}."
                    ),
                    "evidence_refs": [context_refs[context_key]],
                }
            )
        )

    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    for path_state in state_summary.get("service_paths", []):
        status = str(path_state.get("status"))
        if status == "healthy":
            continue
        service_path = str(path_state["service_path"])
        supporting_refs = [
            evidence_ref
            for key, evidence_ref in bucket_refs.items()
            if key[0] == service_path
        ]
        if service_path in service_map_refs:
            supporting_refs.append(service_map_refs[service_path])
        missing_data = [
            "No downstream dependency error metrics",
            "No trace-level causal chain",
            "No independent exchange-side status feed",
        ]
        claims.append(
            claim_with_marker(
                {
                    "claim_id": next_claim_id(claims),
                    "claim_type": "hypothesis",
                    "statement": (
                        f"{service_path} degradation is a plausible incident-window impact hypothesis, "
                        "but the bundle does not prove the underlying root cause."
                    ),
                    "supporting_evidence_refs": supporting_refs,
                    "contradicting_evidence_refs": [],
                    "missing_data": missing_data,
                    "confidence": confidence_from_evidence(
                        supporting_evidence_refs=supporting_refs,
                        contradicting_evidence_refs=[],
                        missing_data=missing_data,
                        evidence_by_id=evidence_by_id,
                    ),
                }
            )
        )

    claims.append(
        claim_with_marker(
            {
                "claim_id": next_claim_id(claims),
                "claim_type": "unknown",
                "statement": "The current bundle does not establish a root cause.",
                "missing_data": [
                    "No downstream dependency error metrics",
                    "No trace-level causal chain",
                    "No independent exchange-side status feed",
                ],
            }
        )
    )

    claim_counts = summarize_issues([{"issue_code": claim["claim_type"]} for claim in claims])
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "status": state_summary["run"]["status"],
        "contract_version": CONTRACT_VERSION,
        "evidence_count": len(evidence),
        "claim_count": len(claims),
        "claim_counts": claim_counts,
        "evidence": evidence,
        "claims": claims,
        "raw_excerpts_emitted": False,
    }


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
        observed_time_status = "missing"
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
                observed_time_status = "invalid_optional_field"
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
            else:
                observed_time_status = "valid"

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
                    "observed_time_status": observed_time_status,
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


def combined_normalized_records(
    *,
    logs_result: dict[str, Any] | None,
    metrics_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    normalized_records: list[dict[str, Any]] = []
    if logs_result is not None:
        normalized_records.extend(logs_result["normalized_records"])
    if metrics_result is not None:
        normalized_records.extend(metrics_result["normalized_records"])
    return normalized_records


def build_bucket_summary(
    *,
    logs_result: dict[str, Any] | None,
    metrics_result: dict[str, Any] | None,
    incident_summary: dict[str, Any],
) -> dict[str, Any]:
    timezone_name = str(incident_summary["timezone"])
    bucket_groups: dict[tuple[str, str], dict[str, Any]] = {}

    normalized_records = combined_normalized_records(logs_result=logs_result, metrics_result=metrics_result)

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


def build_context_metrics(
    *, metrics_result: dict[str, Any] | None, incident_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    if metrics_result is None:
        return []

    timezone_name = str(incident_summary["timezone"])
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in metrics_result["normalized_records"]:
        metric_name = record.get("metric_name")
        if metric_name not in PERCENT_METRIC_NAMES:
            continue

        timestamp = record["timestamp"]
        assert isinstance(timestamp, datetime)
        bucket_start = utc_bucket_start(timestamp)
        bucket_start_utc = isoformat_utc(bucket_start)
        service_path = str(record["service_path"])
        key = (service_path, bucket_start_utc)

        if key not in groups:
            groups[key] = {
                "service_path": service_path,
                "window_type": record["window_type"],
                "bucket_start_utc": bucket_start_utc,
                "bucket_start_local": isoformat_local(bucket_start, timezone_name),
                "source_for_m015": "metrics.csv",
                "source_locations": [],
                "cpu_utilization_pct": [],
                "memory_utilization_pct": [],
            }
        group = groups[key]
        if group["window_type"] != record["window_type"]:
            group["window_type"] = "mixed"
        group["source_locations"].append(record["source_location"])
        group[str(metric_name)].append(float(record["value"]))

    context_metrics: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        cpu_samples = list(group["cpu_utilization_pct"])
        memory_samples = list(group["memory_utilization_pct"])
        context_metrics.append(
            {
                "service_path": group["service_path"],
                "window_type": group["window_type"],
                "bucket_start_utc": group["bucket_start_utc"],
                "bucket_start_local": group["bucket_start_local"],
                "source_for_m015": group["source_for_m015"],
                "source_locations": sorted(group["source_locations"]),
                "metrics": {
                    "cpu_utilization_median_pct": context_metric_value(
                        value=median_value(cpu_samples),
                        sample_count=len(cpu_samples),
                    ),
                    "memory_utilization_median_pct": context_metric_value(
                        value=median_value(memory_samples),
                        sample_count=len(memory_samples),
                    ),
                },
            }
        )
    return context_metrics


def build_metric_summary(
    *,
    logs_result: dict[str, Any] | None,
    metrics_result: dict[str, Any] | None,
    incident_summary: dict[str, Any],
    record_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    timezone_name = str(incident_summary["timezone"])
    primary_telemetry = record_summary["primary_telemetry"]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    source_name = "logs.jsonl" if primary_telemetry == "logs.jsonl" else "metrics.csv"
    metric_issues: list[dict[str, Any]] = []

    for record in combined_normalized_records(logs_result=logs_result, metrics_result=metrics_result):
        if primary_telemetry == "logs.jsonl" and record["source_type"] != "log":
            continue
        if primary_telemetry == "metrics.csv" and record["source_type"] != "metric":
            continue

        timestamp = record["event_time"] if record["source_type"] == "log" else record["timestamp"]
        assert isinstance(timestamp, datetime)
        bucket_start = utc_bucket_start(timestamp)
        bucket_start_utc = isoformat_utc(bucket_start)
        service_path = str(record["service_path"])
        key = (service_path, bucket_start_utc)

        if key not in groups:
            groups[key] = {
                "service_path": service_path,
                "window_type": record["window_type"],
                "bucket_start_utc": bucket_start_utc,
                "bucket_start_local": isoformat_local(bucket_start, timezone_name),
                "source_for_m001_m007": source_name,
                "source_for_m008_m009": source_name,
                "request_count": 0,
                "error_count": 0,
                "latency_samples": [],
                "ingestion_lag_samples": [],
                "ingestion_lag_missing_input_count": 0,
                "ingestion_lag_invalid_optional_field_count": 0,
                "source_locations": [],
            }
        group = groups[key]
        if group["window_type"] != record["window_type"]:
            group["window_type"] = "mixed"
        group["source_locations"].append(record["source_location"])

        if record["source_type"] == "log":
            group["request_count"] += 1
            if record["status"] in ERROR_STATUSES:
                group["error_count"] += 1
            if record["latency_ms"] is not None:
                group["latency_samples"].append(float(record["latency_ms"]))
            if record["observed_time"] is not None:
                assert isinstance(record["observed_time"], datetime)
                event_time = record["event_time"]
                assert isinstance(event_time, datetime)
                group["ingestion_lag_samples"].append(
                    (record["observed_time"] - event_time).total_seconds() * 1000
                )
            elif record.get("observed_time_status") == "invalid_optional_field":
                group["ingestion_lag_invalid_optional_field_count"] += 1
            else:
                group["ingestion_lag_missing_input_count"] += 1
        else:
            metric_name = record["metric_name"]
            value = float(record["value"])
            if metric_name == "request_count":
                group["request_count"] += int(value)
            elif metric_name == "error_count":
                group["error_count"] += int(value)
            elif metric_name == "latency_sample_ms":
                group["latency_samples"].append(value)
            elif metric_name == "ingestion_lag_sample_ms":
                group["ingestion_lag_samples"].append(value)

    bucket_metrics: list[dict[str, Any]] = []
    raw_threshold_values: dict[tuple[str, str], dict[str, float | None]] = {}
    for key in sorted(groups):
        group = groups[key]
        request_count = int(group["request_count"])
        error_count = int(group["error_count"])
        latency_samples = list(group["latency_samples"])
        ingestion_lag_samples = list(group["ingestion_lag_samples"])
        count_inconsistent = primary_telemetry == "metrics.csv" and error_count > request_count
        if count_inconsistent:
            metric_issues.append(
                {
                    "issue_code": "MET001_COUNT_INCONSISTENT",
                    "severity": "degraded",
                    "source_file": "metrics.csv",
                    "source_locations": sorted(group["source_locations"]),
                    "service_path": group["service_path"],
                    "bucket_start_utc": group["bucket_start_utc"],
                    "message": "The metrics.csv bucket has error_count greater than request_count, so request/error aggregation was invalidated.",
                }
            )

        if count_inconsistent:
            throughput: int | float | None = None
        else:
            throughput = rounded_float(Decimal(request_count) / Decimal(60))

        if count_inconsistent:
            error_rate_value = None
            error_rate_raw = None
            error_rate_reason = "not_applicable"
        elif request_count == 0:
            error_rate_value: float | None = None
            error_rate_raw: float | None = None
            error_rate_reason = "zero_denominator"
        else:
            error_rate_raw_decimal = Decimal(error_count) / Decimal(request_count) * Decimal(100)
            error_rate_raw = float(error_rate_raw_decimal)
            error_rate_value = rounded_float(error_rate_raw_decimal)
            error_rate_reason = None

        latency_p50, latency_p50_reason = nearest_rank_value(latency_samples, Decimal("0.50"), 1)
        latency_p95_raw, _latency_p95_raw_reason = nearest_rank_raw_value(latency_samples, Decimal("0.95"), 20)
        latency_p95, latency_p95_reason = nearest_rank_value(latency_samples, Decimal("0.95"), 20)
        latency_p99_raw, _latency_p99_raw_reason = nearest_rank_raw_value(latency_samples, Decimal("0.99"), 100)
        latency_p99, latency_p99_reason = nearest_rank_value(latency_samples, Decimal("0.99"), 100)
        ingestion_lag_p50, ingestion_lag_p50_reason = nearest_rank_value(
            ingestion_lag_samples, Decimal("0.50"), 1
        )
        ingestion_lag_p95_raw, _ingestion_lag_p95_raw_reason = nearest_rank_raw_value(
            ingestion_lag_samples, Decimal("0.95"), 20
        )
        ingestion_lag_p95, ingestion_lag_p95_reason = nearest_rank_value(
            ingestion_lag_samples, Decimal("0.95"), 20
        )
        ingestion_lag_p99, ingestion_lag_p99_reason = nearest_rank_value(
            ingestion_lag_samples, Decimal("0.99"), 100
        )
        raw_threshold_values[(str(group["service_path"]), str(group["bucket_start_utc"]))] = {
            "error_rate_pct": error_rate_raw,
            "latency_p95_ms": latency_p95_raw,
            "latency_p99_ms": latency_p99_raw,
            "ingestion_lag_p95_ms": ingestion_lag_p95_raw,
        }

        bucket_metrics.append(
            {
                "service_path": group["service_path"],
                "window_type": group["window_type"],
                "bucket_start_utc": group["bucket_start_utc"],
                "bucket_start_local": group["bucket_start_local"],
                "source_for_m001_m007": group["source_for_m001_m007"],
                "source_for_m008_m009": group["source_for_m008_m009"],
                "source_locations": sorted(group["source_locations"]),
                "metrics": {
                    "request_count": metric_value(
                        m_id="M-001",
                        value=None if count_inconsistent else request_count,
                        unit="count",
                        reason_code="not_applicable" if count_inconsistent else None,
                    ),
                    "error_count": metric_value(
                        m_id="M-002",
                        value=None if count_inconsistent else error_count,
                        unit="count",
                        reason_code="not_applicable" if count_inconsistent else None,
                    ),
                    "throughput_rps": metric_value(
                        m_id="M-003",
                        value=throughput,
                        unit="requests/second",
                        reason_code="not_applicable" if count_inconsistent else None,
                    ),
                    "error_rate_pct": metric_value(
                        m_id="M-004",
                        value=error_rate_value,
                        unit="percent",
                        reason_code=error_rate_reason,
                    ),
                    "latency_p50_ms": metric_value(
                        m_id="M-005",
                        value=latency_p50,
                        unit="ms",
                        sample_count=len(latency_samples),
                        reason_code=latency_p50_reason,
                    ),
                    "latency_p95_ms": metric_value(
                        m_id="M-006",
                        value=latency_p95,
                        unit="ms",
                        sample_count=len(latency_samples),
                        reason_code=latency_p95_reason,
                    ),
                    "latency_p99_ms": metric_value(
                        m_id="M-007",
                        value=latency_p99,
                        unit="ms",
                        sample_count=len(latency_samples),
                        reason_code=latency_p99_reason,
                    ),
                    "ingestion_lag_ms": ingestion_lag_metric(
                        sample_count=len(ingestion_lag_samples),
                        missing_input_count=int(group["ingestion_lag_missing_input_count"]),
                        invalid_optional_field_count=int(group["ingestion_lag_invalid_optional_field_count"]),
                        source=group["source_for_m008_m009"],
                    ),
                    "ingestion_lag_p50_ms": metric_value(
                        m_id="M-009",
                        value=ingestion_lag_p50,
                        unit="ms",
                        sample_count=len(ingestion_lag_samples),
                        reason_code=ingestion_lag_p50_reason,
                    ),
                    "ingestion_lag_p95_ms": metric_value(
                        m_id="M-009",
                        value=ingestion_lag_p95,
                        unit="ms",
                        sample_count=len(ingestion_lag_samples),
                        reason_code=ingestion_lag_p95_reason,
                    ),
                    "ingestion_lag_p99_ms": metric_value(
                        m_id="M-009",
                        value=ingestion_lag_p99,
                        unit="ms",
                        sample_count=len(ingestion_lag_samples),
                        reason_code=ingestion_lag_p99_reason,
                    ),
                },
            }
        )

    comparison_metrics = build_comparison_metrics(bucket_metrics)
    context_metrics = build_context_metrics(metrics_result=metrics_result, incident_summary=incident_summary)
    metric_issue_counts = summarize_issues(metric_issues)
    metric_status = "degraded" if record_summary["status"] != "success" or metric_issues else "success"

    metric_summary = {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "status": metric_status,
        "contract_version": CONTRACT_VERSION,
        "calculated_m_ids": list(CALCULATED_METRIC_IDS),
        "primary_telemetry": primary_telemetry,
        "bucket_size_seconds": 60,
        "time_basis": "UTC",
        "display_timezone": timezone_name,
        "sort_order": ["service_path", "bucket_start_utc"],
        "bucket_count": len(bucket_metrics),
        "bucket_metrics": bucket_metrics,
        "comparison_metrics": comparison_metrics,
        "comparison_metric_count": len(comparison_metrics),
        "context_metrics": context_metrics,
        "context_metric_count": len(context_metrics),
        "issue_counts": metric_issue_counts,
        "issues": metric_issues,
        "raw_excerpts_emitted": False,
    }
    state_summary = build_state_summary(
        incident_summary=incident_summary,
        record_summary=record_summary,
        metric_issue_counts=metric_issue_counts,
        bucket_metrics=bucket_metrics,
        raw_threshold_values=raw_threshold_values,
    )
    return metric_summary, state_summary


def parse_telemetry_records(
    *, sanitized_files: dict[str, str], preflight_summary: dict[str, Any]
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    incident_summary = preflight_summary["incident"]
    service_map_summary = preflight_summary["service_map"]

    logs_result = None
    metrics_result = None
    if "logs.jsonl" in sanitized_files:
        logs_result, issue = parse_logs_jsonl(sanitized_files["logs.jsonl"], incident_summary)
        if issue is not None:
            return None, None, None, None, issue
    if "metrics.csv" in sanitized_files:
        metrics_result, issue = parse_metrics_csv(sanitized_files["metrics.csv"], incident_summary, service_map_summary)
        if issue is not None:
            return None, None, None, None, issue

    summary = build_record_summary(logs_result=logs_result, metrics_result=metrics_result)
    if int(summary["accepted_in_window"]["total"]) == 0:
        return None, None, None, None, issue_payload(
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
    metric_summary, state_summary = build_metric_summary(
        logs_result=logs_result,
        metrics_result=metrics_result,
        incident_summary=incident_summary,
        record_summary=summary,
    )
    return summary, bucket_summary, metric_summary, state_summary, None


def contract_reference_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "metrics-validation-contract.md"


def contract_reference_sha256() -> tuple[str | None, dict[str, Any] | None]:
    try:
        digest = hashlib.sha256(contract_reference_path().read_bytes()).hexdigest()
    except OSError:
        return None, issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="OUT001_SCHEMA",
            message="The metric contract reference could not be read for analysis.json.",
            argument="output",
        )
    return digest, None


def source_files_from_preflight(preflight_summary: dict[str, Any]) -> list[str]:
    files = preflight_summary.get("files", [])
    names: list[str] = []
    if isinstance(files, list):
        for item in files:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(str(item["name"]))
    return sorted(names)


def analysis_context_files(*, preflight_summary: dict[str, Any], primary_telemetry: str | None) -> list[str]:
    available_files = set(source_files_from_preflight(preflight_summary))
    context_order = ("logs.jsonl", "metrics.csv", "service-map.json")
    return [name for name in context_order if name in available_files and name != primary_telemetry]


def analysis_bucket_metrics(
    *, metric_summary: dict[str, Any], state_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    states_by_key = {
        (str(state["service_path"]), str(state["bucket_start_utc"])): state
        for state in state_summary.get("bucket_states", [])
    }
    buckets: list[dict[str, Any]] = []
    for bucket in metric_summary.get("bucket_metrics", []):
        key = (str(bucket["service_path"]), str(bucket["bucket_start_utc"]))
        state = states_by_key.get(key, {})
        analysis_bucket: dict[str, Any] = {
            "service_path": bucket["service_path"],
            "window_type": bucket["window_type"],
            "bucket_start_utc": bucket["bucket_start_utc"],
            "bucket_start_local": bucket["bucket_start_local"],
            "bucket_state": state.get("bucket_state", "unknown"),
            "metrics": bucket["metrics"],
        }
        if "breach_reasons" in state:
            analysis_bucket["breach_reasons"] = [
                {
                    "metric": reason["metric"],
                    "value": reason["value"],
                    "threshold": float(reason["threshold"]),
                    "operator": reason["operator"],
                }
                for reason in state["breach_reasons"]
            ]
        buckets.append(analysis_bucket)
    return sorted(buckets, key=lambda item: (str(item["service_path"]), str(item["bucket_start_utc"])))


def build_analysis_summary(
    *,
    preflight_summary: dict[str, Any],
    record_summary: dict[str, Any],
    metric_summary: dict[str, Any],
    state_summary: dict[str, Any],
    evidence_summary: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    contract_sha256, issue = contract_reference_sha256()
    if issue is not None:
        return None, issue
    assert contract_sha256 is not None

    incident = preflight_summary["incident"]
    run_issues = list(record_summary.get("issues", [])) + list(metric_summary.get("issues", []))
    run_state = state_summary["run"]
    primary_telemetry = record_summary.get("primary_telemetry")
    analysis = {
        "schema_version": SCHEMA_VERSION,
        "stage": CLI_STAGE,
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": contract_sha256,
        "fixture_id": incident["incident_id"],
        "run": {
            "status": run_state["status"],
            "exit_code": run_state["exit_code"],
            "issue_counts": run_state.get("issue_counts", {}),
            "issues": run_issues,
            "limitations": run_state.get("limitations", []),
        },
        "incident": {
            "incident_id": incident["incident_id"],
            "timezone": incident["timezone"],
            "baseline_window": incident["baseline_window"],
            "incident_window": incident["incident_window"],
        },
        "source_summary": {
            "primary_telemetry": primary_telemetry,
            "context_files": analysis_context_files(
                preflight_summary=preflight_summary,
                primary_telemetry=str(primary_telemetry) if primary_telemetry is not None else None,
            ),
            "metric_contract_reference": CONTRACT_REFERENCE_RELATIVE_PATH,
        },
        "record_counts": record_summary["record_counts"],
        "service_paths": state_summary["service_paths"],
        "bucket_metrics": analysis_bucket_metrics(
            metric_summary=metric_summary,
            state_summary=state_summary,
        ),
        "comparison_metrics": metric_summary["comparison_metrics"],
        "context_metrics": metric_summary["context_metrics"],
        "evidence": evidence_summary["evidence"],
        "claims": evidence_summary["claims"],
        "raw_excerpts_emitted": False,
    }
    return analysis, None


def write_analysis_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / ANALYSIS_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI019_ANALYSIS_WRITE_FAILED",
            message="The analysis.json file could not be written.",
            argument="output",
        )
    return None


def output_validation_issue(
    *,
    issue_code: str,
    message: str,
    source_file: str | None = None,
    source_location: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "issue_code": issue_code,
        "severity": "fatal",
        "message": message,
    }
    if source_file is not None:
        issue["source_file"] = source_file
    if source_location is not None:
        issue["source_location"] = source_location
    return issue


def is_json_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def is_relative_output_reference(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if Path(value).is_absolute():
        return False
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return False
    return True


def add_schema_issue(issues: list[dict[str, Any]], message: str, source_location: str) -> None:
    issues.append(
        output_validation_issue(
            issue_code="OUT001_SCHEMA",
            message=message,
            source_file=ANALYSIS_FILENAME,
            source_location=source_location,
        )
    )


def validate_top_level_analysis_schema(analysis: Any, issues: list[dict[str, Any]]) -> None:
    if not isinstance(analysis, dict):
        add_schema_issue(issues, "analysis.json must contain a top-level object.", "$")
        return

    required_types: dict[str, type | tuple[type, ...]] = {
        "schema_version": str,
        "stage": str,
        "contract_version": str,
        "contract_sha256": str,
        "fixture_id": str,
        "run": dict,
        "incident": dict,
        "source_summary": dict,
        "record_counts": dict,
        "service_paths": list,
        "bucket_metrics": list,
        "comparison_metrics": list,
        "context_metrics": list,
        "evidence": list,
        "claims": list,
    }
    for field, expected_type in required_types.items():
        if not isinstance(analysis.get(field), expected_type):
            add_schema_issue(issues, f"analysis.json field {field} has an invalid type.", f"$.{field}")

    if analysis.get("schema_version") != SCHEMA_VERSION:
        add_schema_issue(issues, "analysis.json schema_version is not supported.", "$.schema_version")
    if analysis.get("stage") != CLI_STAGE:
        add_schema_issue(issues, "analysis.json stage does not match the current CLI stage.", "$.stage")
    if analysis.get("contract_version") != CONTRACT_VERSION:
        add_schema_issue(issues, "analysis.json contract_version is not supported.", "$.contract_version")

    contract_sha256, issue = contract_reference_sha256()
    if issue is None and analysis.get("contract_sha256") != contract_sha256:
        add_schema_issue(issues, "analysis.json contract_sha256 does not match the bundled contract.", "$.contract_sha256")

    if analysis.get("raw_excerpts_emitted") is not False:
        add_schema_issue(issues, "analysis.json must set raw_excerpts_emitted to false.", "$.raw_excerpts_emitted")

    run = analysis.get("run")
    if isinstance(run, dict):
        if run.get("status") not in RUN_STATUS_VALUES:
            add_schema_issue(issues, "analysis.json run.status is not valid.", "$.run.status")
        if not isinstance(run.get("exit_code"), int) or isinstance(run.get("exit_code"), bool):
            add_schema_issue(issues, "analysis.json run.exit_code must be an integer.", "$.run.exit_code")
        if not isinstance(run.get("issues"), list):
            add_schema_issue(issues, "analysis.json run.issues must be a list.", "$.run.issues")
        if not isinstance(run.get("limitations"), list):
            add_schema_issue(issues, "analysis.json run.limitations must be a list.", "$.run.limitations")

    source_summary = analysis.get("source_summary")
    if isinstance(source_summary, dict):
        primary = source_summary.get("primary_telemetry")
        if primary is not None and primary not in ALLOWED_BUNDLE_FILES:
            add_schema_issue(issues, "source_summary.primary_telemetry is not an allowed bundle file.", "$.source_summary.primary_telemetry")
        context_files = source_summary.get("context_files")
        if not isinstance(context_files, list) or not all(file_name in ALLOWED_BUNDLE_FILES for file_name in context_files):
            add_schema_issue(issues, "source_summary.context_files must contain allowed relative bundle file names.", "$.source_summary.context_files")
        contract_reference = source_summary.get("metric_contract_reference")
        if contract_reference != CONTRACT_REFERENCE_RELATIVE_PATH:
            add_schema_issue(issues, "source_summary.metric_contract_reference does not match the bundled contract path.", "$.source_summary.metric_contract_reference")


def validate_analysis_bucket_metrics(analysis: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    bucket_metrics = analysis.get("bucket_metrics")
    if not isinstance(bucket_metrics, list):
        return

    for index, bucket in enumerate(bucket_metrics):
        location = f"$.bucket_metrics[{index}]"
        if not isinstance(bucket, dict):
            add_schema_issue(issues, "Each bucket_metrics item must be an object.", location)
            continue
        if bucket.get("window_type") not in WINDOW_TYPE_VALUES:
            add_schema_issue(issues, "bucket_metrics window_type is not valid.", f"{location}.window_type")
        if bucket.get("bucket_state") not in BUCKET_STATE_VALUES:
            add_schema_issue(issues, "bucket_metrics bucket_state is not valid.", f"{location}.bucket_state")
        if not isinstance(bucket.get("service_path"), str) or bucket.get("service_path") not in STANDARD_SERVICE_PATHS:
            add_schema_issue(issues, "bucket_metrics service_path is not valid.", f"{location}.service_path")
        if not isinstance(bucket.get("metrics"), dict):
            add_schema_issue(issues, "bucket_metrics metrics must be an object.", f"{location}.metrics")

        breach_reasons = bucket.get("breach_reasons")
        if breach_reasons is None:
            continue
        if not isinstance(breach_reasons, list):
            add_schema_issue(issues, "bucket_metrics breach_reasons must be a list.", f"{location}.breach_reasons")
            continue
        for reason_index, reason in enumerate(breach_reasons):
            reason_location = f"{location}.breach_reasons[{reason_index}]"
            if not isinstance(reason, dict):
                add_schema_issue(issues, "Each breach reason must be an object.", reason_location)
                continue
            if set(reason) != BREACH_REASON_KEYS:
                add_schema_issue(
                    issues,
                    "Breach reasons must expose only metric, value, threshold, and operator.",
                    reason_location,
                )
            if not isinstance(reason.get("metric"), str):
                add_schema_issue(issues, "Breach reason metric must be a string.", f"{reason_location}.metric")
            if not is_json_number(reason.get("value")):
                add_schema_issue(issues, "Breach reason value must be numeric.", f"{reason_location}.value")
            if not is_json_number(reason.get("threshold")):
                add_schema_issue(issues, "Breach reason threshold must be numeric.", f"{reason_location}.threshold")
            if reason.get("operator") != ">":
                add_schema_issue(issues, "Breach reason operator must be >.", f"{reason_location}.operator")


def validate_analysis_evidence_and_claims(analysis: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    evidence_items = analysis.get("evidence")
    claim_items = analysis.get("claims")
    if not isinstance(evidence_items, list) or not isinstance(claim_items, list):
        return

    evidence_ids: set[str] = set()
    for index, evidence in enumerate(evidence_items):
        location = f"$.evidence[{index}]"
        if not isinstance(evidence, dict):
            add_schema_issue(issues, "Each evidence item must be an object.", location)
            continue
        evidence_id = evidence.get("evidence_id")
        if not isinstance(evidence_id, str) or EVIDENCE_ID_PATTERN.fullmatch(evidence_id) is None:
            add_schema_issue(issues, "evidence_id must use the E-001 format.", f"{location}.evidence_id")
        elif evidence_id in evidence_ids:
            add_schema_issue(issues, "evidence_id values must be unique.", f"{location}.evidence_id")
        else:
            evidence_ids.add(evidence_id)

        if evidence.get("source_type") not in EVIDENCE_SOURCE_TYPES:
            add_schema_issue(issues, "evidence source_type is not valid.", f"{location}.source_type")
        if not is_relative_output_reference(evidence.get("source_file")):
            add_schema_issue(issues, "evidence source_file must be a relative file reference.", f"{location}.source_file")
        if not isinstance(evidence.get("source_location"), str) or not evidence.get("source_location"):
            add_schema_issue(issues, "evidence source_location must be a non-empty string.", f"{location}.source_location")
        masked_excerpt = evidence.get("masked_excerpt")
        if masked_excerpt is not None and (not isinstance(masked_excerpt, str) or len(masked_excerpt) > 300):
            add_schema_issue(issues, "evidence masked_excerpt must be a string of at most 300 characters.", f"{location}.masked_excerpt")

    claim_ids: set[str] = set()
    for index, claim in enumerate(claim_items):
        location = f"$.claims[{index}]"
        if not isinstance(claim, dict):
            add_schema_issue(issues, "Each claim item must be an object.", location)
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or CLAIM_ID_PATTERN.fullmatch(claim_id) is None:
            add_schema_issue(issues, "claim_id must use the C-001 format.", f"{location}.claim_id")
        elif claim_id in claim_ids:
            add_schema_issue(issues, "claim_id values must be unique.", f"{location}.claim_id")
        else:
            claim_ids.add(claim_id)

        if claim.get("report_claim_marker") != f"[{claim_id}]":
            add_schema_issue(issues, "claim report_claim_marker must match the claim ID.", f"{location}.report_claim_marker")
        if claim.get("claim_type") not in CLAIM_TYPE_VALUES:
            add_schema_issue(issues, "claim_type is not valid.", f"{location}.claim_type")
        if not isinstance(claim.get("statement"), str) or not claim.get("statement"):
            add_schema_issue(issues, "claim statement must be a non-empty string.", f"{location}.statement")

        claim_type = claim.get("claim_type")
        if claim_type == "confirmed_fact":
            evidence_refs = claim.get("evidence_refs")
            if not isinstance(evidence_refs, list):
                add_schema_issue(issues, "confirmed_fact evidence_refs must be a list.", f"{location}.evidence_refs")
                continue
            if not evidence_refs:
                issues.append(
                    output_validation_issue(
                        issue_code="OUT003_FACT_WITHOUT_EVIDENCE",
                        message="confirmed_fact claims must cite at least one evidence ID.",
                        source_file=ANALYSIS_FILENAME,
                        source_location=f"{location}.evidence_refs",
                    )
                )
            for evidence_ref in evidence_refs:
                if evidence_ref not in evidence_ids:
                    issues.append(
                        output_validation_issue(
                            issue_code="OUT002_BROKEN_EVIDENCE_REF",
                            message="A claim references an evidence ID that does not exist.",
                            source_file=ANALYSIS_FILENAME,
                            source_location=f"{location}.evidence_refs",
                        )
                    )
        elif claim_type == "hypothesis":
            supporting_refs = claim.get("supporting_evidence_refs")
            contradicting_refs = claim.get("contradicting_evidence_refs", [])
            if not isinstance(supporting_refs, list) or not supporting_refs:
                add_schema_issue(issues, "hypothesis supporting_evidence_refs must be a non-empty list.", f"{location}.supporting_evidence_refs")
            if not isinstance(contradicting_refs, list):
                add_schema_issue(issues, "hypothesis contradicting_evidence_refs must be a list.", f"{location}.contradicting_evidence_refs")
                contradicting_refs = []
            if claim.get("confidence") not in CLAIM_CONFIDENCE_VALUES:
                add_schema_issue(issues, "hypothesis confidence is not valid.", f"{location}.confidence")
            if not isinstance(claim.get("missing_data"), list):
                add_schema_issue(issues, "hypothesis missing_data must be a list.", f"{location}.missing_data")
            for evidence_ref in list(supporting_refs or []) + list(contradicting_refs):
                if evidence_ref not in evidence_ids:
                    issues.append(
                        output_validation_issue(
                            issue_code="OUT002_BROKEN_EVIDENCE_REF",
                            message="A hypothesis references an evidence ID that does not exist.",
                            source_file=ANALYSIS_FILENAME,
                            source_location=f"{location}.supporting_evidence_refs",
                        )
                    )
        elif claim_type == "unknown":
            if not isinstance(claim.get("missing_data"), list) or not claim.get("missing_data"):
                add_schema_issue(issues, "unknown claims must include non-empty missing_data.", f"{location}.missing_data")


def validate_output_secret_residue(*, output_path: Path, issues: list[dict[str, Any]]) -> list[str]:
    checked_files: list[str] = []
    for file_path in sorted(path for path in output_path.rglob("*") if path.is_file()):
        relative_file = file_path.relative_to(output_path).as_posix()
        checked_files.append(relative_file)
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(
                output_validation_issue(
                    issue_code="OUT005_SECRET_RESIDUE",
                    message="A generated output file is not UTF-8 text and could not be scanned for sensitive residue.",
                    source_file=relative_file,
                )
            )
            continue
        except OSError:
            issues.append(
                output_validation_issue(
                    issue_code="OUT005_SECRET_RESIDUE",
                    message="A generated output file could not be read for sensitive residue scanning.",
                    source_file=relative_file,
                )
            )
            continue
        for match in find_sensitive_matches(text, source_file=relative_file, include_redacted=False):
            issues.append(
                output_validation_issue(
                    issue_code="OUT005_SECRET_RESIDUE",
                    message=f"Sensitive residue pattern remained in generated output: {match['type']}.",
                    source_file=relative_file,
                    source_location=f"L{match['line']}",
                )
            )
    return checked_files


def output_validation_summary(*, issues: list[dict[str, Any]], checked_files: list[str]) -> dict[str, Any]:
    issue_codes = {issue["issue_code"] for issue in issues}
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": CLI_STAGE,
        "status": "failed" if issues else "passed",
        "exit_code": EXIT_CODES["output_validation_error"] if issues else EXIT_CODES["ok"],
        "validator": "validate_bundle.py",
        "checked_files": checked_files,
        "checks": {
            "analysis_schema": "failed" if "OUT001_SCHEMA" in issue_codes else "passed",
            "evidence_references": "failed" if "OUT002_BROKEN_EVIDENCE_REF" in issue_codes else "passed",
            "confirmed_fact_evidence": "failed" if "OUT003_FACT_WITHOUT_EVIDENCE" in issue_codes else "passed",
            "report_claim_refs": "not_applicable_until_p4_16",
            "secret_residue": "failed" if "OUT005_SECRET_RESIDUE" in issue_codes else "passed",
        },
        "issue_counts": {"fatal": len(issues)},
        "issues": issues,
        "raw_excerpts_emitted": False,
    }


def write_output_validation_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / OUTPUT_VALIDATION_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI020_OUTPUT_VALIDATION_WRITE_FAILED",
            message="The output validation summary file could not be written.",
            argument="output",
        )
    return None


def validate_output_directory(
    *, output_path: Path, write_report: bool = True
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    issues: list[dict[str, Any]] = []
    checked_files: list[str] = []

    if not output_path.exists() or not output_path.is_dir():
        issues.append(
            output_validation_issue(
                issue_code="OUT001_SCHEMA",
                message="The output path must be an existing directory.",
                source_file=str(output_path),
            )
        )
        payload = output_validation_summary(issues=issues, checked_files=checked_files)
        return payload, issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="OUT001_SCHEMA",
            message="The output path must be an existing directory.",
            argument="output",
        )

    analysis_path = output_path / ANALYSIS_FILENAME
    analysis: Any = None
    if not analysis_path.exists():
        issues.append(
            output_validation_issue(
                issue_code="OUT001_SCHEMA",
                message="analysis.json is missing.",
                source_file=ANALYSIS_FILENAME,
            )
        )
    else:
        checked_files.append(ANALYSIS_FILENAME)
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            issues.append(
                output_validation_issue(
                    issue_code="OUT001_SCHEMA",
                    message="analysis.json must be valid UTF-8 JSON.",
                    source_file=ANALYSIS_FILENAME,
                )
            )
        except OSError:
            issues.append(
                output_validation_issue(
                    issue_code="OUT001_SCHEMA",
                    message="analysis.json could not be read.",
                    source_file=ANALYSIS_FILENAME,
                )
            )

    validate_top_level_analysis_schema(analysis, issues)
    if isinstance(analysis, dict):
        validate_analysis_bucket_metrics(analysis, issues)
        validate_analysis_evidence_and_claims(analysis, issues)

    scanned_files = validate_output_secret_residue(output_path=output_path, issues=issues)
    checked_files = sorted(set(checked_files + scanned_files))
    payload = output_validation_summary(issues=issues, checked_files=checked_files)

    if write_report:
        write_issue = write_output_validation_summary(output_path=output_path, payload=payload)
        if write_issue is not None:
            return payload, write_issue

    if issues:
        first_issue = issues[0]
        return payload, issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code=str(first_issue["issue_code"]),
            message=str(first_issue["message"]),
            argument="output",
            source_file=str(first_issue.get("source_file", ANALYSIS_FILENAME)),
        )
    return payload, None


def write_state_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / STATE_SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI017_STATE_SUMMARY_WRITE_FAILED",
            message="The state summary file could not be written.",
            argument="output",
        )
    return None


def write_evidence_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / EVIDENCE_SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI018_EVIDENCE_SUMMARY_WRITE_FAILED",
            message="The evidence summary file could not be written.",
            argument="output",
        )
    return None


def write_metric_summary(*, output_path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        (output_path / METRIC_SUMMARY_FILENAME).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return issue_payload(
            exit_code=EXIT_CODES["output_validation_error"],
            issue_code="CLI016_METRIC_SUMMARY_WRITE_FAILED",
            message="The metric summary file could not be written.",
            argument="output",
        )
    return None


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
    metric_summary: dict[str, Any],
    state_summary: dict[str, Any],
    evidence_summary: dict[str, Any],
    analysis_summary: dict[str, Any],
    output_validation_summary_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "stage": CLI_STAGE,
        "run_status": "analysis_validated",
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
            "metric_summary_file": METRIC_SUMMARY_FILENAME,
            "metric_summary_created": True,
            "state_summary_file": STATE_SUMMARY_FILENAME,
            "state_summary_created": True,
            "evidence_summary_file": EVIDENCE_SUMMARY_FILENAME,
            "evidence_summary_created": True,
            "analysis_json_file": ANALYSIS_FILENAME,
            "analysis_json_created": True,
            "output_validation_file": OUTPUT_VALIDATION_FILENAME,
            "output_validation_created": True,
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
        "metrics": {
            "metric_summary_file": METRIC_SUMMARY_FILENAME,
            "calculated_m_ids": metric_summary["calculated_m_ids"],
            "primary_telemetry": metric_summary["primary_telemetry"],
            "bucket_count": metric_summary["bucket_count"],
            "comparison_metric_count": metric_summary["comparison_metric_count"],
            "context_metric_count": metric_summary["context_metric_count"],
            "issue_counts": metric_summary["issue_counts"],
            "sort_order": metric_summary["sort_order"],
            "raw_excerpts_emitted": False,
        },
        "state": {
            "state_summary_file": STATE_SUMMARY_FILENAME,
            "run_status": state_summary["run"]["status"],
            "exit_code": state_summary["run"]["exit_code"],
            "service_path_count": len(state_summary["service_paths"]),
            "bucket_state_counts": state_summary["bucket_state_counts"],
            "path_status_counts": state_summary["path_status_counts"],
            "raw_excerpts_emitted": False,
        },
        "evidence": {
            "evidence_summary_file": EVIDENCE_SUMMARY_FILENAME,
            "status": evidence_summary["status"],
            "evidence_count": evidence_summary["evidence_count"],
            "claim_count": evidence_summary["claim_count"],
            "claim_counts": evidence_summary["claim_counts"],
            "raw_excerpts_emitted": False,
        },
        "analysis": {
            "analysis_json_file": ANALYSIS_FILENAME,
            "schema_version": analysis_summary["schema_version"],
            "contract_version": analysis_summary["contract_version"],
            "contract_sha256": analysis_summary["contract_sha256"],
            "fixture_id": analysis_summary["fixture_id"],
            "run_status": analysis_summary["run"]["status"],
            "service_path_count": len(analysis_summary["service_paths"]),
            "bucket_metric_count": len(analysis_summary["bucket_metrics"]),
            "evidence_count": len(analysis_summary["evidence"]),
            "claim_count": len(analysis_summary["claims"]),
            "raw_excerpts_emitted": False,
        },
        "output_validation": {
            "output_validation_file": OUTPUT_VALIDATION_FILENAME,
            "status": output_validation_summary_payload["status"],
            "exit_code": output_validation_summary_payload["exit_code"],
            "checks": output_validation_summary_payload["checks"],
            "issue_counts": output_validation_summary_payload["issue_counts"],
            "checked_file_count": len(output_validation_summary_payload["checked_files"]),
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
            "calculate M-001 through M-007 basic bucket metrics",
            "calculate M-008 through M-009 observability lag metrics",
            "calculate M-010 through M-013 baseline-vs-incident comparison metrics",
            "calculate M-015 CPU and memory context metrics",
            "invalidate metrics fallback count buckets when error_count exceeds request_count",
            "write metric-summary.json without raw excerpts",
            "judge bucket states from configured thresholds",
            "derive service path outage_start and recovery_time from consecutive buckets",
            "write state-summary.json without raw excerpts",
            "create evidence and claim summaries without raw excerpts",
            "write evidence-summary.json without raw excerpts",
            "write analysis.json without raw excerpts",
            "validate analysis.json structure, evidence references, claim evidence, and secret residue",
            "write output-validation.json without raw excerpts",
        ],
        "deferred_scope": [
            "openbell-report.md generation",
            "OUT004 report claim sentence validation after openbell-report.md exists",
            "M-016 through M-017 pipeline benchmark metric calculation",
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

    record_summary, bucket_summary, metric_summary, state_summary, issue = parse_telemetry_records(
        sanitized_files=sanitized_files,
        preflight_summary=preflight_summary,
    )
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert record_summary is not None
    assert bucket_summary is not None
    assert metric_summary is not None
    assert state_summary is not None
    evidence_summary = build_evidence_claim_summary(
        preflight_summary=preflight_summary,
        metric_summary=metric_summary,
        state_summary=state_summary,
    )
    analysis_summary, issue = build_analysis_summary(
        preflight_summary=preflight_summary,
        record_summary=record_summary,
        metric_summary=metric_summary,
        state_summary=state_summary,
        evidence_summary=evidence_summary,
    )
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    assert analysis_summary is not None

    issue = write_record_summary(output_path=output_path, payload=record_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_bucket_summary(output_path=output_path, payload=bucket_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_metric_summary(output_path=output_path, payload=metric_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_state_summary(output_path=output_path, payload=state_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_evidence_summary(output_path=output_path, payload=evidence_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    issue = write_analysis_summary(output_path=output_path, payload=analysis_summary)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])
    output_validation_summary_payload, issue = validate_output_directory(output_path=output_path, write_report=True)
    if issue is not None:
        write_stderr_json(issue)
        return int(issue["exit_code"])

    payload = success_payload(
        bundle_path=bundle_path,
        preflight_summary=preflight_summary,
        sanitization_summary=sanitization_summary,
        record_summary=record_summary,
        bucket_summary=bucket_summary,
        metric_summary=metric_summary,
        state_summary=state_summary,
        evidence_summary=evidence_summary,
        analysis_summary=analysis_summary,
        output_validation_summary_payload=output_validation_summary_payload,
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
