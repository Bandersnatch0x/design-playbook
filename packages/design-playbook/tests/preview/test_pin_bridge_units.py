"""The bridge's pure helpers, executed from the shipped file.

`pin_bridge.js` runs inside the prototype iframe, so the browser suites are the
only thing that exercises it today, and a syntax check cannot see a swapped
colour channel. The DOM-free helpers are pure, so this test extracts their
source text from the shipped file and runs them in node against known values.
It needs node, which the repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
BRIDGE = PKG_ROOT / "mcp" / "preview" / "pin_bridge.js"

# Pure helpers: no DOM, no module state. `checkGuides` and the toolbar helpers
# are deliberately absent because they read or write bridge state.
PURE_HELPERS = ("hsvToRgb", "rgbToHex", "translated", "drawPathD")

# Extraction counts braces, which is enough for these four: none of them holds a
# brace inside a string or a comment. A helper that gains one needs a real parse.
CHECKS = r"""
var failures = [];
function eq(got, want, label) {
  var g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) failures.push(label + ": got " + g + ", want " + w);
}
eq(hsvToRgb(0, 1, 1), [255, 0, 0], "hsv red");
eq(hsvToRgb(120, 1, 1), [0, 255, 0], "hsv green");
eq(hsvToRgb(240, 1, 1), [0, 0, 255], "hsv blue");
eq(hsvToRgb(60, 1, 1), [255, 255, 0], "hsv yellow");
eq(hsvToRgb(180, 1, 1), [0, 255, 255], "hsv cyan");
eq(hsvToRgb(300, 1, 1), [255, 0, 255], "hsv magenta");
eq(hsvToRgb(0, 0, 0), [0, 0, 0], "hsv black");
eq(hsvToRgb(0, 0, 1), [255, 255, 255], "hsv white");
eq(hsvToRgb(0, 0.5, 1), [255, 128, 128], "hsv half saturation rounds");
eq(rgbToHex(255, 0, 0), "#ff0000", "hex red");
eq(rgbToHex(0, 255, 0), "#00ff00", "hex green");
eq(rgbToHex(0, 0, 255), "#0000ff", "hex blue");
eq(rgbToHex(0, 0, 0), "#000000", "hex black");
eq(rgbToHex(255, 255, 255), "#ffffff", "hex white");
eq(rgbToHex(16, 32, 48), "#102030", "hex keeps each channel");
eq(rgbToHex(1, 2, 3), "#010203", "hex pads a single digit");
eq(translated("", 10, 20), "translate(10px, 20px)", "translate alone");
eq(translated("none", 1, 2), "translate(1px, 2px)", "translate ignores none");
eq(translated("rotate(5deg)", 0, 0), "translate(0px, 0px) rotate(5deg)", "translate appends");
eq(drawPathD(null), "", "no points");
eq(drawPathD([]), "", "empty points");
eq(drawPathD([[0, 0]]), "M0.0 0.0", "one point is a move");
eq(drawPathD([[0, 0], [10, 5]]), "M0.0 0.0L10.0 5.0", "two points are a line");
eq(drawPathD([[0, 0], [10, 5], [20, 0]]), "M0.0 0.0L10.0 5.0L20.0 0.0 Z", "three points close");
eq(drawPathD([[1.24, 2.26]]), "M1.2 2.3", "coordinates round to one decimal");
if (failures.length) {
  console.error(failures.length + " failure(s):\n" + failures.join("\n"));
  process.exit(1);
}
console.log("PIN BRIDGE UNIT OK " + "CHECKS_RUN");
"""


def _extract(name: str, source: str) -> str:
    start = source.index("function " + name + "(")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(f"unterminated function {name}")


def test_the_bridge_pure_helpers_keep_their_values(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    source = BRIDGE.read_text(encoding="utf-8")
    extracted = "\n".join(_extract(name, source) for name in PURE_HELPERS)
    for name in PURE_HELPERS:
        assert "function " + name + "(" in extracted
    checks = CHECKS.replace("CHECKS_RUN", str(CHECKS.count("eq(") - 1))
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "pin_bridge_units.js"
    script_path.write_text(extracted + checks, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "PIN BRIDGE UNIT OK" in result.stdout, result.stdout
