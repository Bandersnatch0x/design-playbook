"""The client net-effect mirror and the Python rule must agree, by execution.

`control.review.js` decides readiness with its own copy of
`visual_batch.has_effective_visual_edits`, so the Approve button can react
without a round trip. Two owners of one rule kept in sync by a comment drift
silently - the two did disagree: the client compares CSS values with
`toLowerCase()` and the server used `casefold()`, which differ on values such as
"ß". The client governs, because the client is what a reviewer sees, so the
server now uses `lower()` and this test holds the pair together by extracting
the shipped mirror from the file and running it in node over the same table.

Both sides are fed the same published batch shape: `status` plus `edits`, with
every edit already carrying its `locator`, `property`, `oldValue`, `newValue`,
`kind` and `source` as strings. That is what the editor publishes and what
`normalize_visual_batch` guarantees, so a shape the contract cannot produce is
not a case this rule has to answer.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview.visual_batch import (  # noqa: E402
    has_effective_visual_edits,
)

MIRROR = _PKG_ROOT / "mcp" / "preview" / "control.review.js"
CONTRACT = _PKG_ROOT / "mcp" / "preview" / "visual_contract.js"


def _edit(**overrides: str) -> dict[str, str]:
    edit = {
        "kind": "style",
        "viewport": "any",
        "locator": "#a",
        "property": "color",
        "oldValue": "",
        "newValue": "red",
        "source": "shell",
    }
    edit.update(overrides)
    return edit


# (label, batch) - the batch is handed to both implementations verbatim.
CASES: list[tuple[str, dict]] = [
    ("no edits", {"status": "pending", "edits": []}),
    ("a real change counts", {"status": "pending", "edits": [_edit()]}),
    ("a no-op does not count",
     {"status": "pending", "edits": [_edit(oldValue="red")]}),
    ("whitespace alone does not count",
     {"status": "pending", "edits": [_edit(oldValue=" red ")]}),
    ("a chain undone to its baseline does not count", {"status": "pending", "edits": [
        _edit(),
        _edit(oldValue="red", newValue=""),
    ]}),
    ("a reversal across viewports does not count", {"status": "pending", "edits": [
        _edit(viewport="desktop"),
        _edit(viewport="mobile", oldValue="red", newValue=""),
    ]}),
    ("a reversal across kinds does not count", {"status": "pending", "edits": [
        _edit(),
        _edit(kind="layout", oldValue="red", newValue=""),
    ]}),
    ("one surviving change beside an undone chain counts", {"status": "pending", "edits": [
        _edit(),
        _edit(oldValue="red", newValue=""),
        _edit(property="padding", oldValue="8px", newValue="16px"),
    ]}),
    ("a frame gesture alone does not count",
     {"status": "pending", "edits": [_edit(source="frame")]}),
    ("an agent tool edit alone does not count",
     {"status": "pending", "edits": [_edit(source="agent")]}),
    ("an edit with no declared source does not count",
     {"status": "pending", "edits": [{k: v for k, v in _edit().items() if k != "source"}]}),
    ("a case-only CSS value does not count",
     {"status": "pending", "edits": [_edit(oldValue="red", newValue="RED")]}),
    # The case that made the two owners disagree: casefold("ß") is "ss" while
    # lower("ß") stays "ß", so the server called this a no-op and the client
    # called it a review. Both now compare the way the client does.
    ("a sharp-s case is a real change for CSS",
     {"status": "pending", "edits": [_edit(oldValue="ß", newValue="SS")]}),
    ("case still matters for text content",
     {"status": "pending", "edits": [
         _edit(kind="content", property="text", oldValue="Red", newValue="red"),
     ]}),
]

# The client owns one check the server rule does not carry: it reads the
# published batch directly, so it must refuse one that is no longer pending.
# The server never reaches this rule with such a batch - normalize_visual_batch
# refuses it first - so these are client-only cases, asserted separately rather
# than folded into the comparison above.
CLIENT_ONLY = [
    ("a stale batch does not count", {"status": "stale", "edits": [_edit()]}),
    ("a batch with no status does not count", {"edits": [_edit()]}),
]


def _mirror_function_text() -> str:
    source = MIRROR.read_text(encoding="utf-8")
    start = source.index("function hasEffectiveVisualEdits(")
    end = source.index("\n  }", start) + len("\n  }")
    return source[start:end]


def _run_client(batches: list[dict], tmp_path: Path) -> list[bool]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    script = (
        "var window = globalThis;\n"
        + CONTRACT.read_text(encoding="utf-8")
        + "\n"
        + _mirror_function_text()
        + "\nconst cases = " + json.dumps(batches) + ";"
        + "\nconsole.log(JSON.stringify(cases.map(function (batch) {"
        + "\n  window.DPB_VISUAL_EDIT_BATCH = batch;"
        + "\n  return hasEffectiveVisualEdits();"
        + "\n})));"
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "net_effect_mirror.js"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_client_net_effect_mirror_matches_the_python_rule(tmp_path) -> None:
    client = _run_client([batch for _, batch in CASES], tmp_path)
    server = [has_effective_visual_edits(batch) for _, batch in CASES]
    assert client == server, "\n".join(
        f"{label}: client={got} server={want}"
        for (label, _), got, want in zip(CASES, client, server)
        if got != want
    )


def test_the_client_refuses_a_batch_the_server_would_have_refused_earlier(
    tmp_path,
) -> None:
    client = _run_client([batch for _, batch in CLIENT_ONLY], tmp_path)
    assert client == [False] * len(CLIENT_ONLY), dict(zip(
        (label for label, _ in CLIENT_ONLY), client,
    ))
