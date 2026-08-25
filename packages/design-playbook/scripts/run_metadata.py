"""Safe, immutable package and selected-run metadata projections."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Availability = Literal["known", "unknown"]
MetadataReason = Literal[
    "source-missing",
    "source-unreadable",
    "source-malformed",
]

_PACKAGE_NAME = "design-playbook"
_STABLE_SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")


class SelectedRunSelectionError(ValueError):
    """Fixed path-free failure for an invalid session selection."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class LimitationProjectionError(ValueError):
    """Fixed error for an invalid closed limitation request."""

    def __init__(self) -> None:
        super().__init__("limitation-input-invalid")


@dataclass(frozen=True)
class PackageIdentity:
    """Installed Design Playbook package identity."""

    name: str
    version: str


@dataclass(frozen=True)
class PackageMetadataProjection:
    """Package identity or an explicit typed non-known result."""

    availability: Availability
    value: PackageIdentity | None
    reason: MetadataReason | None


@dataclass(frozen=True)
class RunIdentity:
    """Opaque session identity for exactly one selected run."""

    run_id: str
    label: None = None


@dataclass(frozen=True)
class Limitation:
    """Closed owner/build limitation safe for Snapshot projection."""

    code: str
    summary: str
    affects_assertion_ids: tuple[str, ...]


_DISABLED_CAPABILITY_LIMITATIONS = (
    Limitation(
        code="role-attestation-owner-unmapped",
        summary=(
            "Role attestation is unavailable until an existing owner is mapped."
        ),
        affects_assertion_ids=(),
    ),
    Limitation(
        code="diagnostic-export-contract-unavailable",
        summary=(
            "Diagnostic export is unavailable until its contract is accepted."
        ),
        affects_assertion_ids=(),
    ),
)


def project_package_metadata(package_root: Path) -> PackageMetadataProjection:
    """Read package identity from the installed Claude plugin manifest."""
    manifest = package_root / ".claude-plugin" / "plugin.json"
    if not manifest.is_file():
        return PackageMetadataProjection(
            availability="unknown",
            value=None,
            reason="source-missing",
        )
    try:
        manifest_text = manifest.read_text(encoding="utf-8")
    except OSError:
        return PackageMetadataProjection(
            availability="unknown",
            value=None,
            reason="source-unreadable",
        )
    try:
        payload = json.loads(manifest_text)
    except json.JSONDecodeError:
        return PackageMetadataProjection(
            availability="unknown",
            value=None,
            reason="source-malformed",
        )
    if not isinstance(payload, dict):
        return PackageMetadataProjection(
            availability="unknown",
            value=None,
            reason="source-malformed",
        )
    name = payload.get("name")
    version = payload.get("version")
    if name != _PACKAGE_NAME or not (
        isinstance(version, str) and _STABLE_SEMVER.fullmatch(version)
    ):
        return PackageMetadataProjection(
            availability="unknown",
            value=None,
            reason="source-malformed",
        )
    return PackageMetadataProjection(
        availability="known",
        value=PackageIdentity(
            name=name,
            version=version,
        ),
        reason=None,
    )


def project_selected_run(selected_root: Path, session_secret: bytes) -> RunIdentity:
    """Create a path-free identity bound to this session and selected root."""
    if not isinstance(session_secret, bytes) or not session_secret:
        raise SelectedRunSelectionError("session-secret-invalid")
    try:
        canonical_root = selected_root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise SelectedRunSelectionError("selected-run-invalid") from None
    if not canonical_root.is_dir():
        raise SelectedRunSelectionError("selected-run-invalid")
    digest = hmac.new(
        session_secret,
        str(canonical_root).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return RunIdentity(run_id=f"run_{digest}")


def project_limitations(
    *,
    owner_unmapped_assertion_ids: tuple[str, ...] = (),
) -> tuple[Limitation, ...]:
    """Return closed owner/build limitations, never caller-authored prose."""
    if (
        len(set(owner_unmapped_assertion_ids))
        != len(owner_unmapped_assertion_ids)
        or any(
            not isinstance(assertion_id, str)
            or _DOMAIN_ID.fullmatch(assertion_id) is None
            for assertion_id in owner_unmapped_assertion_ids
        )
    ):
        raise LimitationProjectionError
    owner_unmapped = ()
    if owner_unmapped_assertion_ids:
        owner_unmapped = (
            Limitation(
                code="owner-unmapped",
                summary=(
                    "No existing authority owner is mapped for the affected "
                    "assertions."
                ),
                affects_assertion_ids=tuple(sorted(owner_unmapped_assertion_ids)),
            ),
        )
    return owner_unmapped + _DISABLED_CAPABILITY_LIMITATIONS
