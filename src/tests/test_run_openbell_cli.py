"""CLI and bundle-preflight tests for OpenBell Guard.

P4-05 keeps the shared command-line entry point and adds the first bundle
preflight gate. The script still must not analyze telemetry records or create
the final analysis outputs.
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
            self.assertEqual("P4-05", payload["stage"])
            self.assertEqual("bundle_preflight_ready", payload["run_status"])
            self.assertFalse(payload["bundle"]["raw_telemetry_records_parsed"])
            self.assertFalse(payload["bundle"]["raw_excerpts_emitted"])
            self.assertFalse(payload["outputs"]["analysis_json_created"])
            self.assertFalse(payload["outputs"]["sanitization_report_created"])
            self.assertEqual("domestic-market-open-min", payload["bundle"]["preflight"]["incident"]["incident_id"])
            self.assertEqual(4, len(payload["bundle"]["preflight"]["files"]))

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


if __name__ == "__main__":
    unittest.main()
