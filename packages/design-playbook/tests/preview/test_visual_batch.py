from __future__ import annotations

import pytest

from design_playbook.mcp.preview.visual_batch import (
    VisualBatchError,
    batch_digest,
    has_effective_visual_edits,
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


def test_validation_fails_closed_on_stale_or_tampered_batch() -> None:
    batch = normalize_visual_batch({"edits": []}, source_hash="v1")
    with pytest.raises(VisualBatchError, match="stale"):
        validate_batch_current(batch, "v2")
    batch["edits"].append({"locator": "#x", "property": "color", "oldValue": "", "newValue": "red"})
    with pytest.raises(VisualBatchError, match="hash mismatch"):
        validate_batch_current(batch, "v1")


def test_validation_accepts_a_current_batch_without_mutating_it() -> None:
    batch = normalize_visual_batch({"edits": []}, source_hash="v1")
    before = dict(batch)
    assert validate_batch_current(batch, "v1") is None
    assert batch == before


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


def test_effective_edits_exclude_no_ops_and_undone_chains() -> None:
    """ADR-0008 amendment (2026-10-08): only a net change substitutes for notes."""
    def effective(edits: list[dict]) -> bool:
        # The parent control shell composes these; provenance is pinned by
        # test_effective_edits_require_the_reviewers_own_provenance.
        edits = [{"source": "shell", **edit} for edit in edits]
        return has_effective_visual_edits(
            normalize_visual_batch({"edits": edits}, source_hash="v1")
        )

    assert effective(
        [{"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"}]
    )
    # A single edit that changes nothing is not substantive.
    assert not effective(
        [{"locator": "#a", "property": "color", "oldValue": "red", "newValue": "red"}]
    )
    # A chain that ends where it started is not substantive either.
    assert not effective([
        {"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"},
        {"locator": "#a", "property": "color", "oldValue": "red", "newValue": ""},
    ])
    # One surviving change is enough, even beside an undone chain.
    assert effective([
        {"locator": "#a", "property": "color", "oldValue": "", "newValue": "red"},
        {"locator": "#a", "property": "color", "oldValue": "red", "newValue": ""},
        {"locator": "#a", "property": "padding", "oldValue": "8px", "newValue": "16px"},
    ])


def test_net_effect_ignores_the_viewport_label() -> None:
    """One shared DOM: a change and its reversal under two labels net to zero."""
    def effective(edits: list[dict]) -> bool:
        # The parent control shell composes these; provenance is pinned by
        # test_effective_edits_require_the_reviewers_own_provenance.
        edits = [{"source": "shell", **edit} for edit in edits]
        return has_effective_visual_edits(
            normalize_visual_batch({"edits": edits}, source_hash="v1")
        )

    assert not effective([
        {"kind": "style", "viewport": "desktop", "locator": "#a",
         "property": "background-color", "oldValue": "", "newValue": "#123456"},
        {"kind": "style", "viewport": "mobile", "locator": "#a",
         "property": "background-color", "oldValue": "#123456", "newValue": ""},
    ]), "a round trip across viewport labels is not an effective change"
    assert effective([
        {"kind": "style", "viewport": "desktop", "locator": "#a",
         "property": "background-color", "oldValue": "", "newValue": "#123456"},
        {"kind": "style", "viewport": "mobile", "locator": "#a",
         "property": "background-color", "oldValue": "#123456", "newValue": "#654321"},
    ])


def test_effective_edits_require_the_reviewers_own_provenance() -> None:
    """ADR-0008 amendment (2026-10-09): only the shell's own edit is evidence.

    The prototype shares the bridge window, so an edit it reports is not proof
    that a human reviewed anything, and neither is a WebMCP tool call the agent
    made to itself.
    """
    def effective(source: str) -> bool:
        batch = normalize_visual_batch(
            {"edits": [{"source": source, "kind": "style", "locator": "#a",
                        "property": "color", "oldValue": "", "newValue": "red"}]},
            source_hash="v1",
        )
        return has_effective_visual_edits(batch)

    assert effective("shell")
    for other in ("frame", "agent", "unknown"):
        assert not effective(other), f"{other} provenance must not satisfy the floor"
    # An edit with no declared source is not attributable, so it is not evidence.
    assert not has_effective_visual_edits(normalize_visual_batch(
        {"edits": [{"kind": "style", "locator": "#a", "property": "color",
                    "oldValue": "", "newValue": "red"}]}, source_hash="v1"))


def test_effective_edits_compare_at_the_reviews_granularity() -> None:
    """A case-only CSS value, or a relabelled kind, is not a review."""
    def effective(edits: list[dict]) -> bool:
        edits = [{"source": "shell", **edit} for edit in edits]
        return has_effective_visual_edits(
            normalize_visual_batch({"edits": edits}, source_hash="v1")
        )

    assert not effective([
        {"kind": "style", "locator": "#a", "property": "color",
         "oldValue": "red", "newValue": "RED"},
    ]), "a case-only CSS value renders identically"
    assert not effective([
        {"kind": "style", "locator": "#a", "property": "padding",
         "oldValue": "8px", "newValue": "16px"},
        {"kind": "layout", "locator": "#a", "property": "padding",
         "oldValue": "16px", "newValue": "8px"},
    ]), "a relabelled kind is the same element, so the round trip still nets to zero"
    assert effective([
        {"kind": "content", "locator": "#a", "property": "text",
         "oldValue": "Save", "newValue": "SAVE"},
    ]), "text content is case-sensitive"


def test_oversized_or_zero_values_are_not_silently_rewritten() -> None:
    """The stored edit must be what the reviewer typed, or the batch fails."""
    zero = normalize_visual_batch(
        {"edits": [{"source": "shell", "locator": "#a", "property": "z-index",
                    "oldValue": 0, "newValue": 1}]},
        source_hash="v1",
    )
    assert [e["oldValue"] for e in zero["edits"]] == ["0"]
    assert [e["newValue"] for e in zero["edits"]] == ["1"]
    with pytest.raises(VisualBatchError, match="exceeds"):
        normalize_visual_batch(
            {"edits": [{"source": "shell", "locator": "#a", "property": "color",
                        "oldValue": "", "newValue": "x" * 2001}]},
            source_hash="v1",
        )
    with pytest.raises(VisualBatchError, match="source must be one of"):
        normalize_visual_batch(
            {"edits": [{"source": "elsewhere", "locator": "#a", "property": "color",
                        "newValue": "red"}]},
            source_hash="v1",
        )


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
