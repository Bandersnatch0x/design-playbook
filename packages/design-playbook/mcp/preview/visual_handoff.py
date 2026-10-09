"""Source-backed handoff projection for pending Preview visual edits."""
from __future__ import annotations

from typing import Any

from design_playbook.mcp.preview.visual_batch import VisualBatchError, validate_batch_current


class VisualHandoffError(ValueError):
    """Raised when a coding-agent handoff cannot be trusted."""


def build_agent_handoff(
    batch: dict[str, Any],
    *,
    current_source_hash: str,
    route_url: str = "",
) -> dict[str, Any]:
    """Build a review-only handoff; never marks source write as authorized."""
    try:
        validate_batch_current(batch, current_source_hash, current_route_url=route_url)
    except (VisualBatchError, TypeError) as exc:
        raise VisualHandoffError(str(exc)) from exc
    return {
        "schemaVersion": 1,
        "kind": "preview-visual-edit-handoff",
        "status": "pending-review",
        "requiresUserConfirmation": True,
        "sourceHash": current_source_hash,
        "routeUrl": route_url,
        "batchHash": batch["batchHash"],
        "edits": list(batch.get("edits") or []),
        "nextAction": "coding-agent-review-diff",
        "writesSource": False,
    }
