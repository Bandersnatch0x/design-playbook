#!/usr/bin/env python3
"""Validate the public state transitions of the release workflow."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


class ReleaseStateError(ValueError):
    """Raised when an irreversible release transition is not allowed."""


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def release_mode(event_name: str, recovery: bool) -> str:
    """Return the only allowed entry point for the release transaction."""
    if event_name == "push" and not recovery:
        return "publish"
    if event_name == "workflow_dispatch" and recovery:
        return "recovery"
    raise ReleaseStateError(
        "workflow_dispatch is recovery-only; tag pushes cannot request recovery"
    )


def release_action(
    *,
    event_name: str,
    recovery: bool,
    npm_exists: bool,
    github_release_exists: bool,
) -> str:
    """Validate the pre-publish state and return publish or recover."""
    mode = release_mode(event_name, recovery)
    if mode == "publish":
        if npm_exists:
            raise ReleaseStateError("unexpected registry collision: npm version already exists")
        if github_release_exists:
            raise ReleaseStateError(
                "GitHub Release already exists before npm publication"
            )
        return "publish"

    if not npm_exists:
        raise ReleaseStateError("recovery requested but npm version is absent")
    if github_release_exists:
        raise ReleaseStateError(
            "recovery requires a missing GitHub Release; it already exists"
        )
    return "recover"


def package_release_action(
    *,
    event_name: str,
    recovery: bool,
    npm_exists: bool,
) -> str:
    """Validate a package-only publish and return publish or verify."""
    mode = release_mode(event_name, recovery)
    if mode == "publish":
        if npm_exists:
            raise ReleaseStateError("unexpected registry collision: npm version already exists")
        return "publish"

    if not npm_exists:
        raise ReleaseStateError("recovery requested but npm version is absent")
    return "verify"


def require_verified_provenance(
    payload: dict[str, Any], *, package_name: str, version: str
) -> None:
    """Require npm audit signatures to verify this exact package's attestation."""
    for entry in payload.get("verified", []):
        if (
            entry.get("name") == package_name
            and entry.get("version") == version
            and entry.get("attestations")
        ):
            return
    raise ReleaseStateError(
        f"npm provenance attestation is not verified for {package_name}@{version}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    mode = subparsers.add_parser("mode")
    mode.add_argument("--event-name", required=True)
    mode.add_argument("--recovery", required=True, type=parse_bool)

    state = subparsers.add_parser("state")
    state.add_argument("--event-name", required=True)
    state.add_argument("--recovery", required=True, type=parse_bool)
    state.add_argument("--npm-exists", required=True, type=parse_bool)
    state.add_argument("--github-release-exists", required=True, type=parse_bool)

    package_state = subparsers.add_parser("package-state")
    package_state.add_argument("--event-name", required=True)
    package_state.add_argument("--recovery", required=True, type=parse_bool)
    package_state.add_argument("--npm-exists", required=True, type=parse_bool)

    provenance = subparsers.add_parser("provenance")
    provenance.add_argument("--package-name", required=True)
    provenance.add_argument("--version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "mode":
            print(f"mode={release_mode(args.event_name, args.recovery)}")
        elif args.command == "state":
            print(
                "action="
                + release_action(
                    event_name=args.event_name,
                    recovery=args.recovery,
                    npm_exists=args.npm_exists,
                    github_release_exists=args.github_release_exists,
                )
            )
        elif args.command == "package-state":
            print(
                "action="
                + package_release_action(
                    event_name=args.event_name,
                    recovery=args.recovery,
                    npm_exists=args.npm_exists,
                )
            )
        else:
            payload = json.load(sys.stdin)
            require_verified_provenance(
                payload, package_name=args.package_name, version=args.version
            )
            print(f"verified provenance for {args.package_name}@{args.version}")
    except (ReleaseStateError, json.JSONDecodeError) as exc:
        print(f"release state error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
