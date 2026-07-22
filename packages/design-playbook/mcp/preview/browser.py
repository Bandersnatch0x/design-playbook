"""Owned-Chromium preview window + local HTTP decide form.

Sibling module split from server.py; behavior unchanged. Opens a centered
app window, serves the prototype + injected control bar over a one-shot
HTTP server, classifies the POSTed decision, applies the ADR-0008 floor,
and tears down the browser + server without hanging on keep-alive sockets.
"""
from __future__ import annotations

import ctypes
import html
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

from confirm import _DecisionSession, _check_feedback_floor, _generate_decision_token
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
# G5 safety contract (verified by test_browser_control.PinAnnotationBridgeTests):
#   - the bridge only postMessages anchor DATA ({selector, tag}) — it never
#     reads parent.document, parent.location, the token, or storage, and it
#     never fetches/XHRs. postMessage is its only outbound channel.
#   - the parent records the anchor only while pin mode is on (control.py
#     message listener filters on pinOn), so no pin-state sync is needed.
#   - the iframe highlights the clicked element itself (dpb-pin-target) since
#     the parent cannot reach into the iframe DOM to do it.
#
# Raw string + single braces: this is plain string concatenation (not .format),
# so JS braces stay literal (no {{ doubling). cssPath is a faithful copy of
# control.py's cssPath so selectors match the same-origin path.
BRIDGE_SCRIPT = r"""<script>
(function () {
  // Inject the pin highlight CSS into the iframe document. The parent's
  // control-bar stylesheet does not cross the iframe boundary, so the bridge
  // brings its own copy of .dpb-pin-target / .dpb-pin-hover (the same rules
  // control.py renders in the parent) to actually show the highlight in-frame.
  var style = document.createElement("style");
  style.textContent =
    ".dpb-pin-target{outline:1.5px solid rgba(20,184,166,.9)!important;" +
    "outline-offset:1px!important;background-color:rgba(20,184,166,.06)!important;" +
    "cursor:crosshair!important}" +
    ".dpb-pin-hover{outline:1px dashed rgba(20,184,166,.45)!important;" +
    "outline-offset:1px!important}";
  (document.head || document.documentElement).appendChild(style);

  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + CSS.escape(el.id);
    var parts = [];
    var cur = el;
    var depth = 0;
    while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {
      if (cur.id === "dpb-preview-bar" || cur.id === "dpb-preview-spacer" || cur.id === "dpb-float-root") break;
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
    var el = e.target;
    if (!el || el === document.body || el === document.documentElement) return;
    e.preventDefault();
    e.stopPropagation();
    var prev = document.querySelector(".dpb-pin-target");
    if (prev && prev !== el) prev.classList.remove("dpb-pin-target");
    el.classList.add("dpb-pin-target");
    var selector = cssPath(el);
    if (!selector) return;
    parent.postMessage({ dpbPinAnchor: { selector: selector, tag: el.tagName.toLowerCase() } }, "*");
  }, true);
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
    the prototype DOM. It captures clicks/hover, computes a cssPath selector
    on its own side of the trust boundary, and postMessages ``{selector, tag}``
    to the parent — restoring anchor collection that G5's cross-origin boundary
    took away (the parent can no longer see iframe clicks or traverse iframe
    DOM). The bridge never touches ``parent.document`` or the token; postMessage
    is its only outbound channel (verified by test_browser_control).
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
        "</style></head><body>"
        + control_html
        + '<iframe class="dpb-proto-frame" sandbox="allow-scripts" srcdoc="'
        + srcdoc
        + '" title="prototype"></iframe>'
        + "</body></html>"
    )


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

    # TOCTOU fix: read bytes once, hash, then decode for display
    raw_bytes = prototype.read_bytes()
    prototype_html_hash = hashlib.sha256(raw_bytes).hexdigest()
    prototype_html = raw_bytes.decode("utf-8")
    result["prototype_html_hash"] = prototype_html_hash

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
            anchors = _parse_anchors((form.get("anchors_json") or ["[]"])[0])
            # G5: validate the one-time decision token before trusting choice.
            # A sandboxed prototype cannot read the hidden token, so a forged
            # fetch('/decide', ...) arrives without it and fails closed.
            try:
                posted_round = int((form.get("dpb_round") or [""])[0])
            except (ValueError, TypeError):
                posted_round = -1
            posted_token = (form.get("dpb_token") or [None])[0]
            validated = session.validate(posted_round, posted_token)
            if not validated:
                # Fail closed: missing / reused / mismatched token -> NOT confirmed.
                result = {
                    "confirmed": False,
                    "selected_options": [],
                    "feedback": feedback,
                    "aborted": True,
                    "anchors": anchors,
                    "rejected": True,
                    "rejection": session.last_rejection,
                }
            elif choice == "__abort__":
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
    if result.get("rejected"):
        # G5 fail-closed: an untrusted decision never passes the floor, even
        # if the forged payload happened to carry substantive feedback.
        result["floor_pass"] = False
    else:
        floor_pass, floor_failure = _check_feedback_floor(raw_feedback, raw_anchors)
        result["floor_pass"] = floor_pass
        if not floor_pass:
            result["floor_failure"] = floor_failure
    # merge anchors into feedback for log readability
    result["feedback"] = _format_feedback(raw_feedback, raw_anchors)
    return result

