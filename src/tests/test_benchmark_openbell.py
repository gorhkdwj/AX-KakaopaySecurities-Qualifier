"""P4-18 benchmark CLI tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_SCRIPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "scripts"
    / "benchmark_openbell.py"
)


def run_benchmark(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT_PATH), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class BenchmarkOpenBellTest(unittest.TestCase):
    def test_small_benchmark_writes_summary_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "benchmark"

            completed = run_benchmark(
                "--output",
                str(output_path),
                "--log-records",
                "120",
                "--metric-records",
                "60",
                "--runs",
                "2",
                "--warmup-runs",
                "0",
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            summary_path = output_path / "benchmark-summary.json"
            report_path = output_path / "benchmark-report.md"
            self.assertTrue(summary_path.exists())
            self.assertTrue(report_path.exists())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual("P4-18", summary["stage"])
            self.assertEqual("passed", summary["status"])
            self.assertEqual(["M-016", "M-017"], summary["metric_ids"])
            self.assertEqual(120, summary["fixture"]["log_records"])
            self.assertEqual(60, summary["fixture"]["metric_records"])
            self.assertEqual(2, summary["measured"]["runs"])
            self.assertEqual(2, len(summary["measured"]["results"]))
            self.assertEqual("runs/run-001", summary["measured"]["results"][0]["output_dir"])
            self.assertTrue(summary["summary"]["exit_codes_passed"])
            self.assertTrue(summary["summary"]["time_passed"])
            self.assertTrue(summary["summary"]["memory_passed"])
            self.assertGreaterEqual(summary["summary"]["deterministic_pipeline_wall_time_seconds"], 0)
            self.assertGreater(summary["summary"]["peak_python_memory_mib"], 0)
            self.assertTrue((output_path / "benchmark-bundle" / "logs.jsonl").exists())
            self.assertTrue((output_path / "runs" / "run-001" / "analysis.json").exists())
            self.assertIn("M-016", report_path.read_text(encoding="utf-8"))

    def test_threshold_failure_returns_exit_5(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "benchmark"

            completed = run_benchmark(
                "--output",
                str(output_path),
                "--log-records",
                "20",
                "--metric-records",
                "10",
                "--runs",
                "1",
                "--warmup-runs",
                "0",
                "--memory-threshold-mib",
                "0",
            )

            self.assertEqual(5, completed.returncode)
            summary = json.loads((output_path / "benchmark-summary.json").read_text(encoding="utf-8"))
            self.assertEqual("failed", summary["status"])
            self.assertFalse(summary["summary"]["memory_passed"])

    def test_rejects_record_count_above_supported_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "benchmark"

            completed = run_benchmark(
                "--output",
                str(output_path),
                "--log-records",
                "100001",
                "--metric-records",
                "1",
            )

            self.assertEqual(4, completed.returncode)
            self.assertIn("BENCH002_LOG_RECORD_LIMIT", completed.stderr)
            self.assertFalse((output_path / "benchmark-summary.json").exists())


if __name__ == "__main__":
    unittest.main()
