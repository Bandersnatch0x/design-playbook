"""Preview visual-edit batch contract.

React and optional WebMCP callers both emit this shape. The batch is pending
until an existing transaction/coding-agent flow confirms it; this module never
writes host source files.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 1
MAX_EDITS = 200
MAX_SELECTOR = 512
MAX_VALUE = 2000
_PROPERTY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
# Change families one batch can carry. `style`/`layout`/`responsive` carry a CSS
# property; `content` carries text; `structure` is a declarative intent that
# still needs an explicit source locator before any write.
CHANGE_KINDS = ("style", "layout", "content", "responsive", "structure")
CONTENT_PROPERTIES = ("text", "placeholder", "aria-label")
VIEWPORTS = ("desktop", "tablet", "mobile", "any")
# A locator addresses an element inside the reviewed artifact. Anything that
# looks like a filesystem path, URL scheme, or traversal target is rejected so a
# hostile page cannot smuggle a host path into a coding-agent handoff.
_FORBIDDEN_LOCATOR_PARTS = ("..", "\\", "file:", "about:", "javascript:")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class VisualBatchError(ValueError):
    """Raised when a visual-edit batch is malformed or stale."""


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualBatchError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > limit:
        raise VisualBatchError(f"{field} exceeds {limit} characters")
    return value


def _locator(value: Any) -> str:
    locator = _text(value, "locator", MAX_SELECTOR)
    folded = locator.casefold()
    for part in _FORBIDDEN_LOCATOR_PARTS:
        if part in folded:
            raise VisualBatchError("locator must be an element selector")
    if _DRIVE_PREFIX_RE.match(locator) or locator.startswith("/"):
        raise VisualBatchError("locator must be an element selector")
    return locator


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def batch_digest(batch: dict[str, Any]) -> str:
    payload = dict(batch)
    payload.pop("batchHash", None)
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def normalize_visual_batch(
    raw: Any,
    *,
    source_hash: str,
    route_url: str = "",
) -> dict[str, Any]:
    """Validate and normalize pending edits against the served source hash."""
    if not isinstance(raw, dict):
        raise VisualBatchError("visual edit batch must be an object")
    if raw.get("schemaVersion", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise VisualBatchError("unsupported visual edit batch schema")
    if not isinstance(source_hash, str) or not source_hash.strip():
        raise VisualBatchError("source_hash is required")
    if raw.get("status", "pending") != "pending":
        raise VisualBatchError("visual edit batch is stale or no longer pending")
    if "sourceHash" in raw and raw["sourceHash"] != source_hash:
        raise VisualBatchError("visual edit batch is stale")
    if "routeUrl" in raw and raw["routeUrl"] != route_url:
        raise VisualBatchError("visual edit batch route is stale")
    if "batchHash" in raw:
        validate_batch_current(raw, source_hash, current_route_url=route_url)
    edits = raw.get("edits", [])
    if not isinstance(edits, list):
        raise VisualBatchError("edits must be an array")
    if len(edits) > MAX_EDITS:
        raise VisualBatchError(f"edits cannot contain more than {MAX_EDITS} items")

    normalized: list[dict[str, str]] = []
    for item in edits:
        if not isinstance(item, dict):
            raise VisualBatchError("each visual edit must be an object")
        kind = str(item.get("kind") or "style").strip()
        if kind not in CHANGE_KINDS:
            raise VisualBatchError(
                f"kind must be one of {', '.join(CHANGE_KINDS)}"
            )
        viewport = str(item.get("viewport") or "any").strip()
        if viewport not in VIEWPORTS:
            raise VisualBatchError(f"viewport must be one of {', '.join(VIEWPORTS)}")
        property_name = _text(item.get("property"), "property", 64)
        if not _PROPERTY_RE.fullmatch(property_name):
            raise VisualBatchError("property contains unsupported characters")
        if kind == "content" and property_name not in CONTENT_PROPERTIES:
            raise VisualBatchError(
                f"content edits must target one of {', '.join(CONTENT_PROPERTIES)}"
            )
        normalized.append({
            "kind": kind,
            "viewport": viewport,
            # `selector` is accepted as the browser-side alias: the bridge
            # captures DOM selectors, the batch contract calls them locators.
            "locator": _locator(item.get("locator") or item.get("selector")),
            "property": property_name,
            "oldValue": str(item.get("oldValue") or "")[:MAX_VALUE],
            "newValue": str(item.get("newValue") or "")[:MAX_VALUE],
        })

    batch: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "status": "pending",
        "sourceHash": source_hash,
        "routeUrl": str(route_url or "")[:2000],
        "edits": normalized,
    }
    batch["batchHash"] = batch_digest(batch)
    if "batchHash" in raw and raw != batch:
        raise VisualBatchError("visual edit batch canonical shape mismatch")
    return batch


def has_effective_visual_edits(batch: dict[str, Any]) -> bool:
    """Read net change from a validated batch, excluding no-ops and undone chains.

    The net-effect key deliberately omits ``viewport``. The editor has one shared
    DOM, so a change made while "desktop" is selected and its reversal while
    "mobile" is selected act on the same element; keying by viewport would count
    that round trip as two effective changes and let a zero-net-change round
    confirm. Viewport stays on each edit as provenance, not as identity.
    """
    values: dict[tuple[str, str, str], tuple[str, str]] = {}
    for edit in batch.get("edits", []):
        key = (edit["kind"], edit["locator"], edit["property"])
        original = values[key][0] if key in values else edit["oldValue"]
        values[key] = (original, edit["newValue"])
    return any(original != final for original, final in values.values())


def validate_batch_current(
    batch: dict[str, Any], current_source_hash: str, *, current_route_url: str | None = None,
) -> None:
    """Fail closed when source bytes changed after visual edits were staged."""
    if not isinstance(batch, dict) or batch.get("schemaVersion") != SCHEMA_VERSION:
        raise VisualBatchError("visual edit batch is malformed")
    if batch.get("sourceHash") != current_source_hash:
        raise VisualBatchError("visual edit batch is stale")
    if current_route_url is not None and batch.get("routeUrl") != current_route_url:
        raise VisualBatchError("visual edit batch route is stale")
    expected = batch_digest(batch)
    if batch.get("batchHash") != expected:
        raise VisualBatchError("visual edit batch hash mismatch")


def confirm_visual_batch(batch: dict[str, Any], current_source_hash: str) -> dict[str, Any]:
    validate_batch_current(batch, current_source_hash)
    confirmed = dict(batch)
    confirmed["status"] = "confirmed"
    confirmed["batchHash"] = batch_digest(confirmed)
    return confirmed
