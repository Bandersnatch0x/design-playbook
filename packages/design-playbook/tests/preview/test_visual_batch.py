from __future__ import annotations

import pytest

from design_playbook.mcp.preview.visual_batch import (
    VisualBatchError,
    batch_digest,
    confirm_visual_batch,
    normalize_visual_batch,
    validate_batch_current,
)


def test_normalizes_pending_batch_and_digest() -> None:
    batch = normalize_visual_batch({
        "schemaVersion": 1,
        "edits": [{
            "locator": "#hero",
            "property": "background-color",
            "oldValue": "white",
            "newValue": "black",
        }],
    }, source_hash="abc", route_url="http://127.0.0.1:5173/")

    assert batch["status"] == "pending"
    assert batch["sourceHash"] == "abc"
    assert batch["batchHash"] == batch_digest(batch)
    # Defaults keep older callers (style only) working unchanged.
    assert batch["edits"][0]["kind"] == "style"
    assert batch["edits"][0]["viewport"] == "any"


def test_batch_carries_every_change_kind() -> None:
    batch = normalize_visual_batch({
        "edits": [
            {"kind": "style", "locator": "#a", "property": "color", "newValue": "red"},
            {"kind": "layout", "locator": "#b", "property": "gap", "newValue": "12px"},
            {"kind": "responsive", "viewport": "mobile", "locator": "#c",
             "property": "padding", "newValue": "8px"},
            {"kind": "content", "locator": "#d", "property": "text",
             "oldValue": "Save", "newValue": "Save changes"},
            {"kind": "structure", "locator": "#e", "property": "order",
             "oldValue": "1", "newValue": "2"},
        ],
    }, source_hash="v1")

    assert [e["kind"] for e in batch["edits"]] == [
        "style", "layout", "responsive", "content", "structure",
    ]
    assert batch["edits"][2]["viewport"] == "mobile"
    assert batch["edits"][3]["property"] == "text"


def test_confirmation_fails_closed_on_stale_or_tampered_batch() -> None:
    batch = normalize_visual_batch({"edits": []}, source_hash="v1")
    with pytest.raises(VisualBatchError, match="stale"):
        validate_batch_current(batch, "v2")
    batch["edits"].append({"locator": "#x", "property": "color", "oldValue": "", "newValue": "red"})
    with pytest.raises(VisualBatchError, match="hash mismatch"):
        confirm_visual_batch(batch, "v1")


def test_confirmation_marks_batch_without_changing_source_hash() -> None:
    batch = normalize_visual_batch({"edits": []}, source_hash="v1")
    confirmed = confirm_visual_batch(batch, "v1")
    assert confirmed["status"] == "confirmed"
    assert confirmed["sourceHash"] == "v1"
    assert confirmed["batchHash"] == batch_digest(confirmed)


@pytest.mark.parametrize("raw", [
    {"edits": [{"locator": "#x", "property": "color;bad", "newValue": "red"}]},
    {"edits": [{"locator": "#x", "property": "color", "newValue": "x"}] * 201},
    {"edits": [{"kind": "guess", "locator": "#x", "property": "color"}]},
    {"edits": [{"kind": "responsive", "viewport": "watch", "locator": "#x",
               "property": "color"}]},
    {"edits": [{"kind": "content", "locator": "#x", "property": "color"}]},
    {"edits": [{"locator": "../../etc/passwd", "property": "color"}]},
    {"edits": [{"locator": "C:\\Users\\x", "property": "color"}]},
    {"edits": [{"locator": "file:///etc/passwd", "property": "color"}]},
    {"edits": [{"locator": "/absolute/path", "property": "color"}]},
])
def test_rejects_unsafe_batches(raw: dict) -> None:
    with pytest.raises(VisualBatchError):
        normalize_visual_batch(raw, source_hash="v1")


def test_bound_batch_cannot_be_resigned_or_moved_to_another_route() -> None:
    batch = normalize_visual_batch({"edits": [{"locator": "#a", "property": "color", "newValue": "red"}]},
                                   source_hash="v1", route_url="http://127.0.0.1:5173/a")
    assert normalize_visual_batch(batch, source_hash="v1", route_url=batch["routeUrl"]) == batch
    with pytest.raises(VisualBatchError, match="stale"):
        normalize_visual_batch(batch, source_hash="v2", route_url=batch["routeUrl"])
    with pytest.raises(VisualBatchError, match="route"):
        normalize_visual_batch(batch, source_hash="v1", route_url="http://127.0.0.1:5173/b")


@pytest.mark.parametrize("url", [
    "file:///tmp/a", "about:blank", "javascript:alert(1)", "http://example.com/",
    "http://127.0.0.1.evil.test/", "http://user:pass@127.0.0.1/", "http://127.0.0.1/#x",
    "http://127.0.0.1/#", "http://127.0.0.1:99999/", "http://127.0.0.1/\nfoo",
])
def test_live_route_rejects_nonlocal_or_ambiguous_urls(url: str) -> None:
    from design_playbook.mcp.preview.live_route import validate_live_route_url
    with pytest.raises(ValueError):
        validate_live_route_url(url)


def test_live_route_allows_only_explicit_loopback_http() -> None:
    from design_playbook.mcp.preview.live_route import validate_live_route_url
    for url in ("http://127.0.0.1:5173/a", "https://localhost/a", "http://[::1]:5173/a"):
        assert validate_live_route_url(url) == url
