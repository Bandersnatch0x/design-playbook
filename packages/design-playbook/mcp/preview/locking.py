"""Preview lock machinery: the per-round lock and the directory lease.

Two policies share one shape: an owner token on disk, a heartbeat that proves the
holder is alive, and a stale takeover that must not silently adopt another
request. The per-round lock binds the decision digest; the directory lease adds an
OS-backed transition fence so a crashed holder cannot delete a replacement lease.
"""
from __future__ import annotations

import errno
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from design_playbook.mcp.preview.entry_io import atomic_write
from design_playbook.mcp.preview.transaction_errors import (
    DirectoryLockError,
    PreviewTransactionError,
    TransactionConflict,
)

LOCK_HEARTBEAT_SECONDS = 30
LOCK_STALE_SECONDS = LOCK_HEARTBEAT_SECONDS * 3
DIRECTORY_LOCK_TIMEOUT_SECONDS = 5.0
DIRECTORY_LOCK_STALE_SECONDS = 30.0
DIRECTORY_LOCK_HEARTBEAT_SECONDS = 10.0
DIRECTORY_LOCK_POLL_SECONDS = 0.01
PROJECTION_LOCK_NAME = ".preview-projection.lock"

def _lock_metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}

def _claim_stale_lock(
    path: Path, *, binding_digest: str, round_n: int, decision_id: str,
) -> None:
    """Serialize stale takeover so one recoverer cannot delete another's lock."""
    guard = path.with_suffix(path.suffix + ".recovery")
    try:
        fd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PreviewTransactionError(
            f"Preview round {round_n} recovery is already active",
            retryable=True, round_n=round_n, decision_id=decision_id,
            artifact=str(guard),
        ) from exc
    os.close(fd)
    try:
        existing = _lock_metadata(path)
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return
        if age < LOCK_STALE_SECONDS:
            raise PreviewTransactionError(
                f"Preview round {round_n} is already active",
                retryable=True, round_n=round_n,
                decision_id=str(existing.get("decision_id") or decision_id),
                artifact=str(path),
            )
        if existing.get("binding_digest") != binding_digest:
            raise TransactionConflict(
                f"stale lock binding differs; use next round: {round_n}",
                retryable=False, round_n=round_n,
                decision_id=str(existing.get("decision_id") or decision_id),
                artifact=str(path),
            )
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    finally:
        try:
            guard.unlink()
        except FileNotFoundError:
            pass

def _lock_owner(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""

def _try_lock_guard(guard: Path) -> BinaryIO | None:
    """Try an OS-backed transition lock that the kernel releases on crash."""
    handle = guard.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return None
            raise
        return handle
    except BaseException as exc:
        if not handle.closed:
            handle.close()
        if isinstance(exc, OSError) and exc.errno in {
            errno.EACCES, errno.EAGAIN,
        }:
            return None
        raise

def _release_lock_guard(handle: BinaryIO) -> None:
    try:
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()

def _directory_lock_is_stale(path: Path, stale_seconds: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime >= stale_seconds
    except FileNotFoundError:
        return False

def _try_acquire_directory_lease(
    path: Path, owner_id: str, stale_seconds: float,
) -> BinaryIO | None:
    """Acquire a lease and retain its OS fence for the full critical section."""
    guard = path.with_suffix(path.suffix + ".recovery")
    guard_handle = _try_lock_guard(guard)
    if guard_handle is None:
        return None
    try:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not _directory_lock_is_stale(path, stale_seconds):
                _release_lock_guard(guard_handle)
                return None
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            try:
                fd = os.open(
                    path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                _release_lock_guard(guard_handle)
                return None
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
                fh.write(owner_id)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            raise
        return guard_handle
    except BaseException:
        if not guard_handle.closed:
            _release_lock_guard(guard_handle)
        raise

@contextmanager
def directory_lock(
    preview_dir: Path,
    lock_name: str,
    *,
    timeout_seconds: float | None = None,
    stale_seconds: float | None = None,
    heartbeat_seconds: float | None = None,
    poll_seconds: float | None = None,
) -> Iterator[None]:
    """Hold an OS-fenced, heartbeat-backed Preview directory lease."""
    timeout = (
        DIRECTORY_LOCK_TIMEOUT_SECONDS
        if timeout_seconds is None else timeout_seconds
    )
    stale = (
        DIRECTORY_LOCK_STALE_SECONDS
        if stale_seconds is None else stale_seconds
    )
    heartbeat_interval = (
        DIRECTORY_LOCK_HEARTBEAT_SECONDS
        if heartbeat_seconds is None else heartbeat_seconds
    )
    poll = DIRECTORY_LOCK_POLL_SECONDS if poll_seconds is None else poll_seconds
    preview_dir.mkdir(parents=True, exist_ok=True)
    path = preview_dir / lock_name
    owner_id = uuid.uuid4().hex
    deadline = time.monotonic() + timeout

    guard_handle = _try_acquire_directory_lease(path, owner_id, stale)
    while guard_handle is None:
        if time.monotonic() >= deadline:
            raise DirectoryLockError(f"directory lock timed out: {path}")
        time.sleep(poll)
        guard_handle = _try_acquire_directory_lease(path, owner_id, stale)

    stopped = threading.Event()
    heartbeat_errors: list[DirectoryLockError] = []

    def heartbeat() -> None:
        while not stopped.wait(heartbeat_interval):
            if _lock_owner(path) != owner_id:
                heartbeat_errors.append(DirectoryLockError(
                    f"directory lock ownership lost: {path}"))
                return
            try:
                os.utime(path, None)
            except OSError as exc:
                heartbeat_errors.append(DirectoryLockError(
                    f"directory lock heartbeat failed: {path}: {exc}"))
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    body_error: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        stopped.set()
        thread.join(timeout=1)
        lease_error = heartbeat_errors[0] if heartbeat_errors else None
        guard = path.with_suffix(path.suffix + ".recovery")
        try:
            if _lock_owner(path) != owner_id:
                lease_error = lease_error or DirectoryLockError(
                    f"directory lock ownership lost: {path}")
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    lease_error = lease_error or DirectoryLockError(
                        f"directory lock ownership lost: {path}")
        finally:
            try:
                _release_lock_guard(guard_handle)
            except OSError as exc:
                lease_error = lease_error or DirectoryLockError(
                    f"directory lock guard cleanup failed: {guard}: {exc}")
        if lease_error is not None:
            if body_error is None:
                raise lease_error
            body_error.add_note(str(lease_error))

@contextmanager
def _round_lock(
    preview_dir: Path, *, round_n: int, binding_digest: str, decision_id: str,
) -> Iterator[None]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    path = preview_dir / f"decision-round-{round_n}.lock"
    owner_id = uuid.uuid4().hex
    metadata = {
        "owner_id": owner_id,
        "decision_id": decision_id,
        "binding_digest": binding_digest,
        "heartbeat": time.time(),
    }
    raw = json.dumps(metadata, sort_keys=True)
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            _claim_stale_lock(
                path, binding_digest=binding_digest,
                round_n=round_n, decision_id=decision_id,
            )
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(raw)
                fh.flush()
            break

    stopped = threading.Event()
    heartbeat_errors: list[OSError] = []

    def heartbeat() -> None:
        while not stopped.wait(LOCK_HEARTBEAT_SECONDS):
            current = _lock_metadata(path)
            if current.get("owner_id") != owner_id:
                return
            metadata["heartbeat"] = time.time()
            try:
                atomic_write(path, json.dumps(metadata, sort_keys=True))
            except OSError as exc:
                heartbeat_errors.append(exc)
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
        if heartbeat_errors:
            raise PreviewTransactionError(
                f"Preview lock heartbeat failed: {heartbeat_errors[0]}",
                retryable=True, round_n=round_n, decision_id=decision_id,
                artifact=str(path),
            )
    finally:
        stopped.set()
        thread.join(timeout=1)
        if _lock_metadata(path).get("owner_id") == owner_id:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
