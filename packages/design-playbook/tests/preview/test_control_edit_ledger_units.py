"""The preview edit ledger, executed from the shipped file.

`control.edits.js` decides how a direct visual edit coalesces into the entry the
review queue publishes, and how undo, redo and a new append move that entry
between the entries list and the redo stack. Until this module existed the
only thing that could evaluate any of it was the browser matrix, so a wrong
comparison or a lost guard was only visible as a large area of red. These rules
are pure over the two lists, so this loads the shipped module in node against
a case table. It needs node, which the repository already requires for its
JavaScript checks.

The first test is `node --check` on the module itself: no other test in the
repository syntax-checks it (`test_browser_control.py` checks only
`control.js`), so without it a syntax error in this file is only discoverable
when the component fails to mount.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
PREVIEW = PKG_ROOT / "mcp" / "preview"
LEDGER = PREVIEW / "control.edits.js"
SHELL = PREVIEW / "control.react.js"

# The shipped module is one self-contained IIFE that only needs `window`.
_HARNESS = """
var failures = [];
function eq(got, want, label) {
  var g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) failures.push(label + ": got " + g + ", want " + w);
}
var L = window.DPBEdit.ledger;
function edit(seq, property, oldValue, newValue) {
  return { kind: "style", viewport: "any", locator: "#a", property: property,
    oldValue: oldValue, newValue: newValue, _seq: seq, _t: seq * 100, _entryId: seq };
}
function at(prev, t) { prev._t = t; return prev; }
// A grouped entry is the array of edits the receipt carries; the component sets
// `_entryId` on the array itself, which is what `getEntryId` reads first.
function group() {
  var g = Array.prototype.slice.call(arguments);
  g._entryId = g[0]._seq;
  return g;
}
function ids(list) { return list.map(L.seqOf); }
function seq(list) { return list.map(function (g) { return L.seqOf(g); }); }
eq(L.MERGE_WINDOW_MS, 500, "merge window");

// mergeEdit: the four branches, in order - same target in window, outside the
// window, another locator, another property.
var other = edit(2, "color", "b", "c");
var answers = [
  L.mergeEdit(at(edit(1, "color", "a", "b"), 1000), other, 1400, L.MERGE_WINDOW_MS),
  L.mergeEdit(at(edit(1, "color", "a", "b"), 1000), other, 1501, L.MERGE_WINDOW_MS),
  L.mergeEdit(at(edit(1, "color", "a", "b"), 1000),
    { locator: "#b", property: "color", viewport: "any", newValue: "c" }, 1100, L.MERGE_WINDOW_MS),
  L.mergeEdit(at(edit(1, "color", "a", "b"), 1000),
    { locator: "#a", property: "width", viewport: "any", newValue: "c" }, 1100, L.MERGE_WINDOW_MS)
];
eq(answers, [true, false, false, false], "mergeEdit branches");
eq(L.mergeEdit(null, other, 1000, L.MERGE_WINDOW_MS), false, "mergeEdit no prev");
eq(L.mergeEdit(at(edit(1, "color", "a", "b"), 0), other, 100, L.MERGE_WINDOW_MS), false,
  "mergeEdit needs a recorded time");
// A view switch is a different target: same locator and property, other viewport.
eq(L.mergeEdit(at(edit(1, "color", "a", "b"), 1000),
  { locator: "#a", property: "color", viewport: "mobile", newValue: "c" }, 1100, L.MERGE_WINDOW_MS),
  false, "mergeEdit viewport branch");

// Aliasing: the coalesce mutates the edit object the last entry of `entries`
// still holds, and that shared identity is what carries the merged value into
// the batch through the flat projection. It is the mechanism, not a coincidence.
var shared = edit(1, "color", "a", "b");
var sharedEntries = [group(shared)];
eq(L.mergeEdit(at(shared, 1000), edit(2, "color", "b", "c"), 1400, L.MERGE_WINDOW_MS),
  true, "alias merge");
eq(sharedEntries[0][0] === L.flatten(sharedEntries)[0], true, "alias identity");
eq(L.flatten(sharedEntries)[0].newValue, "c", "merged value reaches the projected edit");
eq(L.flatten(sharedEntries).length, 1, "a coalesce adds nothing to the projection");

var e1 = edit(1, "color", "a", "b");
var e2 = edit(2, "width", "c", "d");
var e3 = edit(3, "color", "e", "f");
var g1 = group(e1), g2 = group(e2), g3 = group(e3);

// The cardinality the rail depends on: `entries` is the undo stack, the
// projection is the count. One corner resize is one receipt carrying two edits,
// so only the projection length is what `#dpb-visual-count` shows.
var resize = group(edit(4, "width", "1px", "2px"), edit(4, "height", "1px", "2px"));
var card = L.appendEdits({ entries: [], future: [] }, resize, 4);
eq(seq(card.entries), [4], "one receipt is one entry");
eq(card.entries.length, 1, "entries.length counts undo steps, not edits");
eq(L.flatten(card.entries).length, 2, "the projection counts edits");

// flatten: the grouped entries concatenated and ordered by sequence, so a batch
// never publishes out of the order the reviewer made the edits in.
eq(ids(L.flatten([g3, g1, g2])), [1, 2, 3], "flatten orders by sequence");
eq(L.flatten([]).length, 0, "flatten of no entries is empty");
eq(L.flatten(undefined).length, 0, "flatten of nothing is empty");

// Append: the entry joins the list in sequence order, and a newer receipt
// clears the redo stack.
var appended = L.appendEdits({ entries: [g2], future: [] }, g1, 1);
eq(seq(appended.entries), [1, 2], "append reorders the entries list");
eq(ids(L.flatten(appended.entries)), [1, 2], "append reorders the projection");
eq(appended.future, [], "append invalidates the redo stack");
eq(appended.entries[1] === g2, true, "append keeps the existing entry by identity");
eq(L.flatten(appended.entries)[0] === e1, true, "append keeps each edit by identity");

// An older receipt must not throw a newer redo stack away; a null `future` is
// the module's signal that the component leaves its stack alone.
var older = L.appendEdits({ entries: [g1], future: [g3] }, g2, 2);
eq(older.future, null, "an older receipt keeps the redo stack");
eq(seq(older.entries), [1, 2], "an older receipt still records its entry");
var newer = L.appendEdits({ entries: [g1], future: [g2] }, g3, 3);
eq(newer.future, [], "a newer receipt invalidates the redo stack");

// Undo moves the entry out of the list and onto the redo stack; its edits leave
// the projection with it.
var undone = L.undoEntry({ entries: [g1, g2], future: [] }, g2);
eq(seq(undone.entries), [1], "undo consumes the entry");
eq(ids(L.flatten(undone.entries)), [1], "undo clears the entry's edits from the projection");
eq(seq(undone.future), [2], "undo pushes onto the redo stack");
eq(undone.future[0] === g2, true, "undo keeps the entry by identity");
eq(L.undoEntry({ entries: [g1], future: [] }, g2), null,
  "undo of an entry that is no longer in the list does nothing");
// alreadyInFut: the entry is already queued for redo, so it must not appear twice.
var undup = L.undoEntry({ entries: [g1], future: [g1] }, g1);
eq(seq(undup.future), [1], "undo does not duplicate a future entry");

// Redo is undo's mirror, and re-orders the list it touches.
var redone = L.redoEntry({ entries: [g2], future: [g1] }, g1);
eq(seq(redone.entries), [1, 2], "redo re-orders the entries list by sequence");
eq(ids(L.flatten(redone.entries)), [1, 2], "redo returns the edits to the projection");
eq(seq(redone.future), [], "redo consumes the redo stack");
eq(L.redoEntry({ entries: [], future: [g1] }, g2), null,
  "redo of an entry that is no longer in the redo stack does nothing");
// alreadyInHist: a receipt that arrived twice must not put the entry in twice.
var rehist = L.redoEntry({ entries: [g1], future: [g1] }, g1);
eq(seq(rehist.entries), [1], "redo does not duplicate an entry");
eq(ids(L.flatten(rehist.entries)), [1], "redo does not duplicate the projected edits");

// publishBatch's own ordering over a list it is handed: a nested entry sorts on
// its first edit, so a batch never publishes out of sequence.
var flat = [e3, e1, e2];
eq(ids(flat.slice().sort(L.bySeq)), [1, 2, 3], "batch order over a flat list");
eq([e3, e1, e2].map(L.seqOf), [3, 1, 2], "seqOf reads a flat edit");
eq(seq([g3, g1, g2].slice().sort(L.bySeq)), [1, 2, 3], "batch order over grouped entries");
eq(L.seqOf(null), 0, "seqOf of a missing item is zero");
eq(L.seqOf([]), 0, "seqOf of an empty group is zero");
eq(L.getEntryId({ _seq: 0, _entryId: undefined }), 0, "getEntryId keeps a real zero");
eq(L.getEntryId(undefined), null, "getEntryId of nothing is null");

console.log(JSON.stringify(failures));
"""


def _ledger_source() -> str:
    return LEDGER.read_text(encoding="utf-8")


def _run_node(tmp_path: Path, script_text: str, name: str) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / name
    script_path.write_text(script_text, encoding="utf-8")
    return subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )


def test_the_edit_ledger_module_is_syntactically_valid() -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    result = subprocess.run(
        [node, "--check", str(LEDGER)], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_the_edit_ledger_keeps_its_answers(tmp_path) -> None:
    script = "globalThis.window = {};\n" + _ledger_source() + _HARNESS
    result = _run_node(tmp_path, script, "control_edit_ledger_units.js")
    assert result.returncode == 0, result.stderr
    failures = json.loads(result.stdout)
    assert failures == [], "\n".join(failures)


@pytest.mark.parametrize("rule", ["mergeEdit", "getEntryId", "seqOf", "bySeq",
                                  "flatten", "undoEntry", "redoEntry", "appendEdits"])
def test_each_moved_rule_is_defined_exactly_once(rule: str) -> None:
    # The component must not carry a second copy: a drifted pair of copies is
    # the exact failure mode this extraction exists to remove.
    ledger = _ledger_source()
    shell = SHELL.read_text(encoding="utf-8")
    assert ledger.count(f"function {rule}(") == 1
    assert shell.count(f"function {rule}(") == 0


def test_the_merge_window_lives_only_in_the_module() -> None:
    # The component still reads the window, but through the module, so the
    # coalesce interval has one definition left in the shipped source.
    ledger = _ledger_source()
    shell = SHELL.read_text(encoding="utf-8")
    assert ledger.count("var MERGE_WINDOW_MS = 500;") == 1
    assert "var MERGE_WINDOW_MS" not in shell
    assert shell.count("MERGE_WINDOW_MS") == 1


def test_the_component_has_no_comparator_of_its_own() -> None:
    # Five inline seq spellings and the receipt-guard read used to live in the
    # component; the module's one comparator is now the only order reading.
    shell = SHELL.read_text(encoding="utf-8")
    for spelling in ("_seq || ", "[0]._seq", "[0]._entryId"):
        assert spelling not in shell, spelling
    assert "sort(ledger.bySeq)" in shell
