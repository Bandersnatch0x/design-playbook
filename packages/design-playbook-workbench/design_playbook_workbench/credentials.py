"""The one credential record: readable by the current OS user only (R01).

The session receipt (bootstrap secret and slash capability tokens) has to
reach the maintainer's own commands, so it is written once per service
lifetime to a private record outside any project: POSIX mode 0600, and on
Windows an explicit ACL with inheritance removed and a single grant to
the current user. The record is never served over HTTP, never placed in
the data directory's exported surface, and is deleted when the service
stops. A record that cannot be made private is a hard failure, not a
warning: an unprotected credential file is worse than no file.
"""
from __future__ import annotations

import json
import locale
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from .errors import INTERNAL_ERROR, WorkbenchError

_IS_WINDOWS = sys.platform == "win32"
_ACE_PATTERN = re.compile(r"(\S+?):\(([^)]*)\)")
_ICACLS_TIMEOUT_SECONDS = 30


def current_user_principal(environ: dict | None = None) -> str:
    """The ``DOMAIN\\user`` (or bare ``user``) principal for ACL grants."""
    env = os.environ if environ is None else environ
    user = env.get("USERNAME") or env.get("USER") or ""
    domain = env.get("USERDOMAIN") or ""
    if not user:
        raise WorkbenchError(INTERNAL_ERROR)
    return f"{domain}\\{user}" if domain else user


def _run_icacls(arguments: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["icacls", *arguments],
            capture_output=True,
            text=True,
            # icacls emits the Windows ANSI code page, even in Python UTF-8 mode.
            encoding=locale.getencoding(),
            timeout=_ICACLS_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise WorkbenchError(INTERNAL_ERROR) from None
    if completed.returncode != 0:
        raise WorkbenchError(INTERNAL_ERROR)
    return completed.stdout


def restrict_to_current_user(path: Path) -> None:
    """Make one file private to the current OS user, or fail loudly."""
    target = Path(path)
    if _IS_WINDOWS:
        principal = current_user_principal()
        _run_icacls([str(target), "/inheritance:r", "/grant:r", f"{principal}:(F)"])
        return
    os.chmod(target, 0o600)


def restrict_directory_to_current_user(path: Path) -> None:
    """Make one directory private to the current OS user, or fail loudly."""
    target = Path(path)
    if _IS_WINDOWS:
        principal = current_user_principal()
        _run_icacls(
            [str(target), "/inheritance:r", "/grant:r", f"{principal}:(OI)(CI)(F)"]
        )
        return
    os.chmod(target, 0o700)


def _aces_for(path: Path) -> list[tuple[str, str]]:
    output = _run_icacls([str(path)])
    found: list[tuple[str, str]] = []
    for line in output.splitlines():
        for principal, rights in _ACE_PATTERN.findall(line):
            found.append((principal, rights))
    return found


def is_private(path: Path) -> bool:
    """True iff no principal other than the current user holds any access."""
    target = Path(path)
    try:
        if not target.exists():
            return False
    except OSError:  # pragma: no cover - defensive
        return False
    if not _IS_WINDOWS:
        return stat.S_IMODE(os.stat(target).st_mode) == 0o600
    expected = current_user_principal().lower()
    try:
        aces = _aces_for(target)
    except WorkbenchError:
        return False
    if not aces:
        return False
    for principal, rights in aces:
        # Inherited entries (``(I)``) mean the parent still grants access.
        if "(i)" in rights.lower() and "no_inheritance" not in rights.lower():
            return False
        if principal.lower() != expected:
            return False
    return True


def write_private_json(path: Path, payload: dict) -> Path:
    """Atomically write one private JSON record under a private directory."""
    target = Path(path)
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True)
    restrict_directory_to_current_user(directory)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    handle = tempfile.NamedTemporaryFile(
        dir=str(directory), prefix=".session-", delete=False
    )
    try:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        restrict_to_current_user(Path(handle.name))
        os.replace(handle.name, target)
    except BaseException:
        handle.close()
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    restrict_to_current_user(target)
    return target


def remove_private_file(path: Path) -> None:
    """Delete the credential record; absence is success."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return
    except OSError:
        raise WorkbenchError(INTERNAL_ERROR) from None
