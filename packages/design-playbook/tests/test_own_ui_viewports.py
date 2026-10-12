"""U-22: the plugin's own UI declares its target viewports and never hides a scrollbar."""
import json
import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
LEDGER = PKG / "examples" / "self-audit" / "baseline.json"
CSS = PKG / "mcp" / "preview" / "control.css"


def test_ledger_declares_target_viewports():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert ledger.get("viewports") == [1280, 1024, 768]


def test_no_hidden_scrollbar_in_preview_css():
    assert not re.search(r"scrollbar-width\s*:\s*none", CSS.read_text(encoding="utf-8"))
