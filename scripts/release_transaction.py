#!/usr/bin/env python3
"""Release transaction identity and bounded registry/provenance verification.

Pure identity rules live here so local release checks and GitHub Actions use
one implementation. Network and GitHub Actions remain adapters: this module
only receives package/tag facts and runs npm verification commands.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from release_state import ReleaseStateError, require_verified_provenance

STABLE_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class ReleaseTransactionError(ValueError):
    """Release identity or verification state is invalid."""


class RegistryStateError(ReleaseTransactionError):
    """Registry response was neither an exact hit nor a confirmed 404."""


@dataclass(frozen=True)
class RegistryState:
    exists: bool
    version: str | None = None


def classify_registry_result(
    *, returncode: int, stdout: str, stderr: str, version: str,
) -> RegistryState:
    """Purely classify npm view output; transport remains an adapter."""
    if returncode == 0 and stdout.strip() == version:
        return RegistryState(True, version)
    combined = f"{stdout}\n{stderr}"
    if returncode != 0 and re.search(
        r'"code"\s*:\s*"E404"|npm error code E404', combined
    ):
        return RegistryState(False)
    raise RegistryStateError(
        f"npm registry response was not an exact {version} hit or E404"
    )


def _registry_command(package: str, version: str) -> list[str]:
    return ["npm", "view", f"{package}@{version}", "version"]


def read_registry_state(package: str, version: str) -> RegistryState:
    """Read one registry state through npm and classify it centrally."""
    result = subprocess.run(
        _registry_command(package, version),
        capture_output=True, text=True, check=False,
    )
    return classify_registry_result(
        returncode=result.returncode, stdout=result.stdout,
        stderr=result.stderr, version=version,
    )


@dataclass(frozen=True)
class ReleaseIdentity:
    tag: str
    version: str
    package_name: str
    title: str = ""


def resolve_package_identity(
        *, tag: str, manifest: dict, notes_path: Path | None = None,
) -> ReleaseIdentity:
    """Validate stable tag, package manifest, and optional release notes."""
    if not isinstance(manifest, dict):
        raise ReleaseTransactionError("package manifest must be a JSON object")
    match = STABLE_TAG.fullmatch(tag)
    if match is None:
        raise ReleaseTransactionError(
            f"release tag must be stable semver vX.Y.Z: {tag}")
    version = tag[1:]
    package_version = manifest.get("version")
    package_name = manifest.get("name")
    if not isinstance(package_name, str) or not package_name:
        raise ReleaseTransactionError("package manifest has no name")
    if package_version != version:
        raise ReleaseTransactionError(
            f"tag {tag} does not match package version {package_version}")
    title = ""
    if notes_path is not None:
        if not notes_path.is_file():
            raise ReleaseTransactionError(f"release notes missing: {notes_path}")
        lines = notes_path.read_text(encoding="utf-8").splitlines()
        heading = re.compile(rf"^#\s+{re.escape(tag)}(?:\s|$)")
        if not lines or not heading.search(lines[0]):
            raise ReleaseTransactionError(
                f"release notes title must identify {tag}: {notes_path}")
        title = lines[0][2:]
    return ReleaseIdentity(tag, version, package_name, title)


def resolve_identity(
        *, tag: str, manifest: dict, head_commit: str, tag_commit: str,
        main_commit: str, recovery: bool, head_is_ancestor: bool,
        notes_path: Path | None = None,
) -> ReleaseIdentity:
    """Validate one immutable tag/package/main release identity."""
    identity = resolve_package_identity(
        tag=tag, manifest=manifest, notes_path=notes_path
    )
    if tag_commit != head_commit:
        raise ReleaseTransactionError(
            f"tag {tag} points at {tag_commit}, not checkout {head_commit}")
    if recovery:
        if not head_is_ancestor:
            raise ReleaseTransactionError(
                f"recovery tag {tag} is not contained in origin/main")
    elif head_commit != main_commit:
        raise ReleaseTransactionError(
            "normal release requires tag commit to equal origin/main")
    return identity


def _require_retry_budget(attempts: int, interval: int) -> None:
    if attempts < 1:
        raise ReleaseTransactionError("attempts must be >= 1")
    if interval < 0:
        raise ReleaseTransactionError("interval must be >= 0")


def wait_registry(
    package: str,
    version: str,
    *,
    attempts: int,
    interval: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    sleeper: Callable[[int], None] | None = None,
) -> None:
    """Wait for exact package/version visibility through injected adapters."""
    runner = runner or subprocess.run
    sleeper = sleeper or time.sleep
    _require_retry_budget(attempts, interval)
    for attempt in range(1, attempts + 1):
        result = runner(
            _registry_command(package, version),
            capture_output=True, text=True, check=False,
        )
        try:
            state = classify_registry_result(
                returncode=result.returncode, stdout=result.stdout,
                stderr=result.stderr, version=version,
            )
        except RegistryStateError:
            state = RegistryState(False)
        if state.exists:
            print(f"Verified {package}@{version} on attempt {attempt}")
            return
        if attempt < attempts:
            sleeper(interval)
    raise ReleaseTransactionError(
        f"npm registry did not expose required {package}@{version} "
        f"after {attempts} attempts")


def verify_provenance(
        package: str, version: str, *, attempts: int, interval: int,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        sleeper: Callable[[int], None] | None = None,
        make_temp: Callable[[], Path] | None = None,
        cleanup: Callable[[Path], None] | None = None,
) -> None:
    """Verify exact provenance; retry policy uses injected effect adapters."""
    _require_retry_budget(attempts, interval)
    runner = runner or subprocess.run
    sleeper = sleeper or time.sleep
    make_temp = make_temp or (
        lambda: Path(tempfile.mkdtemp(prefix="release-provenance-"))
    )
    cleanup = cleanup or (
        lambda path: shutil.rmtree(path, ignore_errors=True)
    )
    for attempt in range(1, attempts + 1):
        verify_dir = make_temp()
        try:
            install = runner(
                ["npm", "install", "--prefix", str(verify_dir),
                 "--ignore-scripts", "--no-audit", "--no-fund",
                 f"{package}@{version}"],
                capture_output=True, text=True, check=False,
            )
            if install.returncode == 0:
                audit = runner(
                    ["npm", "audit", "signatures", "--prefix", str(verify_dir),
                     "--json", "--include-attestations"],
                    capture_output=True, text=True, check=False,
                )
                if audit.returncode == 0:
                    payload = json.loads(audit.stdout)
                    if not isinstance(payload, dict):
                        raise TypeError("npm audit signatures payload must be an object")
                    try:
                        require_verified_provenance(
                            payload, package_name=package, version=version
                        )
                    except (KeyError, ReleaseStateError, TypeError):
                        pass
                    else:
                        print(
                            f"Verified provenance for {package}@{version} "
                            f"on attempt {attempt}"
                        )
                        return
        except (OSError, json.JSONDecodeError):
            pass
        finally:
            cleanup(verify_dir)
        if attempt < attempts:
            print(
                f"provenance verification attempt {attempt}/{attempts} failed "
                "(npm attestation indexing may lag)",
                file=sys.stderr,
            )
            sleeper(interval)
    raise ReleaseTransactionError(
        f"provenance verification for {package}@{version} failed "
        f"after {attempts} attempts")


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    identity = subs.add_parser("identity")
    identity.add_argument("--tag", required=True)
    identity.add_argument("--manifest", required=True, type=Path)
    identity.add_argument("--head-commit", required=True)
    identity.add_argument("--tag-commit", required=True)
    identity.add_argument("--main-commit", required=True)
    identity.add_argument("--head-is-ancestor", required=True, type=_bool)
    identity.add_argument("--recovery", required=True, type=_bool)
    identity.add_argument("--notes", type=Path)

    registry = subs.add_parser("wait-registry")
    registry.add_argument("--package", required=True)
    registry.add_argument("--version", required=True)
    registry.add_argument("--attempts", type=int, default=18)
    registry.add_argument("--interval", type=int, default=5)

    state = subs.add_parser("registry-state")
    state.add_argument("--package", required=True)
    state.add_argument("--version", required=True)

    provenance = subs.add_parser("verify-provenance")
    provenance.add_argument("--package", required=True)
    provenance.add_argument("--version", required=True)
    provenance.add_argument("--attempts", type=int, default=3)
    provenance.add_argument("--interval", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "identity":
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            identity = resolve_identity(
                tag=args.tag, manifest=manifest,
                head_commit=args.head_commit, tag_commit=args.tag_commit,
                main_commit=args.main_commit, recovery=args.recovery,
                head_is_ancestor=args.head_is_ancestor, notes_path=args.notes,
            )
            print(f"tag={identity.tag}")
            print(f"version={identity.version}")
            print(f"package_name={identity.package_name}")
            if identity.title:
                print(f"title={identity.title}")
        elif args.command == "registry-state":
            state = read_registry_state(args.package, args.version)
            print(f"exists={'true' if state.exists else 'false'}")
        elif args.command == "wait-registry":
            wait_registry(args.package, args.version,
                          attempts=args.attempts, interval=args.interval)
        else:
            verify_provenance(args.package, args.version,
                              attempts=args.attempts, interval=args.interval)
    except (OSError, ReleaseTransactionError) as exc:
        print(f"release transaction error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
