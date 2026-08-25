"""Source-bound logical Source registry for the read-only Run Console.

One selected canonical run root yields exactly the fixed fifteen logical
Source registry keys from the Run Snapshot v1 parity specification
(section 2).  The registry is constructed server-side from the selection
argument alone:

- no run file byte is read during construction;
- the table is fixed: browser-shaped input can never add a source or a
  capture target, and no registration API exists;
- locators are random opaque ``src_`` tokens bound server-side to the
  session, the one selected run, one allowlisted logical source (and one
  canonical contained capture target), an optional semantic anchor, and
  the observed source hash.

Locators expire, are invalid in any other session or run, and lookup of
malformed or unknown tokens is uniformly ``None``.  Errors are stable,
path-free values.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from design_playbook.scripts.run_metadata import (
    SelectedRunSelectionError,
    project_selected_run,
)

SELECTED_RUN_INVALID = "selected-run-invalid"
LOCATOR_INPUT_INVALID = "locator-input-invalid"

DEFAULT_LOCATOR_TTL_SECONDS = 900
_LOCATOR_TTL_MAX_SECONDS = 86400
_LOCATOR_BODY_BYTES = 18  # 24 url-safe characters of fresh entropy

_ERROR_MESSAGES = {
    SELECTED_RUN_INVALID: "The selected run selection is invalid.",
    LOCATOR_INPUT_INVALID: "The locator request input is invalid.",
}

# Parity specification section 2: locator classes are logical allowlist
# classes, never paths; ``non-viewable`` always has a null locator.
_LOCATOR_PATTERN = re.compile(r"^src_[A-Za-z0-9_-]{16,}$")
_SOURCE_REF_PATTERN = re.compile(
    r"^source\.[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$"
)
_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$"
)
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ANCHOR_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,64}$")
# Evidence artifacts are criterion-anchored files under ``evidence/`` (the
# Manifest owner's convention, e.g. ``L6.3-error.png``); the grammar keeps
# slug <-> name round-trips exact and rejects path/encoding shapes.
_ARTIFACT_NAME_PATTERN = re.compile(r"^L6\.[0-9]+(-[A-Za-z0-9]+)+\.[A-Za-z0-9]+$")
_ARTIFACT_SLUG_PATTERN = re.compile(r"^l6-[0-9]+(-[a-z0-9]+){2,}$")
_EVIDENCE_ARTIFACT_REF_PREFIX = "source.evidence-artifact."

_RUN_FACTS_CAPTURE_TARGETS = (
    "spec.md",
    "01-spec.md",
    "point-back.md",
    "plan.md",
    "preview/",
    "evidence/",
    "design-baseline/state.json",
    "decision-report.md",
    "shaping/shaping-log.jsonl",
    "craft-guard.md",
)


@dataclass(frozen=True)
class RegisteredSource:
    """One fixed logical Source registration (allowlist row)."""

    key: str
    source_ref: str | None
    authority_key: str
    kind: str
    locator_class: str
    capture_targets: tuple[str, ...]
    root_scope: str
    viewable: bool
    mapped: bool
    anchored: bool


@dataclass(frozen=True)
class LocatorBinding:
    """Server-side binding of one opaque locator token."""

    locator: str
    session_id: str
    run_id: str
    source_ref: str
    authority_key: str
    kind: str
    locator_class: str
    target: str | None
    anchor: str | None
    expected_hash: str
    issued_at: str
    expires_at: str


def _source(
    key: str,
    source_ref: str,
    kind: str,
    locator_class: str,
    capture_targets: tuple[str, ...],
    *,
    root_scope: str = "run-root",
    anchored: bool = True,
) -> RegisteredSource:
    return RegisteredSource(
        key=key,
        source_ref=source_ref,
        authority_key=key,
        kind=kind,
        locator_class=locator_class,
        capture_targets=capture_targets,
        root_scope=root_scope,
        viewable=locator_class != "non-viewable",
        mapped=True,
        anchored=anchored,
    )


def _gate(
    key: str,
    kind: str = "authority-record",
) -> RegisteredSource:
    return RegisteredSource(
        key=key,
        source_ref=None,
        authority_key=key,
        kind=kind,
        locator_class="non-viewable",
        capture_targets=(),
        root_scope="run-root",
        viewable=False,
        mapped=False,
        anchored=False,
    )


_FIXED_SOURCES: tuple[RegisteredSource, ...] = (
    _source(
        "session.selected-run",
        "source.selected-run",
        "session-selection",
        "session-selection-summary",
        (),
        anchored=False,
    ),
    _source(
        "package.metadata",
        "source.package-metadata",
        "package",
        "package-summary",
        (".claude-plugin/plugin.json",),
        root_scope="package-root",
        anchored=False,
    ),
    _source(
        "run.profile",
        "source.run-profile",
        "authority-record",
        "authority-record-excerpt",
        ("plan.md",),
    ),
    _source(
        "intent.specification",
        "source.specification",
        "artifact",
        "artifact-excerpt",
        ("spec.md", "01-spec.md"),
    ),
    _source(
        "intent.contract",
        "source.contract-bind",
        "authority-record",
        "authority-record-excerpt",
        ("contract-bind.json",),
    ),
    _source(
        "execution.stage-registry",
        "source.run-facts",
        "authority-record",
        "authority-record-excerpt",
        _RUN_FACTS_CAPTURE_TARGETS,
    ),
    _source(
        "execution.preview",
        "source.preview",
        "authority-record",
        "authority-record-excerpt",
        ("preview/",),
    ),
    _source(
        "execution.repair",
        "source.repair-report",
        "artifact",
        "artifact-excerpt",
        ("point-back.md",),
    ),
    _source(
        "evaluation.evaluator",
        "source.evaluator-report",
        "artifact",
        "artifact-excerpt",
        ("point-back.md",),
    ),
    _source(
        "evaluation.ledger",
        "source.evidence-ledger",
        "artifact",
        "artifact-excerpt",
        ("point-back.md",),
    ),
    _source(
        "evaluation.manifest",
        "source.evidence-manifest",
        "authority-record",
        "authority-record-excerpt",
        ("evidence/manifest.jsonl",),
    ),
    _source(
        "run.next-action",
        "source.run-status",
        "authority-record",
        "authority-record-excerpt",
        _RUN_FACTS_CAPTURE_TARGETS + ("contract-bind.json",),
    ),
    _source(
        "run.limitations",
        "source.owner-limitations.run-metadata",
        "authority-record",
        "non-viewable",
        (),
        anchored=False,
    ),
    _gate("role-attestation.owner"),
    _gate("diagnostic-export"),
)

_SOURCES_BY_KEY = {source.key: source for source in _FIXED_SOURCES}
_SOURCES_BY_REF = {
    source.source_ref: source
    for source in _FIXED_SOURCES
    if source.source_ref is not None
}


class SourceRegistryError(ValueError):
    """A stable, path-free registry failure with a safe fixed message."""

    def __init__(self, code: str) -> None:
        super().__init__(_ERROR_MESSAGES.get(code, code))
        self.code = code


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def _artifact_slug(name: str) -> str:
    return name.lower().replace(".", "-")


def _artifact_name_from_slug(slug: str) -> str:
    parts = slug.split("-")
    return f"L6.{parts[1]}-{'-'.join(parts[2:-1])}.{parts[-1]}"


def _is_lexically_contained(relpath: str) -> bool:
    """True iff the relpath is a plain contained relative POSIX path."""
    if relpath in ("", ".", "..") or "\\" in relpath or relpath.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", relpath) or ":" in relpath:
        return False
    if "%" in relpath or "\x00" in relpath:
        return False
    parts = relpath.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def _require_contained_target(relpath: str) -> None:
    """Reject any path-shaped, encoded, or escaping target uniformly."""
    if not isinstance(relpath, str):
        raise TypeError("capture target must be a string")
    if not _is_lexically_contained(relpath):
        raise SourceRegistryError(LOCATOR_INPUT_INVALID)


def _target_allowed(relpath: str, source: RegisteredSource) -> bool:
    for target in source.capture_targets:
        if target.endswith("/"):
            if relpath.startswith(target):
                return True
        elif relpath == target:
            return True
    return False


class SourceRegistry:
    """Immutable allowlist of the fifteen logical Sources for one run.

    Constructed only through :func:`select_source_registry`; there is no
    source-registration surface, and every lookup of an unknown key, ref,
    or locator fails closed.
    """

    def __init__(
        self,
        *,
        selected_root: Path,
        package_root: Path,
        run_id: str,
        session_id: str,
    ) -> None:
        self._selected_root = selected_root
        self._package_root = package_root
        self._run_id = run_id
        self._session_id = session_id
        self._bindings: dict[str, LocatorBinding] = {}

    # -- identity -----------------------------------------------------

    @property
    def selected_root(self) -> Path:
        return self._selected_root

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def session_id(self) -> str:
        return self._session_id

    # -- fixed table --------------------------------------------------

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(source.key for source in _FIXED_SOURCES)

    @property
    def sources(self) -> tuple[RegisteredSource, ...]:
        return _FIXED_SOURCES

    @property
    def mapped_sources(self) -> tuple[RegisteredSource, ...]:
        return tuple(source for source in _FIXED_SOURCES if source.mapped)

    @property
    def viewable_sources(self) -> tuple[RegisteredSource, ...]:
        return tuple(source for source in _FIXED_SOURCES if source.viewable)

    def source(self, key: str) -> RegisteredSource:
        if not isinstance(key, str) or key not in _SOURCES_BY_KEY:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        return _SOURCES_BY_KEY[key]

    def source_by_ref(self, ref: str) -> RegisteredSource:
        if not isinstance(ref, str) or ref not in _SOURCES_BY_REF:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        return _SOURCES_BY_REF[ref]

    def allows_target(self, relpath: str) -> bool:
        """True iff a lexically contained relpath is allowlisted.

        A pure predicate: traversal, absolute, encoded, and drive-letter
        strings are simply not allowlisted (``False``); only a non-string
        browser payload fails loudly.  Issuance and resolution enforce
        containment structurally on top of this table.
        """
        if not isinstance(relpath, str):
            raise TypeError("capture target must be a string")
        if not _is_lexically_contained(relpath):
            return False
        return any(
            _target_allowed(relpath, source) for source in _FIXED_SOURCES
        )

    # -- derived evidence-artifact sources ----------------------------

    def derive_evidence_artifact_source(self, name: str) -> RegisteredSource:
        """Derive the allowlisted source for one contained artifact.

        The artifact name must be a criterion-anchored evidence file name
        (``L6.<n>-<words>.<ext>``); the derived record never extends the
        fixed registry and is stable for equal names.
        """
        if not isinstance(name, str):
            raise TypeError("artifact name must be a string")
        if _ARTIFACT_NAME_PATTERN.fullmatch(name) is None:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        slug = _artifact_slug(name)
        if _ARTIFACT_SLUG_PATTERN.fullmatch(slug) is None:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        canonical = _artifact_name_from_slug(slug)
        return RegisteredSource(
            key="evaluation.manifest",
            source_ref=f"{_EVIDENCE_ARTIFACT_REF_PREFIX}{slug}",
            authority_key="evaluation.manifest",
            kind="artifact",
            locator_class="artifact-excerpt",
            capture_targets=(f"evidence/{canonical}",),
            root_scope="run-root",
            viewable=True,
            mapped=True,
            anchored=True,
        )

    # -- locators -----------------------------------------------------

    def _resolve_issuable_source(self, ref: object) -> RegisteredSource:
        if not isinstance(ref, str) or _SOURCE_REF_PATTERN.fullmatch(ref) is None:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if ref in _SOURCES_BY_REF:
            source = _SOURCES_BY_REF[ref]
        elif ref.startswith(_EVIDENCE_ARTIFACT_REF_PREFIX):
            slug = ref[len(_EVIDENCE_ARTIFACT_REF_PREFIX):]
            if _ARTIFACT_SLUG_PATTERN.fullmatch(slug) is None:
                raise SourceRegistryError(LOCATOR_INPUT_INVALID)
            source = self.derive_evidence_artifact_source(
                _artifact_name_from_slug(slug)
            )
        else:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if not source.viewable:
            # Gate and non-viewable keys can never hold a locator.
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        return source

    def issue_locator(
        self,
        *,
        source_ref: str,
        expected_hash: str,
        now: str,
        target: str | None = None,
        anchor: str | None = None,
        ttl_seconds: int = DEFAULT_LOCATOR_TTL_SECONDS,
    ) -> str:
        """Issue one random opaque locator bound to one allowlisted source.

        Every input is validated server-side; no caller value flows into
        the token itself.
        """
        source = self._resolve_issuable_source(source_ref)
        if not isinstance(expected_hash, str):
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if _HASH_PATTERN.fullmatch(expected_hash) is None:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if not isinstance(now, str) or _TIMESTAMP_PATTERN.fullmatch(now) is None:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if not 1 <= ttl_seconds <= _LOCATOR_TTL_MAX_SECONDS:
            raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        if target is None:
            bound_target = next(
                (
                    candidate
                    for candidate in source.capture_targets
                    if not candidate.endswith("/")
                ),
                None,
            )
        else:
            if not isinstance(target, str):
                raise SourceRegistryError(LOCATOR_INPUT_INVALID)
            _require_contained_target(target)
            if not _target_allowed(target, source):
                raise SourceRegistryError(LOCATOR_INPUT_INVALID)
            bound_target = target
        if anchor is not None:
            if not isinstance(anchor, str) or not source.anchored:
                raise SourceRegistryError(LOCATOR_INPUT_INVALID)
            if _ANCHOR_PATTERN.fullmatch(anchor) is None or ".." in anchor:
                raise SourceRegistryError(LOCATOR_INPUT_INVALID)
        issued = _parse_timestamp(now)
        expires = issued + timedelta(seconds=ttl_seconds)
        for _ in range(8):
            token = "src_" + secrets.token_urlsafe(_LOCATOR_BODY_BYTES)
            if token in self._bindings:
                continue
            self._bindings[token] = LocatorBinding(
                locator=token,
                session_id=self._session_id,
                run_id=self._run_id,
                source_ref=source.source_ref or "",
                authority_key=source.authority_key,
                kind=source.kind,
                locator_class=source.locator_class,
                target=bound_target,
                anchor=anchor,
                expected_hash=expected_hash,
                issued_at=now,
                expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            return token
        raise SourceRegistryError(LOCATOR_INPUT_INVALID)

    def lookup_locator(self, locator: object, now: str) -> LocatorBinding | None:
        """Return the live binding, or ``None`` for any invalid locator.

        Malformed, unknown, expired, cross-session, and cross-run locators
        are uniformly ``None``; no detail crosses the seam.
        """
        if not isinstance(locator, str):
            return None
        if _LOCATOR_PATTERN.fullmatch(locator) is None:
            return None
        binding = self._bindings.get(locator)
        if binding is None:
            return None
        if not isinstance(now, str) or _TIMESTAMP_PATTERN.fullmatch(now) is None:
            return None
        if _parse_timestamp(now) > _parse_timestamp(binding.expires_at):
            return None
        return binding


def select_source_registry(
    selected_root: Path,
    package_root: Path,
    session_secret: bytes,
    sources: object = None,
) -> SourceRegistry:
    """Build the fixed Source registry for one selected canonical run root.

    ``selected_root`` must be an existing directory path; the identity is
    delegated to the run-metadata owner.  ``sources`` exists only so that
    browser-shaped payloads fail loudly: any non-``None`` value is a
    ``TypeError`` and can never register a source or a target.
    """
    if sources is not None:
        raise TypeError(
            "select_source_registry() accepts no browser-supplied sources"
        )
    if not isinstance(selected_root, Path):
        raise TypeError("selected_root must be a path")
    if not isinstance(package_root, Path):
        raise TypeError("package_root must be a path")
    if not isinstance(session_secret, bytes) or not session_secret:
        raise TypeError("session_secret must be non-empty bytes")
    try:
        identity = project_selected_run(selected_root, session_secret)
    except SelectedRunSelectionError:
        raise SourceRegistryError(SELECTED_RUN_INVALID) from None
    canonical_root = selected_root.resolve(strict=True)
    session_id = (
        "sess_"
        + hmac.new(
            session_secret,
            b"run-console-source-registry/v1",
            hashlib.sha256,
        ).hexdigest()[:24]
    )
    return SourceRegistry(
        selected_root=canonical_root,
        package_root=package_root,
        run_id=identity.run_id,
        session_id=session_id,
    )
