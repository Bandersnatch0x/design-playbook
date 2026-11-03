"""One owner for the shapes stored rows decode into (R03, R04).

The Store's interface stops at SQL rows: a draft carries ``attributes_json``
and ``tags_json`` strings, a revision carries five more, and each request,
proposal, and canvas row carries one or two of its own. Written out at every
caller (sixty-plus sites), the decoding rule drifted and each copy picked its
own fallback. These helpers are that rule once.

``owned_asset`` is the one identity guard: a row that is missing, foreign, or
of the wrong kind is refused here rather than by eight private copies.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .errors import INVALID_TARGET, UNSUPPORTED, WorkbenchError
from .store import Store


def load(value: object, default: Any) -> Any:
    """Decode one stored JSON column, or return ``default``.

    The decoded value is returned whatever its JSON type: a proposal payload
    is a list, a draft's attributes are an object, and only the caller knows
    which it stored. A column already decoded (some read paths hand rows back
    through a join) is returned as-is.
    """
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:  # pragma: no cover - stored by us
        return default


def _shaped(row: Mapping[str, Any] | None, key: str, kind: type, empty: Any) -> Any:
    value = row.get(key) if row else None
    decoded = load(value, empty)
    return decoded if isinstance(decoded, kind) else empty


def attributes(draft: Mapping[str, Any] | None) -> dict:
    """A draft's attributes object."""
    return _shaped(draft, "attributes_json", dict, {})


def tags(draft: Mapping[str, Any] | None) -> list:
    """A draft's tags."""
    return _shaped(draft, "tags_json", list, [])


def capabilities(revision: Mapping[str, Any] | None) -> list:
    """A revision's declared capabilities."""
    return _shaped(revision, "capabilities_json", list, [])


def dependencies(revision: Mapping[str, Any] | None) -> list:
    """A revision's recorded dependency edges."""
    return _shaped(revision, "dependencies_json", list, [])


def manifest(revision: Mapping[str, Any] | None) -> list:
    """A revision's manifest entries."""
    return _shaped(revision, "manifest_json", list, [])


def source_locators(revision: Mapping[str, Any] | None) -> list:
    """A revision's typed source locators."""
    return _shaped(revision, "source_locators_json", list, [])


def verified(revision: Mapping[str, Any] | None) -> list:
    """A revision's verification records."""
    return _shaped(revision, "verified_json", list, [])


def origin(revision: Mapping[str, Any] | None) -> dict:
    """A revision's origin facts."""
    return _shaped(revision, "origin_json", dict, {})


def owned_asset(
    store: Store,
    project_id: str,
    asset_id: str,
    *,
    kind: str | None = None,
) -> dict:
    """The asset row, refusing missing, foreign, and wrong-kind targets."""
    row = store.asset(asset_id)
    if row is None or row["project_id"] != project_id:
        raise WorkbenchError(INVALID_TARGET)
    if kind is not None and row["kind"] != kind:
        raise WorkbenchError(UNSUPPORTED, detail=f"asset is not a {kind}")
    return row
