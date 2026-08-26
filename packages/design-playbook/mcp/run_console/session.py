"""Process-owned single-run session (RCV1-006).

One explicit run root is canonicalized once; a fresh >=256-bit session
token and session secret are generated per server lifetime and live only
in process memory; the Snapshot and source-registry lifecycle and
close-time invalidation of the token and every locator are owned here.
The Snapshot is produced and resolved only through the RCV1-005 seams
(:func:`build_snapshot`, :func:`resolve_source_excerpt`); no owner logic
is reimplemented. Every operation is read-only for the run tree.
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .projection import (
    SOURCE_LOCATOR_INVALID,
    SourceExcerpt,
    SourceViewError,
    resolve_source_excerpt,
)
from .snapshot_builder import build_snapshot as _build_snapshot

RUN_ROOT_INVALID = "RUN_ROOT_INVALID"
PACKAGE_ROOT_INVALID = "PACKAGE_ROOT_INVALID"
SESSION_CLOSED = "SESSION_CLOSED"

_ERROR_MESSAGES = {
    RUN_ROOT_INVALID: "The selected run root is not an existing directory.",
    PACKAGE_ROOT_INVALID: "The package root is not an existing directory.",
    SESSION_CLOSED: "The session is closed.",
}

DEFAULT_EXCERPT_MAX_CHARS = 4000
DEFAULT_TOKEN_ENTROPY_BYTES = 32  # 256 bits, the v1 minimum


class RunConsoleSessionError(ValueError):
    """A stable, path-free session lifecycle rejection."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_MESSAGES:
            raise ValueError("unknown session error code")
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code


@dataclass(frozen=True)
class SourceView:
    """One resolved read-only source excerpt plus its authority anchor."""

    excerpt: SourceExcerpt
    anchor: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_directory(value: object, code: str) -> Path:
    if isinstance(value, str):
        value = Path(value)
    if not isinstance(value, Path):
        raise RunConsoleSessionError(code)
    try:
        canonical = value.resolve(strict=True)
    except OSError:
        raise RunConsoleSessionError(code) from None
    if not canonical.is_dir():
        raise RunConsoleSessionError(code)
    return canonical


class RunConsoleSession:
    """One process-owned session bound to exactly one selected run.

    The token is generated from fresh cryptographic entropy and never
    leaves process memory except through the one-time launch line; the
    session secret keys the run identity and the source registry. Closing
    the session invalidates the token, the registry (and therefore every
    locator), and the served document.
    """

    def __init__(
        self,
        *,
        run_root: object,
        package_root: Path | None = None,
        now_fn: Callable[[], str] | None = None,
        token_entropy_bytes: int = DEFAULT_TOKEN_ENTROPY_BYTES,
    ) -> None:
        self._run_root = _canonical_directory(run_root, RUN_ROOT_INVALID)
        if package_root is None:
            package_root = Path(__file__).resolve().parents[2]
        self._package_root = _canonical_directory(package_root, PACKAGE_ROOT_INVALID)
        if isinstance(token_entropy_bytes, bool) or not isinstance(token_entropy_bytes, int):
            raise ValueError("token_entropy_bytes must be an int")
        if token_entropy_bytes < DEFAULT_TOKEN_ENTROPY_BYTES:
            raise ValueError("token entropy must be at least 256 bits")
        if now_fn is not None and not callable(now_fn):
            raise ValueError("now_fn must be callable")
        self._now_fn = now_fn if now_fn is not None else _utc_now
        self._token: str | None = secrets.token_urlsafe(token_entropy_bytes)
        self._session_secret: bytes | None = secrets.token_bytes(32)
        # The HTTP server handles requests on independent worker threads.  A
        # snapshot and the registry that issued its locators are one logical
        # value, so lifecycle transitions must be serialized at this seam.
        self._state_lock = threading.RLock()
        self._closed = False
        self._built = False
        self._document: dict | None = None
        self._registry = None

    # -- identity ------------------------------------------------------

    @property
    def run_root(self) -> Path:
        """The one canonical selected run root."""
        return self._run_root

    @property
    def token(self) -> str | None:
        """The session bearer token, or ``None`` once closed."""
        with self._state_lock:
            return self._token

    @property
    def closed(self) -> bool:
        with self._state_lock:
            return self._closed

    @property
    def built(self) -> bool:
        with self._state_lock:
            return self._built

    @property
    def run_id(self) -> str | None:
        with self._state_lock:
            return self._registry.run_id if self._registry is not None else None

    @property
    def registry(self):
        """The registry that issued the served snapshot's locators."""
        with self._state_lock:
            return self._registry

    # -- lifecycle -----------------------------------------------------

    def build_snapshot(self) -> dict:
        """Build the snapshot once and keep serving that document.

        A closed session raises; a failed build raises the typed
        :class:`SnapshotBuildError` and never installs a document, so no
        older snapshot can be served as current.
        """
        with self._state_lock:
            if self._closed:
                raise RunConsoleSessionError(SESSION_CLOSED)
            if self._built:
                document = self._document
                if document is None:  # pragma: no cover - invariant
                    raise RunConsoleSessionError(SESSION_CLOSED)
                return document
            assert self._session_secret is not None
            built = _build_snapshot(
                selected_root=self._run_root,
                package_root=self._package_root,
                session_secret=self._session_secret,
                now=self._now_fn(),
            )
            # Publish the document and the registry while holding the same
            # lock.  Readers can therefore never observe a mixed pair.
            self._registry = built.registry
            self._document = built.document
            self._built = True
            return built.document

    def invalidate_snapshot_cache(self) -> None:
        """Drop the cached snapshot so the next build is a full rebuild.

        The token, identity, and closed flag are untouched. The rebuild
        itself re-runs through ``build_snapshot``: if it fails, no new
        document is installed, so the prior snapshot is never served as
        current afterwards (the typed refresh action, RCV1-009).
        """
        with self._state_lock:
            self._built = False
            self._document = None
            self._registry = None

    def rebuild_snapshot(self) -> dict:
        """Invalidate and rebuild as one serialized lifecycle transition."""
        with self._state_lock:
            if self._closed:
                raise RunConsoleSessionError(SESSION_CLOSED)
            self._built = False
            self._document = None
            self._registry = None
            # Keep this call indirect so callers/tests that replace the
            # public build seam still observe the rebuild attempt.
            return self.build_snapshot()

    def resolve_source(
        self, locator: object, *, max_chars: int = DEFAULT_EXCERPT_MAX_CHARS
    ) -> SourceView:
        """Resolve one opaque locator through the RCV1-005 seam.

        Every invalid, expired, cross-session, or cross-run locator is the
        uniform typed rejection; a changed source is the typed hash
        mismatch. No path or locator detail crosses the seam.
        """
        with self._state_lock:
            if self._closed:
                raise RunConsoleSessionError(SESSION_CLOSED)
            registry = self._registry
            if not self._built or registry is None:
                # No snapshot has been built, so no locator can be valid.
                raise SourceViewError(SOURCE_LOCATOR_INVALID)
            now = self._now_fn()
            binding = registry.lookup_locator(locator, now)
            excerpt = resolve_source_excerpt(
                registry=registry,
                package_root=self._package_root,
                locator=locator,
                now=now,
                max_chars=max_chars,
            )
            return SourceView(
                excerpt=excerpt, anchor=binding.anchor if binding else None
            )

    def close(self) -> None:
        """Invalidate the token and every locator; drop the document."""
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._token = None
            self._session_secret = None
            self._registry = None
            self._document = None
            self._built = False
