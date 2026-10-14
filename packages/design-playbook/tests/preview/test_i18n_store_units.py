"""The locale store's table swap and lookups, executed from the shipped file.

`mcp/_shared/dpbui-core.js` holds the active label table plus the dual dict,
and the review file's language toggle swaps them. The swap is a single write
point now, so this extracts the store's source text from the canonical shared
file and runs it in node over a case table with a stub dict. It needs node,
which the repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import json
import re
import sys
import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
if str(PKG_ROOT) not in sys.path:  # one import seam (ADR-0022)
    sys.path.insert(0, str(PKG_ROOT))

PREVIEW = PKG_ROOT / "mcp" / "preview"
CORE = PKG_ROOT / "mcp" / "_shared" / "dpbui-core.js"
SHELL = PREVIEW / "control.js"
REVIEW = PREVIEW / "control.review.js"

# Mirrors the shipped shape: the initial active table is the page's own dict
# (single-locale at build time), the dual dict carries both.
DUAL = {
    "app_title": {"zh": "预览", "en": "Preview"},
    "round_n": {"zh": "第 {n} 轮", "en": "Round {n}"},
}
ACTIVE = {"app_title": "Preview"}

_HARNESS = """
var window = {};
window.DPB_I18N = __ACTIVE__;
window.DPB_I18N_DUAL = __DUAL__;
var DPBUI = {};
__STORE__
var rootEl = { getAttribute: function (k) { return k === "lang" ? __ROOT_LANG__ : null; } };
DPBUI.i18n.initialLang(rootEl);
var out = {};
out.initial = {
  lang: DPBUI.i18n.getLang(),
  title: DPBUI.i18n.tt("app_title"),
  round: DPBUI.i18n.ttN("round_n", 3),
};
DPBUI.i18n.setLang("zh");
out.afterZh = {
  lang: DPBUI.i18n.getLang(),
  title: DPBUI.i18n.tt("app_title"),
  round: DPBUI.i18n.ttN("round_n", 3),
  unknown: DPBUI.i18n.tt("no_such_key"),
  fallbackKey: DPBUI.i18n.tt("only_in_dual_unused"),
};
DPBUI.i18n.setLang("en");
out.afterEn = { lang: DPBUI.i18n.getLang(), title: DPBUI.i18n.tt("app_title") };
DPBUI.i18n.setLang("fr");
out.afterBogus = { lang: DPBUI.i18n.getLang(), title: DPBUI.i18n.tt("app_title") };
console.log(JSON.stringify(out));
"""


def _store_text() -> str:
    source = CORE.read_text(encoding="utf-8")
    start = source.index("DPBUI.i18n = (function () {")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1] + ")();"
    raise AssertionError("unterminated DPBUI.i18n store")


def _run(tmp_path, root_lang: str) -> dict:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    harness = (
        _HARNESS.replace("__STORE__", _store_text())
        .replace("__DUAL__", json.dumps(DUAL, ensure_ascii=False))
        .replace("__ACTIVE__", json.dumps(ACTIVE, ensure_ascii=False))
        .replace("__ROOT_LANG__", json.dumps(root_lang))
    )
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / "i18n_store_units.js"
    script_path.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_locale_store_keeps_its_answers(tmp_path) -> None:
    got = _run(tmp_path, "zh-CN")
    # Before any toggle the active table is the page's own dict; a key it
    # lacks falls back to the dual dict in the root's locale.
    assert got["initial"] == {"lang": "zh", "title": "Preview", "round": "第 3 轮"}
    assert got["afterZh"] == {
        "lang": "zh",
        "title": "预览",
        "round": "第 3 轮",
        # Unknown keys fall back to the key itself.
        "unknown": "no_such_key",
        "fallbackKey": "only_in_dual_unused",
    }
    assert got["afterEn"] == {"lang": "en", "title": "Preview"}
    # Anything but "zh" resolves to "en", matching the initial parse.
    assert got["afterBogus"] == {"lang": "en", "title": "Preview"}


def test_the_initial_locale_comes_from_the_root_lang(tmp_path) -> None:
    assert _run(tmp_path, "en").get("initial", {}).get("lang") == "en"
    assert _run(tmp_path, "zh").get("initial", {}).get("lang") == "zh"


def test_the_locale_state_has_one_write_point() -> None:
    core = CORE.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    review = REVIEW.read_text(encoding="utf-8")
    # Every write to the locale lives in the store block: outside it, the
    # shell and the review file only read through DPBUI.i18n.
    outside_store = core.replace(_store_text(), "")
    assert re.search(r"(?m)^\s*(?:var\s+)?lang\s*=", outside_store) is None
    assert re.search(r"(?m)^\s*(?:var\s+)?lang\s*=", shell) is None
    assert "langState" not in shell
    assert "langState" not in review
    assert "DPBUI.i18n" in review
