#!/usr/bin/env python3
"""Release gate for design-playbook.

Automates everything that can be automated before a tag. Run with no args for
a dry-run (no side effects); pass --apply to create the vX.Y.Z tag from the
version in plugin.json. Pushing the tag and creating the GitHub Release stay
manual (irreversible / human).

Steps:
  1. working tree clean (no uncommitted tracked changes)
  2. plugin.json + marketplace.json versions match (2 sites) and are semver
  3. scripts/validate.py green
  4. seam test (test_validate_run.py) green
  5. adapter floor self-check green
  6. tag v<X.Y.Z> does not already exist; create it (only with --apply)

Exit 0 if all gates pass; 1 otherwise. --apply still fails fast on any gate.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
VALIDATOR = ROOT / "scripts" / "validate.py"
SEAM_TEST = PKG / "tests" / "test_validate_run.py"
PREVIEW_SERVER = ROOT / "packages" / "design-playbook-preview" / "server.py"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    failures.append(msg)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git(*args: str) -> str:
    r = run(["git", "-C", str(ROOT), *args])
    return r.stdout.strip() if r.returncode == 0 else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="create the git tag (default: dry-run)")
    args = ap.parse_args()

    # --- 1. working tree clean ---
    print("== 1. working tree clean ==")
    status = git("status", "--porcelain")
    dirty = [l for l in status.splitlines()
             if l and not l.startswith("?? ")]
    if dirty:
        fail(f"working tree has uncommitted tracked changes: {len(dirty)} file(s)")
        for l in dirty[:5]:
            print(f"        {l}")
    else:
        ok("working tree clean (untracked ignored)")

    # --- 2. version consistency ---
    print("== 2. version consistency ==")
    pj = json.loads((PKG / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mj = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    v_pj = pj.get("version", "")
    v_mj_meta = mj.get("metadata", {}).get("version", "")
    v_mj_plugin = (mj.get("plugins") or [{}])[0].get("version", "")
    if not SEMVER.match(v_pj):
        fail(f"plugin.json version not semver: {v_pj!r}")
    elif v_pj == v_mj_meta == v_mj_plugin:
        ok(f"versions match across 3 sites: {v_pj}")
    else:
        fail(f"version mismatch: plugin.json={v_pj!r} "
             f"marketplace.meta={v_mj_meta!r} marketplace.plugin={v_mj_plugin!r}")

    # --- 3. validate.py ---
    print("== 3. scripts/validate.py ==")
    r = run([sys.executable, str(VALIDATOR)])
    if r.returncode == 0 and "VALIDATION PASSED" in r.stdout:
        ok("validate.py PASSED")
    else:
        fail(f"validate.py failed (exit {r.returncode})")
        print(r.stdout[-600:])

    # --- 4. seam test ---
    print("== 4. seam test (test_validate_run.py) ==")
    r = run([sys.executable, str(SEAM_TEST)])
    if r.returncode == 0 and "SEAM TEST PASSED" in r.stdout:
        ok("SEAM TEST PASSED")
    else:
        fail(f"seam test failed (exit {r.returncode})")
        print(r.stdout[-800:])

    # --- 5. adapter floor self-check ---
    print("== 5. adapter floor self-check ==")
    r = run([sys.executable, str(PREVIEW_SERVER), "--self-check"])
    if r.returncode == 0 and "FLOOR SELF-CHECK PASSED" in r.stdout:
        ok("FLOOR SELF-CHECK PASSED")
    else:
        fail(f"adapter self-check failed (exit {r.returncode})")
        print(r.stdout[-400:])

    # --- 6. tag ---
    print("== 6. tag ==")
    tag = f"v{v_pj}"
    existing = git("tag", "-l", tag)
    if existing:
        fail(f"tag {tag} already exists")
    elif v_pj and SEMVER.match(v_pj):
        if args.apply:
            r = run(["git", "-C", str(ROOT), "tag", tag])
            if r.returncode == 0:
                ok(f"created tag {tag}")
            else:
                fail(f"git tag {tag} failed: {r.stderr}")
        else:
            ok(f"tag {tag} not present (dry-run; pass --apply to create)")

    # --- manual steps reminder ---
    print()
    print("== manual (irreversible / human) ==")
    print(f"  - git push origin main")
    print(f"  - git push origin {tag}  (after --apply)")
    print(f"  - GitHub Release @ {tag}, body = docs/releases/{tag[1:]}.md")
    print(f"  - 2nd-session install smoke (release-checklist gate 5)")

    print()
    if failures:
        print(f"RELEASE GATE FAILED: {len(failures)} issue(s)")
        return 1
    print("RELEASE GATE PASSED" + (" (dry-run; --apply to tag)" if not args.apply else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
