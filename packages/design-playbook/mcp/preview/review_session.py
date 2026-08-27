"""Authenticated Preview review behind one deep interface.

Opens a centered app window, serves the prototype and trusted control bar,
authenticates one raw submission, and tears down browser and server without
hanging on keep-alive sockets. Decision authority and floor logic belong to
transaction.py.

The owned-Chromium lifecycle lives in ``owned_browser.py`` and the injected
iframe bridge in ``pin_bridge.py``; both are re-exported here so existing
``review_session.<name>`` import paths keep working (#91).
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from design_playbook.mcp.preview.control import _build_control
from design_playbook.mcp.preview.i18n import lang, t
from design_playbook.mcp.preview.integrity import prototype_html_digest
from design_playbook.mcp.preview.owned_browser import (  # noqa: F401
    BrowserInteraction,
    OwnedBrowserAdapter,
    _browser_candidates,
    _kill_browser_proc,
    _open_preview_window,
    _request_browser_window_close,
    _rm_tree,
    _screen_size,
)
from design_playbook.mcp.preview.pin_bridge import BRIDGE_SCRIPT
from design_playbook.mcp.util import log as _log

__all__ = [
    "BRIDGE_SCRIPT",
    "BrowserInteraction",
    "OwnedBrowserAdapter",
    "collect_review",
]

# Stage 9 static-handoff disclosure contract (imported lazily inside the
# /export-zip + /disclosure-review.json handlers so the stdio server does not
# pay the import cost and tests can stub it).


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
    return hashlib.sha256(f"{round_n}|{index}|{selector}".encode("utf-8")).hexdigest()[
        :8
    ]


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


# Cap shared with the control.js / bridge capture paths: a longer posted
# stroke is truncated rather than rejected (the annotation stays usable).
_DRAW_POINTS_MAX = 512


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
        if item.get("resolved") is True:
            # Only the exact boolean counts: a truthy string must not silently
            # mark a reviewer's open item as resolved.
            anchor["resolved"] = True
        if "points" in item and isinstance(item["points"], list):
            # Malformed entries are skipped, never fatal: a bad float must
            # not 500 the POST handler (that hangs the session to timeout).
            pts: list[list[float]] = []
            for p in item["points"]:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                try:
                    pts.append([float(p[0]), float(p[1])])
                except (TypeError, ValueError):
                    continue
            if pts:
                anchor["points"] = pts[:_DRAW_POINTS_MAX]
        rect = item.get("rect")
        if isinstance(rect, dict):
            try:
                parsed_rect = {
                    "x": float(rect.get("x")),
                    "y": float(rect.get("y")),
                    "width": float(rect.get("width")),
                    "height": float(rect.get("height")),
                }
            except (TypeError, ValueError):
                parsed_rect = None
            if parsed_rect and all(math.isfinite(v) for v in parsed_rect.values()):
                if parsed_rect["width"] > 0 and parsed_rect["height"] > 0:
                    anchor["rect"] = parsed_rect
        if round_n > 0:
            anchor["node_id"] = _anchor_node_id(round_n, index, selector)
            anchor["features"] = _anchor_features(item, tag)
        out.append(anchor)
    return out[:40]


def _parse_criteria_review(raw: str) -> list[dict[str, Any]]:
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
        criterion_id = str(item.get("id") or "").strip()
        if not criterion_id:
            continue
        out.append({
            "id": criterion_id[:120],
            "title": str(item.get("title") or "").strip()[:240],
            "checked": item.get("checked") is True,
        })
    return out[:80]


def _done_page_html() -> bytes:
    # Owned Chromium is killed by the server after submit; JS is best-effort only.
    # Use unique %markers + str.replace (not .format) so the CSS/JS braces don't
    # need escaping.
    html_text = """<!DOCTYPE html><html lang="%html_lang%"><head><meta charset="utf-8"/>
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
    return (
        html_text.replace("%html_lang%", lang())
        .replace("%done_title%", t("done_title"))
        .replace("%done_body%", t("done_body"))
    ).encode("utf-8")


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


def _build_parent_page(prototype_html: str, control_html: str) -> str:
    """Build the trusted parent document (G5 trust boundary).

    The parent renders only the control bar; the prototype is isolated inside
    ``<iframe sandbox="allow-scripts" srcdoc="...">``. ``allow-same-origin`` is
    deliberately omitted so the iframe is treated as a unique opaque origin and
    prototype scripts cannot reach the parent DOM — where the one-time decision
    token lives as a hidden form field.

    The pin-to-annotate bridge (``BRIDGE_SCRIPT``, pin_bridge.py) is appended
    to the prototype BEFORE escaping so it executes inside the iframe document,
    where it can see the prototype DOM. While pin mode is on it captures
    clicks/hover, computes a cssPath selector on its own side of the trust
    boundary, and postMessages ``{selector, tag}`` to the parent — restoring
    anchor collection that G5's cross-origin boundary took away (the parent
    can no longer see iframe clicks or traverse iframe DOM). The parent pushes
    the pin state back down (``dpbPinState``) so the bridge only intercepts
    while the user is actually picking (#56), and drives cross-origin
    locate/badges (``dpbPinLocate`` / ``dpbPinAnchors``, #57 scheme A). The
    bridge never touches ``parent.document`` or the token; postMessage is its
    only outbound channel (verified by test_browser_control).
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
        "<title>preview</title>"
        "<style>"
        "html,body{margin:0;padding:0;height:100%;background:#0f1218;}"
        # v9 shell: the control script relocates the frame into the artboard
        # (#dpb-artboard-inner); until then it stays out of the layout so the
        # shell paints first without a full-viewport flash.
        ".dpb-proto-frame{display:none;}"
        "</style></head><body>"
        + control_html
        + '<iframe class="dpb-proto-frame" sandbox="allow-scripts" srcdoc="'
        + srcdoc
        + '" title="prototype"></iframe>'
        + "</body></html>"
    )


def collect_review(
    prototype: Path,
    summary: str,
    options: list[str],
    round_n: int,
    browser_adapter: BrowserInteraction | None = None,
    *,
    criteria: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Serve prototype + control form; block until user submits or aborts.

    Stage 6 only (ADR-0034): this owns the review round - the page, the
    one-time decision token, and the teardown of browser and server. The
    Stage 9 static handoff is a separate Evidence-owned projection built
    from durable run artifacts by ``mcp/evidence/handoff.py``; it shares
    no process, port, or lifecycle with this session.
    """
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

    control = _build_control(round_n, summary.strip(), options, criteria=criteria)
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
            # Stage 6 only (ADR-0034): the review page. Delivery routes
            # (/static-handoff, /export-zip, /disclosure-review.json) are gone
            # with the Stage 9 handoff - served nowhere near this server.
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
                (form.get("anchors_json") or ["[]"])[0], posted_round
            )
            criteria_review = _parse_criteria_review(
                (form.get("criteria_json") or ["[]"])[0]
            )
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
                    result = with_prototype_hash(
                        {
                            "choice": "",
                            "feedback": feedback,
                            "aborted": True,
                            "anchors": anchors,
                            "criteria_review": criteria_review,
                            "rejected": True,
                            "rejection": session.last_rejection,
                        }
                    )
            else:
                result = with_prototype_hash(
                    {
                        "choice": choice,
                        "feedback": feedback,
                        "aborted": choice == "__abort__",
                        "anchors": anchors,
                        "criteria_review": criteria_review,
                    }
                )
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
            result = with_prototype_hash(
                {
                    "choice": "",
                    "feedback": "timeout waiting for user",
                    "aborted": True,
                    "anchors": [],
                }
            )
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
