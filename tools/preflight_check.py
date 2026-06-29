#!/usr/bin/env python3
"""Token-light preflight checks for the OpenBell Guard project.

The script intentionally uses only the Python standard library. It turns
recurring troubleshooting items into quick local checks so Codex does not need
to reread the full Troubleshootinglog before every implementation step.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Result:
    level: str
    code: str
    message: str
    tid: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def existing_paths(root: Path, relative_paths: list[str]) -> list[Path]:
    return [root / item for item in relative_paths if (root / item).exists()]


def check_utf8_and_markdown(root: Path) -> list[Result]:
    results: list[Result] = []
    paths = existing_paths(
        root,
        [
            "AGENTS.md",
            "Worklog.md",
            "Decisionlog.md",
            "Troubleshootinglog.md",
            "docs/README.md",
            "docs/phase4-implementation-sequence.md",
            "docs/openbell-guard-metrics-validation-contract.md",
            "src/skills/openbell-guard/SKILL.md",
        ],
    )

    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            results.append(Result("ERROR", "UTF8_READ", f"{rel}: UTF-8 decode failed: {exc}", "T-002"))
            continue
        if "\ufffd" in text:
            results.append(Result("ERROR", "UTF8_REPLACEMENT", f"{rel}: replacement character found", "T-002"))
        if path.suffix.lower() == ".md" and text.count("```") % 2:
            results.append(Result("ERROR", "MD_FENCE", f"{rel}: unbalanced fenced code blocks"))

    results.append(Result("OK", "TEXT_FILES", f"checked {len(paths)} UTF-8/Markdown files"))
    return results


def check_troubleshooting_index(root: Path) -> list[Result]:
    path = root / "Troubleshootinglog.md"
    if not path.exists():
        return [Result("ERROR", "TLOG_MISSING", "Troubleshootinglog.md is missing")]
    text = path.read_text(encoding="utf-8")
    missing = [tid for tid in ["T-001", "T-002", "T-003", "T-004"] if tid not in text]
    if missing:
        return [Result("ERROR", "TLOG_IDS", f"missing troubleshooting IDs: {', '.join(missing)}")]
    if "python tools/preflight_check.py" not in text:
        return [Result("WARN", "TLOG_INDEX", "quick index does not mention preflight_check.py")]
    return [Result("OK", "TLOG_INDEX", "quick index and seed T-IDs found")]


def check_pyyaml() -> list[Result]:
    if importlib.util.find_spec("yaml") is None:
        return [
            Result(
                "WARN",
                "PYYAML_MISSING",
                "PyYAML is not installed; official plugin/skill validators may fail",
                "T-001",
            )
        ]
    return [Result("OK", "PYYAML", "PyYAML import is available")]


def check_git(root: Path) -> list[Result]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return [Result("WARN", "GIT_UNAVAILABLE", f"git status precheck unavailable: {exc}", "T-004")]

    if proc.returncode != 0 or proc.stdout.strip().lower() != "true":
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        message = detail[0] if detail else "not a valid git work tree"
        return [Result("WARN", "GIT_INVALID", message, "T-004")]
    return [Result("OK", "GIT", "valid git work tree")]


def check_plugin_scaffold(root: Path) -> list[Result]:
    results: list[Result] = []
    manifest_path = root / "src/.codex-plugin/plugin.json"
    skill_path = root / "src/skills/openbell-guard/SKILL.md"

    if not manifest_path.exists():
        return [Result("ERROR", "PLUGIN_MANIFEST_MISSING", "src/.codex-plugin/plugin.json is missing")]
    if not skill_path.exists():
        results.append(Result("ERROR", "SKILL_MISSING", "src/skills/openbell-guard/SKILL.md is missing"))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [Result("ERROR", "PLUGIN_JSON", f"plugin.json is invalid JSON: {exc}")]

    expected = {
        "name": "openbell-guard",
        "skills": "./skills/",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            results.append(Result("ERROR", "PLUGIN_FIELD", f"plugin.json {key!r} expected {value!r}"))

    unsupported = [key for key in ["mcpServers", "apps", "hooks"] if key in manifest]
    if unsupported:
        results.append(Result("ERROR", "PLUGIN_UNSUPPORTED", f"declares unsupported/nonexistent components: {unsupported}"))

    if skill_path.exists():
        skill = skill_path.read_text(encoding="utf-8")
        if "name: openbell-guard" not in skill:
            results.append(Result("ERROR", "SKILL_NAME", "SKILL.md frontmatter name mismatch"))

    if not results:
        results.append(Result("OK", "PLUGIN_SCAFFOLD", "plugin manifest and skill scaffold look consistent"))
    return results


def format_result(result: Result) -> str:
    suffix = f" [{result.tid}]" if result.tid else ""
    return f"{result.level:<5} {result.code:<24} {result.message}{suffix}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run token-light OpenBell Guard preflight checks.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--quiet", action="store_true", help="Only print warnings/errors and summary.")
    args = parser.parse_args(argv)

    root = project_root()
    results: list[Result] = []
    results.extend(check_utf8_and_markdown(root))
    results.extend(check_troubleshooting_index(root))
    results.extend(check_pyyaml())
    results.extend(check_git(root))
    results.extend(check_plugin_scaffold(root))

    visible = results if not args.quiet else [item for item in results if item.level != "OK"]
    for result in visible:
        print(format_result(result))

    errors = [item for item in results if item.level == "ERROR"]
    warnings = [item for item in results if item.level == "WARN"]
    print(f"SUMMARY ok={sum(1 for item in results if item.level == 'OK')} warn={len(warnings)} error={len(errors)}")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
