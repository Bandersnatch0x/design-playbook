"""The client floor mirror and the Python floor must agree, by execution.

`control.review.js` mirrors `integrity.evaluate_feedback_floor` so the Approve
button can react without a round trip. Two owners of one rule kept in sync by a
comment drift silently, so this test extracts the mirror's function text from
the shipped file and runs it in node against the Python floor over one shared
case table. It needs node, which the repository already requires for its
JavaScript checks.
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
from design_playbook.mcp.preview.integrity import evaluate_feedback_floor  # noqa: E402

MIRROR = _PKG_ROOT / "mcp" / "preview" / "control.review.js"

# (anchors, feedback, effective visual edit, flushable pending edit)
# The client mirror answers "ready now", which includes a pending edit it is
# about to flush. So the invariant is client == floor evaluated with
# has_visual_edits = effective or flushable: readiness anticipates the flush it
# promises to perform, never more.
CASES = [
    ([], "", False, False),
    ([], "   \n  ", False, False),
    ([], "ok", False, False),
    ([], "", True, False),
    ([], "ok", True, False),
    ([], "", False, True),
    ([], "   ", False, True),
    ([{"selector": "h2", "comment": "x"}], "", False, False),
    ([{"selector": "h2", "comment": "x"}], "", True, False),
    ([{"selector": "h2", "comment": "x"}], "", False, True),
    ([{"selector": "h2", "comment": ""}], "", False, False),
    ([{"selector": "h2", "comment": ""}], "ok", True, False),
    ([{"selector": "h2", "comment": "x"}, {"selector": "p", "comment": ""}], "", False, True),
    ([{"selector": "", "comment": "x"}], "", False, False),
    (["not-a-dict"], "", False, True),
    ([{"selector": "h2", "comment": "x"}, {"selector": "p", "comment": "y"}], "", False, False),
]


def _mirror_function_text() -> str:
    source = MIRROR.read_text(encoding="utf-8")
    start = source.index("function dpbFloorVerdict(")
    end = source.index("\n  }", start) + len("\n  }")
    return source[start:end]


def test_the_client_floor_mirror_matches_the_python_floor(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    verdict = _mirror_function_text()
    payload = json.dumps([
        {"anchors": anchors, "feedback": feedback,
         "effectiveEdit": effective, "flushableEdit": flushable}
        for anchors, feedback, effective, flushable in CASES
    ])
    script = (
        verdict
        + "\nconst cases = " + payload + ";"
        + "\nconsole.log(JSON.stringify(cases.map(dpbFloorVerdict)));"
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "floor_mirror.js"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    client = json.loads(result.stdout)
    server = [
        evaluate_feedback_floor(
            feedback, anchors, has_visual_edits=effective or flushable,
        ).passed
        for anchors, feedback, effective, flushable in CASES
    ]
    assert client == server, "\n".join(
        f"case {i} {case!r}: client={got} server={want}"
        for i, (case, got, want) in enumerate(zip(CASES, client, server))
        if got != want
    )
