"""The theme store's rule and write path, executed from the shipped file.

`mcp/_shared/dpbui-core.js` resolves the active theme from three inputs — an explicit host
preference on <html>/<body>, the stored choice, and the system scheme — and
that precedence decides what every shell surface renders in. The store keeps
it as a pure function plus a single write point, so this extracts the store's
source text from the canonical shared file and runs it in node over a case
table, with a minimal DOM stub standing in for the surfaces. It needs node,
which the repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import json
import sys
import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
if str(PKG_ROOT) not in sys.path:  # one import seam (ADR-0022)
    sys.path.insert(0, str(PKG_ROOT))
from design_playbook.mcp.preview import control as preview_control  # noqa: E402

PREVIEW = PKG_ROOT / "mcp" / "preview"
CORE = PKG_ROOT / "mcp" / "_shared" / "dpbui-core.js"
SHELL = PREVIEW / "control.js"
REVIEW = PREVIEW / "control.review.js"

# (explicit, stored, prefersDark, expected)
CASES = [
    ("dark", None, False, "dark"),
    ("light", "dark", True, "light"),
    (None, "dark", False, "dark"),
    (None, None, True, "dark"),
    (None, None, False, "light"),
    ("bogus", "dark", False, "dark"),
    ("bogus", "bogus", True, "dark"),
    (None, "bogus", True, "dark"),
    (None, "bogus", False, "light"),
]

_HARNESS = """
var DPBUI = {};
__STORE__
var els = {};
function mkEl() {
  return {
    attrs: {},
    innerHTML: "",
    setAttribute: function (k, v) { this.attrs[k] = String(v); },
    getAttribute: function (k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
  };
}
["dpb-root", "dpb-float-root", "dpb-toasts", "dpb-theme-icon"].forEach(function (id) { els[id] = mkEl(); });
var writes = [];
globalThis.document = { getElementById: function (id) { return els[id] || null; } };
globalThis.localStorage = {
  getItem: function () { return null; },
  setItem: function (k, v) { writes.push([k, String(v)]); },
};
var cases = __CASES__;
var out = {};
out.resolved = cases.map(function (c) { return DPBUI.theme.resolveTheme(c[0], c[1], c[2]); });
out.storageKey = DPBUI.theme.STORAGE_KEY;
DPBUI.theme.applyTheme("dark", true);
out.afterDark = {
  root: els["dpb-root"].getAttribute("data-theme"),
  float: els["dpb-float-root"].getAttribute("data-theme"),
  toasts: els["dpb-toasts"].getAttribute("data-theme"),
  darkIcon: els["dpb-theme-icon"].innerHTML.indexOf("circle") !== -1,
  writes: writes.slice(),
  current: DPBUI.theme.current(),
};
DPBUI.theme.applyTheme("light", false);
out.afterLight = {
  root: els["dpb-root"].getAttribute("data-theme"),
  darkIcon: els["dpb-theme-icon"].innerHTML.indexOf("circle") !== -1,
  writes: writes.slice(),
  current: DPBUI.theme.current(),
};
delete els["dpb-root"];
out.missingRoot = DPBUI.theme.current();
console.log(JSON.stringify(out));
"""


def _store_text() -> str:
    source = CORE.read_text(encoding="utf-8")
    start = source.index("DPBUI.theme = (function () {")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1] + ")();"
    raise AssertionError("unterminated DPBUI.theme store")


def test_the_theme_store_keeps_its_answers(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    harness = _HARNESS.replace("__STORE__", _store_text()).replace(
        "__CASES__", json.dumps([case[:3] for case in CASES])
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "theme_store_units.js"
    script_path.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    want = [case[3] for case in CASES]
    assert got["resolved"] == want, "\n".join(
        f"case {i} {case[:3]!r}: got {g}, want {w}"
        for i, (case, g, w) in enumerate(zip(CASES, got["resolved"], want))
        if g != w
    )
    assert got["storageKey"] == "dpb.preview.theme"
    assert got["afterDark"] == {
        "root": "dark",
        "float": "dark",
        "toasts": "dark",
        "darkIcon": True,
        "writes": [["dpb.preview.theme", "dark"]],
        "current": "dark",
    }
    assert got["afterLight"] == {
        "root": "light",
        "darkIcon": False,
        "writes": [["dpb.preview.theme", "dark"]],
        "current": "light",
    }
    assert got["missingRoot"] == "light"


def test_the_theme_preference_has_one_write_point() -> None:
    core = CORE.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    review = REVIEW.read_text(encoding="utf-8")
    assert core.count('"dpb.preview.theme"') == 1
    assert "dpb.preview.theme" not in shell
    assert "dpb.preview.theme" not in review


def test_the_assembled_page_carries_the_stores_once_before_the_shell() -> None:
    # The shell reads through the stores, so the canonical bytes must reach the
    # page exactly once, in their own block ahead of the shell bundle — a second
    # copy here is the drift this move exists to remove.
    core = CORE.read_text(encoding="utf-8")
    page = preview_control._build_control(2, "Review summary", ["Confirm", "Revise"])
    assert page.count(core) == 1
    shell_anchor = 'function chromeLabels(surface, selector) {'
    assert page.index(core) < page.index(shell_anchor)
    assert page.count("DPBUI.theme = (function () {") == 1
