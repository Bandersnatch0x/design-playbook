"""Owned-Chromium lifecycle behind the ``BrowserInteraction`` seam (US-4).

Executable discovery, the centered app window on a private profile, and the
forceful window/process/profile teardown live here so the review session only
drives ``open`` / ``close``. Tests substitute one fake adapter for the whole
owned-browser lifecycle instead of patching process/profile internals.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Protocol

from design_playbook.mcp.util import log as _log


def _screen_size() -> tuple[int, int]:
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:  # noqa: BLE001
        return 1440, 900


def _browser_candidates() -> list[str]:
    found: list[str] = []
    for env in ("DPB_PREVIEW_BROWSER", "CHROME_PATH", "EDGE_PATH"):
        v = os.environ.get(env)
        if v:
            found.append(v)
    for name in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        w = shutil.which(name)
        if w:
            found.append(w)
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    rels = [
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Google", "Chrome", "Application", "chrome.exe"),
        ("Microsoft", "Edge Beta", "Application", "msedge.exe"),
    ]
    for root in roots:
        if not root:
            continue
        for rel in rels:
            found.append(str(Path(root).joinpath(*rel)))
    out: list[str] = []
    seen: set[str] = set()
    for c in found:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        if Path(c).is_file():
            out.append(c)
    return out


def _open_preview_window(url: str, *, width: int = 1100, height: int = 780):
    """Open a centered Chromium app window; fallback to default browser.

    Returns (proc, profile_dir). profile_dir is a private user-data-dir so the
    Chromium process stays owned by us and can be killed on submit (shared
    profiles hand off to an existing browser and ignore terminate/window.close).
    """
    sw, sh = _screen_size()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    profile_dir = tempfile.mkdtemp(prefix="dpb-preview-")
    args_tail = [
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        f"--window-size={width},{height}",
        f"--window-position={x},{y}",
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI",
    ]
    for exe in _browser_candidates():
        try:
            proc = subprocess.Popen(
                [exe, *args_tail],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log(
                f"preview app window: {exe} pid={proc.pid} pos={x},{y} "
                f"size={width}x{height} profile={profile_dir}"
            )
            return proc, profile_dir
        except Exception as exc:  # noqa: BLE001
            _log(f"app window open failed ({exe}): {exc}")
    try:
        webbrowser.open(url)
        _log("preview fallback: webbrowser.open")
    except Exception as exc:  # noqa: BLE001
        _log(f"webbrowser.open failed: {exc}")
    _rm_tree(profile_dir)
    return None, None


def _kill_browser_proc(
    proc: subprocess.Popen | None,
    profile_dir: str | None = None,
) -> None:
    """Force-close the owned preview Chromium.

    Chromium may exit the launcher PID and keep the app window under another
    process that still holds --user-data-dir. Kill by PID tree first, then by
    profile path in the command line.
    """
    launcher_killed = False
    if proc is not None and proc.poll() is None:
        try:
            if sys.platform == "win32":
                completed = subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
                launcher_killed = completed.returncode == 0
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                launcher_killed = True
        except subprocess.TimeoutExpired:
            _log("browser kill by pid timed out; trying profile fallback")
        except Exception as exc:  # noqa: BLE001
            _log(f"browser kill by pid failed: {exc}")

    if launcher_killed:
        _log(f"browser kill by pid tree: {proc.pid}")
        return
    if not profile_dir:
        return
    try:
        if sys.platform == "win32":
            # Keep the marker out of PowerShell's own command line, otherwise
            # the matcher can terminate itself before reaching Chromium.
            ps = (
                "$m=$env:DPB_PREVIEW_PROFILE;"
                "Get-CimInstance Win32_Process | Where-Object {"
                "  $_.ProcessId -ne $PID -and $_.CommandLine -and "
                "  $_.CommandLine.IndexOf($m,[StringComparison]::OrdinalIgnoreCase) -ge 0"
                "} | ForEach-Object {"
                "  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue"
                "}"
            )
            env = os.environ.copy()
            # Match the unique leaf name because Chromium may expand an 8.3
            # temp path (AMSTER~1) to its long form in the child command line.
            env["DPB_PREVIEW_PROFILE"] = Path(profile_dir).name
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                env=env,
                timeout=8,
            )
        else:
            # pkill -f is common on mac/linux for matching cmdline
            for pat in (str(Path(profile_dir).resolve()), profile_dir):
                if not pat:
                    continue
                subprocess.run(
                    ["pkill", "-f", pat],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        _log(f"browser kill by profile: {profile_dir}")
    except subprocess.TimeoutExpired:
        _log(f"browser kill by profile timed out: {profile_dir}")
    except Exception as exc:  # noqa: BLE001
        _log(f"browser kill by profile failed: {exc}")


def _request_browser_window_close(proc: subprocess.Popen | None) -> None:
    """Hide the owned app window synchronously before process cleanup."""
    if proc is None or sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        target_pid = proc.pid
        closed = 0

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def close_if_owned(hwnd, _lparam):
            nonlocal closed
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == target_pid and user32.IsWindowVisible(hwnd):
                user32.ShowWindow(hwnd, 0)  # SW_HIDE
                closed += 1
            return True

        user32.EnumWindows(close_if_owned, 0)
        if closed:
            _log(f"browser window hidden: pid={target_pid} windows={closed}")
    except Exception as exc:  # noqa: BLE001
        _log(f"browser window close failed: {exc}")


def _rm_tree(path: str | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass


class BrowserInteraction(Protocol):
    """Seam for owning a browser window across one preview round (US-4).

    ``open`` returns an opaque owned handle; ``close`` tears down the owned
    browser and its private profile. The interface exposes no executable,
    PID, profile, subprocess, or platform cleanup details - those stay inside
    the production adapter as implementation details. Tests substitute one
    fake adapter for the whole owned-browser lifecycle instead of patching
    process/profile internals.
    """

    def open(self, url: str) -> Any:
        """Open ``url`` in an owned browser window; return an opaque handle."""
        ...

    def close(self, handle: Any) -> None:
        """Close the owned browser and release its private profile."""
        ...


class OwnedBrowserAdapter:
    """Production :class:`BrowserInteraction` for the owned-Chromium lifecycle.

    The adapter hides executable discovery, process launch, profile cleanup,
    terminate, and kill behind ``open``/``close``. The module-level owned-
    browser helpers (``_browser_candidates``, ``_open_preview_window``,
    ``_request_browser_window_close``, ``_kill_browser_proc``, ``_rm_tree``)
    are this adapter's implementation details. They are referenced by name
    (not captured) so the production path stays unit-injectable at the helper
    seam: callers that patch a helper still intercept the adapter's call.
    """

    def open(self, url: str) -> Any:
        return _open_preview_window(url)

    def close(self, handle: Any) -> None:
        proc, profile = handle
        _request_browser_window_close(proc)
        _kill_browser_proc(proc, profile)
        _rm_tree(profile)
