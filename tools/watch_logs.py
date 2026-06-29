#!/usr/bin/env python3
"""Continuously mirror Codex IDE conversations into the project's logs folder."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

from save_log import slim_transcript


def _normalized(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def _session_info(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as source:
            first = source.readline()
        obj = json.loads(first)
        if obj.get("type") != "session_meta":
            return None
        payload = obj.get("payload") or {}
        cwd = payload.get("cwd")
        session_id = payload.get("session_id") or payload.get("id")
        if not cwd or not session_id:
            return None
        return cwd, os.path.basename(str(session_id))
    except (OSError, ValueError, TypeError):
        return None


def _sync(transcript: Path, project_dir: Path, session_id: str) -> None:
    raw = transcript.read_text(encoding="utf-8", errors="replace")
    output = slim_transcript(raw, "codex")
    if output is None:
        output = raw

    destination_dir = project_dir / "logs" / "codex"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{session_id}.jsonl"
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(output, encoding="utf-8", newline="")
    os.replace(temporary, destination)


def _acquire_single_instance(project_dir: Path):
    """Keep one watcher per project on Windows; return a held mutex handle."""
    if os.name != "nt":
        return None
    import ctypes

    digest = hashlib.sha256(_normalized(project_dir).encode("utf-8")).hexdigest()[:24]
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, f"Local\\axwar-log-{digest}")
    if not handle or ctypes.windll.kernel32.GetLastError() == 183:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        raise SystemExit(0)
    return handle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    sessions_dir = Path.home() / ".codex" / "sessions"
    if not sessions_dir.is_dir():
        return 0

    mutex = _acquire_single_instance(project_dir) if not args.once else None
    del mutex  # The Windows handle remains owned by this process until exit.

    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    observed: dict[Path, tuple[int, int]] = {}
    target = _normalized(project_dir)

    while not stopped:
        for transcript in sessions_dir.rglob("*.jsonl"):
            try:
                stat = transcript.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if observed.get(transcript) == signature:
                    continue
                observed[transcript] = signature
                info = _session_info(transcript)
                if info and _normalized(info[0]) == target:
                    _sync(transcript, project_dir, info[1])
            except OSError:
                continue

        if args.once:
            break
        time.sleep(max(args.interval, 0.25))

    return 0


if __name__ == "__main__":
    sys.exit(main())
