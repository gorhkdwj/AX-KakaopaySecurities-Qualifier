"""Validate the AX hackathon submission.zip structure."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "submission.zip"
ALLOWED_LOG_EXTENSIONS = {".md", ".txt", ".json", ".jsonl"}
FORBIDDEN_PREFIXES = (
    ".git/",
    ".agents/",
    ".claude/",
    ".codex/",
    ".vscode/",
    ".pytest_cache/",
    "docs/",
    "out/",
    "submission/",
)
FORBIDDEN_PARTS = {"__pycache__"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".token"}
REQUIRED_FILES = {
    "README.md",
    "src/.codex-plugin/plugin.json",
    "src/skills/openbell-guard/SKILL.md",
    "src/skills/openbell-guard/scripts/run_openbell.py",
    "src/skills/openbell-guard/scripts/validate_bundle.py",
    "src/skills/openbell-guard/references/metrics-validation-contract.md",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def read_zip_text(archive: zipfile.ZipFile, name: str) -> str:
    with archive.open(name) as handle:
        return handle.read().decode("utf-8")


def validate_zip(zip_path: Path) -> dict[str, object]:
    if not zip_path.is_file():
        fail(f"Missing submission zip: {zip_path}")

    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(name for name in archive.namelist() if not name.endswith("/"))

        errors: list[str] = []
        name_set = set(names)
        missing = sorted(REQUIRED_FILES - name_set)
        if missing:
            errors.append(f"Missing required files: {missing}")

        root_names = {name.split("/", 1)[0] for name in names}
        allowed_roots = {"README.md", "src", "logs"}
        unexpected_roots = sorted(root_names - allowed_roots)
        if unexpected_roots:
            errors.append(f"Unexpected top-level entries: {unexpected_roots}")

        for name in names:
            if "\\" in name or name.startswith("/") or ".." in Path(name).parts:
                errors.append(f"Unsafe zip path: {name}")
            if any(name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
                errors.append(f"Forbidden path in zip: {name}")
            parts = set(Path(name).parts)
            if parts & FORBIDDEN_PARTS:
                errors.append(f"Forbidden cache path in zip: {name}")
            if Path(name).suffix.lower() in FORBIDDEN_SUFFIXES:
                errors.append(f"Forbidden file suffix in zip: {name}")

        log_files = [name for name in names if name.startswith("logs/")]
        if not log_files:
            errors.append("logs/ must contain at least one file.")
        for log_name in log_files:
            if Path(log_name).suffix.lower() not in ALLOWED_LOG_EXTENSIONS:
                errors.append(f"Unsupported log extension: {log_name}")

        try:
            manifest = json.loads(read_zip_text(archive, "src/.codex-plugin/plugin.json"))
        except Exception as exc:  # pragma: no cover - defensive branch
            errors.append(f"plugin.json is not valid UTF-8 JSON: {exc}")
            manifest = {}

        if manifest.get("name") != "openbell-guard":
            errors.append("plugin.json name must be openbell-guard.")
        if manifest.get("skills") != "./skills/":
            errors.append("plugin.json skills must be ./skills/.")
        if "mcpServers" in manifest:
            errors.append("plugin.json must not declare mcpServers without .mcp.json.")
        if "apps" in manifest:
            errors.append("plugin.json must not declare apps without .app.json.")

        readme_text = read_zip_text(archive, "README.md") if "README.md" in name_set else ""
        if "OpenBell Guard" not in readme_text:
            errors.append("README.md must describe OpenBell Guard.")
        if "실제 고객정보" not in readme_text:
            errors.append("README.md must include the safety boundary around real customer data.")

        if errors:
            fail("\n".join(errors))

        return {
            "status": "passed",
            "zip_path": str(zip_path),
            "file_count": len(names),
            "log_file_count": len(log_files),
            "required_file_count": len(REQUIRED_FILES),
            "top_level_entries": sorted(root_names),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OpenBell Guard submission.zip.")
    parser.add_argument("zip_path", nargs="?", default=str(DEFAULT_ZIP))
    args = parser.parse_args(argv)

    summary = validate_zip(Path(args.zip_path))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
