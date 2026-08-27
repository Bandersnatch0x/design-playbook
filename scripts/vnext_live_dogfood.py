#!/usr/bin/env python3
"""vNext live dogfood preflight, checklist printer, and post-run verifier.

Usage:
  python scripts/vnext_live_dogfood.py preflight
  python scripts/vnext_live_dogfood.py checklist
  python scripts/vnext_live_dogfood.py verify --run-root .scratch/<run>
  python scripts/vnext_live_dogfood.py all --run-root .scratch/<run>   # preflight + checklist
                                                     # (+ verify if --run-root set)

Does not drive the coding agent or MCP HITL. Humans/agents follow the printed
list; this script only automates environment and artifact checks.
See docs/agents/vnext-live-dogfood.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
SCRIPTS = PKG / "scripts"
DOCS = ROOT / "docs" / "agents" / "vnext-live-dogfood.md"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    validate_capture_snapshot,
)

DEFAULT_ASK = (
    "Build a greenfield ops alert inbox: table of alerts with severity, "
    "last seen, and one primary ack action. Empty / loading / error / "
    "no-permission each need a next action. CJK labels ok."
)


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _ok(msg: str) -> None:
    print(f"  ok    {msg}")


def _fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def _warn(msg: str) -> None:
    print(f"  WARN  {msg}")


def preflight() -> int:
    print("== vNext live dogfood preflight ==")
    failures = 0

    required = [
        SCRIPTS / "validate_run.py",
        SCRIPTS / "run_status.py",
        SCRIPTS / "doctor.py",
        SCRIPTS / "contract_v1.py",
        SCRIPTS / "g7_contract_drift.py",
        PKG / "mcp" / "evidence" / "server.py",
        PKG / "mcp" / "preview" / "server.py",
        DOCS,
    ]
    for path in required:
        if path.is_file():
            _ok(f"present {path.relative_to(ROOT)}")
        else:
            _fail(f"missing {path.relative_to(ROOT)}")
            failures += 1

    validate = _run([sys.executable, str(ROOT / "scripts" / "validate.py")])
    if validate.returncode == 0 and "VALIDATION PASSED" in validate.stdout:
        _ok("scripts/validate.py PASSED")
    else:
        _fail("scripts/validate.py did not pass")
        failures += 1

    doctor = _run([sys.executable, str(SCRIPTS / "doctor.py"), "--json"])
    if doctor.returncode not in (0, 1):
        _fail(f"doctor crashed exit={doctor.returncode}")
        failures += 1
    else:
        try:
            payload = json.loads(doctor.stdout)
            level = payload.get("level")
            if level == "broken":
                _fail("doctor level=broken — fix install before live dogfood")
                failures += 1
            else:
                _ok(f"doctor level={level}")
                if level == "degraded":
                    _warn(
                        "doctor degraded (often missing DESIGN_PLAYBOOK_RUN_ROOT); "
                        "set it to the run abs path before observe*"
                    )
        except json.JSONDecodeError:
            _fail("doctor --json produced invalid JSON")
            failures += 1

    try:
        import playwright  # noqa: F401

        _ok("playwright importable (observe* possible)")
    except ImportError:
        _warn("playwright not installed — observe* must skip or install first")

    # One import seam (ADR-0022): package root on sys.path once, then absolute
    # design_playbook.* imports below. No per-runtime sys.path adapters.
    if str(PKG) not in sys.path:
        sys.path.insert(0, str(PKG))
    try:
        from design_playbook.mcp.evidence import server as evidence

        try:
            evidence.parse_capture_contract({"url": "about:blank"})
            _fail("capture contract accepted missing schemaVersion")
            failures += 1
        except ValueError as exc:
            if "schemaVersion" in str(exc):
                _ok("capture contract fails closed without schemaVersion=1")
            else:
                _fail(f"unexpected capture error: {exc}")
                failures += 1
        evidence.parse_capture_contract(
            {
                "schemaVersion": 1,
                "viewport": {
                    "width": 1280,
                    "height": 800,
                    "devicePixelRatio": 1,
                    "colorScheme": "light",
                },
            }
        )
        _ok("capture contract v1 viewport parse ok")
    except Exception as exc:  # noqa: BLE001
        _fail(f"evidence server import/parse: {exc}")
        failures += 1

    print()
    if failures:
        print(f"PREFLIGHT FAILED: {failures} issue(s)")
        return 1
    print("PREFLIGHT PASSED — continue with interactive design-io")
    print(f"Checklist doc: {DOCS.relative_to(ROOT)}")
    return 0


def checklist() -> int:
    print("== vNext live dogfood checklist ==")
    print()
    print("Default ask:")
    print(f"  {DEFAULT_ASK}")
    print()
    print("Host load (pick one):")
    print(f"  claude --plugin-dir {PKG}")
    print("  # or installed: /design-playbook:design-io <ask>")
    print(f"  # machine handshake (creates its own isolated config): python {ROOT / 'scripts' / 'plugin_dir_smoke.py'}")
    print()
    print("Observe env (when adapter present):")
    print("  set DESIGN_PLAYBOOK_RUN_ROOT=<abs path to .scratch/<run>>")
    print()
    steps = [
        ("0 Entry", "Start /design-playbook:design-io with the ask; skip baseline/reference for greenfield"),
        ("1 Bind", "If project contract exists: bind-first; ack assumed; do not invent decided"),
        ("2 Spec", "L1–L6 on disk; L6 = user-risk Given/When/Then (soft 3–7)"),
        ("3 Plan", "plan.md three blocks before decision report"),
        ("4 Decision", "decision-report.md before Fill"),
        ("5 preview*", "If preview_prototype present: HITL until floor_pass confirm; else narrate skip"),
        ("6 Status", f"python {SCRIPTS / 'run_status.py'} <run> --json"),
        ("7 Fill", "Main flow + L5 paths; never copy preview/reference assets"),
        ("8 Craft", "craft-guard rows; N/A needs observable reason"),
        ("9 observe*", "If execute_capture_plan present: schemaVersion=1 + viewport every call; else skip narrate"),
        ("10 Accept", "point-back + verdict + run artifact index"),
        ("11 Verify", "python scripts/vnext_live_dogfood.py verify --run-root <run>"),
        ("12 Log", "Write .scratch/design-playbook-v0/dogfood/YYYY-MM-DD-HHMM-vnext-live.md"),
    ]
    for title, detail in steps:
        print(f"  [ ] {title}")
        print(f"      {detail}")
    print()
    print("Capture minimum (observe*):")
    print(
        '  {"schemaVersion":1,"viewport":{"width":1280,"height":800,'
        '"devicePixelRatio":1,"colorScheme":"light"},'
        '"url":"...","type":"screenshot","state":"...","actions":[],'
        '"artifact_path":"evidence/....png"}'
    )
    print()
    print(f"Full prose: {DOCS.relative_to(ROOT)}")
    return 0


def _manifest_capture_ok(manifest: Path) -> list[str]:
    """Project capture-contract read authority over each manifest line."""
    problems: list[str] = []
    if not manifest.is_file():
        return problems
    for i, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"manifest.jsonl:{i} invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            problems.append(f"manifest.jsonl:{i} not an object")
            continue
        capture = row.get("capture") if isinstance(row.get("capture"), dict) else {}
        request = row.get("request")
        if not isinstance(request, dict):
            request = (
                capture.get("request")
                if isinstance(capture.get("request"), dict)
                else {}
            )
        for fact in validate_capture_snapshot(request):
            problems.append(f"manifest.jsonl:{i} {fact.code}: {fact.detail}")
    return problems


def verify(run_root: Path) -> int:
    print(f"== vNext live dogfood verify ({run_root}) ==")
    failures = 0
    if not run_root.is_dir():
        _fail(f"not a directory: {run_root}")
        return 1

    required = ("spec.md", "plan.md", "decision-report.md", "point-back.md")
    for name in required:
        path = run_root / name
        if path.is_file():
            _ok(f"artifact {name}")
        else:
            _fail(f"missing {name}")
            failures += 1

    spec = run_root / "spec.md"
    pb = run_root / "point-back.md"
    if spec.is_file() and pb.is_file():
        base = [
            sys.executable,
            str(SCRIPTS / "validate_run.py"),
            str(spec),
            str(pb),
        ]
        text = _run(base)
        if text.returncode == 0 and "RUN OK" in text.stdout:
            _ok("validate_run text RUN OK")
        elif text.returncode == 1:
            _warn("validate_run text RUN INVALID — inspect FAIL lines")
            print(text.stdout[-800:])
        else:
            _fail(f"validate_run text exit={text.returncode}")
            failures += 1

        j = _run([*base, "--format", "json"])
        try:
            findings = json.loads(j.stdout or "[]")
            if not isinstance(findings, list):
                raise ValueError("not a list")
            if j.returncode == 0 and findings == []:
                _ok("validate_run json empty findings")
            elif j.returncode == 1 and findings:
                first = findings[0]
                keys = {"rule_id", "owner", "expected", "actual", "repair", "severity"}
                missing = keys - set(first)
                if missing:
                    _fail(f"json findings missing fields {sorted(missing)}")
                    failures += 1
                else:
                    _ok(
                        f"validate_run json structured errors "
                        f"(first rule_id={first.get('rule_id')})"
                    )
            else:
                _warn(f"validate_run json exit={j.returncode} findings={len(findings)}")
        except (json.JSONDecodeError, ValueError) as exc:
            _fail(f"validate_run json unreadable: {exc}")
            failures += 1

        preview = run_root / "preview"
        if preview.is_dir():
            g5_cmd = [*base, "--preview-dir", str(preview)]
            report = run_root / "decision-report.md"
            if report.is_file():
                g5_cmd.extend(["--decision-report", str(report)])
            g5 = _run(g5_cmd)
            if g5.returncode == 0:
                _ok("G5 preview path RUN OK")
            else:
                _warn(f"G5 preview path exit={g5.returncode}")
                print(g5.stdout[-600:])
        else:
            _warn("no preview/ — G5 not exercised (skip ok if narrated)")

        evidence = run_root / "evidence"
        ledger = pb.read_text(encoding="utf-8") if pb.is_file() else ""
        if evidence.is_dir() and "evidence/" in ledger.casefold():
            g6 = _run(
                [
                    *base,
                    "--evidence-dir",
                    str(evidence),
                    "--run-root",
                    str(run_root),
                ]
            )
            if g6.returncode == 0:
                _ok("G6 evidence path RUN OK")
            else:
                _warn(f"G6 evidence path exit={g6.returncode}")
                print(g6.stdout[-600:])
            for problem in _manifest_capture_ok(evidence / "manifest.jsonl"):
                _fail(problem)
                failures += 1
            if not (evidence / "manifest.jsonl").is_file():
                _fail("evidence/ present but manifest.jsonl missing")
                failures += 1
            elif "schemaVersion" not in (evidence / "manifest.jsonl").read_text(
                encoding="utf-8"
            ):
                # already covered line-by-line; keep quiet
                pass
            else:
                _ok("manifest rows inspected for capture contract v1")
        else:
            _warn("no evidence/ binding in ledger — G6/capture contract not exercised")

    # Project contract beside run or under project-contract/
    for project in (run_root, run_root / "project-contract", run_root.parent):
        contract = project / "contract.json"
        bind = run_root / "contract-bind.json"
        if contract.is_file() and bind.is_file():
            g7 = _run(
                [
                    sys.executable,
                    str(SCRIPTS / "validate_run.py"),
                    str(spec),
                    str(pb),
                    "--format",
                    "json",
                    "--contract-project",
                    str(project),
                    "--contract-run",
                    str(run_root),
                ]
            )
            if g7.returncode == 0:
                _ok(f"G7 ok (project={project.name})")
            else:
                _warn(f"G7 exit={g7.returncode} project={project}")
                print(g7.stdout[-600:])
            break
    else:
        _warn("no contract.json + contract-bind.json pair — G7 not exercised")

    status = _run(
        [sys.executable, str(SCRIPTS / "run_status.py"), str(run_root), "--json"]
    )
    if status.returncode == 0:
        try:
            payload = json.loads(status.stdout)
            if "stages" in payload and "next" in payload:
                _ok(f"run_status next={payload['next'][:80]!r}")
            else:
                _fail("run_status json missing stages/next")
                failures += 1
        except json.JSONDecodeError:
            _fail("run_status invalid JSON")
            failures += 1
    else:
        _fail(f"run_status exit={status.returncode}")
        failures += 1

    doctor = _run(
        [
            sys.executable,
            str(SCRIPTS / "doctor.py"),
            "--json",
            "--run-root",
            str(run_root),
        ]
    )
    if doctor.returncode in (0, 1):
        try:
            level = json.loads(doctor.stdout).get("level")
            if level == "broken":
                _fail("doctor level=broken")
                failures += 1
            else:
                _ok(f"doctor level={level}")
        except json.JSONDecodeError:
            _fail("doctor invalid JSON")
            failures += 1
    else:
        _fail(f"doctor exit={doctor.returncode}")
        failures += 1

    print()
    print("Human gates still required (not automated):")
    print("  [ ] six process gates filled in dogfood log")
    print("  [ ] skip narration if preview*/observe* absent")
    print("  [ ] recirculate trail or acceptance for every blocking finding")
    print("  [ ] log at .scratch/design-playbook-v0/dogfood/*-vnext-live.md")
    print()
    if failures:
        print(f"VERIFY FAILED: {failures} automated issue(s)")
        return 1
    print("VERIFY PASSED (automated). Complete human gates + dogfood log.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("preflight", "checklist", "verify", "all"),
        help="preflight env | print checklist | verify a run | preflight+checklist",
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="run directory for verify (or all)",
    )
    args = parser.parse_args(argv)

    if args.command == "preflight":
        return preflight()
    if args.command == "checklist":
        return checklist()
    if args.command == "verify":
        if args.run_root is None:
            print("verify requires --run-root", file=sys.stderr)
            return 2
        return verify(args.run_root.resolve())
    # all
    code = preflight()
    print()
    checklist()
    if args.run_root is not None:
        print()
        code = verify(args.run_root.resolve()) or code
    return code


if __name__ == "__main__":
    sys.exit(main())
