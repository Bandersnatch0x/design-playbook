#!/usr/bin/env python3
"""Packaged install/runtime doctor for design-playbook (vNext ticket 10).

Runs against the installed plugin package root (this file's grandparents),
not the monorepo. Reports capability level and concrete repairs.

Also reports drifted ``npx design-playbook init <agent>`` artifacts in the
target repository (report-only; the refresh action is re-running init).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from design_playbook.scripts.audit_preferences import (  # noqa: E402
    effective_plan,
    resolve_preferences,
)
from design_playbook.scripts.adapter_matrix import MATRIX  # noqa: E402
from design_playbook.scripts.generate_adapter import render_entries  # noqa: E402

LEVELS = ("ok", "degraded", "broken")


def _check(name: str, ok: bool, repair: str, *, required: bool = True) -> dict:
    return {
        "name": name,
        "ok": ok,
        "required": required,
        "repair": repair if not ok else "",
        "level": "ok" if ok else ("broken" if required else "degraded"),
    }


# ---------------------------------------------------------------------------
# Adapter lifecycle (CONTEXT.md "Adapter lifecycle check", 2026-09-19).
# Report-only: drift means re-running `npx design-playbook init <agent>` with
# the installed package would change the file. Never writes; never blocks.
# ---------------------------------------------------------------------------

_MARKER_RE = re.compile(r"generated-by design-playbook v(\d[^\s\"']*)")
_MARKER_NORM_RE = re.compile(r"generated-by design-playbook v\d[^\s\"']*")

# Namespaced output roots that can hold orphaned generated files, per agent.
# Kept honest by tests/test_adapter_lifecycle.py: every non-native agent's
# fresh init must be discovered through this map plus _WHOLE_FILE_CANDIDATES.
_ORPHAN_SCAN_DIRS: dict[str, tuple[str, ...]] = {
    "codex": (".codex-plugin", "codex"),
    "cursor": (".cursor/rules",),
    "gemini-cli": (".gemini/commands",),
    "windsurf": (".windsurf/rules", ".windsurf/workflows"),
    "github-copilot": (".github/instructions",),
}
# Whole-file candidates carrying the generated-by marker outside namespaced
# dirs (marker-block targets are always re-rendered in place, so they are
# discovered here rather than via orphan scanning).
_WHOLE_FILE_CANDIDATES = (
    "AGENTS.md",
    "GEMINI.md",
    ".github/copilot-instructions.md",
    "design-playbook-mcp-setup.md",
)

_LIMITATIONS = (
    "marker-less JSON merge targets (.mcp.json, opencode.json, "
    "settings.json) are never attributed; re-init may still merge into them"
)


def _read_text_safe(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _normalize_generation(text: str) -> str:
    """Marker-version and CRLF normalization for byte comparison."""
    return _MARKER_NORM_RE.sub(
        "generated-by design-playbook vNORM", text.replace("\r\n", "\n")
    )


def _iter_orphan_candidates(repo_root: Path):
    """Yield (agent, path, rel) for every file under a namespaced output
    root — the single walk behind both the discovery gate and the orphan
    scan, so _ORPHAN_SCAN_DIRS has exactly one interpretation."""
    for agent, dirs in _ORPHAN_SCAN_DIRS.items():
        for d in dirs:
            base = repo_root / d
            if not base.is_dir():
                continue
            for f in sorted(base.iterdir()):
                if f.is_file():
                    yield agent, f, f.relative_to(repo_root).as_posix()


def _lifecycle_findings(repo_root: Path, package_version: str | None) -> dict:
    """Classify generated init artifacts under *repo_root*. Read-only and
    fail-open per agent: a renderer that cannot compute content (malformed
    JSON merge target, undecodable marker file) degrades to a render_error
    finding instead of crashing the doctor report.

    Only files carrying the generated-by marker are judged; marker-less
    files (user-authored content, marker-less JSON merge targets) are never
    attributed — an unreadable file counts as unattributed for the same
    reason (it cannot be judged as ours).
    """
    files: list[dict] = []
    counts = {
        "drifted": 0,
        "orphaned": 0,
        "clean": 0,
        "absent": 0,
        "unattributed": 0,
        "render_error": 0,
    }

    def record(agent: str, rel: str, cls: str, marker_version: str | None = None) -> None:
        counts[cls] += 1
        if cls in ("drifted", "orphaned"):
            files.append({
                "agent": agent,
                "path": rel,
                "cls": cls,
                "marker_version": marker_version,
                "repair": (
                    f"npx design-playbook init {agent}"
                    if cls == "drifted"
                    else f"delete {rel} then npx design-playbook init {agent}"
                ),
            })

    # Discovery gate: without any generated-by marker anywhere there is
    # nothing to attribute — skip the per-agent renders entirely. One walk
    # over the namespaced roots feeds both this gate and the orphan scan.
    orphan_candidates = list(_iter_orphan_candidates(repo_root))
    discovered = False
    for rel in _WHOLE_FILE_CANDIDATES:
        text = _read_text_safe(repo_root / rel)
        if text is not None and _MARKER_RE.search(text):
            discovered = True
            break
    if not discovered:
        for _agent, path, _rel in orphan_candidates:
            text = _read_text_safe(path)
            if text is not None and _MARKER_RE.search(text):
                discovered = True
                break
    if not discovered:
        return {
            "status": "not-initialized",
            "counts": counts,
            "files": [],
            "package_version": package_version,
            "limitations": _LIMITATIONS,
        }

    # One render pass over all non-native agents, grouped by target path.
    # AGENTS.md is a shared target (opencode + every tier-3 floor agent), so
    # a file is clean when it matches ANY current candidate render; drift is
    # "matches no current renderer", never "differs from one agent's render".
    renders: dict[str, list[tuple[str, str]]] = {}
    rendered_by_agent: dict[str, set[str]] = {}
    render_failed: set[str] = set()
    for row in MATRIX:
        if row.native:
            continue
        try:
            _version, _out_dir, entries = render_entries(row.agent, repo_root)
        except (ValueError, OSError) as exc:
            # Fail-loud renderer inputs (malformed merge JSON, undecodable
            # marker file) degrade to a finding; the other agents still
            # classify and the doctor keeps reporting. No rendered set means
            # the orphan scan must skip this agent too — flagging its
            # marker'd files orphaned would be a false positive.
            counts["render_error"] += 1
            render_failed.add(row.agent)
            files.append({
                "agent": row.agent,
                "path": None,
                "cls": "render_error",
                "marker_version": None,
                "reason": str(exc),
                "repair": (
                    f"fix or remove the unreadable config, then "
                    f"npx design-playbook init {row.agent}"
                ),
            })
            continue
        rendered_by_agent[row.agent] = {rel for rel, _content in entries}
        for rel, content in entries:
            renders.setdefault(rel, []).append((row.agent, content))

    for rel in sorted(renders):
        candidates = renders[rel]
        path = repo_root / rel
        if not path.is_file():
            counts["absent"] += 1
            continue
        actual = _read_text_safe(path)
        m = _MARKER_RE.search(actual) if actual is not None else None
        if m is None:
            counts["unattributed"] += 1
            continue
        if any(
            _normalize_generation(content) == _normalize_generation(actual)
            for _agent, content in candidates
        ):
            counts["clean"] += 1
            continue
        agents = [agent for agent, _content in candidates]
        if len(agents) == 1:
            agent: str | None = agents[0]
            repair = f"npx design-playbook init {agent}"
        else:
            agent = None
            repair = (
                f"npx design-playbook init <your-agent> "
                f"({rel} is shared by: {', '.join(agents)})"
            )
        counts["drifted"] += 1
        files.append({
            "agent": agent,
            "path": rel,
            "cls": "drifted",
            "marker_version": m.group(1),
            "repair": repair,
        })

    for agent, path, rel in orphan_candidates:
        if agent in render_failed or rel in rendered_by_agent.get(agent, set()):
            continue
        text = _read_text_safe(path)
        m = _MARKER_RE.search(text) if text is not None else None
        if m is not None:
            record(agent, rel, "orphaned", m.group(1))

    return {
        "status": "scanned",
        "counts": counts,
        "files": files,
        "package_version": package_version,
        "limitations": _LIMITATIONS,
    }


def _adapter_lifecycle_check(repo_root: Path, package_version: str | None) -> dict:
    report = _lifecycle_findings(repo_root, package_version)
    findings = report["files"]
    return {
        "name": "adapter_lifecycle",
        "ok": not findings,
        "required": False,
        "repair": (
            "Refresh drifted init artifacts: "
            + "; ".join(dict.fromkeys(f["repair"] for f in findings))
            if findings
            else ""
        ),
        "level": "degraded" if findings else "ok",
        "detail": report,
    }


def run_checks(
    *,
    run_root: str | None = None,
    repo_root: str | None = None,
) -> list[dict]:
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
    audit_preferences = PACKAGE_ROOT / "scripts" / "audit_preferences.py"
    preview = PACKAGE_ROOT / "mcp" / "preview" / "server.py"
    evidence = PACKAGE_ROOT / "mcp" / "evidence" / "server.py"

    for path, label in (
        (plugin_json, "plugin.json"),
        (mcp_json, ".mcp.json"),
        (validate_run, "scripts/validate_run.py"),
        (run_status, "scripts/run_status.py"),
        (audit_preferences, "scripts/audit_preferences.py"),
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

    # Audit preferences are repository-scoped. Absence is healthy and means
    # run-all defaults; corrupt layers degrade with a concrete repair.
    preference_root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    if preference_root.is_dir():
        effective = resolve_preferences(preference_root)
        plan = effective_plan(effective)
        invalid = plan["invalid_files"]
        checks.append({
            "name": "audit_preferences.state",
            "ok": not invalid,
            "required": False,
            "repair": (
                "Repair or remove corrupt preference layer(s): "
                + ", ".join(invalid)
            ) if invalid else "",
            "level": "degraded" if invalid else "ok",
            "detail": {
                "repo_root": str(preference_root),
                "asked": plan["asked"],
                "stages": plan["stages"],
                "invalid_files": invalid,
            },
        })
    else:
        checks.append(_check(
            "audit_preferences.state",
            False,
            f"Pass an existing repository root (got {preference_root})",
            required=False,
        ))

    # Unconditional: a nonexistent root classifies as not-initialized rather
    # than omitting the check entirely (uniform skip entry).
    checks.append(_adapter_lifecycle_check(preference_root, version))

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
    parser.add_argument(
        "--repo-root",
        default=None,
        help="target repository holding .design-playbook preferences (default: cwd)",
    )
    args = parser.parse_args(argv)
    checks = run_checks(run_root=args.run_root, repo_root=args.repo_root)
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
            elif item.get("detail") is not None:
                line += " — " + json.dumps(
                    item["detail"], ensure_ascii=False, sort_keys=True)
            print(line)
    return 0 if level != "broken" else 1


if __name__ == "__main__":
    sys.exit(main())
