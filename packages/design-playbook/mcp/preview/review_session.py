"""Authenticated Preview review behind one deep interface.

Opens a centered app window, serves the prototype and trusted control bar,
authenticates one raw submission, and tears down browser and server without
hanging on keep-alive sockets. Decision authority and floor logic belong to
transaction.py.
"""
from __future__ import annotations

import ctypes
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs

from design_playbook.mcp.preview.control import _build_control
from design_playbook.mcp.preview.i18n import lang, t
from design_playbook.mcp.preview.integrity import prototype_html_digest
from design_playbook.mcp.preview.util import _log


def _generate_decision_token() -> str:
    """One-time URL-safe decision token (G5 trust boundary).

    Proves a POST to /decide originated from the trusted parent control bar
    (which renders the hidden field) rather than from prototype scripts running
    inside the sandboxed iframe, which cannot read the parent DOM. Bound to a
    single preview round via :class:`_DecisionSession`.
    """
    return secrets.token_urlsafe(32)


class _DecisionSession:
    """First-decision-wins token lock for a single preview round (G5).

    ``validate`` returns ``True`` only for the first POST whose token matches
    (constant-time) AND whose round matches. Every other POST — missing token,
    reused token, mismatched round, or wrong token — is rejected so the caller
    can fail the decision closed. The session grants at most one valid decision.
    """

    def __init__(self, round_n: int, token: str) -> None:
        self.round_n = round_n
        self._token = token
        self._locked = False
        self._lock = threading.Lock()
        self.last_rejection: str = ""

    @property
    def locked(self) -> bool:
        return self._locked

    def validate(self, posted_round: int, posted_token: str | None) -> bool:
        # LOW-1 (secure-ship-0.4.4): the check-then-set on ``_locked`` must
        # be atomic. ThreadingHTTPServer handles each POST on its own
        # thread, so two concurrent valid-token POSTs could both pass the
        # ``if self._locked`` check and each consume the session. Hold the
        # lock for the whole decision so first-decision-wins holds under
        # real concurrency; the lock is uncontended in the single-POST
        # happy path, so the cost is a no-op acquire/release.
        with self._lock:
            if not posted_token:
                self.last_rejection = "missing"
                return False
            if posted_round != self.round_n:
                self.last_rejection = "round_mismatch"
                return False
            if self._locked:
                # First valid decision already consumed the session; every
                # later POST (even with the correct token) is a replay.
                self.last_rejection = "reuse"
                return False
            if not secrets.compare_digest(posted_token, self._token):
                self.last_rejection = "invalid_token"
                return False
            self._locked = True
            self.last_rejection = ""
            return True


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



def _anchor_node_id(round_n: int, index: int, selector: str) -> str:
    """Round-local stable anchor id (schema v2; changes across rounds by design).

    Identifies the anchor within a round's decision entry; it is NOT stable
    across rounds (a changed prototype legitimately re-targets elements).
    """
    return hashlib.sha256(
        f"{round_n}|{index}|{selector}".encode("utf-8")).hexdigest()[:8]


def _anchor_features(item: dict, tag: str) -> dict[str, Any]:
    """Reconnect hints derived from the anchor's existing fields (v2, optional).

    Not a promise of automatic cross-round re-linking (sandboxed iframe limits,
    assets/current-canvas-matrix.md §5/§7): hints are stored so a later manual
    re-pin can propose candidates.
    """
    features: dict[str, Any] = {"tag": tag or ""}
    label = str(item.get("label") or "")
    quoted = re.search(r'"([^"]+)"', label)
    if quoted:
        features["text"] = quoted.group(1)[:80]
    classes = re.findall(r"\.([A-Za-z][\w-]*)", str(item.get("selector") or ""))
    if classes:
        features["classes"] = classes[:8]
    return features


def _parse_anchors(raw: str, round_n: int = 0) -> list[dict[str, Any]]:
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        selector = str(item.get("selector") or "").strip()
        if not selector:
            continue
        tag = str(item.get("tag") or "").strip()[:40]
        anchor: dict[str, Any] = {
            "selector": selector,
            "label": str(item.get("label") or "").strip()[:120],
            "comment": str(item.get("comment") or "").strip()[:500],
            "tag": tag,
        }
        if "points" in item and isinstance(item["points"], list):
            anchor["points"] = [
                [float(p[0]), float(p[1])]
                for p in item["points"]
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
        if round_n > 0:
            anchor["node_id"] = _anchor_node_id(round_n, index, selector)
            anchor["features"] = _anchor_features(item, tag)
        out.append(anchor)
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



# G5: the parent control form's opening tag — a stable hook for token
# injection. control.py owns the template; we only splice hidden fields in.
_FORM_MARKER = '<form method="POST" action="/decide" id="dpb-decide-form">'


def _inject_token_fields(control_html: str, token: str, round_n: int) -> str:
    """Insert hidden dpb_token + dpb_round fields into the control form (G5).

    The token is the parent page's proof-of-origin; the round binds it to this
    preview session. Spliced in post-template so control.py stays untouched
    (sibling agents own its contents).
    """
    safe_token = html.escape(token, quote=True)
    fields = (
        f'<input type="hidden" name="dpb_token" value="{safe_token}"/>'
        f'<input type="hidden" name="dpb_round" value="{round_n}"/>'
    )
    if _FORM_MARKER in control_html:
        return control_html.replace(_FORM_MARKER, _FORM_MARKER + fields, 1)
    # Defensive fallback: anchor to any <form ...> open tag if the template
    # marker ever moves. Lambda keeps the replacement literal (no backslash
    # expansion of the HTML/JS payload).
    return re.sub(
        r"(<form\b[^>]*>)",
        lambda m: m.group(1) + fields,
        control_html,
        count=1,
    )


# pin-to-annotate postMessage bridge (G5 sandbox regression fix).
#
# G5 isolated the prototype inside <iframe sandbox="allow-scripts" srcdoc=...>
# with allow-same-origin DELIBERATELY omitted, so the iframe is an opaque
# origin and prototype scripts cannot reach the parent DOM (where the decision
# token lives). That broke pin-to-annotate: the parent's document.click +
# cssPath(e.target) can no longer see clicks inside the iframe or traverse the
# iframe DOM (cross-origin). This bridge runs INSIDE the iframe document and
# restores anchor collection by postMessaging {selector, tag} to the parent.
#
# Pin-state sync (#56): the parent owns pinOn and pushes it down via
# postMessage {dpbPinState:{on}} (on every toggle + iframe load). The bridge
# gates its capture-phase click/mousemove listeners on that state: while pin
# is OFF the prototype receives clicks and hover exactly as if the bridge were
# not injected (no preventDefault/stopPropagation, no dashed outline); while
# ON it keeps the capture behaviour (anchor + highlight + dashed hover).
#
# Cross-origin locate + numbered badges (#57, scheme A): the parent drives
# {dpbPinLocate:{selector}} (scrollIntoView + flash), {dpbPinFlash:{selector}}
# (duplicate-pick feedback) and {dpbPinAnchors:[{selector,n,comment}]} (in-
# frame numbered badges mirroring the same-origin float-notes) into the iframe.
#
# G5 safety contract (verified by test_browser_control.PinAnnotationBridgeTests):
#   - the bridge only postMessages anchor DATA ({selector, tag}) — it never
#     reads parent.document, parent.location, the token, or storage, and it
#     never fetches/XHRs. postMessage is its only outbound channel.
#   - the parent additionally records anchors only while pin mode is on
#     (control.js message listener filters on pinOn) — defense in depth.
#   - the iframe highlights the clicked element itself (dpb-pin-target) since
#     the parent cannot reach into the iframe DOM to do it.
#
# Raw string + single braces: this is plain string concatenation (not .format),
# so JS braces stay literal (no {{ doubling). cssPath is a faithful copy of
# control.py's cssPath so selectors match the same-origin path.
BRIDGE_SCRIPT = r"""<script>
(function () {
  // Inject the pin highlight + badge CSS into the iframe document. The
  // parent's control-bar stylesheet does not cross the iframe boundary, so the
  // bridge brings its own copy of .dpb-pin-target / .dpb-pin-hover (the same
  // rules control.py renders in the parent) plus the numbered annotation
  // badges (.dpb-pin-badge*, #57 scheme A) to render them in-frame.
  var style = document.createElement("style");
  style.textContent =
    ".dpb-pin-target{outline:1.5px solid rgba(20,184,166,.9)!important;" +
    "outline-offset:1px!important;background-color:rgba(20,184,166,.06)!important;" +
    "cursor:crosshair!important}" +
    ".dpb-pin-hover{outline:1px dashed rgba(20,184,166,.45)!important;" +
    "outline-offset:1px!important}" +
    ".dpb-pin-badge{position:absolute;z-index:2147483000;min-width:18px;height:18px;" +
    "padding:0 5px;border-radius:999px;background:#14b8a6;color:#042f2e;" +
    "font:700 11px/18px system-ui,sans-serif;text-align:center;pointer-events:none;" +
    "box-shadow:0 1px 3px rgba(0,0,0,.3)}" +
    ".dpb-pin-badge-note{position:absolute;z-index:2147483000;max-width:220px;" +
    "padding:4px 8px;border-radius:8px;background:#1f2430;color:#f3f4f6;" +
    "border:1px solid #2c3444;font:11px/1.4 system-ui,sans-serif;" +
    "word-break:break-word;pointer-events:none;box-shadow:0 6px 18px rgba(0,0,0,.25)}" +
    ".dpb-pin-flash{animation:dpb-pin-flash .9s ease-out 1}" +
    "@keyframes dpb-pin-flash{0%{box-shadow:0 0 0 0 rgba(20,184,166,.55)}" +
    "50%{box-shadow:0 0 0 8px rgba(20,184,166,.25)}" +
    "100%{box-shadow:0 0 0 0 rgba(20,184,166,0)}}" +
    // Draw mode: stroke layer + crosshair while capturing. Strokes use the
    // same red-orange the parent theme tokens use (#ff7849) — the sandboxed
    // frame cannot read the parent's custom properties.
    "#dpb-draw-layer{position:absolute;top:0;left:0;z-index:2147482999;" +
    "pointer-events:none;overflow:visible}" +
    "html.dpb-draw-mode{cursor:crosshair}" +
    "#dpb-draw-layer .dpb-draw-path{fill:none;stroke:#ff7849;" +
    "stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;opacity:.92}" +
    "#dpb-draw-layer .dpb-draw-live{opacity:.65}" +
    "#dpb-draw-layer .dpb-draw-badge-c{fill:#ff7849}" +
    "#dpb-draw-layer .dpb-draw-badge text{fill:#3b1d10;" +
    "font:700 11px/1 system-ui,sans-serif}" +
    ".dpb-draw-flash{animation:dpb-draw-flash .9s ease-out 1}" +
    "@keyframes dpb-draw-flash{0%{stroke-width:2.5px;filter:drop-shadow(0 0 0 rgba(244,96,42,0))}" +
    "50%{stroke-width:5px;filter:drop-shadow(0 0 8px rgba(244,96,42,.85))}" +
    "100%{stroke-width:2.5px;filter:drop-shadow(0 0 0 rgba(244,96,42,0))}}" +
    // W5: honor reduced-motion inside the iframe too (host control.css only
    // covers the parent document).
    "@media (prefers-reduced-motion:reduce){.dpb-pin-flash{animation:none!important}}" +
    "@media (prefers-reduced-motion:reduce){.dpb-draw-flash{animation:none!important}}";
  (document.head || document.documentElement).appendChild(style);

  // #56: pin state is owned by the parent control bar and synced down via
  // postMessage. OFF (the initial state) means the bridge is fully passive:
  // clicks and hover pass through to the prototype untouched.
  var pinOn = false;

  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    var cur = el;
    var depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {
      if (cur.id === "dpb-preview-bar" || cur.id === "dpb-float-root") break;
      var part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) {
        var cls = Array.prototype.slice.call(cur.classList, 0, 2)
          .filter(function (c) { return c && c.indexOf("dpb-") !== 0; })
          .map(function (c) { return "." + CSS.escape(c); })
          .join("");
        part += cls;
      }
      var parent = cur.parentElement;
      if (parent) {
        var kids = parent.children;
        var n = 0, idx = 0, i;
        for (i = 0; i < kids.length; i++) {
          if (kids[i].tagName === cur.tagName) {
            n++;
            if (kids[i] === cur) idx = n;
          }
        }
        if (n > 1) part += ":nth-of-type(" + idx + ")";
      }
      parts.unshift(part);
      if (cur.tagName === "BODY") break;
      cur = parent;
      depth++;
    }
    return parts.join(" > ");
  }
  var hoverEl = null;
  function clearHover() {
    if (hoverEl) {
      hoverEl.classList.remove("dpb-pin-hover");
      hoverEl = null;
    }
  }
  document.addEventListener("mousemove", function (e) {
    if (!pinOn) return;  // #56: no dashed hover outline outside pin mode
    var el = e.target;
    if (!el || el === document.body || el === document.documentElement) {
      clearHover();
      return;
    }
    if (hoverEl !== el) {
      clearHover();
      hoverEl = el;
      hoverEl.classList.add("dpb-pin-hover");
    }
  }, true);
  document.addEventListener("click", function (e) {
    // #56: outside pin mode the bridge must not swallow clicks — links,
    // buttons, tabs and forms inside the prototype stay fully interactive.
    if (!pinOn) return;
    var raw = e.target;
    if (!raw || raw === document.body || raw === document.documentElement) return;
    var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
    e.preventDefault();
    e.stopPropagation();
    // highlight reconciliation is syncAnchors' job — the parent echoes the
    // full list back after recording the anchor, so every pinned element
    // stays highlighted (not just the latest click).
    el.classList.add("dpb-pin-target");
    var selector = cssPath(el);
    if (!selector) return;
    parent.postMessage({ dpbPinAnchor: { selector: selector, tag: el.tagName.toLowerCase() } }, "*");
  }, true);

  // ---- #57 scheme A: cross-origin locate, flash and numbered badges ----
  function findEl(selector) {
    try { return document.querySelector(selector); } catch (err) { return null; }
  }
  function flashEl(el) {
    el.classList.remove("dpb-pin-flash");
    void el.offsetWidth;  // force reflow so the animation can restart
    el.classList.add("dpb-pin-flash");
  }
  function locateEl(el) {
    try { el.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (err) {}
    flashEl(el);
  }
  var badgeMap = {};  // selector -> { n: span, note: div }
  function clearBadges() {
    for (var sel in badgeMap) {
      if (badgeMap[sel].n.parentNode) badgeMap[sel].n.parentNode.removeChild(badgeMap[sel].n);
      if (badgeMap[sel].note.parentNode) badgeMap[sel].note.parentNode.removeChild(badgeMap[sel].note);
    }
    badgeMap = {};
  }
  function placeBadge(entry) {
    var pair = badgeMap[entry.selector];
    var el = findEl(entry.selector);
    if (!el || !pair) return;
    var rect = el.getBoundingClientRect();
    var left = window.scrollX + rect.right + 6;
    var top = window.scrollY + rect.top - 9;
    // flip to the left side when the badge would run past the right edge
    if (rect.right + 40 > document.documentElement.clientWidth) {
      left = Math.max(window.scrollX + 4, window.scrollX + rect.left - 30);
    }
    pair.n.style.left = left + "px";
    pair.n.style.top = top + "px";
    pair.note.style.left = left + "px";
    pair.note.style.top = (top + 22) + "px";
  }
  function syncAnchors(list) {
    clearBadges();
    // Draw anchors have no cssPath to resolve — they render as strokes on
    // the in-frame draw layer instead of element outlines/badges.
    lastAnchorEcho = list || [];
    renderDrawItems(lastAnchorEcho);
    // #57: the parent's list is the single owner of the cross-origin
    // highlight too — removals and undo/redo must drop the teal outline
    // from elements whose anchor is gone (el is null cross-origin, so the
    // parent cannot clear them itself) and restore it for kept anchors,
    // mirroring the same-origin behavior.
    var keepEls = [];
    list.forEach(function (item) {
      if (item.tag === "draw") return;  // stroke anchors never match an element
      var keepEl = findEl(item.selector);
      if (keepEl) keepEls.push(keepEl);
    });
    var stale = document.querySelectorAll(".dpb-pin-target");
    for (var si = 0; si < stale.length; si++) {
      if (keepEls.indexOf(stale[si]) < 0) {
        stale[si].classList.remove("dpb-pin-target");
      }
    }
    keepEls.forEach(function (keepEl) {
      keepEl.classList.add("dpb-pin-target");
    });
    var body = document.body || document.documentElement;
    list.forEach(function (item) {
      if (item.tag === "draw") return;  // rendered by renderDrawItems
      var el = findEl(item.selector);
      if (!el) return;
      var n = document.createElement("span");
      n.className = "dpb-pin-badge";
      n.setAttribute("aria-hidden", "true");
      n.textContent = String(item.n);
      body.appendChild(n);
      var note = document.createElement("div");
      note.className = "dpb-pin-badge-note";
      note.textContent = String(item.comment || "");
      note.style.display = item.comment ? "block" : "none";
      body.appendChild(note);
      badgeMap[item.selector] = { n: n, note: note };
      placeBadge({ selector: item.selector });
    });
  }
  var badgeTick = false;
  function repositionBadges() {
    if (badgeTick) return;
    badgeTick = true;
    window.requestAnimationFrame(function () {
      badgeTick = false;
      for (var sel in badgeMap) placeBadge({ selector: sel });
    });
  }
  window.addEventListener("scroll", repositionBadges, true);
  window.addEventListener("resize", repositionBadges);

  // ---- draw mode (圈画标注): freehand strokes captured in-frame ----
  // The stroke is drawn live on an in-frame SVG overlay (coordinates stay
  // local to this document); on pointerup the points travel to the parent,
  // which records the draw anchor and echoes it back via dpbPinAnchors for
  // the durable in-frame rendering below (renderDrawItems).
  var drawOn = false;
  var drawSvg = null;
  var livePts = null;
  var livePathEl = null;

  function ensureDrawLayer() {
    if (drawSvg && drawSvg.isConnected) return drawSvg;
    drawSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    drawSvg.setAttribute("id", "dpb-draw-layer");
    drawSvg.setAttribute("aria-hidden", "true");
    sizeDrawLayer();
    (document.body || document.documentElement).appendChild(drawSvg);
    return drawSvg;
  }
  function sizeDrawLayer() {
    if (!drawSvg) return;
    var d = document.documentElement;
    drawSvg.setAttribute("width", String(Math.max(d.scrollWidth, window.innerWidth)));
    drawSvg.setAttribute("height", String(Math.max(d.scrollHeight, window.innerHeight)));
  }
  window.addEventListener("resize", function () {
    if (drawSvg) { sizeDrawLayer(); renderDrawItems(lastAnchorEcho); }
  });

  function drawPathD(points) {
    if (!points || !points.length) return "";
    var d = "";
    for (var i = 0; i < points.length; i++) {
      d += (i ? "L" : "M") + Number(points[i][0]).toFixed(1) + " " + Number(points[i][1]).toFixed(1);
    }
    return d + (points.length > 2 ? " Z" : "");
  }

  function cancelLiveStroke() {
    livePts = null;
    if (livePathEl && livePathEl.parentNode) livePathEl.parentNode.removeChild(livePathEl);
    livePathEl = null;
  }

  document.addEventListener("pointerdown", function (e) {
    if (!drawOn) return;  // passive outside draw mode
    e.preventDefault();
    e.stopPropagation();
    ensureDrawLayer();
    livePts = [[e.clientX + window.scrollX, e.clientY + window.scrollY]];
    livePathEl = document.createElementNS("http://www.w3.org/2000/svg", "path");
    livePathEl.setAttribute("class", "dpb-draw-path dpb-draw-live");
    drawSvg.appendChild(livePathEl);
  }, true);
  document.addEventListener("pointermove", function (e) {
    if (!drawOn || !livePts) return;
    e.preventDefault();
    livePts.push([e.clientX + window.scrollX, e.clientY + window.scrollY]);
    if (livePathEl) livePathEl.setAttribute("d", drawPathD(livePts));
  }, true);
  document.addEventListener("pointerup", function (e) {
    if (!drawOn || !livePts) return;
    e.preventDefault();
    var pts = livePts;
    cancelLiveStroke();
    if (pts.length >= 4) {
      parent.postMessage({ dpbDrawStroke: { points: pts } }, "*");
    }
  }, true);

  function setDrawOn(on) {
    drawOn = !!on;
    if (!on) cancelLiveStroke();
    document.documentElement.classList.toggle("dpb-draw-mode", drawOn);
  }

  // Durable rendering of the parent's draw anchors (echoed via dpbPinAnchors).
  var lastAnchorEcho = [];
  function renderDrawItems(list) {
    lastAnchorEcho = list || [];
    var items = (list || []).filter(function (it) {
      return it.tag === "draw" && it.points && it.points.length;
    });
    if (!items.length && !drawSvg) return;
    ensureDrawLayer();
    var stale = drawSvg.querySelectorAll(".dpb-draw-path, .dpb-draw-badge, .dpb-draw-live");
    for (var i = 0; i < stale.length; i++) stale[i].remove();
    (list || []).forEach(function (item) {
      if (item.tag !== "draw" || !item.points || !item.points.length) return;
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", drawPathD(item.points));
      path.setAttribute("class", "dpb-draw-path");
      path.setAttribute("data-draw-n", String(item.n));
      drawSvg.appendChild(path);
      var p0 = item.points[0];
      var g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "dpb-draw-badge");
      g.setAttribute("transform", "translate(" + Number(p0[0]).toFixed(1) + "," + Math.max(9, Number(p0[1]) - 12).toFixed(1) + ")");
      var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", "9");
      c.setAttribute("class", "dpb-draw-badge-c");
      var t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("dy", "3.2");
      t.textContent = String(item.n);
      g.appendChild(c); g.appendChild(t);
      drawSvg.appendChild(g);
    });
  }

  window.addEventListener("message", function (e) {
    // W3: only the parent window may drive the bridge. The prototype scripts
    // share this window and must not be able to spoof pin state or badges.
    if (e.source !== window.parent) return;
    var data = e.data;
    if (!data) return;
    if (data.dpbPinState) {
      // #56: parent is the single owner of the pin state.
      pinOn = !!data.dpbPinState.on;
      if (!pinOn) clearHover();
      return;
    }
    if (data.dpbDrawState) {
      // Draw mode mirrors pin ownership: the parent flips it, the bridge
      // only obeys. OFF means fully passive - pointer events pass through.
      setDrawOn(!!data.dpbDrawState.on);
      return;
    }
    if (data.dpbPinLocate) {
      var locEl = findEl(String(data.dpbPinLocate.selector || ""));
      if (locEl) locateEl(locEl);
      return;
    }
    if (data.dpbDrawLocate) {
      var targetN = String(data.dpbDrawLocate.n || "");
      var targetPath = drawSvg ? drawSvg.querySelector('.dpb-draw-path[data-draw-n="' + targetN + '"]') : null;
      if (targetPath) {
        targetPath.classList.remove("dpb-draw-flash");
        void targetPath.offsetWidth;
        targetPath.classList.add("dpb-draw-flash");
      }
      for (var di = 0; di < (lastAnchorEcho || []).length; di++) {
        var dItem = lastAnchorEcho[di];
        if (dItem.tag === "draw" && String(dItem.n) === targetN && dItem.points && dItem.points[0]) {
          try {
            window.scrollTo({
              left: Math.max(0, Number(dItem.points[0][0]) - 100),
              top: Math.max(0, Number(dItem.points[0][1]) - 100),
              behavior: "smooth"
            });
          } catch (err) {}
          break;
        }
      }
      return;
    }
    if (data.dpbPinFlash) {
      var flashTarget = findEl(String(data.dpbPinFlash.selector || ""));
      if (flashTarget) flashEl(flashTarget);
      return;
    }
    if (data.dpbPinNote) {
      // #57: one badge note updated in place — per-keystroke comment edits
      // must not clear and rebuild the whole badge set.
      var noteSel = String(data.dpbPinNote.selector || "");
      var pair = badgeMap[noteSel];
      if (pair) {
        var noteText = String(data.dpbPinNote.comment || "");
        pair.note.textContent = noteText;
        pair.note.style.display = noteText ? "block" : "none";
        placeBadge({ selector: noteSel });
      }
      return;
    }
    if (Array.isArray(data.dpbPinAnchors)) {
      syncAnchors(data.dpbPinAnchors);
    }
  });
  // Ask the parent for a pin-state resend after (re)load so a refresh never
  // strands the bridge in the wrong mode.
  parent.postMessage({ dpbPinHello: true }, "*");
})();
</script>"""


def _build_parent_page(prototype_html: str, control_html: str) -> str:
    """Build the trusted parent document (G5 trust boundary).

    The parent renders only the control bar; the prototype is isolated inside
    ``<iframe sandbox="allow-scripts" srcdoc="...">``. ``allow-same-origin`` is
    deliberately omitted so the iframe is treated as a unique opaque origin and
    prototype scripts cannot reach the parent DOM — where the one-time decision
    token lives as a hidden form field.

    The pin-to-annotate bridge (``BRIDGE_SCRIPT``) is appended to the prototype
    BEFORE escaping so it executes inside the iframe document, where it can see
    the prototype DOM. While pin mode is on it captures clicks/hover, computes
    a cssPath selector on its own side of the trust boundary, and postMessages
    ``{selector, tag}`` to the parent — restoring anchor collection that G5's
    cross-origin boundary took away (the parent can no longer see iframe clicks
    or traverse iframe DOM). The parent pushes the pin state back down
    (``dpbPinState``) so the bridge only intercepts while the user is actually
    picking (#56), and drives cross-origin locate/badges (``dpbPinLocate`` /
    ``dpbPinAnchors``, #57 scheme A). The bridge never touches
    ``parent.document`` or the token; postMessage is its only outbound channel
    (verified by test_browser_control).
    """
    # html.escape neutralizes every </script> (and quote) in both the prototype
    # and the bridge trailer to entity form inside the srcdoc ATTRIBUTE, so the
    # prototype's own script boundaries cannot leak across and truncate the
    # bridge. The browser decodes the entities when rendering the iframe
    # document, restoring the original <script>...</script> blocks. This is the
    # attribute-escaping context (safe); it is NOT the inline-<script> context
    # where </script> would need splitting.
    srcdoc = html.escape(prototype_html + BRIDGE_SCRIPT, quote=True)
    # String concatenation (not .format): the CSS braces are literal here, and
    # concatenation sidesteps the format()-on-HTML brace-escaping trap.
    return (
        '<!DOCTYPE html><html lang="' + lang() + '"><head>'
        '<meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
        '<title>preview</title>'
        "<style>"
        "html,body{margin:0;padding:0;height:100%;background:#0f1218;}"
        ".dpb-proto-frame{position:fixed;inset:0;width:100%;height:100%;"
        "border:0;background:#ffffff;}"
        # Third state: while the drawer is open the 48px topbar (part of the
        # injected control html) owns the strip across the top; the prototype
        # frame dodges it so nothing clickable hides underneath (fixes #04).
        "body.dpb-workspace .dpb-proto-frame{top:48px;height:calc(100% - 48px);}"
        "</style></head><body>"
        + control_html
        + '<iframe class="dpb-proto-frame" sandbox="allow-scripts" srcdoc="'
        + srcdoc
        + '" title="prototype"></iframe>'
        + "</body></html>"
    )


def collect_review(
        prototype: Path, summary: str, options: list[str],
        round_n: int,
        browser_adapter: BrowserInteraction | None = None,
) -> dict[str, Any]:
    """Serve prototype + control form; block until user submits or aborts."""
    adapter = browser_adapter or OwnedBrowserAdapter()
    result: dict[str, Any] = {
        "choice": "",
        "feedback": "",
        "aborted": True,
        "anchors": [],
    }
    done = threading.Event()

    # TOCTOU fix: read bytes once, hash (LF-normalized), then decode for display
    raw_bytes = prototype.read_bytes()
    prototype_html_hash = prototype_html_digest(raw_bytes)
    prototype_html = raw_bytes.decode("utf-8")
    result["prototype_html_hash"] = prototype_html_hash

    def with_prototype_hash(submission: dict[str, Any]) -> dict[str, Any]:
        submission["prototype_html_hash"] = prototype_html_hash
        return submission

    control = _build_control(round_n, summary.strip(), options)
    # G5 trust boundary: one-time token + first-decision-wins session. The
    # token renders as a hidden field in the PARENT control form (trusted);
    # the sandboxed prototype iframe cannot read it, so a forged
    # fetch('/decide', ...) arrives without proof and fails closed.
    token = _generate_decision_token()
    control = _inject_token_fields(control, token, round_n)
    page = _build_parent_page(prototype_html, control)
    session = _DecisionSession(round_n, token)

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
            try:
                posted_round = int((form.get("dpb_round") or [""])[0])
            except (ValueError, TypeError):
                posted_round = -1
            anchors = _parse_anchors(
                (form.get("anchors_json") or ["[]"])[0], posted_round)
            # G5: validate the one-time decision token before trusting choice.
            # A sandboxed prototype cannot read the hidden token, so a forged
            # fetch('/decide', ...) arrives without it and fails closed.
            posted_token = (form.get("dpb_token") or [None])[0]
            validated = session.validate(posted_round, posted_token)
            if not validated:
                # Fail closed: missing / reused / mismatched token -> NOT confirmed.
                # First-decision-wins also guards the shared ``result`` slot:
                # once a valid POST owns the result, a later rejected POST (replay,
                # mismatch) must NOT clobber it — otherwise a double-click or
                # browser retry after a valid confirm overwrites the confirmed
                # result with an aborted/rejected one and G5 fails despite the
                # user's confirm. Only mutate ``result`` before any valid
                # decision has landed (session not yet locked).
                if not session.locked:
                    result = with_prototype_hash({
                        "choice": "",
                        "feedback": feedback,
                        "aborted": True,
                        "anchors": anchors,
                        "rejected": True,
                        "rejection": session.last_rejection,
                    })
            else:
                result = with_prototype_hash({
                    "choice": choice,
                    "feedback": feedback,
                    "aborted": choice == "__abort__",
                    "anchors": anchors,
                })
            reply = _done_page_html()
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(reply)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(reply)
            self.wfile.flush()
            # MEDIUM-1 (secure-ship-0.4.4) anti-DoS: only end the session when
            # the POST proves trusted-form origin — validated (first valid
            # decision) OR carried a dpb_token at all (real control-form
            # submit, even on replay/mismatch). A forged cross-origin fetch
            # arrives with no token (sandboxed iframe cannot read the hidden
            # field); responding 200 keeps it quiet, but the server stays
            # alive so the real user can still confirm. Unconditional
            # done.set() here let one forged POST abort every preview before
            # the user clicked anything. Fail-closed semantics above are
            # unchanged — only session termination is now gated.
            if validated:
                done.set()

    _preview_port = int(os.environ.get("DESIGN_PLAYBOOK_PREVIEW_PORT", "0"))
    server = HTTPServer(("127.0.0.1", _preview_port), Handler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, name="dpb-preview-http", daemon=True
    )
    thread.start()
    url = f"http://127.0.0.1:{port}/"
    _log(f"preview UI at {url}")
    handle = adapter.open(url)
    try:
        if not done.wait(timeout=1800):
            result = with_prototype_hash({
                "choice": "",
                "feedback": "timeout waiting for user",
                "aborted": True,
                "anchors": [],
            })
    finally:
        # Close the owned Chromium first so keep-alive sockets cannot block
        # HTTPServer.shutdown; the response is already flushed before
        # done.set(). The adapter hides window-hide + process kill + profile
        # cleanup behind the seam; HTTP stop stays here so a bound MCP call
        # always returns even if the adapter raises.
        try:
            adapter.close(handle)
        finally:
            _stop_http_server(server, thread, timeout_s=1.5)
    return result

