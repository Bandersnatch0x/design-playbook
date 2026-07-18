"""Owned-Chromium preview window + local HTTP decide form.

Sibling module split from server.py; behavior unchanged. Opens a centered
app window, serves the prototype + injected control bar over a one-shot
HTTP server, classifies the POSTed decision, applies the ADR-0008 floor,
and tears down the browser + server without hanging on keep-alive sockets.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from confirm import _check_feedback_floor
from control import _build_control, _format_feedback
from i18n import CONFIRM_LABELS, lang, t
from util import _log


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



def _stop_http_server(
    server: HTTPServer,
    serve_thread: threading.Thread,
    *,
    timeout_s: float = 1.5,
) -> None:
    """Stop the threaded preview server and prove its serve loop exited."""
    errors: list[str] = []
    try:
        server.shutdown()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"http shutdown failed: {exc}")
    try:
        server.server_close()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"http server_close failed: {exc}")

    serve_thread.join(timeout=timeout_s)
    if serve_thread.is_alive():
        errors.append(f"http serve thread still alive after {timeout_s:.1f}s")
    if errors:
        message = "; ".join(errors)
        _log(message)
        raise RuntimeError(message)



def _parse_anchors(raw: str) -> list[dict[str, Any]]:
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        selector = str(item.get("selector") or "").strip()
        if not selector:
            continue
        out.append({
            "selector": selector,
            "label": str(item.get("label") or "").strip()[:120],
            "comment": str(item.get("comment") or "").strip()[:500],
            "tag": str(item.get("tag") or "").strip()[:40],
        })
    return out[:40]



def _done_page_html() -> bytes:
    # Owned Chromium is killed by the server after submit; JS is best-effort only.
    # Use unique %markers + str.replace (not .format) so the CSS/JS braces don't
    # need escaping.
    html = """<!DOCTYPE html><html lang="%html_lang%"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>%done_title%</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
background:#0f1218;color:#e5e7eb}
.card{width:min(420px,92vw);padding:28px 24px;border-radius:14px;
background:#171b24;border:1px solid #2c3444;text-align:center}
h1{margin:0 0 8px;font-size:18px;font-weight:650;letter-spacing:-.02em}
p{margin:0;color:#9aa3b2;font-size:13px}
.ok{display:inline-flex;align-items:center;justify-content:center;
width:40px;height:40px;border-radius:999px;margin-bottom:14px;
background:rgba(20,184,166,.14);color:#5eead4;font-weight:700}
</style>
<script>
setTimeout(function () {
  try { window.open("", "_self"); window.close(); } catch (e) {}
  try { window.close(); } catch (e) {}
}, 200);
</script>
</head><body><div class="card">
<div class="ok" aria-hidden="true">OK</div>
<h1>%done_title%</h1><p>%done_body%</p>
</div></body></html>"""
    return (html
            .replace("%html_lang%", lang())
            .replace("%done_title%", t("done_title"))
            .replace("%done_body%", t("done_body"))).encode("utf-8")



def _collect_via_browser(
        prototype: Path, summary: str, options: list[str],
        round_n: int) -> dict[str, Any]:
    """Serve prototype + control form; block until user submits or aborts."""
    result: dict[str, Any] = {
        "confirmed": False,
        "selected_options": [],
        "feedback": "",
        "aborted": True,
        "anchors": [],
    }
    done = threading.Event()

    html = prototype.read_text(encoding="utf-8")
    control = _build_control(round_n, summary.strip(), options)
    m = re.search(r"</body\s*>", html, re.I)
    if m:
        # Avoid re.sub replacement template: control HTML/JS has backslashes (e.g. \s).
        page = html[: m.start()] + control + html[m.start() :]
    else:
        page = html + control

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            _log("http: " + (fmt % args))

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            data = page.encode("utf-8")
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            nonlocal result
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            form = parse_qs(body)
            choice = (form.get("choice") or ["__abort__"])[0]
            feedback = (form.get("feedback") or [""])[0]
            anchors = _parse_anchors((form.get("anchors_json") or ["[]"])[0])
            if choice == "__abort__":
                result = {
                    "confirmed": False,
                    "selected_options": [],
                    "feedback": feedback,
                    "aborted": True,
                    "anchors": anchors,
                }
            else:
                confirmed = choice in CONFIRM_LABELS or choice.casefold() in {
                    c.casefold() for c in CONFIRM_LABELS
                }
                result = {
                    "confirmed": confirmed,
                    "selected_options": [choice],
                    "feedback": feedback,
                    "aborted": False,
                    "anchors": anchors,
                }
            reply = _done_page_html()
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(reply)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(reply)
            self.wfile.flush()
            done.set()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, name="dpb-preview-http", daemon=True
    )
    thread.start()
    url = f"http://127.0.0.1:{port}/"
    _log(f"preview UI at {url}")
    browser_proc, browser_profile = _open_preview_window(url)
    try:
        if not done.wait(timeout=1800):
            result = {
                "confirmed": False,
                "selected_options": [],
                "feedback": "timeout waiting for user",
                "aborted": True,
                "anchors": [],
            }
    finally:
        # Hide for immediate visual feedback. Kill the owned Chromium next so
        # keep-alive sockets cannot block HTTPServer.shutdown; response is
        # already flushed before done.set(). Bound HTTP stop so MCP returns.
        _request_browser_window_close(browser_proc)
        _kill_browser_proc(browser_proc, browser_profile)
        try:
            _stop_http_server(server, thread, timeout_s=1.5)
        finally:
            _rm_tree(browser_profile)
    # ADR-0008: floor is checked against the RAW feedback (pre-format), else
    # _format_feedback would always make it non-empty by merging anchors.
    raw_feedback = result.get("feedback") or ""
    raw_anchors = list(result.get("anchors") or [])
    floor_pass, floor_failure = _check_feedback_floor(raw_feedback, raw_anchors)
    result["floor_pass"] = floor_pass
    if not floor_pass:
        result["floor_failure"] = floor_failure
    # merge anchors into feedback for log readability
    result["feedback"] = _format_feedback(raw_feedback, raw_anchors)
    return result

