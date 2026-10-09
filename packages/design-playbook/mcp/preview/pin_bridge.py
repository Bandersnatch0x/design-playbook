"""Pin-to-annotate bridge injected into the sandboxed prototype iframe (G5).

G5 isolated the prototype inside ``<iframe sandbox="allow-scripts" srcdoc=...>``
with allow-same-origin DELIBERATELY omitted, so the iframe is an opaque
origin and prototype scripts cannot reach the parent DOM (where the decision
token lives). That broke pin-to-annotate: the parent's document.click +
cssPath(e.target) can no longer see clicks inside the iframe or traverse the
iframe DOM (cross-origin). This bridge runs INSIDE the iframe document and
restores anchor collection by postMessaging {selector, tag} to the parent.

Pin-state sync (#56): the parent owns pinOn and pushes it down via
postMessage {dpbPinState:{on}} (on every toggle + iframe load). The bridge
gates its capture-phase click/mousemove listeners on that state: while pin
is OFF the prototype receives clicks and hover exactly as if the bridge were
not injected (no preventDefault/stopPropagation, no dashed outline); while
ON it keeps the capture behaviour (anchor + highlight + dashed hover).

Cross-origin locate + numbered badges (#57, scheme A): the parent drives
{dpbPinLocate:{selector}} (scrollIntoView + flash), {dpbPinFlash:{selector}}
(duplicate-pick feedback) and {dpbPinAnchors:[{selector,n,comment}]} (in-
frame numbered badges mirroring the same-origin float-notes) into the iframe.

G5 safety contract (verified by test_browser_control.PinAnnotationBridgeTests):
  - the bridge only postMessages anchor DATA ({selector, tag}) — it never
    reads parent.document, parent.location, the token, or storage, and it
    never fetches/XHRs. postMessage is its only outbound channel.
  - the parent additionally records anchors only while pin mode is on
    (control.js message listener filters on pinOn) — defense in depth.
  - the iframe highlights the clicked element itself (dpb-pin-target) since
    the parent cannot reach into the iframe DOM to do it.

The script body ships as ``pin_bridge.js`` beside this module and is loaded at
import like control.py's frontend resources. The label substitution is plain
string concatenation (not .format), so JS braces stay literal. cssPath is a
faithful copy of control.py's cssPath so selectors match the same-origin path.
"""

from __future__ import annotations

import json
from pathlib import Path

from design_playbook.mcp.preview.i18n import ZH, _STRINGS

HERE = Path(__file__).resolve().parent


def _load_bridge_script() -> str:
    """Load the bridge script bundled beside this module."""
    try:
        return (HERE / "pin_bridge.js").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Failed to load the pin bridge from {HERE}") from exc


BRIDGE_SCRIPT = _load_bridge_script()


BRIDGE_SCRIPT = BRIDGE_SCRIPT.replace("__DPB_VISUAL_LABELS__", json.dumps(
    {key: value for key, value in _STRINGS[ZH].items() if key.startswith("visual_")},
    ensure_ascii=True,
))

def build_visual_edit_bridge_script() -> str:
    """Host opt-in: embed this script in the loopback page used as live_route_url.

    Only the sandbox parent can issue preview commands. This never writes host
    source; include the bridge before starting a review so served bytes stay stable.
    """
    return BRIDGE_SCRIPT
