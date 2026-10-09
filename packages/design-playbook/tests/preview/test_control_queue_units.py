"""The shell's pending-edit rule, executed from the shipped file.

`control.react.js` decides whether a round still holds unpublished visual work
from a handful of refs. That rule is the one a disconnect, a refusal and a stale
round all feed into, and until now only the browser suites could evaluate it.
It is pure over a state snapshot, so this extracts its source text from the
shipped file and runs it in node over a case table. It needs node, which the
repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
SHELL = PKG_ROOT / "mcp" / "preview" / "control.react.js"


def _state(**over):
    state = {
        "selected": {"selector": "#panel-title"},
        "published": True,
        "request": None,
        "unacked": {},
        "draftTimers": {},
        "drafts": {},
        "dispatched": {},
    }
    state.update(over)
    return state


# (state, expected) - the rule answers "does the round still hold unpublished
# visual work".
CASES = [
    (_state(selected=None), False),
    (_state(), False),
    (_state(drafts={"color": "red"}, dispatched={"color": "red"}), False),
    (_state(drafts={"color": "red"}), True),
    (_state(published=False), True),
    (_state(request={"id": "r1"}), True),
    (_state(unacked={"r1": {"id": "r1"}}), True),
    (_state(unacked={}), False),
    (_state(draftTimers={"color": 1}), True),
    # A stale flag alone is not unpublished work, and stale never hides work
    # that is there: the rule does not consult it either way.
    (_state(stale=True), False),
    (_state(stale=True, drafts={"color": "red"}), True),
    # Only an absent selection makes drafts irrelevant.
    (_state(selected=None, drafts={"color": "red"}), False),
]


def _rule_text() -> str:
    source = SHELL.read_text(encoding="utf-8")
    start = source.index("function dpbPendingVisualEdits(")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError("unterminated dpbPendingVisualEdits")


def test_the_pending_edit_rule_keeps_its_answers(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    payload = json.dumps([state for state, _ in CASES])
    script = (
        _rule_text()
        + "\nconst states = " + payload + ";"
        + "\nconsole.log(JSON.stringify(states.map(dpbPendingVisualEdits)));"
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "control_queue_units.js"
    script_path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    want = [expected for _, expected in CASES]
    assert got == want, "\n".join(
        f"case {i} {state!r}: got {g}, want {w}"
        for i, (state, g, w) in enumerate(zip([s for s, _ in CASES], got, want))
        if g != w
    )
