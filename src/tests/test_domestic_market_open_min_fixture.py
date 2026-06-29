"""Golden-seed checks for the domestic-market-open-min fixture.

P4-03 fixes the smallest input/output example before analyzer code exists.
These tests validate the fixture and expected analysis shape without invoking
any future telemetry analyzer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "src" / "tests" / "fixtures" / "domestic-market-open-min"
BUNDLE_ROOT = FIXTURE_ROOT / "bundle"
EXPECTED_ANALYSIS = FIXTURE_ROOT / "expected" / "analysis.json"
CONTRACT_REFERENCE = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "references"
    / "metrics-validation-contract.md"
)

ALLOWED_BUNDLE_FILES = {"incident.json", "logs.jsonl", "metrics.csv", "service-map.json"}
STANDARD_SERVICE_PATHS = {
    "auth_access",
    "market_data",
    "watchlist_info",
    "order_execution",
    "recurring_investment",
    "external_dependency",
}
STANDARD_DEPENDENCY_TYPES = {
    "internal",
    "exchange",
    "depository",
    "overseas_broker",
    "observability",
    "unknown",
}
LOG_STATUSES = {"ok", "error", "timeout", "rejected"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DomesticMarketOpenMinFixtureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.incident = load_json(BUNDLE_ROOT / "incident.json")
        self.logs = load_jsonl(BUNDLE_ROOT / "logs.jsonl")
        self.service_map = load_json(BUNDLE_ROOT / "service-map.json")
        self.expected = load_json(EXPECTED_ANALYSIS)

    def test_bundle_contains_only_contract_allowed_files(self) -> None:
        actual_files = {path.name for path in BUNDLE_ROOT.iterdir() if path.is_file()}
        self.assertEqual(ALLOWED_BUNDLE_FILES, actual_files)

    def test_incident_versions_and_windows_are_minimal_valid_contract_shape(self) -> None:
        self.assertEqual("1.0", self.incident["schema_version"])
        self.assertEqual("1.0.0", self.incident["contract_version"])
        self.assertEqual("domestic-market-open-min", self.incident["incident_id"])
        self.assertEqual("Asia/Seoul", self.incident["timezone"])

        baseline_start = parse_iso(self.incident["baseline_window"]["start"])
        baseline_end = parse_iso(self.incident["baseline_window"]["end"])
        incident_start = parse_iso(self.incident["incident_window"]["start"])
        incident_end = parse_iso(self.incident["incident_window"]["end"])

        for value in (baseline_start, baseline_end, incident_start, incident_end):
            self.assertEqual(0, value.second)
            self.assertEqual(0, value.microsecond)
            self.assertIsNotNone(value.tzinfo)

        self.assertEqual(60, int((baseline_end - baseline_start).total_seconds()))
        self.assertEqual(120, int((incident_end - incident_start).total_seconds()))
        self.assertLessEqual(baseline_end, incident_start)

    def test_logs_and_service_map_use_standard_codes(self) -> None:
        self.assertEqual(8, len(self.logs))
        for row in self.logs:
            self.assertEqual("quote-api", row["service_name"])
            self.assertIn(row["service_path"], STANDARD_SERVICE_PATHS)
            self.assertIn(row["dependency_type"], STANDARD_DEPENDENCY_TYPES)
            self.assertIn(row["status"], LOG_STATUSES)
            self.assertGreaterEqual(row["latency_ms"], 0)
            self.assertGreaterEqual(parse_iso(row["observed_time"]), parse_iso(row["event_time"]))

        services = self.service_map["services"]
        self.assertEqual(1, len(services))
        self.assertEqual("quote-api", services[0]["service_name"])
        self.assertEqual("market_data", services[0]["service_path"])
        self.assertEqual("exchange", services[0]["dependency_type"])

    def test_metrics_csv_has_single_context_row(self) -> None:
        with (BUNDLE_ROOT / "metrics.csv").open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(1, len(rows))
        self.assertEqual("cpu_utilization_pct", rows[0]["metric_name"])
        self.assertEqual("percent", rows[0]["unit"])
        self.assertEqual("market_data", rows[0]["service_path"])

    def test_golden_contract_version_and_sha_match_reference(self) -> None:
        self.assertEqual("1.0", self.expected["schema_version"])
        self.assertEqual("1.0.0", self.expected["contract_version"])
        self.assertEqual(sha256_bytes(CONTRACT_REFERENCE), self.expected["contract_sha256"])

    def test_golden_record_counts_satisfy_m_014_equations(self) -> None:
        self.assertEqual("M-014", self.expected["record_counts"]["m_id"])
        for counts in [
            self.expected["record_counts"]["total"],
            *self.expected["record_counts"]["by_source"].values(),
        ]:
            self.assertEqual(
                counts["physical_record_count"],
                counts["accepted_record_count"] + counts["rejected_record_count"],
            )
            self.assertEqual(0, counts["rejected_record_count"])
            self.assertEqual(0, counts["outside_analysis_window_count"])
            self.assertEqual(0, counts["field_dropped_count"])

        self.assertEqual(9, self.expected["record_counts"]["total"]["physical_record_count"])
        self.assertEqual(8, self.expected["record_counts"]["by_source"]["logs.jsonl"]["physical_record_count"])
        self.assertEqual(1, self.expected["record_counts"]["by_source"]["metrics.csv"]["physical_record_count"])

    def test_golden_minimal_m_001_to_m_007_values_are_fixed(self) -> None:
        buckets = {item["bucket_start_local"]: item for item in self.expected["bucket_metrics"]}
        self.assertEqual(
            {"2026-06-30T08:58:00+09:00", "2026-06-30T09:00:00+09:00", "2026-06-30T09:01:00+09:00"},
            set(buckets),
        )

        incident_first = buckets["2026-06-30T09:00:00+09:00"]
        self.assertEqual("breach", incident_first["bucket_state"])
        self.assertEqual(3, incident_first["metrics"]["request_count"]["value"])
        self.assertEqual(2, incident_first["metrics"]["error_count"]["value"])
        self.assertEqual(0.05, incident_first["metrics"]["throughput_rps"]["value"])
        self.assertEqual(66.667, incident_first["metrics"]["error_rate_pct"]["value"])
        self.assertEqual(160, incident_first["metrics"]["latency_p50_ms"]["value"])
        self.assertIsNone(incident_first["metrics"]["latency_p95_ms"]["value"])
        self.assertEqual("insufficient_sample", incident_first["metrics"]["latency_p95_ms"]["reason_code"])
        self.assertIsNone(incident_first["metrics"]["latency_p99_ms"]["value"])
        self.assertEqual("insufficient_sample", incident_first["metrics"]["latency_p99_ms"]["reason_code"])

        incident_second = buckets["2026-06-30T09:01:00+09:00"]
        self.assertEqual("healthy", incident_second["bucket_state"])
        self.assertEqual(33.333, incident_second["metrics"]["error_rate_pct"]["value"])
        self.assertEqual(140, incident_second["metrics"]["latency_p50_ms"]["value"])

    def test_golden_evidence_and_claim_references_are_valid(self) -> None:
        evidence_ids = {item["evidence_id"] for item in self.expected["evidence"]}
        self.assertEqual(len(evidence_ids), len(self.expected["evidence"]))

        for evidence in self.expected["evidence"]:
            self.assertFalse(Path(evidence["source_file"]).is_absolute())
            self.assertIn(evidence["source_type"], {"incident", "log", "metric", "service_map"})

        claim_ids = {item["claim_id"] for item in self.expected["claims"]}
        self.assertEqual(len(claim_ids), len(self.expected["claims"]))

        for claim in self.expected["claims"]:
            self.assertIn(claim["claim_type"], {"confirmed_fact", "hypothesis", "unknown"})
            if claim["claim_type"] == "confirmed_fact":
                self.assertTrue(claim["evidence_refs"])
                self.assertTrue(set(claim["evidence_refs"]).issubset(evidence_ids))

    def test_golden_does_not_claim_root_cause(self) -> None:
        serialized = json.dumps(self.expected, ensure_ascii=False)
        self.assertNotIn("root_cause", serialized)
        unknown_claims = [claim for claim in self.expected["claims"] if claim["claim_type"] == "unknown"]
        self.assertTrue(unknown_claims)


if __name__ == "__main__":
    unittest.main()
