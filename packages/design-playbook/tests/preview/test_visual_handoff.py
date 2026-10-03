from __future__ import annotations

import pytest

from design_playbook.mcp.preview.visual_batch import normalize_visual_batch
from design_playbook.mcp.preview.visual_handoff import (
    VisualHandoffError,
    build_agent_handoff,
    confirm_agent_handoff,
)


def _batch() -> dict:
    return normalize_visual_batch({
        "edits": [{
            "locator": "#hero",
            "property": "padding",
            "oldValue": "8px",
            "newValue": "16px",
        }],
    }, source_hash="source-v1", route_url="http://127.0.0.1:5173/")


def test_handoff_is_pending_review_and_never_source_write() -> None:
    handoff = build_agent_handoff(_batch(), current_source_hash="source-v1", route_url="http://127.0.0.1:5173/")
    assert handoff["status"] == "pending-review"
    assert handoff["requiresUserConfirmation"] is True
    assert handoff["writesSource"] is False
    assert handoff["nextAction"] == "coding-agent-review-diff"


def test_handoff_confirmation_requires_fresh_source() -> None:
    handoff = build_agent_handoff(_batch(), current_source_hash="source-v1", route_url="http://127.0.0.1:5173/")
    with pytest.raises(VisualHandoffError, match="stale"):
        confirm_agent_handoff(handoff, current_source_hash="source-v2")
    confirmed = confirm_agent_handoff(handoff, current_source_hash="source-v1")
    assert confirmed["status"] == "confirmed-for-agent"
    assert confirmed["writesSource"] is False


def test_handoff_rejects_a_different_current_route() -> None:
    with pytest.raises(VisualHandoffError, match="route"):
        build_agent_handoff(_batch(), current_source_hash="source-v1", route_url="http://127.0.0.1:5173/other")
