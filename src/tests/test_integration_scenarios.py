"""End-to-end scenario matrix tests for OpenBell Guard.

P4-17 expands the single domestic-market fixture into lightweight integration
scenarios A through H. These tests create temporary synthetic bundles, run the
public CLI entry point, and validate generated outputs through
``validate_bundle.py``. The fixtures intentionally remain synthetic and must not
be described as Kakao Pay Securities internal data.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "scripts"
    / "run_openbell.py"
)
VALIDATOR_SCRIPT_PATH = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "scripts"
    / "validate_bundle.py"
)

SCENARIO_IDS = tuple("ABCDEFGH")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT_PATH), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def scenario_incident(
    *,
    incident_id: str,
    thresholds: dict[str, dict[str, float]] | None,
    incident_end: str = "2026-06-30T09:04:00+09:00",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "contract_version": "1.0.0",
        "incident_id": incident_id,
        "timezone": "Asia/Seoul",
        "baseline_window": {
            "start": "2026-06-30T08:58:00+09:00",
            "end": "2026-06-30T09:00:00+09:00",
        },
        "incident_window": {
            "start": "2026-06-30T09:00:00+09:00",
            "end": incident_end,
        },
    }
    if thresholds is not None:
        payload["thresholds"] = thresholds
    return payload


def add_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(value)
    return (parsed + timedelta(seconds=seconds)).isoformat()


def log_row(
    event_time: str,
    *,
    service_name: str,
    service_path: str,
    status: str = "ok",
    latency_ms: int = 100,
    dependency_type: str = "internal",
    observed_lag_seconds: int = 1,
    message: str = "synthetic integration event",
) -> dict[str, Any]:
    return {
        "event_time": event_time,
        "observed_time": add_seconds(event_time, observed_lag_seconds),
        "service_name": service_name,
        "service_path": service_path,
        "dependency_type": dependency_type,
        "status": status,
        "latency_ms": latency_ms,
        "trace_id": f"trace-{service_name}-{event_time[-14:-9]}-{status}",
        "log_type": "request",
        "severity": "error" if status in {"error", "timeout", "rejected"} else "info",
        "message": message,
    }


def repeat_logs(
    event_time: str,
    *,
    service_name: str,
    service_path: str,
    statuses: list[str],
    dependency_type: str = "internal",
    latency_ms: int = 100,
    observed_lag_seconds: int = 1,
    message: str = "synthetic integration event",
) -> list[dict[str, Any]]:
    return [
        log_row(
            event_time,
            service_name=service_name,
            service_path=service_path,
            status=status,
            latency_ms=latency_ms,
            dependency_type=dependency_type,
            observed_lag_seconds=observed_lag_seconds,
            message=message,
        )
        for status in statuses
    ]


def write_logs(bundle_path: Path, rows: list[dict[str, Any]], *, append_invalid_line: bool = False) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    if append_invalid_line:
        lines.append("{this is not valid json")
    (bundle_path / "logs.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_metrics(bundle_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "timestamp",
        "service_name",
        "service_path",
        "dependency_type",
        "metric_name",
        "value",
        "unit",
    ]
    with (bundle_path / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def context_metric_row(
    timestamp: str,
    *,
    service_name: str,
    service_path: str,
    metric_name: str,
    value: float,
    unit: str = "percent",
    dependency_type: str = "internal",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "service_name": service_name,
        "service_path": service_path,
        "dependency_type": dependency_type,
        "metric_name": metric_name,
        "value": value,
        "unit": unit,
    }


def write_service_map(bundle_path: Path, services: list[dict[str, Any]]) -> None:
    write_json(bundle_path / "service-map.json", {"services": services})


def make_bundle(
    root: Path,
    *,
    incident: dict[str, Any],
    logs: list[dict[str, Any]],
    metrics: list[dict[str, Any]] | None = None,
    service_map: list[dict[str, Any]] | None = None,
    append_invalid_log_line: bool = False,
) -> Path:
    bundle_path = root / "bundle"
    bundle_path.mkdir()
    write_json(bundle_path / "incident.json", incident)
    write_logs(bundle_path, logs, append_invalid_line=append_invalid_log_line)
    if metrics is not None:
        write_metrics(bundle_path, metrics)
    if service_map is not None:
        write_service_map(bundle_path, service_map)
    return bundle_path


def read_output(output_path: Path, file_name: str) -> dict[str, Any]:
    return json.loads((output_path / file_name).read_text(encoding="utf-8"))


def service_statuses(analysis: dict[str, Any]) -> dict[str, str]:
    return {str(item["service_path"]): str(item["status"]) for item in analysis["service_paths"]}


def assert_validator_passes(test_case: unittest.TestCase, output_path: Path) -> None:
    validated = run_validator("--output", str(output_path))
    test_case.assertEqual(0, validated.returncode, validated.stderr)
    payload = json.loads(validated.stdout)
    test_case.assertEqual("passed", payload["status"])
    test_case.assertEqual("passed", payload["checks"]["report_claim_refs"])
    test_case.assertEqual("passed", payload["checks"]["secret_residue"])


class ScenarioMatrixTest(unittest.TestCase):
    def test_declares_all_p4_17_scenario_ids(self) -> None:
        self.assertEqual(tuple("ABCDEFGH"), SCENARIO_IDS)

    def test_a_domestic_market_open_partial_degradation_keeps_order_path_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-a-domestic-partial",
                thresholds={
                    "market_data": {"error_rate_pct_max": 50.0},
                    "watchlist_info": {"error_rate_pct_max": 50.0},
                    "order_execution": {"error_rate_pct_max": 50.0},
                },
            )
            logs = []
            for service_name, service_path in [
                ("quote-api", "market_data"),
                ("watchlist-api", "watchlist_info"),
                ("order-api", "order_execution"),
            ]:
                logs.extend(
                    repeat_logs(
                        "2026-06-30T08:58:05+09:00",
                        service_name=service_name,
                        service_path=service_path,
                        statuses=["ok", "ok"],
                    )
                )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "timeout", "error"],
                    dependency_type="exchange",
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="watchlist-api",
                    service_path="watchlist_info",
                    statuses=["ok", "timeout", "error"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="order-api",
                    service_path="order_execution",
                    statuses=["ok", "ok", "ok"],
                )
            )
            for service_name, service_path in [
                ("quote-api", "market_data"),
                ("watchlist-api", "watchlist_info"),
                ("order-api", "order_execution"),
            ]:
                logs.extend(
                    repeat_logs(
                        "2026-06-30T09:01:05+09:00",
                        service_name=service_name,
                        service_path=service_path,
                        statuses=["ok", "ok"],
                    )
                )
            metrics = [
                context_metric_row(
                    "2026-06-30T09:00:30+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    metric_name="cpu_utilization_pct",
                    value=61.0,
                    dependency_type="exchange",
                )
            ]
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=metrics)
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            statuses = service_statuses(analysis)
            self.assertEqual("degradation_observed", statuses["market_data"])
            self.assertEqual("degradation_observed", statuses["watchlist_info"])
            self.assertEqual("healthy", statuses["order_execution"])
            report = (output_path / "openbell-report.md").read_text(encoding="utf-8")
            self.assertIn("`order_execution`: 상태 `healthy`", report)
            self.assertNotIn("전체 주문장애", report)
            assert_validator_passes(self, output_path)

    def test_b_overseas_broker_dependency_is_kept_separate_from_internal_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-b-overseas-broker",
                thresholds={
                    "recurring_investment": {"error_rate_pct_max": 50.0},
                    "auth_access": {"error_rate_pct_max": 50.0},
                },
            )
            logs = []
            logs.extend(
                repeat_logs(
                    "2026-06-30T08:58:05+09:00",
                    service_name="broker-adapter",
                    service_path="recurring_investment",
                    dependency_type="overseas_broker",
                    statuses=["ok", "ok"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T08:58:05+09:00",
                    service_name="auth-api",
                    service_path="auth_access",
                    statuses=["ok", "ok"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="broker-adapter",
                    service_path="recurring_investment",
                    dependency_type="overseas_broker",
                    statuses=["ok", "timeout", "timeout"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="auth-api",
                    service_path="auth_access",
                    statuses=["ok", "ok", "ok"],
                )
            )
            service_map = [
                {
                    "service_name": "broker-adapter",
                    "service_path": "recurring_investment",
                    "dependency_type": "overseas_broker",
                    "dependencies": [],
                },
                {
                    "service_name": "auth-api",
                    "service_path": "auth_access",
                    "dependency_type": "internal",
                    "dependencies": [],
                },
            ]
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=[], service_map=service_map)
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            statuses = service_statuses(analysis)
            self.assertEqual("degradation_observed", statuses["recurring_investment"])
            self.assertEqual("healthy", statuses["auth_access"])
            evidence_text = json.dumps(analysis["evidence"], ensure_ascii=False)
            self.assertIn("overseas_broker", evidence_text)
            self.assertNotIn("internal capacity root cause", json.dumps(analysis, ensure_ascii=False))
            assert_validator_passes(self, output_path)

    def test_c_incomplete_data_preserves_unknown_state_without_report_claim_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-c-incomplete-data",
                thresholds={},
            )
            logs = repeat_logs(
                "2026-06-30T09:00:05+09:00",
                service_name="quote-api",
                service_path="market_data",
                statuses=["ok", "timeout", "error"],
                dependency_type="exchange",
            )
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=None, service_map=None)
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            self.assertEqual("degraded", analysis["run"]["status"])
            self.assertEqual("unknown", service_statuses(analysis)["market_data"])
            limitations = json.dumps(analysis["run"]["limitations"], ensure_ascii=False)
            self.assertIn("single_telemetry_source", limitations)
            self.assertIn("state_unknown", limitations)
            report = (output_path / "openbell-report.md").read_text(encoding="utf-8")
            self.assertIn("해당 항목은 없습니다.", report)
            assert_validator_passes(self, output_path)

    def test_d_seeded_secrets_are_removed_from_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-d-seeded-secrets",
                thresholds={"market_data": {"error_rate_pct_max": 50.0}},
            )
            secret_message = (
                "Authorization: Bearer seededTOKEN123 "
                "api_key=plainsecretvalue analyst@example.com "
                "010-1234-5678 account_no: 123-456-789012"
            )
            logs = repeat_logs(
                "2026-06-30T09:00:05+09:00",
                service_name="quote-api",
                service_path="market_data",
                statuses=["ok", "timeout", "error"],
                dependency_type="exchange",
                message=secret_message,
            )
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=[])
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            combined_outputs = "\n".join(
                file_path.read_text(encoding="utf-8")
                for file_path in output_path.rglob("*")
                if file_path.is_file()
            )
            for raw_secret in [
                "seededTOKEN123",
                "plainsecretvalue",
                "analyst@example.com",
                "010-1234-5678",
                "123-456-789012",
            ]:
                self.assertNotIn(raw_secret, combined_outputs)
            assert_validator_passes(self, output_path)

    def test_e_observability_lag_does_not_create_service_degradation_when_service_metrics_are_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-e-observability-lag",
                thresholds={"market_data": {"error_rate_pct_max": 50.0}},
            )
            logs = []
            logs.extend(
                repeat_logs(
                    "2026-06-30T08:58:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "ok"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "ok", "ok"],
                    observed_lag_seconds=180,
                )
            )
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=[])
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            self.assertEqual("healthy", service_statuses(analysis)["market_data"])
            incident_bucket = next(
                bucket
                for bucket in analysis["bucket_metrics"]
                if bucket["window_type"] == "incident"
            )
            self.assertEqual(180000, incident_bucket["metrics"]["ingestion_lag_p50_ms"]["value"])
            report = (output_path / "openbell-report.md").read_text(encoding="utf-8")
            self.assertNotIn("market_data degradation is a plausible", report)
            assert_validator_passes(self, output_path)

    def test_f_timeout_symptom_is_not_promoted_to_db_or_jvm_root_cause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-f-timeout-symptom",
                thresholds={"market_data": {"error_rate_pct_max": 50.0}},
            )
            logs = repeat_logs(
                "2026-06-30T09:00:05+09:00",
                service_name="quote-api",
                service_path="market_data",
                statuses=["ok", "timeout", "timeout"],
                dependency_type="internal",
                message="DB connection timeout during synthetic request",
            )
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=[])
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis_and_report = (
                (output_path / "analysis.json").read_text(encoding="utf-8")
                + "\n"
                + (output_path / "openbell-report.md").read_text(encoding="utf-8")
            )
            self.assertIn("does not establish a root cause", analysis_and_report)
            self.assertNotIn("DB connection timeout", analysis_and_report)
            self.assertNotIn("JVM warm", analysis_and_report)
            self.assertNotIn("database capacity root cause", analysis_and_report)
            assert_validator_passes(self, output_path)

    def test_g_threshold_boundary_two_breach_buckets_and_two_healthy_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-g-threshold-boundary",
                thresholds={"market_data": {"error_rate_pct_max": 50.0}},
                incident_end="2026-06-30T09:05:00+09:00",
            )
            logs = []
            logs.extend(
                repeat_logs(
                    "2026-06-30T08:58:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "ok"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:00:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "error"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:01:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["error", "error"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:02:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["timeout", "error"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:03:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "ok"],
                )
            )
            logs.extend(
                repeat_logs(
                    "2026-06-30T09:04:05+09:00",
                    service_name="quote-api",
                    service_path="market_data",
                    statuses=["ok", "ok"],
                )
            )
            bundle_path = make_bundle(root, incident=incident, logs=logs, metrics=[])
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            service = next(item for item in analysis["service_paths"] if item["service_path"] == "market_data")
            self.assertEqual("outage_detected", service["status"])
            self.assertEqual("2026-06-30T00:01:00+00:00", service["outage_start"])
            self.assertEqual("2026-06-30T00:03:00+00:00", service["recovery_time"])
            boundary_bucket = next(
                bucket
                for bucket in analysis["bucket_metrics"]
                if bucket["bucket_start_local"] == "2026-06-30T09:00:00+09:00"
            )
            self.assertEqual("healthy", boundary_bucket["bucket_state"])
            self.assertEqual(50.0, boundary_bucket["metrics"]["error_rate_pct"]["value"])
            assert_validator_passes(self, output_path)

    def test_h_damaged_rows_degrade_and_limit_excess_exits_4_before_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incident = scenario_incident(
                incident_id="scenario-h-damaged-rows",
                thresholds={"market_data": {"error_rate_pct_max": 50.0}},
            )
            logs = repeat_logs(
                "2026-06-30T09:00:05+09:00",
                service_name="quote-api",
                service_path="market_data",
                statuses=["ok", "error"],
                dependency_type="exchange",
            )
            bundle_path = make_bundle(
                root,
                incident=incident,
                logs=logs,
                metrics=[],
                append_invalid_log_line=True,
            )
            output_path = root / "out"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(0, completed.returncode, completed.stderr)
            analysis = read_output(output_path, "analysis.json")
            self.assertEqual("degraded", analysis["run"]["status"])
            self.assertIn("record_quality_degraded", json.dumps(analysis["run"]["limitations"]))
            assert_validator_passes(self, output_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle_path = root / "bundle"
            bundle_path.mkdir()
            (bundle_path / "incident.json").write_text("x" * (5 * 1024 * 1024 + 1), encoding="utf-8")
            (bundle_path / "logs.jsonl").write_text("{}\n", encoding="utf-8")
            output_path = root / "out-limit"

            completed = run_cli("--bundle", str(bundle_path), "--output", str(output_path))

            self.assertEqual(4, completed.returncode)
            self.assertIn("LIM001_FILE_BYTES", completed.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
