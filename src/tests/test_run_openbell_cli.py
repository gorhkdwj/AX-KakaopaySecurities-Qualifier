"""CLI skeleton tests for OpenBell Guard.

P4-04 tests only the shared command-line entry point and path safety. The
script must not analyze raw telemetry files yet.
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
            self.assertEqual("P4-04", payload["stage"])
            self.assertEqual("cli_ready", payload["run_status"])
            self.assertFalse(payload["bundle"]["raw_telemetry_files_read"])
            self.assertFalse(payload["outputs"]["analysis_json_created"])
            self.assertFalse(payload["outputs"]["sanitization_report_created"])

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


if __name__ == "__main__":
    unittest.main()
