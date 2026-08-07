#!/usr/bin/env python3
"""Packaged install/runtime doctor for design-playbook (vNext ticket 10).

Runs against the installed plugin package root (this file's grandparents),
not the monorepo. Reports capability level and concrete repairs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("ok", "degraded", "broken")


def _check(name: str, ok: bool, repair: str, *, required: bool = True) -> dict:
    return {
        "name": name,
        "ok": ok,
        "required": required,
        "repair": repair if not ok else "",
        "level": "ok" if ok else ("broken" if required else "degraded"),
    }


def run_checks(*, run_root: str | None = None) -> list[dict]:
    checks: list[dict] = []

    checks.append(_check(
        "python>=3.10",
        sys.version_info >= (3, 10),
        f"Install Python 3.10+ (found {sys.version.split()[0]})",
    ))

    plugin_json = PACKAGE_ROOT / ".claude-plugin" / "plugin.json"
    mcp_json = PACKAGE_ROOT / ".mcp.json"
    validate_run = PACKAGE_ROOT / "scripts" / "validate_run.py"
    run_status = PACKAGE_ROOT / "scripts" / "run_status.py"
    preview = PACKAGE_ROOT / "mcp" / "preview" / "server.py"
    evidence = PACKAGE_ROOT / "mcp" / "evidence" / "server.py"

    for path, label in (
        (plugin_json, "plugin.json"),
        (mcp_json, ".mcp.json"),
        (validate_run, "scripts/validate_run.py"),
        (run_status, "scripts/run_status.py"),
        (preview, "mcp/preview/server.py"),
        (evidence, "mcp/evidence/server.py"),
    ):
        checks.append(_check(
            f"package:{label}",
            path.is_file(),
            f"Reinstall design-playbook; missing {label}",
        ))

    version = None
    if plugin_json.is_file():
        try:
            version = json.loads(plugin_json.read_text(encoding="utf-8")).get("version")
        except (OSError, json.JSONDecodeError):
            version = None
    checks.append(_check(
        "plugin.version",
        isinstance(version, str) and bool(version),
        "plugin.json must declare a semver version",
    ))

    # Optional: Playwright for evidence capture.
    playwright_ok = importlib.util.find_spec("playwright") is not None
    checks.append(_check(
        "dependency:playwright",
        playwright_ok,
        "pip install playwright && playwright install chromium",
        required=False,
    ))

    # Optional MCP tools cannot be probed without a live host; report env config.
    run_env = os.environ.get("DESIGN_PLAYBOOK_RUN_ROOT")
    if run_root:
        target = Path(run_root)
        checks.append(_check(
            "run_root.path",
            target.is_dir(),
            f"Create or pass an existing run root (got {run_root})",
            required=False,
        ))
    else:
        checks.append(_check(
            "run_root.env",
            True,
            "",
            required=False,
        ) if run_env else _check(
            "run_root.env",
            False,
            "Set DESIGN_PLAYBOOK_RUN_ROOT to the absolute .scratch/<run> path for evidence captures",
            required=False,
        ))

    return checks


def overall_level(checks: list[dict]) -> str:
    if any(item["level"] == "broken" for item in checks):
        return "broken"
    if any(item["level"] == "degraded" for item in checks):
        return "degraded"
    return "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Packaged design-playbook doctor")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--run-root", default=None, help="optional run root to verify")
    args = parser.parse_args(argv)
    checks = run_checks(run_root=args.run_root)
    level = overall_level(checks)
    payload = {
        "package_root": str(PACKAGE_ROOT),
        "level": level,
        "checks": checks,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"design-playbook doctor: {level}")
        print(f"package: {PACKAGE_ROOT}")
        for item in checks:
            mark = "ok" if item["ok"] else ("WARN" if not item["required"] else "FAIL")
            line = f"  {mark:4} {item['name']}"
            if item["repair"]:
                line += f" — {item['repair']}"
            print(line)
    return 0 if level != "broken" else 1


if __name__ == "__main__":
    sys.exit(main())
