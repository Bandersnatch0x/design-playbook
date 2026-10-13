"""U-23: coalesced visual edits, text-field undo stays native, undo label names the property."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parents[2] / "mcp" / "preview" / "control.react.js").read_text(encoding="utf-8")


def _merge_fn():
    return re.search(r"var MERGE_WINDOW_MS = 500;\n  function mergeEdit.*?\n  \}\n", SRC, re.S).group(0)


@pytest.mark.skipif(not shutil.which("node"), reason="node missing")
def test_merge_rule_table(tmp_path):
    node = shutil.which("node")
    cases = [
        ({"locator": "a", "property": "color", "viewport": "any", "_t": 1000, "newValue": "1"},
         {"locator": "a", "property": "color", "viewport": "any", "newValue": "2"}, 1400, True),
        ({"locator": "a", "property": "color", "viewport": "any", "_t": 1000, "newValue": "1"},
         {"locator": "a", "property": "color", "viewport": "any", "newValue": "2"}, 1501, False),
        ({"locator": "a", "property": "color", "viewport": "any", "_t": 1000, "newValue": "1"},
         {"locator": "b", "property": "color", "viewport": "any", "newValue": "2"}, 1100, False),
        ({"locator": "a", "property": "color", "viewport": "any", "_t": 1000, "newValue": "1"},
         {"locator": "a", "property": "width", "viewport": "any", "newValue": "2"}, 1100, False),
    ]
    js = _merge_fn() + "\nconst cases=" + json.dumps(cases) + \
        ";console.log(JSON.stringify(cases.map(([p,n,t,e])=>mergeEdit(p,n,t,MERGE_WINDOW_MS))));"
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "history_merge.js"
    script_path.write_text(js, encoding="utf-8")
    out = subprocess.run([node, str(script_path)], capture_output=True, text=True,
                         encoding="utf-8", timeout=60, check=True).stdout
    assert json.loads(out) == [True, False, False, False]


def test_history_shortcut_ignores_text_fields_and_labels_carry_property():
    assert 'closest("input, textarea, select, [contenteditable]")' in SRC
    assert 'tgt.closest(".dpb-react-field")' in SRC
    assert "historyLabel(t(\"visual_undo\")" in SRC and "historyLabel(t(\"visual_redo\")" in SRC
