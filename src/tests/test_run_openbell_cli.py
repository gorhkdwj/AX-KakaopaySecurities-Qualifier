"""CLI, bundle-preflight, sanitizer, row-parser, bucket, and metric tests for OpenBell Guard.

P4-10 keeps the shared command-line entry point and adds M-001 through M-013
bucket, observability-lag, and comparison metric calculation for sanitized logs
and metrics. The script still must not create the final analysis outputs.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "scripts"
    / "run_openbell.py"
)
FIXTURE_BUNDLE = (
    PROJECT_ROOT
    / "src"
    / "tests"
    / "fixtures"
    / "domestic-market-open-min"
    / "bundle"
)
EXPECTED_ANALYSIS = (
    PROJECT_ROOT
    / "src"
    / "tests"
    / "fixtures"
    / "domestic-market-open-min"
    / "expected"
    / "analysis.json"
)

VALID_INCIDENT = {
    "schema_version": "1.0",
    "contract_version": "1.0.0",
    "incident_id": "temp-valid",
    "timezone": "Asia/Seoul",
    "baseline_window": {
        "start": "2026-06-30T08:58:00+09:00",
        "end": "2026-06-30T08:59:00+09:00",
    },
    "incident_window": {
        "start": "2026-06-30T09:00:00+09:00",
        "end": "2026-06-30T09:02:00+09:00",
    },
    "thresholds": {"market_data": {"error_rate_pct_max": 50.0}},
}

SEEDED_SECRET_VALUES = [
    "PRIVATEKEYLINE",
    "bearerTOKEN123",
    "abcdefghij.klmnopqrst.uvwxyzABCD",
    "plainsecretvalue",
    "analyst@example.com",
    "010-1234-5678",
    "123-456-789012",
]


def load_run_openbell_module():
    spec = importlib.util.spec_from_file_location("run_openbell", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_valid_incident(bundle_path: Path, payload: dict | None = None) -> None:
    write_json(bundle_path / "incident.json", payload or VALID_INCIDENT)


def write_minimal_logs(bundle_path: Path) -> None:
    (bundle_path / "logs.jsonl").write_text("{}\n", encoding="utf-8")


def write_logs(bundle_path: Path, rows: list[dict]) -> None:
    (bundle_path / "logs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def valid_log_row(**overrides: object) -> dict:
    row = {
        "event_time": "2026-06-30T09:00:05+09:00",
        "observed_time": "2026-06-30T09:00:06+09:00",
        "service_name": "quote-api",
        "service_path": "market_data",
        "dependency_type": "exchange",
        "status": "ok",
        "latency_ms": 100,
        "trace_id": "trace-temp",
        "log_type": "request",
        "severity": "info",
        "message": "synthetic request completed",
    }
    row.update(overrides)
    return row


def write_metrics(bundle_path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    fieldnames = fieldnames or [
        "timestamp",
        "service_name",
        "service_path",
        "dependency_type",
        "metric_name",
        "value",
        "unit",
    ]
    lines = [",".join(fieldnames)]
    for row in rows:
        lines.append(",".join(str(row.get(field, "")) for field in fieldnames))
    (bundle_path / "metrics.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_valid_service_map(bundle_path: Path) -> None:
    write_json(
        bundle_path / "service-map.json",
        {
            "services": [
                {
                    "service_name": "quote-api",
                    "service_path": "market_data",
                    "dependency_type": "exchange",
                    "dependencies": [],
                }
            ]
        },
    )


def write_seeded_secret_logs(bundle_path: Path) -> None:
    message = (
        "-----BEGIN PRIVATE KEY-----\\nPRIVATEKEYLINE\\n-----END PRIVATE KEY----- "
        "Authorization: Bearer bearerTOKEN123 "
        "abcdefghij.klmnopqrst.uvwxyzABCD "
        "api_key=plainsecretvalue "
        "analyst@example.com "
        "010-1234-5678 "
        "account_no: 123-456-789012"
    )
    row = valid_log_row(message=message)
    write_logs(bundle_path, [row])


class RunOpenBellCliTest(unittest.TestCase):
    def test_exit_code_skeleton_is_explicit(self) -> None:
        module = load_run_openbell_module()
        self.assertEqual(
            {
                "ok": 0,
                "input_error": 2,
                "security_block": 3,
                "limit_exceeded": 4,
                "output_validation_error": 5,
            },
            module.EXIT_CODES,
        )

    def test_success_creates_output_summary_without_analysis_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "openbell-out"
            completed = run_cli("--bundle", str(FIXTURE_BUNDLE), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            summary_path = output_path / "openbell-cli-summary.json"
            self.assertTrue(summary_path.exists())

            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual("P4-10", payload["stage"])
            self.assertEqual("observability_and_comparison_metrics_calculated_ready", payload["run_status"])
            self.assertFalse(payload["bundle"]["raw_telemetry_records_parsed"])
            self.assertTrue(payload["bundle"]["sanitized_telemetry_records_parsed"])
            self.assertFalse(payload["bundle"]["raw_excerpts_emitted"])
            self.assertFalse(payload["outputs"]["analysis_json_created"])
            self.assertTrue(payload["outputs"]["sanitization_report_created"])
            self.assertTrue(payload["outputs"]["record_summary_created"])
            self.assertTrue(payload["outputs"]["bucket_summary_created"])
            self.assertTrue(payload["outputs"]["metric_summary_created"])
            self.assertEqual("domestic-market-open-min", payload["bundle"]["preflight"]["incident"]["incident_id"])
            self.assertEqual(4, len(payload["bundle"]["preflight"]["files"]))
            self.assertTrue((output_path / "sanitized-bundle" / "logs.jsonl").exists())
            self.assertTrue((output_path / "sanitization-report.md").exists())
            self.assertTrue((output_path / "record-summary.json").exists())
            self.assertTrue((output_path / "bucket-summary.json").exists())
            self.assertTrue((output_path / "metric-summary.json").exists())
            self.assertEqual("logs.jsonl", payload["telemetry"]["primary_telemetry"])
            self.assertEqual(9, payload["telemetry"]["record_counts"]["total"]["physical_record_count"])
            self.assertEqual(9, payload["telemetry"]["record_counts"]["total"]["accepted_record_count"])
            self.assertEqual(0, payload["telemetry"]["record_counts"]["total"]["rejected_record_count"])
            self.assertEqual(3, payload["buckets"]["bucket_count"])
            self.assertEqual(["service_path", "bucket_start_utc"], payload["buckets"]["sort_order"])
            self.assertEqual(
                [
                    "M-001",
                    "M-002",
                    "M-003",
                    "M-004",
                    "M-005",
                    "M-006",
                    "M-007",
                    "M-008",
                    "M-009",
                    "M-010",
                    "M-011",
                    "M-012",
                    "M-013",
                ],
                payload["metrics"]["calculated_m_ids"],
            )
            self.assertEqual(3, payload["metrics"]["bucket_count"])
            self.assertGreaterEqual(payload["metrics"]["comparison_metric_count"], 1)

            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn(str(FIXTURE_BUNDLE), serialized)

    def test_missing_bundle_returns_exit_2_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_bundle = Path(temp_dir) / "missing-bundle"
            output_path = Path(temp_dir) / "openbell-out"
            completed = run_cli("--bundle", str(missing_bundle), "--output", str(output_path))

            self.assertEqual(2, completed.returncode)
            self.assertFalse(output_path.exists())
            self.assertIn("CLI001_BUNDLE_NOT_FOUND", completed.stderr)

    def test_file_output_path_returns_exit_5(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "not-a-directory"
            output_file.write_text("already a file", encoding="utf-8")
            completed = run_cli("--bundle", str(FIXTURE_BUNDLE), "--output", str(output_file))

            self.assertEqual(5, completed.returncode)
            self.assertIn("CLI010_OUTPUT_NOT_DIRECTORY", completed.stderr)
            self.assertEqual("already a file", output_file.read_text(encoding="utf-8"))

    def test_output_inside_bundle_returns_exit_5(self) -> None:
        completed = run_cli(
            "--bundle",
            str(FIXTURE_BUNDLE),
            "--output",
            str(FIXTURE_BUNDLE / "openbell-out"),
        )

        self.assertEqual(5, completed.returncode)
        self.assertIn("CLI011_OUTPUT_OVERLAPS_BUNDLE", completed.stderr)
        self.assertFalse((FIXTURE_BUNDLE / "openbell-out").exists())


class BundlePreflightValidationTest(unittest.TestCase):
    def test_missing_incident_returns_inp001_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            write_minimal_logs(bundle_path)
            output_path = Path(temp_dir) / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP001_MISSING_INCIDENT", completed.stderr)
            self.assertFalse(output_path.exists())

    def test_no_telemetry_returns_inp002(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP002_NO_TELEMETRY", completed.stderr)

    def test_unsupported_entry_returns_inp003(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_minimal_logs(bundle_path)
            (bundle_path / "unexpected.txt").write_text("unsupported", encoding="utf-8")

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP003_UNSUPPORTED_ENTRY", completed.stderr)

    def test_file_byte_limit_returns_lim001_before_schema_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            (bundle_path / "incident.json").write_bytes(b"{" + (b"x" * ((5 * 1024 * 1024) + 1)))
            write_minimal_logs(bundle_path)

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(4, completed.returncode)
            self.assertIn("LIM001_FILE_BYTES", completed.stderr)
            self.assertIn("incident.json", completed.stderr)

    def test_invalid_utf8_returns_inp004(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            (bundle_path / "logs.jsonl").write_bytes(b"\xff")

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP004_ENCODING", completed.stderr)
            self.assertIn("logs.jsonl", completed.stderr)

    def test_invalid_timezone_returns_inp006(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            incident = dict(VALID_INCIDENT)
            incident["timezone"] = "Mars/Base"
            write_valid_incident(bundle_path, incident)
            write_minimal_logs(bundle_path)

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP006_TIMEZONE", completed.stderr)

    def test_invalid_window_returns_inp007(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            incident = dict(VALID_INCIDENT)
            incident["baseline_window"] = {
                "start": "2026-06-30T08:58:30+09:00",
                "end": "2026-06-30T08:59:00+09:00",
            }
            write_valid_incident(bundle_path, incident)
            write_minimal_logs(bundle_path)

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP007_WINDOW", completed.stderr)

    def test_invalid_service_map_returns_inp009(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_minimal_logs(bundle_path)
            write_json(
                bundle_path / "service-map.json",
                {
                    "services": [
                        {
                            "service_name": "quote-api",
                            "service_path": "market_data",
                            "dependency_type": "exchange",
                            "dependencies": ["missing-service"],
                        }
                    ]
                },
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(Path(temp_dir) / "out"))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP009_SERVICE_MAP", completed.stderr)


class SanitizationTest(unittest.TestCase):
    def test_seeded_sensitive_values_are_redacted_in_working_copy_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_seeded_secret_logs(bundle_path)
            original_logs = (bundle_path / "logs.jsonl").read_text(encoding="utf-8")

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(original_logs, (bundle_path / "logs.jsonl").read_text(encoding="utf-8"))

            summary = json.loads((output_path / "openbell-cli-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("P4-10", summary["stage"])
            self.assertTrue(summary["outputs"]["sanitization_report_created"])
            self.assertFalse(summary["outputs"]["analysis_json_created"])
            self.assertEqual(7, summary["sanitization"]["total_redactions"])

            sanitized_logs_path = output_path / "sanitized-bundle" / "logs.jsonl"
            sanitized_logs = sanitized_logs_path.read_text(encoding="utf-8")
            report = (output_path / "sanitization-report.md").read_text(encoding="utf-8")
            combined_outputs = sanitized_logs + "\n" + report + "\n" + json.dumps(summary, ensure_ascii=False)

            for raw_value in SEEDED_SECRET_VALUES:
                self.assertNotIn(raw_value, combined_outputs)

            for marker in [
                "[REDACTED:PRIVATE_KEY]",
                "Authorization: [REDACTED:BEARER_TOKEN]",
                "[REDACTED:JWT]",
                "[REDACTED:SECRET]",
                "[REDACTED:EMAIL]",
                "[REDACTED:PHONE]",
                "[REDACTED:ACCOUNT]",
            ]:
                self.assertIn(marker, sanitized_logs)

            for secret_type in [
                "PRIVATE_KEY",
                "BEARER_TOKEN",
                "JWT",
                "SECRET",
                "EMAIL",
                "PHONE",
                "ACCOUNT",
            ]:
                self.assertIn(secret_type, report)

            self.assertIn("logs.jsonl:L1", report)
            self.assertNotIn(str(bundle_path), report)

    def test_redacted_secret_placeholder_is_not_counted_as_sensitive_residue(self) -> None:
        module = load_run_openbell_module()
        matches = module.find_sensitive_matches("api_key=[REDACTED:SECRET]", include_redacted=False)
        self.assertEqual([], matches)


class RowParserTest(unittest.TestCase):
    def test_logs_parser_reports_m014_counts_and_row_level_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            invalid_required = valid_log_row()
            invalid_required.pop("status")
            write_logs(
                bundle_path,
                [
                    valid_log_row(extra_debug="ignored"),
                    valid_log_row(
                        event_time="2026-06-30T09:03:00+09:00",
                        observed_time="2026-06-30T09:03:01+09:00",
                    ),
                    valid_log_row(latency_ms=-1),
                    invalid_required,
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            record_summary = json.loads((output_path / "record-summary.json").read_text(encoding="utf-8"))
            counts = record_summary["record_counts"]["by_source"]["logs.jsonl"]
            self.assertEqual(4, counts["physical_record_count"])
            self.assertEqual(3, counts["accepted_record_count"])
            self.assertEqual(1, counts["rejected_record_count"])
            self.assertEqual(1, counts["outside_analysis_window_count"])
            self.assertEqual(1, counts["field_dropped_count"])
            self.assertEqual("degraded", record_summary["status"])
            self.assertEqual("logs.jsonl", record_summary["primary_telemetry"])
            self.assertEqual(2, record_summary["accepted_in_window"]["logs.jsonl"])
            self.assertEqual(1, record_summary["issue_counts"]["REC002_REQUIRED_FIELD"])
            self.assertEqual(1, record_summary["issue_counts"]["FLD001_OPTIONAL_DROPPED"])
            self.assertEqual(1, record_summary["issue_counts"]["TIM001_OUTSIDE_WINDOW"])
            self.assertEqual(1, record_summary["issue_counts"]["WRN001_UNKNOWN_FIELD"])
            self.assertEqual(
                4,
                counts["accepted_record_count"] + counts["rejected_record_count"],
            )

    def test_metrics_parser_uses_service_map_for_missing_service_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_valid_service_map(bundle_path)
            write_metrics(
                bundle_path,
                [
                    {
                        "timestamp": "2026-06-30T09:00:00+09:00",
                        "service_name": "quote-api",
                        "metric_name": "request_count",
                        "value": "3",
                        "unit": "count",
                    }
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            record_summary = json.loads((output_path / "record-summary.json").read_text(encoding="utf-8"))
            counts = record_summary["record_counts"]["by_source"]["metrics.csv"]
            self.assertEqual(1, counts["physical_record_count"])
            self.assertEqual(1, counts["accepted_record_count"])
            self.assertEqual(0, counts["rejected_record_count"])
            self.assertEqual("metrics.csv", record_summary["primary_telemetry"])

    def test_parser_returns_inp008_when_no_valid_in_window_record_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_logs(
                bundle_path,
                [
                    valid_log_row(
                        event_time="2026-06-30T09:03:00+09:00",
                        observed_time="2026-06-30T09:03:01+09:00",
                    )
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP008_NO_VALID_RECORD", completed.stderr)
            self.assertFalse((output_path / "openbell-cli-summary.json").exists())
            self.assertFalse((output_path / "record-summary.json").exists())

    def test_metrics_header_schema_error_is_fatal_inp005(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_metrics(
                bundle_path,
                [
                    {
                        "timestamp": "2026-06-30T09:00:00+09:00",
                        "service_name": "quote-api",
                        "metric_name": "request_count",
                        "value": "3",
                    }
                ],
                fieldnames=["timestamp", "service_name", "metric_name", "value"],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(2, completed.returncode)
            self.assertIn("INP005_SCHEMA", completed.stderr)


class BucketSummaryTest(unittest.TestCase):
    def test_bucket_summary_uses_utc_floor_local_display_and_sort_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_logs(
                bundle_path,
                [
                    valid_log_row(
                        event_time="2026-06-30T09:00:30+09:00",
                        observed_time="2026-06-30T09:00:31+09:00",
                        service_name="auth-api",
                        service_path="auth_access",
                        dependency_type="internal",
                        message="DO_NOT_LEAK_BUCKET_MESSAGE",
                    ),
                    valid_log_row(
                        event_time="2026-06-30T09:00:59.999000+09:00",
                        observed_time="2026-06-30T09:01:00+09:00",
                        service_name="quote-api",
                        service_path="market_data",
                        dependency_type="exchange",
                    ),
                    valid_log_row(
                        event_time="2026-06-30T09:01:00+09:00",
                        observed_time="2026-06-30T09:01:01+09:00",
                        service_name="quote-api",
                        service_path="market_data",
                        dependency_type="exchange",
                    ),
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            bucket_summary = json.loads((output_path / "bucket-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("P4-10", bucket_summary["stage"])
            self.assertEqual("UTC", bucket_summary["time_basis"])
            self.assertEqual("Asia/Seoul", bucket_summary["display_timezone"])
            self.assertEqual(["service_path", "bucket_start_utc"], bucket_summary["sort_order"])
            self.assertEqual(3, bucket_summary["bucket_count"])

            buckets = bucket_summary["buckets"]
            self.assertEqual(
                [
                    ("auth_access", "2026-06-30T00:00:00+00:00"),
                    ("market_data", "2026-06-30T00:00:00+00:00"),
                    ("market_data", "2026-06-30T00:01:00+00:00"),
                ],
                [(bucket["service_path"], bucket["bucket_start_utc"]) for bucket in buckets],
            )
            self.assertEqual("2026-06-30T09:00:00+09:00", buckets[0]["bucket_start_local"])
            self.assertEqual("incident", buckets[0]["window_type"])
            self.assertEqual({"logs.jsonl": 1, "metrics.csv": 0}, buckets[0]["source_counts"])
            self.assertEqual({"logs.jsonl": 1, "metrics.csv": 0}, buckets[1]["source_counts"])
            self.assertEqual({"logs.jsonl": 1, "metrics.csv": 0}, buckets[2]["source_counts"])

            serialized = json.dumps(bucket_summary, ensure_ascii=False)
            self.assertNotIn("DO_NOT_LEAK_BUCKET_MESSAGE", serialized)

    def test_metrics_rows_are_included_in_bucket_summary_after_service_map_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_valid_service_map(bundle_path)
            write_metrics(
                bundle_path,
                [
                    {
                        "timestamp": "2026-06-30T09:00:00+09:00",
                        "service_name": "quote-api",
                        "metric_name": "request_count",
                        "value": "3",
                        "unit": "count",
                    }
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            bucket_summary = json.loads((output_path / "bucket-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(1, bucket_summary["bucket_count"])
            bucket = bucket_summary["buckets"][0]
            self.assertEqual("market_data", bucket["service_path"])
            self.assertEqual("2026-06-30T00:00:00+00:00", bucket["bucket_start_utc"])
            self.assertEqual({"logs.jsonl": 0, "metrics.csv": 1}, bucket["source_counts"])


class BasicMetricSummaryTest(unittest.TestCase):
    def test_fixture_metric_summary_matches_m001_to_m007_golden_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "openbell-out"

            completed = run_cli("--bundle", str(FIXTURE_BUNDLE), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            metric_summary = json.loads((output_path / "metric-summary.json").read_text(encoding="utf-8"))
            expected_analysis = json.loads(EXPECTED_ANALYSIS.read_text(encoding="utf-8"))

            self.assertEqual("P4-10", metric_summary["stage"])
            self.assertEqual("logs.jsonl", metric_summary["primary_telemetry"])
            self.assertEqual(
                [
                    "M-001",
                    "M-002",
                    "M-003",
                    "M-004",
                    "M-005",
                    "M-006",
                    "M-007",
                    "M-008",
                    "M-009",
                    "M-010",
                    "M-011",
                    "M-012",
                    "M-013",
                ],
                metric_summary["calculated_m_ids"],
            )
            self.assertEqual(["service_path", "bucket_start_utc"], metric_summary["sort_order"])
            self.assertEqual(3, metric_summary["bucket_count"])
            self.assertFalse(metric_summary["raw_excerpts_emitted"])

            actual_by_key = {
                (bucket["service_path"], bucket["bucket_start_utc"]): bucket
                for bucket in metric_summary["bucket_metrics"]
            }
            expected_by_key = {
                (bucket["service_path"], bucket["bucket_start_utc"]): bucket
                for bucket in expected_analysis["bucket_metrics"]
            }
            self.assertEqual(set(expected_by_key), set(actual_by_key))

            for key, expected_bucket in expected_by_key.items():
                actual_bucket = actual_by_key[key]
                self.assertEqual(expected_bucket["window_type"], actual_bucket["window_type"])
                self.assertEqual(expected_bucket["bucket_start_local"], actual_bucket["bucket_start_local"])
                self.assertEqual("logs.jsonl", actual_bucket["source_for_m001_m007"])
                for metric_name, expected_metric in expected_bucket["metrics"].items():
                    self.assertEqual(expected_metric, actual_bucket["metrics"][metric_name])

            baseline_bucket = actual_by_key[("market_data", "2026-06-29T23:58:00+00:00")]
            incident_bucket = actual_by_key[("market_data", "2026-06-30T00:00:00+00:00")]
            self.assertEqual("logs.jsonl", baseline_bucket["source_for_m008_m009"])
            self.assertEqual(
                {
                    "m_id": "M-008",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 2,
                    "source": "logs.jsonl",
                    "individual_values_emitted": False,
                },
                baseline_bucket["metrics"]["ingestion_lag_ms"],
            )
            self.assertEqual(
                {"m_id": "M-009", "value": 1000, "unit": "ms", "sample_count": 2},
                baseline_bucket["metrics"]["ingestion_lag_p50_ms"],
            )
            self.assertEqual(
                {
                    "m_id": "M-009",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 2,
                    "reason_code": "insufficient_sample",
                },
                baseline_bucket["metrics"]["ingestion_lag_p95_ms"],
            )
            self.assertEqual(
                {"m_id": "M-009", "value": 1000, "unit": "ms", "sample_count": 3},
                incident_bucket["metrics"]["ingestion_lag_p50_ms"],
            )

            comparisons = {
                (comparison["service_path"], comparison["metric_name"]): comparison
                for comparison in metric_summary["comparison_metrics"]
            }
            self.assertEqual(len(comparisons), metric_summary["comparison_metric_count"])
            self.assertEqual(
                {
                    "m_id": "M-010",
                    "value": 80,
                    "unit": "ms",
                    "sample_count": 1,
                },
                comparisons[("market_data", "latency_p50_ms")]["metrics"]["baseline_median"],
            )
            self.assertEqual(
                {
                    "m_id": "M-011",
                    "value": 160,
                    "unit": "ms",
                    "sample_count": 2,
                },
                comparisons[("market_data", "latency_p50_ms")]["metrics"]["incident_peak"],
            )
            self.assertEqual(
                {"m_id": "M-012", "value": 80, "unit": "ms"},
                comparisons[("market_data", "latency_p50_ms")]["metrics"]["change_abs"],
            )
            self.assertEqual(
                {"m_id": "M-013", "value": 100.0, "unit": "percent"},
                comparisons[("market_data", "latency_p50_ms")]["metrics"]["change_pct"],
            )
            self.assertEqual(
                {
                    "m_id": "M-013",
                    "value": None,
                    "unit": "percent",
                    "reason_code": "zero_denominator",
                },
                comparisons[("market_data", "error_count")]["metrics"]["change_pct"],
            )
            self.assertEqual(
                {"m_id": "M-012", "value": 0, "unit": "ms"},
                comparisons[("market_data", "ingestion_lag_p50_ms")]["metrics"]["change_abs"],
            )

    def test_metrics_only_source_calculates_counts_error_rate_and_nearest_rank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            rows = [
                {
                    "timestamp": "2026-06-30T09:00:00+09:00",
                    "service_name": "quote-api",
                    "service_path": "market_data",
                    "dependency_type": "exchange",
                    "metric_name": "request_count",
                    "value": "5",
                    "unit": "count",
                },
                {
                    "timestamp": "2026-06-30T09:00:00+09:00",
                    "service_name": "quote-api",
                    "service_path": "market_data",
                    "dependency_type": "exchange",
                    "metric_name": "error_count",
                    "value": "1",
                    "unit": "count",
                },
            ]
            for value in range(1, 21):
                rows.append(
                    {
                        "timestamp": f"2026-06-30T09:00:{value:02}+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "exchange",
                        "metric_name": "latency_sample_ms",
                        "value": str(value),
                        "unit": "ms",
                    }
                )
            write_metrics(bundle_path, rows)

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            metric_summary = json.loads((output_path / "metric-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("metrics.csv", metric_summary["primary_telemetry"])
            self.assertEqual(1, metric_summary["bucket_count"])
            bucket = metric_summary["bucket_metrics"][0]
            self.assertEqual("metrics.csv", bucket["source_for_m001_m007"])
            self.assertEqual("2026-06-30T00:00:00+00:00", bucket["bucket_start_utc"])
            self.assertEqual({"m_id": "M-001", "value": 5, "unit": "count"}, bucket["metrics"]["request_count"])
            self.assertEqual({"m_id": "M-002", "value": 1, "unit": "count"}, bucket["metrics"]["error_count"])
            self.assertEqual(
                {"m_id": "M-003", "value": 0.083, "unit": "requests/second"},
                bucket["metrics"]["throughput_rps"],
            )
            self.assertEqual(
                {"m_id": "M-004", "value": 20.0, "unit": "percent"},
                bucket["metrics"]["error_rate_pct"],
            )
            self.assertEqual(
                {"m_id": "M-005", "value": 10, "unit": "ms", "sample_count": 20},
                bucket["metrics"]["latency_p50_ms"],
            )
            self.assertEqual(
                {"m_id": "M-006", "value": 19, "unit": "ms", "sample_count": 20},
                bucket["metrics"]["latency_p95_ms"],
            )
            self.assertEqual(
                {
                    "m_id": "M-007",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 20,
                    "reason_code": "insufficient_sample",
                },
                bucket["metrics"]["latency_p99_ms"],
            )

    def test_metric_summary_marks_zero_denominator_and_does_not_emit_raw_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_logs(
                bundle_path,
                [
                    valid_log_row(
                        event_time="2026-06-30T09:00:05+09:00",
                        observed_time="2026-06-30T09:00:06+09:00",
                        message="DO_NOT_LEAK_METRIC_MESSAGE",
                    )
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            serialized = (output_path / "metric-summary.json").read_text(encoding="utf-8")
            self.assertNotIn("DO_NOT_LEAK_METRIC_MESSAGE", serialized)

        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_metrics(
                bundle_path,
                [
                    {
                        "timestamp": "2026-06-30T09:00:05+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "exchange",
                        "metric_name": "latency_sample_ms",
                        "value": "123",
                        "unit": "ms",
                    }
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            metric_summary = json.loads((output_path / "metric-summary.json").read_text(encoding="utf-8"))
            bucket = metric_summary["bucket_metrics"][0]
            self.assertEqual(
                {
                    "m_id": "M-004",
                    "value": None,
                    "unit": "percent",
                    "reason_code": "zero_denominator",
                },
                bucket["metrics"]["error_rate_pct"],
            )
            self.assertEqual(
                {"m_id": "M-005", "value": 123, "unit": "ms", "sample_count": 1},
                bucket["metrics"]["latency_p50_ms"],
            )

    def test_metrics_only_ingestion_lag_samples_and_baseline_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            write_metrics(
                bundle_path,
                [
                    {
                        "timestamp": "2026-06-30T08:58:01+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "observability",
                        "metric_name": "ingestion_lag_sample_ms",
                        "value": "100",
                        "unit": "ms",
                    },
                    {
                        "timestamp": "2026-06-30T08:58:02+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "observability",
                        "metric_name": "ingestion_lag_sample_ms",
                        "value": "300",
                        "unit": "ms",
                    },
                    {
                        "timestamp": "2026-06-30T09:00:01+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "observability",
                        "metric_name": "ingestion_lag_sample_ms",
                        "value": "500",
                        "unit": "ms",
                    },
                    {
                        "timestamp": "2026-06-30T09:01:01+09:00",
                        "service_name": "quote-api",
                        "service_path": "market_data",
                        "dependency_type": "observability",
                        "metric_name": "ingestion_lag_sample_ms",
                        "value": "700",
                        "unit": "ms",
                    },
                ],
            )

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            metric_summary = json.loads((output_path / "metric-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("metrics.csv", metric_summary["primary_telemetry"])

            buckets = {
                (bucket["service_path"], bucket["bucket_start_utc"]): bucket
                for bucket in metric_summary["bucket_metrics"]
            }
            baseline_bucket = buckets[("market_data", "2026-06-29T23:58:00+00:00")]
            self.assertEqual("metrics.csv", baseline_bucket["source_for_m008_m009"])
            self.assertEqual(
                {
                    "m_id": "M-008",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 2,
                    "source": "metrics.csv",
                    "individual_values_emitted": False,
                },
                baseline_bucket["metrics"]["ingestion_lag_ms"],
            )
            self.assertEqual(
                {"m_id": "M-009", "value": 100, "unit": "ms", "sample_count": 2},
                baseline_bucket["metrics"]["ingestion_lag_p50_ms"],
            )

            comparisons = {
                (comparison["service_path"], comparison["metric_name"]): comparison
                for comparison in metric_summary["comparison_metrics"]
            }
            lag_comparison = comparisons[("market_data", "ingestion_lag_p50_ms")]
            self.assertEqual(
                {
                    "m_id": "M-010",
                    "value": 100,
                    "unit": "ms",
                    "sample_count": 1,
                },
                lag_comparison["metrics"]["baseline_median"],
            )
            self.assertEqual(
                {
                    "m_id": "M-011",
                    "value": 700,
                    "unit": "ms",
                    "sample_count": 2,
                },
                lag_comparison["metrics"]["incident_peak"],
            )
            self.assertEqual({"m_id": "M-012", "value": 600, "unit": "ms"}, lag_comparison["metrics"]["change_abs"])
            self.assertEqual(
                {"m_id": "M-013", "value": 600.0, "unit": "percent"},
                lag_comparison["metrics"]["change_pct"],
            )

    def test_log_ingestion_lag_marks_missing_observed_time_without_leaking_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle_path = Path(temp_dir) / "bundle"
            output_path = Path(temp_dir) / "out"
            bundle_path.mkdir()
            write_valid_incident(bundle_path)
            row = valid_log_row(message="DO_NOT_LEAK_MISSING_OBSERVED_TIME")
            row.pop("observed_time")
            write_logs(bundle_path, [row])

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            metric_summary_text = (output_path / "metric-summary.json").read_text(encoding="utf-8")
            self.assertNotIn("DO_NOT_LEAK_MISSING_OBSERVED_TIME", metric_summary_text)
            metric_summary = json.loads(metric_summary_text)
            bucket = metric_summary["bucket_metrics"][0]
            self.assertEqual(
                {
                    "m_id": "M-008",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 0,
                    "source": "logs.jsonl",
                    "individual_values_emitted": False,
                    "missing_input_count": 1,
                    "reason_code": "missing_input",
                },
                bucket["metrics"]["ingestion_lag_ms"],
            )
            self.assertEqual(
                {
                    "m_id": "M-009",
                    "value": None,
                    "unit": "ms",
                    "sample_count": 0,
                    "reason_code": "insufficient_sample",
                },
                bucket["metrics"]["ingestion_lag_p50_ms"],
            )


if __name__ == "__main__":
    unittest.main()
