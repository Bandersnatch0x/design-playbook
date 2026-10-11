"""U-21: Preview shows a retry button when the editor bridge never connects."""
from __future__ import annotations

from pathlib import Path

MCP = Path(__file__).resolve().parents[2] / "mcp" / "preview"


def test_disconnected_state_offers_retry():
    js = (MCP / "control.react.js").read_text(encoding="utf-8")
    assert 'visual_retry' in js
    assert 'frame.dispatchEvent(new Event("load"))' in js
    i18n = (MCP / "i18n.py").read_text(encoding="utf-8")
    assert i18n.count('"visual_retry"') == 2
