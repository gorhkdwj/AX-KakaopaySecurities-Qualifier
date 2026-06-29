"""CLI, bundle-preflight, sanitizer, and row-parser tests for OpenBell Guard.

P4-07 keeps the shared command-line entry point and adds line-level parsing for
sanitized logs and metrics. The script still must not calculate metrics or
create the final analysis outputs.
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
            self.assertEqual("P4-07", payload["stage"])
            self.assertEqual("records_parsed_ready", payload["run_status"])
            self.assertFalse(payload["bundle"]["raw_telemetry_records_parsed"])
            self.assertTrue(payload["bundle"]["sanitized_telemetry_records_parsed"])
            self.assertFalse(payload["bundle"]["raw_excerpts_emitted"])
            self.assertFalse(payload["outputs"]["analysis_json_created"])
            self.assertTrue(payload["outputs"]["sanitization_report_created"])
            self.assertTrue(payload["outputs"]["record_summary_created"])
            self.assertEqual("domestic-market-open-min", payload["bundle"]["preflight"]["incident"]["incident_id"])
            self.assertEqual(4, len(payload["bundle"]["preflight"]["files"]))
            self.assertTrue((output_path / "sanitized-bundle" / "logs.jsonl").exists())
            self.assertTrue((output_path / "sanitization-report.md").exists())
            self.assertTrue((output_path / "record-summary.json").exists())
            self.assertEqual("logs.jsonl", payload["telemetry"]["primary_telemetry"])
            self.assertEqual(9, payload["telemetry"]["record_counts"]["total"]["physical_record_count"])
            self.assertEqual(9, payload["telemetry"]["record_counts"]["total"]["accepted_record_count"])
            self.assertEqual(0, payload["telemetry"]["record_counts"]["total"]["rejected_record_count"])

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
            self.assertEqual("P4-07", summary["stage"])
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


if __name__ == "__main__":
    unittest.main()
