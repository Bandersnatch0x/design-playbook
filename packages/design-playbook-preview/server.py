#!/usr/bin/env python3
"""Minimal stdio MCP server: single tool `preview_prototype`.

No third-party deps. Opens the prototype in a local browser, collects
confirm / revise / abort via a tiny HTTP form, writes confirm JSON under
the preview directory (ticket 06).

Run (example MCP client config):
  { "command": "python", "args": ["<repo>/packages/design-playbook-preview/server.py"] }
"""
from __future__ import annotations

import ctypes
import hashlib
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

TOOL_NAME = "preview_prototype"
DEFAULT_OPTIONS = ["确认通过", "需要修改"]
CONFIRM_LABELS = {"确认通过", "confirm", "confirmed", "pass", "ok"}
STDIO_FRAMING_CONTENT_LENGTH = "content-length"
STDIO_FRAMING_NEWLINE = "newline"
_stdio_framing: str | None = None


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_message() -> dict[str, Any] | None:
    """Read Content-Length or newline-delimited JSON-RPC from stdin."""
    global _stdio_framing

    while True:
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None
        if first_line not in (b"\r\n", b"\n"):
            break

    if not first_line.lower().startswith(b"content-length:"):
        _stdio_framing = STDIO_FRAMING_NEWLINE
        return json.loads(first_line.decode("utf-8"))

    _stdio_framing = STDIO_FRAMING_CONTENT_LENGTH
    headers: dict[str, str] = {}
    line = first_line
    while line not in (b"\r\n", b"\n"):
        key, separator, value = line.decode("utf-8").partition(":")
        if not separator:
            raise ValueError(f"invalid MCP stdio header: {line!r}")
        headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError("MCP stdio headers ended before the blank line")
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise ValueError("MCP stdio Content-Length must be positive")
    body = sys.stdin.buffer.read(length)
    if len(body) != length:
        raise EOFError(
            f"MCP stdio body ended early: expected {length}, got {len(body)}"
        )
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _stdio_framing == STDIO_FRAMING_NEWLINE:
        sys.stdout.buffer.write(raw + b"\n")
    else:
        sys.stdout.buffer.write(
            f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        )
    sys.stdout.buffer.flush()


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Show a disposable HTML prototype in a centered app window, collect "
            "user confirm/revise feedback, and write preview confirm records."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to prototype HTML (preferred).",
                },
                "html": {
                    "type": "string",
                    "description": "Inline full-page HTML when path is absent.",
                },
                "summary": {
                    "type": "string",
                    "description": "Decision-report summary / change note.",
                },
                "round": {
                    "type": "integer",
                    "description": "Loop round number; first round = 1.",
                },
                "report_ref": {
                    "type": "string",
                    "description": "Path or version id of the decision report.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Default ["确认通过","需要修改"].',
                },
            },
            "required": ["summary", "round", "report_ref"],
        },
    }


def _preview_dir_for(path: Path | None) -> Path:
    if path is not None:
        return path.parent
    scratch = Path.cwd() / ".scratch" / "preview-adapter" / "preview"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def _ensure_prototype(path_arg: str | None, html: str | None, round_n: int,
                      preview_dir: Path) -> Path:
    if path_arg:
        p = Path(path_arg)
        if not p.is_file():
            raise ValueError(f"prototype path does not exist: {path_arg}")
        return p
    if not html:
        raise ValueError("path or html is required")
    preview_dir.mkdir(parents=True, exist_ok=True)
    target = preview_dir / f"round-{round_n}.html"
    target.write_text(html, encoding="utf-8")
    return target


def _append_log(preview_dir: Path, *, round_n: int, report_ref: str,
                feedback: str, aborted: bool, selected: list[str],
                anchors: list[dict[str, Any]] | None = None) -> None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    log_path = preview_dir / "log.md"
    if not log_path.is_file():
        log_path.write_text("# preview log\n", encoding="utf-8")
    block = (
        f"\n## round {round_n}\n"
        f"- report_ref: {report_ref}\n"
        f"- timestamp: {_now_iso()}\n"
        f"- feedback: {feedback or ''}\n"
        f"- selected: {', '.join(selected) if selected else ''}\n"
        f"- aborted: {str(aborted).lower()}\n"
        f"- anchors: {len(anchors or [])}\n"
    )
    if anchors:
        for i, a in enumerate(anchors, 1):
            sel = a.get("selector") or ""
            note = a.get("comment") or ""
            label = a.get("label") or ""
            block += f"  - [{i}] {sel} | {label} | {note}\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _write_confirm(preview_dir: Path, *, round_n: int, report_ref: str,
                   selected: list[str], feedback: str,
                   prototype: Path,
                   confirmed: bool, floor_pass: bool,
                   floor_failure: str = "") -> Path:
    digest = hashlib.sha256(prototype.read_bytes()).hexdigest()
    record = {
        "round": round_n,
        "report_ref": report_ref,
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": selected,
        "feedback": feedback,
        "timestamp": _now_iso(),
        "prototype_path": f"preview/{prototype.name}",
        "prototype_html_hash": digest,
    }
    if floor_failure:
        record["floor_failure"] = floor_failure
    out = preview_dir / f"confirm-round-{round_n}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return out


def _check_feedback_floor(feedback: str,
                          anchors: list[dict[str, Any]]) -> tuple[bool, str]:
    """ADR-0008 preview feedback floor (structural, machine-checkable).

    A confirm passes the floor when the feedback is non-empty OR at least one
    anchor carries both a non-empty selector and a non-empty comment. This is
    deliberately structural; semantic quality is left to ui-evaluator (G6).
    Returns (floor_pass, floor_failure_reason).
    """
    feedback = (feedback or "").strip()
    if feedback:
        return True, ""
    if anchors:
        for a in anchors:
            if not isinstance(a, dict):
                continue
            sel = str(a.get("selector") or "").strip()
            note = str(a.get("comment") or "").strip()
            if sel and note:
                return True, ""
    return False, "confirm with no substantive feedback: empty feedback and no anchor with a non-empty comment"


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


def _format_feedback(feedback: str, anchors: list[dict[str, Any]]) -> str:
    feedback = (feedback or "").strip()
    if not anchors:
        return feedback
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(f"锚点批注 ({len(anchors)}):")
    for i, a in enumerate(anchors, 1):
        label = a.get("label") or a.get("tag") or "?"
        note = a.get("comment") or "(无文字)"
        sel = a.get("selector") or ""
        lines.append(f"{i}. [{label}] {note} — {sel}")
    return "\n".join(lines)


def _done_page_html() -> bytes:
    # Owned Chromium is killed by the server after submit; JS is best-effort only.
    html = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>已记录</title>
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
<h1>已记录</h1><p>窗口即将自动关闭。</p>
</div></body></html>"""
    return html.encode("utf-8")


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
    confirm_cf = {c.casefold() for c in CONFIRM_LABELS}
    primary_bits: list[str] = []
    secondary_bits: list[str] = []
    for opt in options:
        safe_val = html_lib.escape(opt, quote=True)
        safe_label = html_lib.escape(opt)
        primary = opt in CONFIRM_LABELS or opt.casefold() in confirm_cf
        cls = "dpb-btn dpb-btn-primary" if primary else "dpb-btn dpb-btn-secondary"
        bit = (
            f'<button type="submit" name="choice" value="{safe_val}" class="{cls}">'
            f"{safe_label}</button>"
        )
        (primary_bits if primary else secondary_bits).append(bit)
    options_html = "\n".join(secondary_bits + primary_bits)
    secondary_html = "\n".join(secondary_bits)
    # secondary actions surfaced directly on the floating pill (so revise isn't hidden in the drawer)
    pill_secondary_html = "\n".join(
        b.replace('class="dpb-btn dpb-btn-secondary"', 'class="dpb-btn-pill-secondary"')
         .replace("dpb-btn-secondary", "dpb-btn-pill-secondary")
        for b in secondary_bits
    )
    summary_safe = html_lib.escape(summary)
    primary_opt = next(
        (o for o in options if o in CONFIRM_LABELS or o.casefold() in confirm_cf),
        options[0] if options else "确认通过",
    )
    primary_val = html_lib.escape(primary_opt, quote=True)
    primary_label = html_lib.escape(primary_opt)
    control_tpl = r"""
<style>
  #dpb-preview-bar {{
    --dpb-bg: #1e2330;
    --dpb-surface: #252b38;
    --dpb-elev: #2a3140;
    --dpb-line: #2c3444;
    --dpb-line-strong: #3d475a;
    --dpb-ink: #f3f4f6;
    --dpb-muted: #9aa3b2;
    --dpb-soft: #c5cbd6;
    --dpb-accent: #14b8a6;
    --dpb-accent-ink: #ffffff;
    --dpb-accent-deep: #0f766e;
    --dpb-danger: #f87171;
    --dpb-radius: 10px;
    --dpb-control-h: 40px;
    font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--dpb-ink);
  }}
  /* ---- floating pill (default state) ---- */
  #dpb-preview-bar {{
    position: fixed;
    right: 24px;
    bottom: 24px;
    left: auto;
    top: auto;
    z-index: 1000;
    background: transparent;
    border: 0;
    padding: 0;
    border-radius: 0;
    border-top: 0;
  }}
  #dpb-preview-bar .dpb-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 8px 8px 16px;
    background: var(--dpb-bg);
    border: 1px solid var(--dpb-line);
    border-radius: 999px;
    box-shadow: 0 8px 28px rgba(0,0,0,.15), 0 2px 6px rgba(0,0,0,.1);
  }}
  #dpb-preview-bar .dpb-pill .dpb-pill-info {{
    display: inline-flex; align-items: center; gap: 8px; max-width: 260px;
  }}
  #dpb-preview-bar .dpb-pill .dpb-round {{
    flex: 0 0 auto; display: inline-flex; align-items: center; height: 22px;
    padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 700;
    font-variant-numeric: tabular-nums; color: #99f6e4;
    background: rgba(20,184,166,.14); border: 1px solid rgba(20,184,166,.35);
  }}
  #dpb-preview-bar .dpb-pill .dpb-summary {{
    margin: 0; min-width: 0; color: var(--dpb-soft);
    font-size: 12.5px; font-weight: 500; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-pill .dpb-pill-actions {{
    display: inline-flex; align-items: center; gap: 6px;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost {{
    appearance: none; cursor: pointer; height: 32px; padding: 0 12px;
    border-radius: 999px; border: 1px solid var(--dpb-line-strong);
    background: var(--dpb-surface); color: var(--dpb-soft);
    font: 650 12.5px/1 system-ui, sans-serif;
    display: inline-flex; align-items: center; gap: 6px;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost:hover {{
    background: var(--dpb-elev); border-color: #5b6578; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  #dpb-preview-bar .dpb-pill .dpb-badge-dot {{
    display: none; min-width: 18px; height: 18px; padding: 0 5px;
    align-items: center; justify-content: center; border-radius: 999px;
    font-size: 11px; font-weight: 700; color: #042f2e;
    background: var(--dpb-accent);
  }}
  #dpb-preview-bar .dpb-pill .dpb-badge-dot.is-on {{ display: inline-flex; }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary {{
    appearance: none; cursor: pointer; height: 32px; padding: 0 16px;
    border-radius: 999px; border: 1px solid var(--dpb-accent-deep);
    background: var(--dpb-accent); color: var(--dpb-accent-ink);
    font: 650 12.5px/1 system-ui, sans-serif;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.18);
    transition: background 140ms ease, transform 100ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:hover {{ background: #2dd4bf; color: #042f2e; }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:active {{ transform: translateY(1px); }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  /* secondary action surfaced on the pill (e.g. 需要修改) */
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary {{
    appearance: none; cursor: pointer; height: 32px; padding: 0 14px;
    border-radius: 999px; border: 1px solid var(--dpb-line-strong);
    background: var(--dpb-elev); color: var(--dpb-soft);
    font: 650 12.5px/1 system-ui, sans-serif;
    display: inline-flex; align-items: center;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary:hover {{
    background: #3a4150; border-color: #6b7588; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  @media (max-width: 720px) {{
    #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary {{ display: none; }}
  }}

  /* ---- drawer (expanded state) ---- */
  #dpb-preview-bar .dpb-drawer {{
    display: none;
    width: 380px;
    max-width: calc(100vw - 48px);
    max-height: calc(100vh - 48px);
    flex-direction: column;
    background: var(--dpb-bg);
    border: 1px solid var(--dpb-line);
    border-radius: 16px;
    box-shadow: 0 16px 48px rgba(0,0,0,.22), 0 4px 12px rgba(0,0,0,.12);
    overflow: hidden;
  }}
  /* dim overlay when drawer is open — gives the dark drawer modal context on a light page */
  #dpb-preview-bar.is-open::before {{
    content: "";
    position: fixed; inset: 0; z-index: -1;
    background: rgba(15,23,42,.18);
    pointer-events: none;
  }}
  #dpb-preview-bar.is-open .dpb-pill {{ display: none; }}
  #dpb-preview-bar.is-open .dpb-drawer {{ display: flex; }}

  #dpb-preview-bar .dpb-drawer-head {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; padding: 12px 14px;
    border-bottom: 1px solid var(--dpb-line);
    background: linear-gradient(180deg, #131722, var(--dpb-bg));
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-head-left {{
    display: inline-flex; align-items: center; gap: 8px; min-width: 0;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-round {{
    flex: 0 0 auto; display: inline-flex; align-items: center; height: 22px;
    padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 700;
    font-variant-numeric: tabular-nums; color: #99f6e4;
    background: rgba(20,184,166,.14); border: 1px solid rgba(20,184,166,.35);
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-title {{
    margin: 0; font-size: 13px; font-weight: 650; color: var(--dpb-ink);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn {{
    appearance: none; cursor: pointer; width: 28px; height: 28px;
    border-radius: 8px; border: 1px solid transparent;
    background: transparent; color: var(--dpb-muted);
    font: 650 16px/1 system-ui, sans-serif;
    display: inline-grid; place-items: center;
    transition: background 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn:hover {{
    background: var(--dpb-elev); color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 1px;
  }}

  #dpb-preview-bar .dpb-drawer-body {{
    display: flex; flex-direction: column; min-height: 0;
    overflow: auto; padding: 10px 14px 14px; gap: 14px;
  }}
  #dpb-preview-bar .dpb-drawer-body .dpb-subhead {{
    margin: 0; font-size: 11px; font-weight: 700; letter-spacing: 0.05em;
    color: var(--dpb-muted); text-transform: uppercase;
  }}

  /* pin toggle in drawer */
  #dpb-preview-bar .dpb-pin-toggle {{
    appearance: none; cursor: pointer; height: 34px; padding: 0 12px;
    border-radius: 8px; border: 1px solid var(--dpb-line-strong);
    background: var(--dpb-surface); color: var(--dpb-soft);
    font: 650 12.5px/1 system-ui, sans-serif;
    display: inline-flex; align-items: center; gap: 7px;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pin-toggle:hover {{
    background: var(--dpb-elev); border-color: #5b6578; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pin-toggle.is-on {{
    color: #042f2e; background: var(--dpb-accent); border-color: var(--dpb-accent-deep);
  }}
  #dpb-preview-bar .dpb-pin-toggle:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  #dpb-preview-bar .dpb-pin-row {{
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
  }}
  #dpb-preview-bar .dpb-pin-count {{
    font-size: 11.5px; color: var(--dpb-muted); font-variant-numeric: tabular-nums;
  }}

  /* anchor list */
  #dpb-preview-bar .dpb-anchors {{
    display: none; flex-direction: column; gap: 6px;
    max-height: 180px; overflow: auto; padding: 8px;
    border-radius: 8px; background: var(--dpb-surface);
    border: 1px solid var(--dpb-line);
  }}
  #dpb-preview-bar .dpb-anchors.has-items {{ display: flex; }}
  #dpb-preview-bar .dpb-empty {{
    display: none; padding: 10px 4px; font-size: 12px; color: var(--dpb-muted);
    text-align: center;
  }}
  #dpb-preview-bar .dpb-anchors:not(.has-items) + .dpb-empty {{ display: block; }}
  #dpb-preview-bar .dpb-anchor {{
    display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px;
    align-items: start; padding: 6px 8px; border-radius: 8px;
    background: var(--dpb-elev); border: 1px solid var(--dpb-line);
  }}
  #dpb-preview-bar .dpb-anchor .n {{
    font-size: 11px; font-weight: 700; color: var(--dpb-accent); padding-top: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .meta {{
    min-width: 0; display: grid; gap: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .label {{
    font-size: 12px; font-weight: 650; color: var(--dpb-ink);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    appearance: none; border: 0; background: transparent; padding: 0;
    text-align: left; cursor: pointer; width: 100%;
    display: block; min-width: 0;
  }}
  #dpb-preview-bar .dpb-anchor .label:hover {{ color: var(--dpb-accent); }}
  #dpb-preview-bar .dpb-anchor .label:focus-visible {{
    outline: 2px solid var(--dpb-accent); outline-offset: 1px; border-radius: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .sel {{
    font-size: 11px; color: var(--dpb-muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-anchor input {{
    width: 100%; box-sizing: border-box; height: 28px; margin: 0; padding: 0 8px;
    border-radius: 6px; border: 1px solid var(--dpb-line-strong);
    background: var(--dpb-surface); color: var(--dpb-ink); font: inherit; outline: none;
  }}
  #dpb-preview-bar .dpb-anchor input:focus {{
    border-color: var(--dpb-accent); box-shadow: 0 0 0 2px rgba(20,184,166,.2);
  }}
  #dpb-preview-bar .dpb-anchor .rm {{
    appearance: none; cursor: pointer; height: 28px; padding: 0 8px;
    border: 0; border-radius: 6px; background: transparent; color: var(--dpb-muted);
    font: 650 12px/1 system-ui, sans-serif;
  }}
  #dpb-preview-bar .dpb-anchor .rm:hover {{ color: var(--dpb-danger); background: rgba(248,113,113,.08); }}

  /* overall comment */
  #dpb-preview-bar .dpb-field {{ display: grid; gap: 6px; min-width: 0; }}
  #dpb-preview-bar .dpb-label-row {{
    display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  }}
  #dpb-preview-bar .dpb-label {{ font-size: 12px; font-weight: 650; color: var(--dpb-muted); }}
  #dpb-preview-bar .dpb-hint {{ margin: 0; font-size: 12px; color: var(--dpb-danger); display: none; }}
  #dpb-preview-bar .dpb-hint.is-on {{ display: block; }}
  #dpb-preview-bar textarea[name="feedback"] {{
    width: 100%; box-sizing: border-box; min-height: 56px; max-height: 120px;
    resize: vertical; margin: 0; padding: 8px 12px; color: var(--dpb-ink);
    background: var(--dpb-surface); border: 1px solid var(--dpb-line-strong);
    border-radius: var(--dpb-radius); font: inherit; line-height: 1.45; outline: none;
    transition: border-color 140ms ease, box-shadow 140ms ease, background 140ms ease;
  }}
  #dpb-preview-bar textarea[name="feedback"]::placeholder {{ color: #7d8698; }}
  #dpb-preview-bar textarea[name="feedback"]:hover {{ border-color: #525c70; background: var(--dpb-elev); }}
  #dpb-preview-bar textarea[name="feedback"]:focus {{
    border-color: var(--dpb-accent); box-shadow: 0 0 0 3px rgba(20,184,166,.22); background: #12161e;
  }}
  #dpb-preview-bar textarea[name="feedback"][aria-invalid="true"] {{
    border-color: #f87171; box-shadow: 0 0 0 3px rgba(248,113,113,.18);
  }}

  /* footer actions */
  #dpb-preview-bar .dpb-drawer-foot {{
    display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end;
    align-items: center; padding: 12px 14px;
    border-top: 1px solid var(--dpb-line);
    background: linear-gradient(180deg, var(--dpb-bg), #131722);
  }}
  #dpb-preview-bar .dpb-btns {{
    display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center;
  }}
  #dpb-preview-bar .dpb-btn {{
    appearance: none; cursor: pointer; box-sizing: border-box; height: var(--dpb-control-h);
    min-width: 96px; padding: 0 16px; border-radius: var(--dpb-radius);
    font: 650 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif;
    border: 1px solid transparent;
    transition: background 140ms ease, border-color 140ms ease, color 140ms ease, transform 100ms ease;
  }}
  #dpb-preview-bar .dpb-btn:active {{ transform: translateY(1px); }}
  #dpb-preview-bar .dpb-btn:focus-visible {{ outline: 2px solid var(--dpb-accent); outline-offset: 2px; }}
  #dpb-preview-bar .dpb-btn-primary {{
    background: var(--dpb-accent); color: var(--dpb-accent-ink); border-color: var(--dpb-accent-deep);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.18);
  }}
  #dpb-preview-bar .dpb-btn-primary:hover {{ background: #2dd4bf; color: #042f2e; }}
  #dpb-preview-bar .dpb-btn-secondary {{
    background: var(--dpb-elev); color: var(--dpb-ink); border-color: var(--dpb-line-strong);
  }}
  #dpb-preview-bar .dpb-btn-secondary:hover {{ background: #252b39; border-color: #5b6578; }}
  #dpb-preview-bar .dpb-btn-quiet {{
    min-width: 72px; background: transparent; color: var(--dpb-muted); border-color: transparent;
  }}
  #dpb-preview-bar .dpb-btn-quiet:hover {{ color: var(--dpb-ink); background: rgba(255,255,255,.04); }}

  /* floating annotation bubbles pinned to targeted elements */
  .dpb-float-note {{
    position: absolute;
    z-index: 1001;
    max-width: 240px;
    min-width: 120px;
    padding: 6px 10px 6px 8px;
    border-radius: 10px;
    background: #1f2430;
    color: #f3f4f6;
    border: 1px solid #2c3444;
    box-shadow: 0 8px 24px rgba(0,0,0,.32), 0 2px 6px rgba(0,0,0,.18);
    font: 12px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
    pointer-events: none;
    transform: translateY(4px);
    opacity: 0;
    transition: opacity 160ms ease, transform 160ms ease;
  }}
  .dpb-float-note.is-visible {{ opacity: 1; transform: translateY(0); }}
  .dpb-float-note .dpb-float-n {{
    position: absolute; top: -7px; left: -7px;
    width: 18px; height: 18px; border-radius: 999px;
    background: var(--dpb-accent); color: #042f2e;
    font-size: 11px; font-weight: 700;
    display: inline-grid; place-items: center;
    box-shadow: 0 1px 3px rgba(0,0,0,.3);
  }}
  .dpb-float-note .dpb-float-label {{
    display: block; font-weight: 650; color: #99f6e4;
    font-size: 11px; margin-bottom: 2px; word-break: break-word;
  }}
  .dpb-float-note .dpb-float-comment {{
    color: var(--dpb-soft); word-break: break-word; white-space: pre-wrap;
  }}

  .dpb-pin-target {{
    outline: 1.5px solid rgba(20,184,166,.9) !important;
    outline-offset: 1px !important;
    background-color: rgba(20,184,166,.06) !important;
    cursor: crosshair !important;
  }}
  .dpb-pin-hover {{
    outline: 1px dashed rgba(20,184,166,.45) !important;
    outline-offset: 1px !important;
  }}
  /* brief flash when an anchor is located from the list */
  .dpb-pin-flash {{
    animation: dpb-flash 900ms ease-out 1;
  }}
  @keyframes dpb-flash {{
    0% {{ box-shadow: 0 0 0 0 rgba(20,184,166,.55); outline-color: rgba(20,184,166,.9) !important; }}
    50% {{ box-shadow: 0 0 0 6px rgba(20,184,166,.25); }}
    100% {{ box-shadow: 0 0 0 0 rgba(20,184,166,0); }}
  }}
  body.dpb-pin-mode, body.dpb-pin-mode * {{ cursor: crosshair !important; }}
  body.dpb-pin-mode #dpb-preview-bar, body.dpb-pin-mode #dpb-preview-bar * {{
    cursor: default !important;
  }}

  @media (max-width: 720px) {{
    #dpb-preview-bar {{ right: 12px; bottom: 12px; }}
    #dpb-preview-bar .dpb-drawer {{ width: calc(100vw - 24px); }}
    #dpb-preview-bar .dpb-pill .dpb-pill-info {{ display: none; }}
    #dpb-preview-bar .dpb-drawer-body {{ padding: 10px 10px 14px; }}
    #dpb-preview-bar .dpb-drawer-foot {{ justify-content: stretch; }}
    #dpb-preview-bar .dpb-btn {{ flex: 1 1 auto; min-width: 0; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    #dpb-preview-bar .dpb-btn,
    #dpb-preview-bar textarea[name="feedback"],
    .dpb-float-note {{ transition: none; }}
    #dpb-preview-bar .dpb-btn:active {{ transform: none; }}
    .dpb-pin-flash {{ animation: none; }}
  }}
</style>
<div id="dpb-preview-bar" role="region" aria-label="预览确认">
  <form method="POST" action="/decide" id="dpb-decide-form">
    <input type="hidden" name="anchors_json" id="dpb-anchors-json" value="[]" />

    <!-- floating pill (default) -->
    <div class="dpb-pill">
      <span class="dpb-pill-info">
        <span class="dpb-round">第 {round_n} 轮</span>
        <p class="dpb-summary" title="{summary_safe}">{summary_safe}</p>
      </span>
      <span class="dpb-pill-actions">
        {pill_secondary_html}
        <button type="button" class="dpb-btn-ghost" id="dpb-open-drawer">
          <span aria-hidden="true">💬</span>批注<span class="dpb-badge-dot" id="dpb-pill-count">0</span>
        </button>
        <button type="submit" name="choice" value="{primary_val}" class="dpb-btn-primary">{primary_label}</button>
      </span>
    </div>

    <!-- drawer (expanded) -->
    <div class="dpb-drawer" role="dialog" aria-modal="true" aria-label="批注与确认">
      <div class="dpb-drawer-head">
        <span class="dpb-head-left">
          <span class="dpb-round">第 {round_n} 轮</span>
          <h2 class="dpb-title">{summary_safe}</h2>
        </span>
        <button type="button" class="dpb-icon-btn" id="dpb-close-drawer" aria-label="收起">−</button>
      </div>
      <div class="dpb-drawer-body">
        <div class="dpb-pin-row">
          <button type="button" class="dpb-pin-toggle" id="dpb-pin-toggle" aria-pressed="false">
            <span aria-hidden="true">🎯</span><span class="dpb-pin-label">点选批注</span>
          </button>
          <span class="dpb-pin-count" id="dpb-pin-count">已选 0 处</span>
        </div>

        <div>
          <p class="dpb-subhead">选中批注</p>
          <div class="dpb-anchors" id="dpb-anchors" aria-live="polite"></div>
          <p class="dpb-empty">尚未选中元素。点上方「点选批注」后，再点页面上的元素。</p>
        </div>

        <div class="dpb-field">
          <span class="dpb-label-row">
            <span class="dpb-label">整体批注</span>
            <span class="dpb-hint" id="dpb-feedback-hint" role="alert">选「需要修改」时请写整体意见，或点选元素加锚点</span>
          </span>
          <textarea name="feedback" rows="2"
            placeholder="对整页的总意见；页面元素的局部问题用「点选批注」"
            autocomplete="off"></textarea>
        </div>
      </div>
      <div class="dpb-drawer-foot">
        <div class="dpb-btns">
          {secondary_html}
          <button type="submit" name="choice" value="{primary_val}" class="dpb-btn dpb-btn-primary">{primary_label}</button>
          <button type="submit" name="choice" value="__abort__" class="dpb-btn dpb-btn-quiet">关闭</button>
        </div>
      </div>
    </div>
  </form>
</div>
<div id="dpb-preview-spacer" aria-hidden="true"></div>
<script>
(function () {{
  var bar = document.getElementById("dpb-preview-bar");
  var form = document.getElementById("dpb-decide-form");
  if (!form) return;
  var field = form.querySelector('textarea[name="feedback"]');
  var hint = document.getElementById("dpb-feedback-hint");
  var pinBtn = document.getElementById("dpb-pin-toggle");
  var pinLabel = pinBtn ? pinBtn.querySelector(".dpb-pin-label") : null;
  var listEl = document.getElementById("dpb-anchors");
  var hidden = document.getElementById("dpb-anchors-json");
  var openBtn = document.getElementById("dpb-open-drawer");
  var closeBtn = document.getElementById("dpb-close-drawer");
  var pinCountEl = document.getElementById("dpb-pin-count");
  var pillCountEl = document.getElementById("dpb-pill-count");
  var anchors = [];
  var pinOn = false;
  var hoverEl = null;
  var floatRoot = null;
  var floatMap = {{}};  // selector -> bubble element

  function ensureFloatRoot() {{
    if (floatRoot) return floatRoot;
    floatRoot = document.createElement("div");
    floatRoot.id = "dpb-float-root";
    document.body.appendChild(floatRoot);
    return floatRoot;
  }}

  function esc(s) {{
    return String(s || "").replace(/[&<>"']/g, function (c) {{
      return ({{"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}})[c];
    }});
  }}

  function cssPath(el) {{
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    var cur = el;
    var depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {{
      if (cur.id === "dpb-preview-bar" || cur.id === "dpb-preview-spacer" || cur.id === "dpb-float-root") break;
      var part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) {{
        var cls = Array.prototype.slice.call(cur.classList, 0, 2)
          .filter(function (c) {{ return c && c.indexOf("dpb-") !== 0; }})
          .map(function (c) {{ return "." + CSS.escape(c); }})
          .join("");
        part += cls;
      }}
      var parent = cur.parentElement;
      if (parent) {{
        var kids = parent.children;
        var n = 0, idx = 0, i;
        for (i = 0; i < kids.length; i++) {{
          if (kids[i].tagName === cur.tagName) {{
            n++;
            if (kids[i] === cur) idx = n;
          }}
        }}
        if (n > 1) part += ":nth-of-type(" + idx + ")";
      }}
      parts.unshift(part);
      if (cur.tagName === "BODY") break;
      cur = parent;
      depth++;
    }}
    return parts.join(" > ");
  }}

  function labelFor(el) {{
    var t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
    if (t.length > 40) t = t.slice(0, 40) + "…";
    if (t) return el.tagName.toLowerCase() + ' "' + t + '"';
    if (el.getAttribute("aria-label")) return el.tagName.toLowerCase() + " " + el.getAttribute("aria-label");
    if (el.id) return "#" + el.id;
    if (el.className && typeof el.className === "string") return el.tagName.toLowerCase() + "." + el.className.trim().split(/\s+/)[0];
    return el.tagName.toLowerCase();
  }}

  function syncHidden() {{
    hidden.value = JSON.stringify(anchors.map(function (a) {{
      return {{ selector: a.selector, label: a.label, comment: a.comment, tag: a.tag }};
    }}));
  }}

  function positionFloat(a, idx) {{
    // ponytail: orphan guard — if target element left the DOM, drop the bubble
    if (!a.el || !a.el.isConnected) {{ removeBubble(a.selector); return; }}
    var bubble = floatMap[a.selector];
    if (!bubble) return;
    var rect = a.el.getBoundingClientRect();
    var root = ensureFloatRoot();
    var nEl = bubble.querySelector(".dpb-float-n");
    if (nEl) nEl.textContent = String(idx + 1);
    bubble.style.left = (window.scrollX + rect.right + 8) + "px";
    var top = window.scrollY + rect.top;
    // keep on screen
    var maxTop = window.scrollY + window.innerHeight - 60;
    bubble.style.top = Math.min(top, maxTop) + "px";
    // flip to left if overflows right
    if (rect.right + 260 > window.innerWidth) {{
      bubble.style.left = (window.scrollX + rect.left - bubble.offsetWidth - 8) + "px";
    }}
  }}

  function ensureBubble(a, idx) {{
    if (!a.el || !a.el.isConnected) {{ removeBubble(a.selector); return; }}
    if (!floatMap[a.selector]) {{
      var bubble = document.createElement("div");
      bubble.className = "dpb-float-note";
      bubble.setAttribute("role", "status");
      bubble.innerHTML =
        '<span class="dpb-float-n" aria-hidden="true">' + (idx + 1) + "</span>" +
        '<span class="dpb-float-label">' + esc(a.label) + "</span>" +
        '<span class="dpb-float-comment"></span>';
      ensureFloatRoot().appendChild(bubble);
      floatMap[a.selector] = bubble;
    }}
    var bubble = floatMap[a.selector];
    var commentEl = bubble.querySelector(".dpb-float-comment");
    commentEl.textContent = a.comment || "";
    bubble.style.display = a.comment ? "block" : "none";
    if (a.comment) {{
      // position after layout
      requestAnimationFrame(function () {{
        positionFloat(a, idx);
        bubble.classList.add("is-visible");
      }});
    }} else {{
      bubble.classList.remove("is-visible");
    }}
  }}

  function removeBubble(selector) {{
    var bubble = floatMap[selector];
    if (bubble) {{
      bubble.remove();
      delete floatMap[selector];
    }}
  }}

  function render() {{
    listEl.innerHTML = "";
    if (!anchors.length) {{
      listEl.classList.remove("has-items");
      syncHidden();
      updateCounts();
      return;
    }}
    listEl.classList.add("has-items");
    anchors.forEach(function (a, idx) {{
      var row = document.createElement("div");
      row.className = "dpb-anchor";
      row.innerHTML =
        '<span class="n">' + (idx + 1) + "</span>" +
        '<div class="meta">' +
          '<button type="button" class="label" data-locate="' + idx + '" title="定位到该元素" aria-label="定位到锚点 ' + (idx + 1) + '">' + esc(a.label) + "</button>" +
          '<div class="sel" title="' + esc(a.selector) + '">' + esc(a.selector) + "</div>" +
          '<input type="text" data-i="' + idx + '" aria-label="锚点 ' + (idx + 1) + ' 的修改意见" placeholder="这条要改什么" value="' + esc(a.comment) + '" />' +
        "</div>" +
        '<button type="button" class="rm" data-rm="' + idx + '" aria-label="移除锚点 ' + (idx + 1) + '">移除</button>';
      listEl.appendChild(row);
      ensureBubble(a, idx);
    }});
    syncHidden();
    updateCounts();
  }}

  function updateCounts() {{
    var n = anchors.length;
    if (pinCountEl) pinCountEl.textContent = "已选 " + n + " 处";
    if (pillCountEl) {{
      pillCountEl.textContent = String(n);
      pillCountEl.classList.toggle("is-on", n > 0);
    }}
  }}

  function clearHover() {{
    if (hoverEl) {{
      hoverEl.classList.remove("dpb-pin-hover");
      hoverEl = null;
    }}
  }}

  function setPin(on) {{
    pinOn = !!on;
    document.body.classList.toggle("dpb-pin-mode", pinOn);
    if (pinBtn) {{
      pinBtn.classList.toggle("is-on", pinOn);
      pinBtn.setAttribute("aria-pressed", pinOn ? "true" : "false");
    }}
    if (pinLabel) pinLabel.textContent = pinOn ? "点选中 · 再点关闭" : "点选批注";
    if (!pinOn) clearHover();
  }}

  function focusableEls() {{
    if (!bar) return [];
    return Array.prototype.slice.call(
      bar.querySelectorAll('a[href],button:not([disabled]),textarea,input:not([disabled]),[tabindex="0"]')
    ).filter(function (el) {{ return el.offsetParent !== null || el === document.activeElement; }});
  }}
  var lastFocus = null;
  function openDrawer() {{
    bar.classList.add("is-open");
    lastFocus = document.activeElement;
    // focus the close button so keyboard users land inside the dialog
    setTimeout(function () {{ if (closeBtn) closeBtn.focus(); }}, 0);
  }}
  function closeDrawer() {{
    bar.classList.remove("is-open");
    if (pinOn) setPin(false);
    if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }}

  if (openBtn) openBtn.addEventListener("click", openDrawer);
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (pinBtn) pinBtn.addEventListener("click", function () {{ setPin(!pinOn); }});

  // ponytail: dialog focus trap + ESC to close — a11y baseline, single keydown on bar
  bar.addEventListener("keydown", function (e) {{
    if (!bar.classList.contains("is-open")) return;
    if (e.key === "Escape") {{ e.preventDefault(); closeDrawer(); return; }}
    if (e.key !== "Tab") return;
    var items = focusableEls();
    if (!items.length) return;
    var first = items[0], lastItem = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {{ e.preventDefault(); lastItem.focus(); }}
    else if (!e.shiftKey && document.activeElement === lastItem) {{ e.preventDefault(); first.focus(); }}
  }});

  document.addEventListener("mousemove", function (e) {{
    if (!pinOn) return;
    var el = e.target;
    if (!el || el.closest("#dpb-preview-bar") || el.closest("#dpb-preview-spacer") || el.closest("#dpb-float-root")) {{
      clearHover();
      return;
    }}
    if (el === document.body || el === document.documentElement) {{
      clearHover();
      return;
    }}
    if (hoverEl !== el) {{
      clearHover();
      hoverEl = el;
      hoverEl.classList.add("dpb-pin-hover");
    }}
  }}, true);

  document.addEventListener("click", function (e) {{
    if (!pinOn) return;
    var raw = e.target;
    if (!raw || raw.closest("#dpb-preview-bar") || raw.closest("#dpb-preview-spacer") || raw.closest("#dpb-float-root")) return;
    if (raw === document.body || raw === document.documentElement) return;
    e.preventDefault();
    e.stopPropagation();
    // anchor to the hovered element, not the inner node that received the click
    var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
    var selector = cssPath(el);
    if (!selector) return;
    // de-dupe by selector; clear stale highlight on any previous element ref
    for (var i = 0; i < anchors.length; i++) {{
      if (anchors[i].selector === selector) {{
        if (anchors[i].el && anchors[i].el !== el) anchors[i].el.classList.remove("dpb-pin-target");
        anchors[i].el = el;
        el.classList.add("dpb-pin-target");
        render();
        return;
      }}
    }}
    el.classList.add("dpb-pin-target");
    anchors.push({{
      selector: selector,
      label: labelFor(el),
      comment: "",
      tag: el.tagName.toLowerCase(),
      el: el
    }});
    render();
    // focus newest comment input
    setTimeout(function () {{
      var inputs = listEl.querySelectorAll("input[data-i]");
      if (inputs.length) inputs[inputs.length - 1].focus();
    }}, 0);
  }}, true);

  listEl.addEventListener("input", function (e) {{
    var t = e.target;
    if (!t || !t.getAttribute) return;
    if (t.getAttribute("data-i") == null) return;
    var i = Number(t.getAttribute("data-i"));
    anchors[i].comment = t.value;
    syncHidden();
    ensureBubble(anchors[i], i);
  }});

  listEl.addEventListener("click", function (e) {{
    var t = e.target;
    if (!t || !t.getAttribute) return;
    var loc = t.getAttribute("data-locate");
    if (loc != null) {{
      e.preventDefault();
      var a = anchors[Number(loc)];
      if (a && a.el && a.el.isConnected) {{
        a.el.scrollIntoView({{ behavior: "smooth", block: "center" }});
        a.el.classList.remove("dpb-pin-flash");
        // force reflow so the animation can restart
        void a.el.offsetWidth;
        a.el.classList.add("dpb-pin-flash");
      }}
      return;
    }}
    var rm = t.getAttribute("data-rm");
    if (rm == null) return;
    var i = Number(rm);
    var a = anchors[i];
    if (a) {{
      if (a.el) a.el.classList.remove("dpb-pin-target");
      removeBubble(a.selector);
    }}
    anchors.splice(i, 1);
    render();
  }});

  // reposition floats on scroll/resize
  function repositionAll() {{
    anchors.forEach(function (a, idx) {{ positionFloat(a, idx); }});
  }}
  window.addEventListener("scroll", repositionAll, true);
  window.addEventListener("resize", repositionAll);

  var reviseLabels = {{"需要修改": 1, "revise": 1, "needs changes": 1}};
  form.addEventListener("submit", function (e) {{
    syncHidden();
    var submitter = e.submitter;
    var choice = submitter && submitter.name === "choice" ? submitter.value : "";
    if (!choice || choice === "__abort__") return;
    var isRevise = !!reviseLabels[choice] || /修改|revise|change/i.test(choice);
    if (!isRevise) return;
    var value = (field && field.value || "").trim();
    // allow revise if free-text OR at least one anchor exists
    if (value || anchors.length) {{
      if (field) field.removeAttribute("aria-invalid");
      if (hint) hint.classList.remove("is-on");
      return;
    }}
    e.preventDefault();
    if (field) {{ field.setAttribute("aria-invalid", "true"); field.focus(); }}
    if (hint) hint.classList.add("is-on");
    if (!bar.classList.contains("is-open")) openDrawer();
    if (!pinOn) setPin(true);
  }});
  if (field) {{
    field.addEventListener("input", function () {{
      if ((field.value || "").trim() || anchors.length) {{
        field.removeAttribute("aria-invalid");
        if (hint) hint.classList.remove("is-on");
      }}
    }});
  }}
}})();
</script>
"""
    control = control_tpl.format(
        round_n=html_lib.escape(str(round_n)),
        summary_safe=summary_safe,
        secondary_html=secondary_html,
        pill_secondary_html=pill_secondary_html,
        primary_val=primary_val,
        primary_label=primary_label,
    )
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


def handle_preview_prototype(args: dict[str, Any]) -> dict[str, Any]:
    path_arg = args.get("path")
    html = args.get("html")
    summary = args.get("summary")
    round_n = args.get("round")
    report_ref = args.get("report_ref")
    options = args.get("options") or list(DEFAULT_OPTIONS)

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary is required")
    if not isinstance(round_n, int) or isinstance(round_n, bool) or round_n < 1:
        raise ValueError("round must be a positive integer")
    if not isinstance(report_ref, str) or not report_ref.strip():
        raise ValueError("report_ref is required")
    if path_arg is not None and not isinstance(path_arg, str):
        raise ValueError("path must be a string")
    if html is not None and not isinstance(html, str):
        raise ValueError("html must be a string")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        raise ValueError("options must be string[]")

    preview_dir = _preview_dir_for(Path(path_arg) if path_arg else None)
    prototype = _ensure_prototype(
        path_arg, html, round_n, preview_dir)

    decision = _collect_via_browser(prototype, summary.strip(), options, round_n)
    floor_pass = bool(decision.get("floor_pass"))
    floor_failure = str(decision.get("floor_failure") or "")
    # ADR-0008: a confirm whose feedback fails the structural floor is NOT
    # authoritative — write the record with confirmed=false + floor_failure
    # (single source of truth on disk and in payload) so the orchestrator
    # treats it as not-yet-confirmed (revise) instead of advancing to Fill.
    user_confirmed = bool(decision["confirmed"]) and not decision["aborted"]
    confirmed = user_confirmed and floor_pass
    confirm_path = ""
    if user_confirmed:
        out = _write_confirm(
            preview_dir,
            round_n=round_n,
            report_ref=report_ref.strip(),
            selected=decision["selected_options"],
            feedback=decision["feedback"],
            prototype=prototype,
            confirmed=confirmed,
            floor_pass=floor_pass,
            floor_failure=floor_failure,
        )
        confirm_path = str(out)
    _append_log(
        preview_dir,
        round_n=round_n,
        report_ref=report_ref.strip(),
        feedback=decision["feedback"],
        aborted=bool(decision["aborted"]),
        selected=list(decision["selected_options"]),
        anchors=list(decision.get("anchors") or []),
    )
    return {
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": list(decision["selected_options"]),
        "feedback": decision["feedback"],
        "anchors": list(decision.get("anchors") or []),
        "round": round_n,
        "confirm_record_path": confirm_path,
        "aborted": bool(decision["aborted"]),
    }


def _result_text(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def _error_result(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def serve() -> None:
    _log("design-playbook-preview MCP server starting (stdio)")
    while True:
        msg = _read_message()
        if msg is None:
            break
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": params.get(
                        "protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "design-playbook-preview",
                        "version": "0.1.0",
                    },
                },
            })
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": [_tool_schema()]},
            })
            continue

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name != TOOL_NAME:
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _error_result(f"unknown tool: {name}"),
                })
                continue
            try:
                payload = handle_preview_prototype(arguments)
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _result_text(payload),
                })
            except Exception as exc:  # noqa: BLE001 — return to client
                _log(f"tools/call error: {exc}")
                _write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _error_result(str(exc)),
                })
            continue

        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            continue

        if msg_id is not None:
            _write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            })


def _self_check_floor() -> None:
    """ADR-0008 floor branch logic self-check (ponytail: one runnable check)."""
    cases = [
        ("empty + no anchors", "", [], False),
        ("whitespace-only feedback", "   \n  ", [], False),
        ("non-empty feedback", "ok", [], True),
        ("anchor with comment", "", [{"selector": "h2", "comment": "x"}], True),
        ("anchor no comment (0015 garbage)", "",
         [{"selector": "h2", "comment": ""}], False),
        ("anchor empty selector", "",
         [{"selector": "", "comment": "x"}], False),
        ("non-dict anchor skipped", "", ["not-a-dict"], False),
    ]
    for label, fb, anc, want in cases:
        got, _ = _check_feedback_floor(fb, anc)
        assert got == want, f"{label}: want {want}, got {got}"
    print("FLOOR SELF-CHECK PASSED")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check_floor()
    else:
        serve()
