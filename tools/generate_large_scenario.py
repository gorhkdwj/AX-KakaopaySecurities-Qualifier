"""Generate a realistic large synthetic OpenBell Guard manual-test scenario.

This generator intentionally creates controlled synthetic telemetry rather than
real operating data. It is designed for manual case-002 validation:

- enough rows to exercise the local pipeline at a realistic scale;
- fixed seed for reproducibility;
- healthy paths with small amounts of noise;
- degraded paths with mixed successes and failures;
- boundary buckets near configured thresholds;
- sparse fake secret-shaped values for redaction validation.

The generated OpenBell Guard input bundle contains only the allowed bundle
files. Ground truth is written next to the bundle, not inside it, so the plugin
cannot read expected answers during analysis.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CASE_ID = "case-002-large-scenario"
DEFAULT_SEED = 20260630
DEFAULT_LOG_RECORDS = 60_000
DEFAULT_METRIC_RECORDS = 20_000
KST = timezone(timedelta(hours=9))
BASELINE_START = datetime(2026, 6, 30, 8, 50, 0, tzinfo=KST)
INCIDENT_START = datetime(2026, 6, 30, 9, 0, 0, tzinfo=KST)
INCIDENT_END = datetime(2026, 6, 30, 9, 10, 0, tzinfo=KST)
BUCKET_COUNT = 20
SERVICE_PATHS = ("market_data", "watchlist_info", "order_execution")


@dataclass(frozen=True)
class ServiceProfile:
    service_path: str
    service_names: tuple[str, ...]
    dependency_type: str
    error_threshold_pct: float
    p95_latency_threshold_ms: float | None
    ingestion_lag_threshold_ms: float | None
    baseline_error_pct: float
    baseline_high_latency_pct: float
    baseline_lag_spike_pct: float
    healthy_latency_range: tuple[int, int]
    slow_latency_range: tuple[int, int]
    healthy_lag_range_ms: tuple[int, int]
    slow_lag_range_ms: tuple[int, int]


PROFILES: dict[str, ServiceProfile] = {
    "market_data": ServiceProfile(
        service_path="market_data",
        service_names=("quote-api", "quote-cache", "quote-provider-adapter"),
        dependency_type="exchange",
        error_threshold_pct=8.0,
        p95_latency_threshold_ms=900.0,
        ingestion_lag_threshold_ms=1500.0,
        baseline_error_pct=1.2,
        baseline_high_latency_pct=1.0,
        baseline_lag_spike_pct=0.5,
        healthy_latency_range=(80, 260),
        slow_latency_range=(1050, 1700),
        healthy_lag_range_ms=(50, 280),
        slow_lag_range_ms=(1800, 3200),
    ),
    "watchlist_info": ServiceProfile(
        service_path="watchlist_info",
        service_names=("watchlist-api", "portfolio-snapshot", "instrument-info-api"),
        dependency_type="internal",
        error_threshold_pct=8.0,
        p95_latency_threshold_ms=1000.0,
        ingestion_lag_threshold_ms=1600.0,
        baseline_error_pct=1.0,
        baseline_high_latency_pct=1.0,
        baseline_lag_spike_pct=0.7,
        healthy_latency_range=(95, 320),
        slow_latency_range=(1100, 1900),
        healthy_lag_range_ms=(80, 360),
        slow_lag_range_ms=(1900, 3400),
    ),
    "order_execution": ServiceProfile(
        service_path="order_execution",
        service_names=("order-api", "order-router", "execution-gateway"),
        dependency_type="internal",
        error_threshold_pct=3.0,
        p95_latency_threshold_ms=1200.0,
        ingestion_lag_threshold_ms=None,
        baseline_error_pct=0.4,
        baseline_high_latency_pct=0.5,
        baseline_lag_spike_pct=0.3,
        healthy_latency_range=(110, 420),
        slow_latency_range=(650, 980),
        healthy_lag_range_ms=(60, 300),
        slow_lag_range_ms=(900, 1300),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate case-002 large realistic synthetic OpenBell Guard data.",
    )
    parser.add_argument(
        "--output",
        default=f"out/manual-tests/{CASE_ID}",
        help="Case output root. The bundle is written to <output>/bundle.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic random seed.",
    )
    parser.add_argument(
        "--log-records",
        type=int,
        default=DEFAULT_LOG_RECORDS,
        help="Synthetic logs.jsonl row count. Default is 60,000.",
    )
    parser.add_argument(
        "--metric-records",
        type=int,
        default=DEFAULT_METRIC_RECORDS,
        help="Synthetic metrics.csv row count. Default is 20,000.",
    )
    return parser


def bucket_start(index: int) -> datetime:
    return BASELINE_START + timedelta(minutes=index)


def service_bucket_error_pct(service_path: str, bucket: datetime) -> float:
    minute = int((bucket - INCIDENT_START).total_seconds() // 60)
    if bucket < INCIDENT_START:
        return PROFILES[service_path].baseline_error_pct
    if service_path == "market_data":
        return {
            0: 8.0,
            1: 12.0,
            2: 15.0,
            3: 12.0,
            4: 10.0,
            5: 5.0,
            6: 3.0,
            7: 2.0,
            8: 1.4,
            9: 1.2,
        }.get(minute, 1.2)
    if service_path == "watchlist_info":
        return {
            0: 5.0,
            1: 11.0,
            2: 12.0,
            3: 9.0,
            4: 6.0,
            5: 4.0,
            6: 2.0,
            7: 1.5,
            8: 1.2,
            9: 1.0,
        }.get(minute, 1.0)
    return {
        0: 0.8,
        1: 1.2,
        2: 2.5,
        3: 1.5,
        4: 1.2,
        5: 0.9,
        6: 0.8,
        7: 0.6,
        8: 0.5,
        9: 0.4,
    }.get(minute, 0.4)


def service_bucket_high_latency_pct(service_path: str, bucket: datetime) -> float:
    minute = int((bucket - INCIDENT_START).total_seconds() // 60)
    if bucket < INCIDENT_START:
        return PROFILES[service_path].baseline_high_latency_pct
    if service_path == "market_data":
        return {0: 4.0, 1: 12.0, 2: 14.0, 3: 12.0, 4: 10.0, 5: 4.0}.get(minute, 1.5)
    if service_path == "watchlist_info":
        return {0: 3.0, 1: 11.0, 2: 13.0, 3: 10.0, 4: 4.0}.get(minute, 1.5)
    return {2: 3.0, 3: 2.0}.get(minute, 0.8)


def service_bucket_lag_spike_pct(service_path: str, bucket: datetime) -> float:
    minute = int((bucket - INCIDENT_START).total_seconds() // 60)
    if bucket < INCIDENT_START:
        return PROFILES[service_path].baseline_lag_spike_pct
    if service_path == "market_data":
        return {0: 3.0, 1: 12.0, 2: 14.0, 3: 11.0, 4: 9.0, 5: 3.0}.get(minute, 1.0)
    if service_path == "watchlist_info":
        return {1: 8.0, 2: 10.0, 3: 7.0}.get(minute, 1.2)
    return {2: 1.5}.get(minute, 0.5)


def allocate_counts(total: int, groups: int) -> list[int]:
    base = total // groups
    remainder = total % groups
    return [base + (1 if index < remainder else 0) for index in range(groups)]


def pick_indices(rng: random.Random, population: int, count: int) -> set[int]:
    if count <= 0:
        return set()
    return set(rng.sample(range(population), min(count, population)))


def secret_message(service_path: str) -> str:
    return (
        f"{service_path} synthetic redaction probe Authorization: Bearer "
        "case002BearerToken api_key=case002SyntheticKey analyst@example.com "
        "010-2222-3333 account_no: 999-888-777666"
    )


def normal_message(service_path: str, status: str, high_latency: bool, lag_spike: bool, row_index: int) -> str:
    variants = {
        "market_data": (
            "quote fanout completed with exchange timestamp alignment",
            "quote snapshot served after cache freshness check",
            "quote provider adapter returned synthetic throttle symptom",
            "market open quote burst handled with partial retry",
        ),
        "watchlist_info": (
            "watchlist refresh completed with latest quote snapshot",
            "portfolio watchlist view used cached symbol metadata",
            "watchlist quote dependency stale beyond synthetic guard window",
            "instrument metadata read completed after dependency retry",
        ),
        "order_execution": (
            "order validation completed without downstream placement",
            "order route dry-run passed synthetic risk checks",
            "order request retry exhausted before local dry-run completion",
            "execution gateway heartbeat remained available",
        ),
    }[service_path]
    base = variants[row_index % len(variants)]
    flags: list[str] = []
    if status in {"error", "timeout", "rejected"}:
        flags.append(f"status={status}")
    if high_latency:
        flags.append("slow_path=true")
    if lag_spike:
        flags.append("observer_lag=spike")
    if row_index % 97 == 0:
        flags.append("open_bell_load=burst")
    suffix = " ".join(flags)
    return f"{base}; {suffix}".strip()


def make_log_rows(total_log_records: int, seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    group_count = BUCKET_COUNT * len(SERVICE_PATHS)
    counts = allocate_counts(total_log_records, group_count)
    rows: list[dict[str, Any]] = []
    bucket_summary: list[dict[str, Any]] = []
    secret_inserted = 0

    group_index = 0
    for bucket_index in range(BUCKET_COUNT):
        current_bucket = bucket_start(bucket_index)
        window_type = "baseline" if current_bucket < INCIDENT_START else "incident"
        for service_path in SERVICE_PATHS:
            profile = PROFILES[service_path]
            count = counts[group_index]
            group_index += 1
            error_pct = service_bucket_error_pct(service_path, current_bucket)
            high_latency_pct = service_bucket_high_latency_pct(service_path, current_bucket)
            lag_spike_pct = service_bucket_lag_spike_pct(service_path, current_bucket)
            missing_observed_pct = 0.25 if service_path != "order_execution" else 0.1

            error_count = round(count * error_pct / 100)
            high_latency_count = round(count * high_latency_pct / 100)
            lag_spike_count = round(count * lag_spike_pct / 100)
            missing_observed_count = round(count * missing_observed_pct / 100)

            error_indices = pick_indices(rng, count, error_count)
            high_latency_indices = pick_indices(rng, count, high_latency_count)
            lag_spike_indices = pick_indices(rng, count, lag_spike_count)
            missing_observed_indices = pick_indices(rng, count, missing_observed_count)
            secret_indices: set[int] = set()
            if window_type == "incident" and service_path in {"market_data", "watchlist_info"} and bucket_index in {11, 12}:
                secret_indices = pick_indices(rng, count, 1)

            for row_index in range(count):
                offset_ms = int((60_000 * row_index) / max(count, 1)) + rng.randint(0, 37)
                event_time = current_bucket + timedelta(milliseconds=offset_ms)
                service_name = profile.service_names[(row_index + bucket_index) % len(profile.service_names)]
                is_error = row_index in error_indices
                is_high_latency = row_index in high_latency_indices
                is_lag_spike = row_index in lag_spike_indices
                status = "ok"
                if is_error:
                    status = ("timeout", "error", "rejected")[(row_index + bucket_index) % 3]
                latency_range = profile.slow_latency_range if is_high_latency else profile.healthy_latency_range
                latency_ms = rng.randint(*latency_range)
                lag_range = profile.slow_lag_range_ms if is_lag_spike else profile.healthy_lag_range_ms
                observed_lag_ms = rng.randint(*lag_range)
                message = (
                    secret_message(service_path)
                    if row_index in secret_indices
                    else normal_message(service_path, status, is_high_latency, is_lag_spike, row_index)
                )
                if row_index in secret_indices:
                    secret_inserted += 1

                row: dict[str, Any] = {
                    "event_time": event_time.isoformat(timespec="milliseconds"),
                    "service_name": service_name,
                    "service_path": service_path,
                    "dependency_type": profile.dependency_type,
                    "status": status,
                    "latency_ms": latency_ms,
                    "trace_id": f"case002-{service_path[:2]}-{bucket_index:02d}-{row_index:05d}",
                    "log_type": "request",
                    "severity": "error" if status in {"error", "timeout", "rejected"} else ("warning" if is_high_latency else "info"),
                    "message": message,
                }
                if row_index not in missing_observed_indices:
                    row["observed_time"] = (event_time + timedelta(milliseconds=observed_lag_ms)).isoformat(
                        timespec="milliseconds"
                    )
                rows.append(row)

            bucket_summary.append(
                {
                    "bucket_start_local": current_bucket.isoformat(timespec="seconds"),
                    "window_type": window_type,
                    "service_path": service_path,
                    "request_count": count,
                    "error_count": error_count,
                    "error_rate_pct": round(error_count / count * 100, 3) if count else None,
                    "high_latency_target_pct": high_latency_pct,
                    "lag_spike_target_pct": lag_spike_pct,
                    "expected_bucket_state_by_design": expected_bucket_state(service_path, current_bucket),
                }
            )
    return rows, {"bucket_design": bucket_summary, "secret_probe_rows": secret_inserted}


def expected_bucket_state(service_path: str, bucket: datetime) -> str:
    profile = PROFILES[service_path]
    error_pct = service_bucket_error_pct(service_path, bucket)
    high_latency_pct = service_bucket_high_latency_pct(service_path, bucket)
    lag_spike_pct = service_bucket_lag_spike_pct(service_path, bucket)
    if error_pct > profile.error_threshold_pct:
        return "breach"
    if profile.p95_latency_threshold_ms is not None and high_latency_pct >= 6.0:
        return "breach"
    if profile.ingestion_lag_threshold_ms is not None and lag_spike_pct >= 6.0:
        return "breach"
    return "healthy"


def make_metric_rows(total_metric_records: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 101)
    group_count = BUCKET_COUNT * len(SERVICE_PATHS)
    counts = allocate_counts(total_metric_records, group_count)
    rows: list[dict[str, Any]] = []
    group_index = 0
    metric_names = ("cpu_utilization_pct", "memory_utilization_pct")
    for bucket_index in range(BUCKET_COUNT):
        current_bucket = bucket_start(bucket_index)
        for service_path in SERVICE_PATHS:
            profile = PROFILES[service_path]
            count = counts[group_index]
            group_index += 1
            incident_minute = int((current_bucket - INCIDENT_START).total_seconds() // 60)
            stress = expected_bucket_state(service_path, current_bucket) == "breach"
            for row_index in range(count):
                timestamp = current_bucket + timedelta(milliseconds=int((60_000 * row_index) / max(count, 1)))
                metric_name = metric_names[row_index % len(metric_names)]
                base = 42 if metric_name == "cpu_utilization_pct" else 48
                if service_path == "market_data":
                    base += 8
                elif service_path == "watchlist_info":
                    base += 5
                if stress:
                    base += 18 if metric_name == "cpu_utilization_pct" else 11
                if service_path == "order_execution" and incident_minute == 2:
                    base += 7
                value = max(1.0, min(98.0, base + rng.uniform(-4.5, 4.5)))
                rows.append(
                    {
                        "timestamp": timestamp.isoformat(timespec="milliseconds"),
                        "service_name": profile.service_names[row_index % len(profile.service_names)],
                        "service_path": service_path,
                        "dependency_type": profile.dependency_type,
                        "metric_name": metric_name,
                        "value": round(value, 3),
                        "unit": "percent",
                    }
                )
    return rows


def incident_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "contract_version": "1.0.0",
        "incident_id": CASE_ID,
        "timezone": "Asia/Seoul",
        "baseline_window": {
            "start": BASELINE_START.isoformat(timespec="seconds"),
            "end": INCIDENT_START.isoformat(timespec="seconds"),
        },
        "incident_window": {
            "start": INCIDENT_START.isoformat(timespec="seconds"),
            "end": INCIDENT_END.isoformat(timespec="seconds"),
        },
        "thresholds": {
            service_path: {
                key: value
                for key, value in {
                    "error_rate_pct_max": profile.error_threshold_pct,
                    "p95_latency_ms_max": profile.p95_latency_threshold_ms,
                    "ingestion_lag_p95_ms_max": profile.ingestion_lag_threshold_ms,
                }.items()
                if value is not None
            }
            for service_path, profile in PROFILES.items()
        },
    }


def service_map_payload() -> dict[str, Any]:
    services = []
    for profile in PROFILES.values():
        for service_name in profile.service_names:
            dependencies = []
            if profile.service_path == "watchlist_info":
                dependencies = ["quote-api", "quote-cache"]
            services.append(
                {
                    "service_name": service_name,
                    "service_path": profile.service_path,
                    "dependency_type": profile.dependency_type,
                    "dependencies": dependencies,
                }
            )
    return {"services": services}


def expected_service_paths() -> dict[str, dict[str, Any]]:
    return {
        "market_data": {
            "status": "outage_detected",
            "outage_start": "2026-06-30T00:01:00+00:00",
            "recovery_time": "2026-06-30T00:05:00+00:00",
            "reason": "09:01-09:04 KST are designed breach buckets; 09:05-09:06 KST are the first two healthy recovery buckets.",
        },
        "watchlist_info": {
            "status": "outage_detected",
            "outage_start": "2026-06-30T00:01:00+00:00",
            "recovery_time": "2026-06-30T00:04:00+00:00",
            "reason": "09:01-09:03 KST are designed breach buckets; 09:04-09:05 KST are the first two healthy recovery buckets.",
        },
        "order_execution": {
            "status": "healthy",
            "outage_start": None,
            "recovery_time": None,
            "reason": "Order path includes noise below thresholds and should not be classified as degraded.",
        },
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_logs(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_metrics(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ("timestamp", "service_name", "service_path", "dependency_type", "metric_name", "value", "unit")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_generation_summary(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# case-002 large scenario generation summary",
        "",
        f"- case_id: `{payload['case_id']}`",
        f"- seed: `{payload['seed']}`",
        f"- log_records: `{payload['log_records']}`",
        f"- metric_records: `{payload['metric_records']}`",
        f"- secret_probe_rows: `{payload['secret_probe_rows']}`",
        "",
        "## Expected service path outcomes",
        "",
        "| service_path | expected status | outage_start UTC | recovery_time UTC |",
        "| --- | --- | --- | --- |",
    ]
    for service_path, expected in payload["expected_service_paths"].items():
        lines.append(
            "| "
            f"`{service_path}` | "
            f"`{expected['status']}` | "
            f"`{expected['outage_start']}` | "
            f"`{expected['recovery_time']}` |"
        )
    lines.extend(
        [
            "",
            "## Synthetic design notes",
            "",
            "- This is controlled synthetic telemetry, not real Kakao Pay Securities data.",
            "- Normal paths include small noise, and degraded paths include successful requests.",
            "- Ground truth is stored outside the OpenBell Guard input bundle.",
            "- Fake secret-shaped values are inserted only to verify redaction behavior.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_args(args: argparse.Namespace) -> None:
    if args.log_records <= 0 or args.metric_records <= 0:
        raise SystemExit("--log-records and --metric-records must be positive.")
    if args.log_records > 100_000:
        raise SystemExit("--log-records must not exceed OpenBell Guard's 100,000 row limit.")
    if args.metric_records > 50_000:
        raise SystemExit("--metric-records must not exceed OpenBell Guard's 50,000 row limit.")


def generate_case(output_root: Path, *, seed: int, log_records: int, metric_records: int) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    bundle_dir = output_root / "bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir()

    logs, log_design = make_log_rows(log_records, seed)
    metrics = make_metric_rows(metric_records, seed)

    write_json(bundle_dir / "incident.json", incident_payload())
    write_json(bundle_dir / "service-map.json", service_map_payload())
    write_logs(bundle_dir / "logs.jsonl", logs)
    write_metrics(bundle_dir / "metrics.csv", metrics)

    ground_truth = {
        "case_id": CASE_ID,
        "schema_version": "0.1",
        "seed": seed,
        "log_records": len(logs),
        "metric_records": len(metrics),
        "baseline_window": incident_payload()["baseline_window"],
        "incident_window": incident_payload()["incident_window"],
        "expected_service_paths": expected_service_paths(),
        "secret_probe_rows": log_design["secret_probe_rows"],
        "bucket_design": log_design["bucket_design"],
        "limitations": [
            "Synthetic data validates deterministic pipeline behavior, not real operating performance.",
            "Ground truth is design-time expectation and must be compared against generated analysis outputs.",
            "Fake secret-shaped values are deliberately synthetic and must not be replaced with real secrets.",
        ],
    }
    write_json(output_root / "ground-truth.json", ground_truth)
    write_generation_summary(output_root / "generation-summary.md", ground_truth)
    return ground_truth


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(args)
    output_root = Path(args.output)
    summary = generate_case(
        output_root,
        seed=args.seed,
        log_records=args.log_records,
        metric_records=args.metric_records,
    )
    print(json.dumps({k: summary[k] for k in ("case_id", "seed", "log_records", "metric_records", "secret_probe_rows")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
