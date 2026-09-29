"""One process-owned workbench session (R01).

Each service start mints a fresh boot ID, session token, and one-time
bootstrap secret; the receipt (boot ID, authority, expiry) is written to
the private credential record so the maintainer's own slash entry point
can present a *restricted* capability instead of the session token. Both
kinds of credential live only in this process, so a restart invalidates
every old session and every old capability: nothing persists that could
be replayed, and no task can continue without being re-authorized.
"""
from __future__ import annotations

import secrets
import uuid
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

from .errors import UNAUTHORIZED, WorkbenchError
from .security import token_is_valid

DEFAULT_TOKEN_ENTROPY_BYTES = 32  # 256 bits
DEFAULT_SESSION_TTL_SECONDS = 12 * 3600

BROWSER_SCOPE = "session"
PROJECT_SCOPES: tuple[str, ...] = ("read", "write", "execute", "model-send")


@dataclass(frozen=True)
class Principal:
    """Who is acting, and what that credential is allowed to touch."""

    kind: str  # "browser" or "slash"
    boot_id: str
    project_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    #: A claim credential is bound to exactly one work request (R11).
    request_id: str | None = None
    capability_id: str | None = None

    @property
    def is_browser(self) -> bool:
        return self.kind == "browser"

    def allows(self, scope: str) -> bool:
        return scope in self.scopes

    def permits_project(self, project_id: str, scope: str) -> bool:
        """A browser session is not project-scoped; a capability is."""
        if not self.allows(scope):
            return False
        if self.project_id is None:
            return True
        return self.project_id == project_id

    def permits_request(self, request_id: str) -> bool:
        """A request-bound capability may act on that request only."""
        if self.request_id is None:
            return False
        return self.request_id == request_id


@dataclass
class _Capability:
    token: str
    project_id: str
    scopes: frozenset[str]
    expires_at: float
    request_id: str | None = None
    capability_id: str | None = None


def _utc_iso(epoch_seconds: float) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class WorkbenchSession:
    """The single live session authority for one running service."""

    def __init__(
        self,
        *,
        authority: str,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        entropy_bytes: int = DEFAULT_TOKEN_ENTROPY_BYTES,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise ValueError("ttl_seconds must be an int")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if isinstance(entropy_bytes, bool) or not isinstance(entropy_bytes, int):
            raise ValueError("entropy_bytes must be an int")
        if entropy_bytes < DEFAULT_TOKEN_ENTROPY_BYTES:
            raise ValueError("token entropy must be at least 256 bits")
        self._now = now_fn if now_fn is not None else time.time
        self._lock = threading.RLock()
        self._authority = authority
        self.boot_id = "boot_" + secrets.token_hex(12)
        self._token: str | None = secrets.token_urlsafe(entropy_bytes)
        self._bootstrap: str | None = secrets.token_urlsafe(entropy_bytes)
        self._started_at = self._now()
        self._expires_at = self._started_at + ttl_seconds
        self._capabilities: dict[str, _Capability] = {}
        self._closed = False

    # -- receipt -------------------------------------------------------

    @property
    def authority(self) -> str:
        return self._authority

    @property
    def token(self) -> str | None:
        with self._lock:
            return self._token

    @property
    def expires_at_iso(self) -> str:
        return _utc_iso(self._expires_at)

    @property
    def started_at_iso(self) -> str:
        return _utc_iso(self._started_at)

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def receipt(self) -> dict:
        """SessionReceipt: the secret members are written to the record file only."""
        with self._lock:
            return {
                "authority": self._authority,
                "bootId": self.boot_id,
                "startedAt": self.started_at_iso,
                "expiresAt": self.expires_at_iso,
            }

    def bootstrap_url(self) -> str:
        """The one launch URL. The secret travels in the fragment only."""
        with self._lock:
            if self._closed or self._bootstrap is None:
                raise WorkbenchError(UNAUTHORIZED)
            return f"{self._authority}/#bootstrap={self._bootstrap}"

    # -- authentication ------------------------------------------------

    def _expired(self) -> bool:
        return self._now() >= self._expires_at

    def exchange_bootstrap(self, presented: object) -> dict:
        """One-time bootstrap exchange: the only way to obtain a session token."""
        with self._lock:
            if self._closed or self._expired():
                raise WorkbenchError(UNAUTHORIZED)
            secret = self._bootstrap
            if secret is None or not token_is_valid(secret, presented):
                raise WorkbenchError(UNAUTHORIZED)
            # Consumed: a replayed bootstrap (browser reload, leaked URL,
            # back/forward replay) is rejected exactly like a wrong one.
            self._bootstrap = None
            assert self._token is not None
            return {
                "token": self._token,
                "bootId": self.boot_id,
                "authority": self._authority,
                "expiresAt": self.expires_at_iso,
                "scopes": [BROWSER_SCOPE],
            }

    def authorize_browser(self, presented: object) -> Principal:
        with self._lock:
            if self._closed or self._expired():
                raise WorkbenchError(UNAUTHORIZED)
            if not token_is_valid(self._token, presented):
                raise WorkbenchError(UNAUTHORIZED)
            return Principal(kind="browser", boot_id=self.boot_id)

    def issue_request_capability(
        self,
        *,
        project_id: str,
        scopes: Iterable[str],
        request_id: str,
        ttl_seconds: int | None = None,
    ) -> tuple[str, str]:
        """Mint a capability bound to one work request; returns (token, id)."""
        return self._issue_capability(
            project_id=project_id,
            scopes=scopes,
            ttl_seconds=ttl_seconds,
            request_id=request_id,
            with_id=True,
        )

    def issue_capability(
        self,
        *,
        project_id: str,
        scopes: Iterable[str],
        ttl_seconds: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Mint one project-scoped, action-scoped slash capability.

        A capability may additionally be bound to a single work request, so
        an Agent credential can claim that task and nothing else.
        """
        return self._issue_capability(
            project_id=project_id,
            scopes=scopes,
            ttl_seconds=ttl_seconds,
            request_id=request_id,
        )

    def _issue_capability(
        self,
        *,
        project_id: str,
        scopes: Iterable[str],
        ttl_seconds: int | None = None,
        request_id: str | None = None,
        with_id: bool = False,
    ) -> tuple[str, str]:
        requested = frozenset(scopes)
        unknown = requested - set(PROJECT_SCOPES)
        if unknown or not requested:
            raise WorkbenchError(UNAUTHORIZED)
        with self._lock:
            if self._closed or self._expired():
                raise WorkbenchError(UNAUTHORIZED)
            token = secrets.token_urlsafe(DEFAULT_TOKEN_ENTROPY_BYTES)
            deadline = self._expires_at
            if ttl_seconds is not None:
                if ttl_seconds <= 0:
                    raise WorkbenchError(UNAUTHORIZED)
                deadline = min(deadline, self._now() + ttl_seconds)
            capability_id = str(uuid.uuid4())
            self._capabilities[token] = _Capability(
                token=token,
                project_id=project_id,
                scopes=requested,
                expires_at=deadline,
                request_id=request_id,
                capability_id=capability_id,
            )
            return (token, capability_id) if with_id else (token, capability_id)[0]

    def authorize_capability(self, presented: object) -> Principal:
        with self._lock:
            if self._closed or self._expired():
                raise WorkbenchError(UNAUTHORIZED)
            if not isinstance(presented, str):
                raise WorkbenchError(UNAUTHORIZED)
            record = self._capabilities.get(presented)
            if record is None or self._now() >= record.expires_at:
                raise WorkbenchError(UNAUTHORIZED)
            return Principal(
                kind="slash",
                boot_id=self.boot_id,
                project_id=record.project_id,
                scopes=record.scopes,
                request_id=record.request_id,
                capability_id=record.capability_id,
            )

    def revoke_capabilities(self, *, project_id: str | None = None) -> None:
        """Drop capabilities; the whole set when ``project_id`` is None."""
        with self._lock:
            if project_id is None:
                self._capabilities.clear()
                return
            for token in [
                token
                for token, record in self._capabilities.items()
                if record.project_id == project_id
            ]:
                del self._capabilities[token]

    def close(self) -> None:
        """Invalidate the token, the bootstrap, and every capability."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._token = None
            self._bootstrap = None
            self._capabilities.clear()
