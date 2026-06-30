"""Build the AX hackathon submission.zip package.

The package root must contain exactly the main submission README, the Codex
plugin root under src/, and the original conversation logs under logs/.
Generated development artifacts such as docs/, out/, caches, and Git metadata
are intentionally excluded.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUBMISSION_DIR = ROOT / "submission"
DEFAULT_ZIP = ROOT / "submission.zip"
ALLOWED_LOG_EXTENSIONS = {".md", ".txt", ".json", ".jsonl"}
EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def ensure_inside_root(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Refusing to operate outside project root: {resolved}")
    return resolved


def copy_tree_filtered(src: Path, dst: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            if name in EXCLUDED_DIR_NAMES:
                ignored.add(name)
            elif Path(name).suffix.lower() in EXCLUDED_SUFFIXES:
                ignored.add(name)
        return ignored

    shutil.copytree(src, dst, ignore=ignore)


def validate_inputs(readme: Path, src: Path, logs: Path) -> list[Path]:
    errors: list[str] = []
    if not readme.is_file():
        errors.append(f"Missing README.md: {readme}")
    if not (src / ".codex-plugin" / "plugin.json").is_file():
        errors.append(f"Missing plugin manifest: {src / '.codex-plugin' / 'plugin.json'}")
    if not (src / "skills" / "openbell-guard" / "SKILL.md").is_file():
        errors.append(f"Missing OpenBell Guard SKILL.md: {src / 'skills' / 'openbell-guard' / 'SKILL.md'}")
    if not logs.is_dir():
        errors.append(f"Missing logs directory: {logs}")

    log_files = [p for p in logs.rglob("*") if p.is_file()] if logs.is_dir() else []
    if not log_files:
        errors.append("logs/ must contain at least one log file.")
    for log_file in log_files:
        if log_file.suffix.lower() not in ALLOWED_LOG_EXTENSIONS:
            errors.append(f"Unsupported log file extension: {log_file.relative_to(ROOT)}")

    if errors:
        raise SystemExit("\n".join(errors))
    return log_files


def zip_directory(source_dir: Path, zip_path: Path) -> int:
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            archive.write(file_path, file_path.relative_to(source_dir).as_posix())
            file_count += 1
    return file_count


def build_submission(submission_dir: Path, zip_path: Path) -> dict[str, object]:
    readme = ROOT / "README.md"
    src = ROOT / "src"
    logs = ROOT / "logs"
    log_files = validate_inputs(readme, src, logs)

    submission_dir = ensure_inside_root(submission_dir)
    zip_path = ensure_inside_root(zip_path)

    if submission_dir.exists():
        if submission_dir == ROOT:
            raise ValueError("Refusing to remove project root.")
        shutil.rmtree(submission_dir)
    if zip_path.exists():
        zip_path.unlink()

    submission_dir.mkdir(parents=True)
    shutil.copy2(readme, submission_dir / "README.md")
    copy_tree_filtered(src, submission_dir / "src")
    copy_tree_filtered(logs, submission_dir / "logs")

    zip_file_count = zip_directory(submission_dir, zip_path)
    return {
        "submission_dir": str(submission_dir.relative_to(ROOT)),
        "zip_path": str(zip_path.relative_to(ROOT)),
        "zip_file_count": zip_file_count,
        "log_file_count": len(log_files),
        "status": "built",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build submission.zip for OpenBell Guard.")
    parser.add_argument("--submission-dir", default=str(DEFAULT_SUBMISSION_DIR))
    parser.add_argument("--zip", default=str(DEFAULT_ZIP))
    args = parser.parse_args(argv)

    summary = build_submission(Path(args.submission_dir), Path(args.zip))
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
