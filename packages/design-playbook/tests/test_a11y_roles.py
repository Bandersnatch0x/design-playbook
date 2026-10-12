"""U-14: ARIA roles match the widgets they sit on."""
from __future__ import annotations

import re
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
_WB = _PKG.parent / "design-playbook-workbench" / "design_playbook_workbench" / "web"
CONTROL_HTML = (_PKG / "mcp/preview/control.html").read_text(encoding="utf-8")
CONTROL_JS = (_PKG / "mcp/preview/control.js").read_text(encoding="utf-8")
RC_HTML = (_PKG / "mcp/run_console/app.html").read_text(encoding="utf-8")
WB_HTML = (_WB / "app.html").read_text(encoding="utf-8")
BRIDGE_JS = (_PKG / "mcp/preview/pin_bridge.js").read_text(encoding="utf-8")
I18N = (_PKG / "mcp/preview/i18n.py").read_text(encoding="utf-8")


def test_no_tablist_wraps_pressed_buttons():
    for tag in re.findall(r'<div class="dpb-filter-tabs"[^>]*>', CONTROL_HTML):
        assert 'role="tablist"' not in tag
    block = CONTROL_HTML.split('class="dpb-filter-tabs"', 1)[1].split("</div>", 1)[0]
    assert "aria-pressed" in block
    assert 'role="group"' in CONTROL_HTML.split('class="dpb-filter-tabs"', 1)[1][:80] or \
        'role="group"' in CONTROL_HTML.split('class="dpb-filter-tabs"', 1)[0][-80:]


def test_toolbar_role_with_roving_tabindex():
    assert 'role="toolbar"' in CONTROL_HTML
    assert not re.search(r'<nav[^>]*id="dpb-toolbar"', CONTROL_HTML)
    assert "dpb-toolbar" in CONTROL_JS and "tabindex" in CONTROL_JS.split("dpb-toolbar", 1)[1]


def test_run_console_main_is_not_live_region():
    main = re.search(r"<main[^>]*>", RC_HTML).group(0)
    assert "role=" not in main and "aria-live" not in main


def test_workbench_canvas_is_not_application():
    assert 'role="application"' not in WB_HTML


def test_slider_valuetext_comes_from_language_table():
    assert 'text("visual_color_value"' in BRIDGE_JS
    assert '"Saturation "' not in BRIDGE_JS
    assert I18N.count('"visual_color_value"') == 2
