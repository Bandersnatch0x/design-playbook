"""The review shell's two remaining preferences, executed from the shipped file.

`mcp/preview/control.review.js` keeps one store each for the single-key shortcut
switch and the first-use coachmark card, both with a single write point. The
read rules and the swallowing of storage exceptions decide whether a reviewer's
plain keys work and whether the card comes back, so this extracts each store's
source text from the shipped file and runs it in node over a case table with a
stub `localStorage`. It needs node, which the repository already requires for
its JavaScript checks.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
if str(PKG_ROOT) not in sys.path:  # one import seam (ADR-0022)
    sys.path.insert(0, str(PKG_ROOT))

PREVIEW = PKG_ROOT / "mcp" / "preview"
SHELL = PREVIEW / "control.js"
REVIEW = PREVIEW / "control.review.js"

SINGLE_KEYS_KEY = "dpb.singlekeys.v1"
COACHMARK_KEY = "dpb.onboarding.v1"
STORES = ("DPBUI.singleKeys = (function () {", "DPBUI.coachmark = (function () {")

_HARNESS = """
var DPBUI = {};
__STORES__
var store = {};
var writes = [];
var throwRead = false;
var throwWrite = false;
globalThis.localStorage = {
  getItem: function (k) {
    if (throwRead) { throw new Error("denied"); }
    return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
  },
  setItem: function (k, v) {
    if (throwWrite) { throw new Error("denied"); }
    store[k] = String(v);
    writes.push([k, String(v)]);
  },
};
function reset(stored) {
  store = {};
  writes = [];
  if (stored !== undefined) {
    store[stored[0]] = stored[1];
  }
}
var out = {};
out.singleKeysKey = DPBUI.singleKeys.STORAGE_KEY;
out.coachmarkKey = DPBUI.coachmark.STORAGE_KEY;
// The switch defaults on: only the literal "off" turns plain keys off.
out.single = [];
[[undefined, undefined], ["on", undefined], ["off", undefined], ["bogus", undefined]]
  .forEach(function (c) {
    reset(c[0] === undefined ? undefined : [DPBUI.singleKeys.STORAGE_KEY, c[0]]);
    out.single.push(DPBUI.singleKeys.on());
  });
throwRead = true;
out.singleThrowRead = DPBUI.singleKeys.on();
throwRead = false;
reset();
DPBUI.singleKeys.set(true);
out.setOn = writes.slice();
DPBUI.singleKeys.set(false);
out.setOnThenOff = writes.slice();
throwWrite = true;
DPBUI.singleKeys.set(true);
throwWrite = false;
out.setSwallowsWriteThrow = writes.slice();
// The card counts one stored value; anything else means first use.
out.seen = [];
[[undefined, undefined], ["1", undefined], ["0", undefined], ["bogus", undefined]]
  .forEach(function (c) {
    reset(c[0] === undefined ? undefined : [DPBUI.coachmark.STORAGE_KEY, c[0]]);
    out.seen.push(DPBUI.coachmark.seen());
  });
throwRead = true;
out.coachmarkThrowRead = DPBUI.coachmark.seen();
throwRead = false;
reset();
DPBUI.coachmark.remember();
out.rememberWrite = writes.slice();
out.rememberStored = store[DPBUI.coachmark.STORAGE_KEY];
throwWrite = true;
DPBUI.coachmark.remember();
throwWrite = false;
out.rememberSwallowsWriteThrow = writes.slice();
console.log(JSON.stringify(out));
"""


def _store_text(marker: str) -> str:
    source = REVIEW.read_text(encoding="utf-8")
    start = source.index(marker)
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1] + ")();"
    raise AssertionError(f"unterminated {marker}")


def _run(tmp_path) -> dict:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    harness = _HARNESS.replace("__STORES__", "\n".join(_store_text(m) for m in STORES))
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "review_prefs_store_units.js"
    script_path.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_single_keys_store_keeps_its_answers(tmp_path) -> None:
    got = _run(tmp_path)
    assert got["singleKeysKey"] == SINGLE_KEYS_KEY
    # stored value → on(): missing, "on", "off", other
    assert got["single"] == [True, True, False, True]
    # A storage read that throws falls back to the default, which is on.
    assert got["singleThrowRead"] is True
    assert got["setOn"] == [[SINGLE_KEYS_KEY, "on"]]
    assert got["setOnThenOff"] == [[SINGLE_KEYS_KEY, "on"], [SINGLE_KEYS_KEY, "off"]]
    # A private-mode write throw is swallowed, not surfaced to the toggle.
    assert got["setSwallowsWriteThrow"] == got["setOnThenOff"]


def test_the_coachmark_store_keeps_its_answers(tmp_path) -> None:
    got = _run(tmp_path)
    assert got["coachmarkKey"] == COACHMARK_KEY
    # stored value → seen(): missing, "1", "0", other
    assert got["seen"] == [False, True, False, False]
    # A storage read that throws means first use, so the card shows.
    assert got["coachmarkThrowRead"] is False
    assert got["rememberWrite"] == [[COACHMARK_KEY, "1"]]
    assert got["rememberStored"] == "1"
    # Quota or private-mode write throws are best-effort, same as before.
    assert got["rememberSwallowsWriteThrow"] == got["rememberWrite"]


def test_each_preference_keeps_one_write_point() -> None:
    # Outside the two store blocks the review file must not touch localStorage
    # at all, and each key string stays a literal in exactly one place.
    review = REVIEW.read_text(encoding="utf-8")
    outside = review
    for marker in STORES:
        outside = outside.replace(_store_text(marker), "")
    assert "localStorage" not in outside
    for key in (SINGLE_KEYS_KEY, COACHMARK_KEY):
        assert review.count(f'"{key}"') == 1
        assert key not in SHELL.read_text(encoding="utf-8")
    # The wrappers the stores replace must not survive as a second path.
    assert re.search(r"(?m)^\s*var (?:SINGLE_KEYS|ONBOARDING_KEY)\s*=", review) is None
    for gone in ("singleKeysOn", "onboardingWasSeen", "rememberOnboarding"):
        assert gone not in review
    for through in ("DPBUI.singleKeys.on()", "DPBUI.singleKeys.set(",
                    "DPBUI.coachmark.seen()", "DPBUI.coachmark.remember()"):
        assert through in review
