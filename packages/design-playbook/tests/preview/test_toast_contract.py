"""U-15: toasts carry only errors and results that need acknowledging."""
import re
from pathlib import Path

PREVIEW = Path(__file__).resolve().parents[2] / "mcp" / "preview"
SRC = "\n".join((PREVIEW / n).read_text(encoding="utf-8") for n in ("control.js", "control.review.js"))
TRIVIAL = ("toast_vp", "toast_mode_", "tool_draw", "tool_box", "tool_ruler", "tool_hand",
           "toast_drawer_", "toast_lang", "toast_focus", "toast_reopened", "toast_resolved")


def test_trivial_state_changes_do_not_toast():
    calls = re.findall(r"\btoast\((.*)\)", SRC)
    for call in calls:
        for key in TRIVIAL:
            assert key not in call, call


def test_toast_has_role_duration_hover_pause_and_single_slot():
    body = re.search(r"function toast\(.*?\n  \}\n", SRC, re.S)
    assert body, "toast() missing"
    text = body.group(0)
    assert "role" in text and "status" in text and "alert" in text
    assert "mouseenter" in text and "focusin" in text
    assert "TOAST_MS = 5000" in SRC and "TOAST_ACTION_MS = 10000" in SRC
    assert "2400" not in text
    assert "removeChild" in text and "firstChild" in text or "replaceChildren" in text
