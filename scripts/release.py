#!/usr/bin/env python3
"""Release gate for design-playbook.

Run with no arguments for a side-effect-free dry run. Pass ``--apply`` to
create the version tag after every selected check passes. The human atomically
pushes ``main`` and that tag; ``.github/workflows/release.yml`` then publishes
npm through Trusted Publishing and creates the GitHub Release.

See docs/agents/release-checklist.md 'Validation surfaces' for the split
between validate.py (static structure gate), this script (publish gate),
and doctor.py (read-only diagnostic aggregator).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import _checks

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
DSH_PKG = ROOT / "packages" / "dsh-design-playbook"
VALIDATOR = ROOT / "scripts" / "validate.py"
SEAM_TEST = PKG / "tests" / "test_validate_run.py"
PREVIEW_SERVER = PKG / "mcp" / "preview" / "server.py"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CHECK_ORDER = ("tree", "version", "validate", "seam", "adapter", "tag")
failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    failures.append(msg)


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def git(*args: str) -> str:
    result = run(["git", "-C", str(ROOT), *args])
    return result.stdout.strip() if result.returncode == 0 else ""


def read_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path.relative_to(ROOT)}: {exc}")
        return None
    if not isinstance(payload, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
        return None
    return payload


def plugin_version() -> str:
    payload = read_json(PKG / ".claude-plugin" / "plugin.json")
    if payload is None:
        return ""
    version = payload.get("version", "")
    return version if isinstance(version, str) else ""


def codex_plugin_version() -> str:
    """Version declared in the Codex dual-publish manifest (ADR-0009).

    The Codex marketplace ships its own ``.codex-plugin/plugin.json``; a bump
    that skips it leaves the Codex surface advertising a stale version. This
    is one of the 6+ version sites ``check_version`` polices (issue 07).
    """
    payload = read_json(PKG / ".codex-plugin" / "plugin.json")
    if payload is None:
        return ""
    version = payload.get("version", "")
    return version if isinstance(version, str) else ""


def npm_package_version() -> str:
    """Version declared in the npm/pi publish manifest.

    ``packages/design-playbook/package.json`` is what feeds the pi package
    gallery, which indexes npm rather than this repo. A bump that skips it
    leaves the gallery listing a stale version forever, since the gallery
    only ever sees published tarballs.
    """
    payload = read_json(PKG / "package.json")
    if payload is None:
        return ""
    version = payload.get("version", "")
    return version if isinstance(version, str) else ""


def check_tree() -> None:
    print("== 1. working tree clean ==")
    status = git("status", "--porcelain", "--untracked-files=all")
    dirty = [line for line in status.splitlines() if line]
    if not dirty:
        ok("working tree clean")
        return

    fail(f"working tree has uncommitted changes: {len(dirty)} file(s)")
    for line in dirty[:10]:
        print(f"        {line}")


def check_version() -> None:
    print("== 2. version consistency ==")
    version = plugin_version()
    codex_version = codex_plugin_version()
    npm_version = npm_package_version()
    marketplace = read_json(ROOT / ".claude-plugin" / "marketplace.json")
    if marketplace is None:
        return

    metadata = marketplace.get("metadata", {})
    plugins = marketplace.get("plugins", [])
    metadata_version = metadata.get("version", "") if isinstance(metadata, dict) else ""
    plugin_entry = plugins[0] if isinstance(plugins, list) and plugins else {}
    marketplace_version = (
        plugin_entry.get("version", "") if isinstance(plugin_entry, dict) else ""
    )

    if not SEMVER.fullmatch(version):
        fail(f"plugin.json version not semver: {version!r}")
    elif version == metadata_version == marketplace_version == codex_version == npm_version:
        ok(f"versions match across 5 manifest sites: {version}")
    else:
        fail(
            f"version mismatch: plugin.json={version!r} "
            f"marketplace.meta={metadata_version!r} "
            f"marketplace.plugin={marketplace_version!r} "
            f"codex.plugin={codex_version!r} "
            f"package.json={npm_version!r}"
        )

    release_group_errors = _checks.release_group_errors(
        read_json(PKG / "package.json"),
        read_json(DSH_PKG / "package.json"),
    )
    if release_group_errors:
        for message in release_group_errors:
            fail(message)
    else:
        ok(f"npm release group versions match: {npm_version}")

    badge_re = re.compile(r"badge/Version-(\d+\.\d+\.\d+)-")
    for relative in ("README.md", "README-zh.md"):
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"cannot read {relative}: {exc}")
            continue
        match = badge_re.search(text)
        if not match:
            fail(f"{relative}: no Version badge found")
        elif match.group(1) != version:
            fail(f"{relative}: Version badge {match.group(1)} != plugin.json {version}")
        else:
            ok(f"{relative} Version badge matches: {match.group(1)}")

    if not SEMVER.fullmatch(version):
        return
    tag = f"v{version}"
    relative = Path("docs") / "releases" / f"{tag}.md"
    release_notes = ROOT / relative
    try:
        notes = release_notes.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"{relative.as_posix()}: release notes unavailable: {exc}")
        return
    heading = re.compile(rf"^#\s+{re.escape(tag)}(?:\s|$)", re.MULTILINE)
    if not heading.search(notes):
        fail(f"{relative.as_posix()}: title must identify {tag}")
    else:
        ok(f"{relative.as_posix()} matches version {version}")


def check_validate() -> None:
    print("== 3. scripts/validate.py ==")
    result = run([sys.executable, str(VALIDATOR)])
    if result.returncode == 0 and "VALIDATION PASSED" in result.stdout:
        ok("validate.py PASSED")
        return
    fail(f"validate.py failed (exit {result.returncode})")
    print(result.stdout[-600:])


def check_seam() -> None:
    print("== 4. seam test (test_validate_run.py) ==")
    result = run([sys.executable, str(SEAM_TEST)])
    if result.returncode == 0 and "SEAM TEST PASSED" in result.stdout:
        ok("SEAM TEST PASSED")
        return
    fail(f"seam test failed (exit {result.returncode})")
    print(result.stdout[-800:])


def check_adapter() -> None:
    print("== 5. adapter floor self-check ==")
    result = run([sys.executable, str(PREVIEW_SERVER), "--self-check"])
    if result.returncode == 0 and "FLOOR SELF-CHECK PASSED" in result.stdout:
        ok("FLOOR SELF-CHECK PASSED")
        return
    fail(f"adapter self-check failed (exit {result.returncode})")
    print(result.stdout[-400:])


def check_tag(*, apply: bool) -> str:
    print("== 6. tag ==")
    version = plugin_version()
    if not SEMVER.fullmatch(version):
        fail(f"cannot check tag: invalid plugin version {version!r}")
        return ""

    tag = f"v{version}"
    tag_commit = git("rev-list", "-n", "1", tag)
    head = git("rev-parse", "HEAD")
    if tag_commit:
        if tag_commit == head:
            ok(f"tag {tag} already points at HEAD")
        else:
            fail(f"tag {tag} points at {tag_commit[:12]}, not HEAD {head[:12]}")
        return tag

    if not apply:
        ok(f"tag {tag} not present (dry-run; pass --apply to create)")
        return tag

    if failures:
        fail(f"refusing to create tag {tag}: "
             f"{len(failures)} earlier gate failure(s)")
        return tag

    result = run(["git", "-C", str(ROOT), "tag", tag])
    if result.returncode == 0:
        ok(f"created tag {tag}")
    else:
        fail(f"git tag {tag} failed: {result.stderr.strip()}")
    return tag


def parse_checks(value: str) -> tuple[str, ...]:
    requested = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = sorted(set(requested) - set(CHECK_ORDER))
    if unknown:
        choices = ",".join(CHECK_ORDER)
        raise argparse.ArgumentTypeError(
            f"unknown check(s): {','.join(unknown)}; choose from {choices}"
        )
    if not requested:
        raise argparse.ArgumentTypeError("at least one check is required")
    requested_set = set(requested)
    return tuple(name for name in CHECK_ORDER if name in requested_set)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="create the git tag after selected checks pass (default: dry-run)",
    )
    parser.add_argument(
        "--checks",
        type=parse_checks,
        default=CHECK_ORDER,
        metavar="NAMES",
        help=f"comma-separated checks (default: {','.join(CHECK_ORDER)})",
    )
    args = parser.parse_args()

    checks = {
        "tree": check_tree,
        "version": check_version,
        "validate": check_validate,
        "seam": check_seam,
        "adapter": check_adapter,
    }
    tag = f"v{plugin_version()}"
    for name in args.checks:
        if name == "tag":
            tag = check_tag(apply=args.apply)
        else:
            checks[name]()

    print()
    print("== next (irreversible tag push) ==")
    print(f"  - git push --atomic origin main {tag}  (after --apply)")
    print("  - Actions: publish design-playbook -> publish dsh-design-playbook "
          "-> verify both -> shared GitHub Release")
    print(f"  - DSH artifact recovery: gh workflow run release-dsh-bundle.yml "
          f"--ref {tag} -f tag={tag} -f recovery=true")
    print(f"  - shared Release recovery: gh workflow run release.yml --ref {tag} "
          f"-f tag={tag} -f recovery=true")
    print("  - 2nd-session install smoke (release-checklist gate 5)")

    print()
    if failures:
        print(f"RELEASE GATE FAILED: {len(failures)} issue(s)")
        return 1
    suffix = " (dry-run; --apply to tag)" if not args.apply else ""
    print(f"RELEASE GATE PASSED{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
