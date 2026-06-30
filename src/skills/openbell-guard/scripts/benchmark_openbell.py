"""Benchmark OpenBell Guard's deterministic local pipeline.

P4-18 measures M-016 and M-017 for a synthetic support-limit bundle:

- M-016 ``deterministic_pipeline_wall_time_seconds``: median wall-clock time
  from immediately before ``run_openbell.run`` starts preflight until the
  deterministic run returns.
- M-017 ``peak_python_memory_mib``: peak Python allocations traced by
  ``tracemalloc`` over the same measured interval.

This script is intentionally local and deterministic. It does not call network
services, does not use real customer/account data, and does not claim operating
environment performance.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import shutil
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_openbell  # noqa: E402


BENCHMARK_STAGE = "P4-18"
BENCHMARK_SUMMARY_FILENAME = "benchmark-summary.json"
BENCHMARK_REPORT_FILENAME = "benchmark-report.md"
DEFAULT_TIME_THRESHOLD_SECONDS = 60.0
DEFAULT_MEMORY_THRESHOLD_MIB = 512.0
DEFAULT_MEASURED_RUNS = 5
DEFAULT_WARMUP_RUNS = 1
KST = timezone(timedelta(hours=9))
BENCHMARK_START = datetime(2026, 6, 30, 8, 55, 0, tzinfo=KST)
BENCHMARK_SECONDS = 600


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchmark_openbell.py",
        description=(
            "Generate a synthetic support-limit OpenBell Guard bundle and measure "
            "M-016 wall time plus M-017 traced Python memory."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Directory where benchmark fixture, run outputs, and benchmark summaries are written.",
    )
    parser.add_argument(
        "--log-records",
        type=int,
        default=run_openbell.LOG_RECORD_LIMIT,
        help="Number of synthetic logs.jsonl rows to generate. Defaults to the supported limit.",
    )
    parser.add_argument(
        "--metric-records",
        type=int,
        default=run_openbell.METRIC_RECORD_LIMIT,
        help="Number of synthetic metrics.csv rows to generate. Defaults to the supported limit.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_MEASURED_RUNS,
        help="Number of measured benchmark runs. P4-18 default is 5.",
    )
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=DEFAULT_WARMUP_RUNS,
        help="Number of unmeasured warm-up runs before measured runs.",
    )
    parser.add_argument(
        "--time-threshold-seconds",
        type=float,
        default=DEFAULT_TIME_THRESHOLD_SECONDS,
        help="Pass threshold for the measured wall-time median.",
    )
    parser.add_argument(
        "--memory-threshold-mib",
        type=float,
        default=DEFAULT_MEMORY_THRESHOLD_MIB,
        help="Pass threshold for the maximum measured traced Python memory.",
    )
    return parser


def validate_positive_int(value: int, *, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def validate_nonnegative_int(value: int, *, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0.")


def validate_nonnegative_float(value: float, *, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0.")


def ensure_benchmark_args(args: argparse.Namespace) -> dict[str, Any] | None:
    try:
        validate_positive_int(args.log_records, name="--log-records")
        validate_positive_int(args.metric_records, name="--metric-records")
        validate_positive_int(args.runs, name="--runs")
        validate_nonnegative_int(args.warmup_runs, name="--warmup-runs")
        validate_nonnegative_float(args.time_threshold_seconds, name="--time-threshold-seconds")
        validate_nonnegative_float(args.memory_threshold_mib, name="--memory-threshold-mib")
    except ValueError as exc:
        return {
            "schema_version": "0.1",
            "stage": BENCHMARK_STAGE,
            "status": "fatal",
            "exit_code": 2,
            "issues": [{"issue_code": "BENCH001_INVALID_ARGUMENT", "message": str(exc)}],
        }

    if args.log_records > run_openbell.LOG_RECORD_LIMIT:
        return {
            "schema_version": "0.1",
            "stage": BENCHMARK_STAGE,
            "status": "fatal",
            "exit_code": 4,
            "issues": [
                {
                    "issue_code": "BENCH002_LOG_RECORD_LIMIT",
                    "message": "--log-records exceeds the supported logs.jsonl record limit.",
                    "limit": run_openbell.LOG_RECORD_LIMIT,
                }
            ],
        }
    if args.metric_records > run_openbell.METRIC_RECORD_LIMIT:
        return {
            "schema_version": "0.1",
            "stage": BENCHMARK_STAGE,
            "status": "fatal",
            "exit_code": 4,
            "issues": [
                {
                    "issue_code": "BENCH003_METRIC_RECORD_LIMIT",
                    "message": "--metric-records exceeds the supported metrics.csv record limit.",
                    "limit": run_openbell.METRIC_RECORD_LIMIT,
                }
            ],
        }
    return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def benchmark_timestamp(index: int) -> datetime:
    return BENCHMARK_START + timedelta(seconds=index % BENCHMARK_SECONDS)


def write_incident(bundle_dir: Path) -> None:
    incident = {
        "schema_version": "1.0",
        "contract_version": "1.0.0",
        "incident_id": "p4-18-support-limit-benchmark",
        "timezone": "Asia/Seoul",
        "baseline_window": {
            "start": "2026-06-30T08:55:00+09:00",
            "end": "2026-06-30T09:00:00+09:00",
        },
        "incident_window": {
            "start": "2026-06-30T09:00:00+09:00",
            "end": "2026-06-30T09:05:00+09:00",
        },
        "thresholds": {
            "market_data": {
                "error_rate_pct_max": 10.0,
                "p95_latency_ms_max": 1000.0,
                "p99_latency_ms_max": 1200.0,
                "ingestion_lag_p95_ms_max": 1000.0,
            }
        },
    }
    write_json(bundle_dir / "incident.json", incident)


def write_service_map(bundle_dir: Path) -> None:
    service_map = {
        "services": [
            {
                "service_name": "quote-api",
                "service_path": "market_data",
                "dependency_type": "exchange",
                "dependencies": [],
            }
        ]
    }
    write_json(bundle_dir / "service-map.json", service_map)


def write_logs(bundle_dir: Path, log_records: int) -> None:
    logs_path = bundle_dir / "logs.jsonl"
    with logs_path.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(log_records):
            event_time = benchmark_timestamp(index)
            observed_time = event_time + timedelta(milliseconds=100 + (index % 17))
            row = {
                "event_time": event_time.isoformat(timespec="milliseconds"),
                "observed_time": observed_time.isoformat(timespec="milliseconds"),
                "service_name": "quote-api",
                "service_path": "market_data",
                "dependency_type": "exchange",
                "status": "ok",
                "latency_ms": 120 + (index % 31),
                "trace_id": f"bench-{index:06d}",
                "log_type": "request",
                "severity": "info",
                "message": "synthetic benchmark request completed",
            }
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_metrics(bundle_dir: Path, metric_records: int) -> None:
    metrics_path = bundle_dir / "metrics.csv"
    header = "timestamp,service_name,service_path,dependency_type,metric_name,value,unit\n"
    with metrics_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(header)
        for index in range(metric_records):
            timestamp = benchmark_timestamp(index).isoformat(timespec="milliseconds")
            metric_name = "cpu_utilization_pct" if index % 2 == 0 else "memory_utilization_pct"
            value = 35 + (index % 20)
            handle.write(f"{timestamp},quote-api,market_data,internal,{metric_name},{value},percent\n")


def generate_benchmark_bundle(*, output_root: Path, log_records: int, metric_records: int) -> Path:
    bundle_dir = output_root / "benchmark-bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)
    write_incident(bundle_dir)
    write_service_map(bundle_dir)
    write_logs(bundle_dir, log_records)
    write_metrics(bundle_dir, metric_records)
    return bundle_dir


def prepare_child_dir(parent: Path, child_name: str) -> Path:
    child = parent / child_name
    parent_resolved = parent.resolve(strict=False)
    child_resolved = child.resolve(strict=False)
    if parent_resolved != child_resolved and parent_resolved not in child_resolved.parents:
        raise RuntimeError("Benchmark child directory resolved outside the benchmark output root.")
    if child.exists():
        shutil.rmtree(child)
    child.mkdir(parents=True)
    return child


def run_once(*, bundle_dir: Path, run_output: Path, run_index: int, measured: bool) -> dict[str, Any]:
    if run_output.exists():
        shutil.rmtree(run_output)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    tracemalloc.start()
    start_counter = time.perf_counter()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        exit_code = run_openbell.run(str(bundle_dir), str(run_output))
    elapsed_seconds = time.perf_counter() - start_counter
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    result: dict[str, Any] = {
        "run_index": run_index,
        "measured": measured,
        "exit_code": exit_code,
        "deterministic_pipeline_wall_time_seconds": round(elapsed_seconds, 6),
        "peak_python_memory_mib": round(peak_bytes / (1024 * 1024), 6),
        "output_dir": (Path("runs") / run_output.name).as_posix(),
    }
    if exit_code != run_openbell.EXIT_CODES["ok"]:
        result["stderr_tail"] = stderr_buffer.getvalue()[-1000:]
    return result


def environment_summary() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }


def build_summary(
    *,
    output_root: Path,
    bundle_dir: Path,
    args: argparse.Namespace,
    warmup_results: list[dict[str, Any]],
    measured_results: list[dict[str, Any]],
) -> dict[str, Any]:
    wall_times = [float(item["deterministic_pipeline_wall_time_seconds"]) for item in measured_results]
    peak_memory_values = [float(item["peak_python_memory_mib"]) for item in measured_results]
    exit_codes_passed = all(item["exit_code"] == run_openbell.EXIT_CODES["ok"] for item in measured_results)
    wall_time_median = statistics.median(wall_times)
    peak_memory_max = max(peak_memory_values)
    time_passed = wall_time_median <= args.time_threshold_seconds
    memory_passed = peak_memory_max <= args.memory_threshold_mib
    status = "passed" if exit_codes_passed and time_passed and memory_passed else "failed"
    return {
        "schema_version": "0.1",
        "stage": BENCHMARK_STAGE,
        "status": status,
        "exit_code": 0 if status == "passed" else run_openbell.EXIT_CODES["output_validation_error"],
        "metric_ids": ["M-016", "M-017"],
        "fixture": {
            "kind": "support_limit_synthetic",
            "bundle_dir": bundle_dir.relative_to(output_root).as_posix(),
            "log_records": args.log_records,
            "metric_records": args.metric_records,
            "supported_log_record_limit": run_openbell.LOG_RECORD_LIMIT,
            "supported_metric_record_limit": run_openbell.METRIC_RECORD_LIMIT,
        },
        "thresholds": {
            "wall_time_median_seconds_max": args.time_threshold_seconds,
            "peak_python_memory_mib_max": args.memory_threshold_mib,
        },
        "environment": environment_summary(),
        "warmup": {
            "runs": args.warmup_runs,
            "results": warmup_results,
        },
        "measured": {
            "runs": args.runs,
            "results": measured_results,
        },
        "summary": {
            "deterministic_pipeline_wall_time_seconds": round(wall_time_median, 6),
            "peak_python_memory_mib": round(peak_memory_max, 6),
            "exit_codes_passed": exit_codes_passed,
            "time_passed": time_passed,
            "memory_passed": memory_passed,
        },
        "limitations": [
            "This is a local synthetic benchmark, not an operating performance guarantee.",
            "M-017 uses tracemalloc and excludes native memory plus operating-system file cache.",
            "The generated bundle contains synthetic telemetry only and no real customer, account, or secret data.",
        ],
    }


def write_report(output_root: Path, summary: dict[str, Any]) -> None:
    report_path = output_root / BENCHMARK_REPORT_FILENAME
    summary_values = summary["summary"]
    thresholds = summary["thresholds"]
    environment = summary["environment"]
    fixture = summary["fixture"]
    lines = [
        "# OpenBell Guard P4-18 Benchmark Report",
        "",
        f"- status: `{summary['status']}`",
        f"- M-016 deterministic pipeline wall-time median: `{summary_values['deterministic_pipeline_wall_time_seconds']}` seconds",
        f"- M-016 threshold: `<= {thresholds['wall_time_median_seconds_max']}` seconds",
        f"- M-017 peak traced Python memory: `{summary_values['peak_python_memory_mib']}` MiB",
        f"- M-017 threshold: `<= {thresholds['peak_python_memory_mib_max']}` MiB",
        f"- measured runs: `{summary['measured']['runs']}`",
        f"- warm-up runs: `{summary['warmup']['runs']}`",
        f"- synthetic log records: `{fixture['log_records']}`",
        f"- synthetic metric records: `{fixture['metric_records']}`",
        "",
        "## Environment",
        "",
        f"- platform: `{environment['platform']}`",
        f"- Python: `{environment['python_version']} ({environment['python_implementation']})`",
        f"- machine: `{environment['machine']}`",
        f"- processor: `{environment['processor']}`",
        f"- cpu_count: `{environment['cpu_count']}`",
        "",
        "## Measured runs",
        "",
        "| run | exit_code | M-016 seconds | M-017 MiB |",
        "|---:|---:|---:|---:|",
    ]
    for result in summary["measured"]["results"]:
        lines.append(
            "| "
            f"{result['run_index']} | "
            f"{result['exit_code']} | "
            f"{result['deterministic_pipeline_wall_time_seconds']} | "
            f"{result['peak_python_memory_mib']} |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    for limitation in summary["limitations"]:
        lines.append(f"- {limitation}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    bundle_dir = generate_benchmark_bundle(
        output_root=output_root,
        log_records=args.log_records,
        metric_records=args.metric_records,
    )
    runs_root = prepare_child_dir(output_root, "runs")

    warmup_results: list[dict[str, Any]] = []
    for index in range(1, args.warmup_runs + 1):
        warmup_results.append(
            run_once(
                bundle_dir=bundle_dir,
                run_output=runs_root / f"warmup-{index:03d}",
                run_index=index,
                measured=False,
            )
        )

    measured_results: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        measured_results.append(
            run_once(
                bundle_dir=bundle_dir,
                run_output=runs_root / f"run-{index:03d}",
                run_index=index,
                measured=True,
            )
        )

    summary = build_summary(
        output_root=output_root,
        bundle_dir=bundle_dir,
        args=args,
        warmup_results=warmup_results,
        measured_results=measured_results,
    )
    write_json(output_root / BENCHMARK_SUMMARY_FILENAME, summary)
    write_report(output_root, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    issue_payload = ensure_benchmark_args(args)
    if issue_payload is not None:
        print(json.dumps(issue_payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return int(issue_payload["exit_code"])

    summary = run_benchmark(args)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
