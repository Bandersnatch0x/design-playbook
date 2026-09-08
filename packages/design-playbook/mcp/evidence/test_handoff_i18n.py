"""Locale behavior at the static builder public file boundary."""
from __future__ import annotations

import json
import html
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.handoff import build_static_handoff  # noqa: E402
from design_playbook.mcp.ui_locale import resolve_ui_locale  # noqa: E402
from design_playbook.mcp.preview.i18n import lang  # noqa: E402
from design_playbook.mcp.preview.integrity import decision_name  # noqa: E402
from design_playbook.scripts.run_handoff import main, run_handoff  # noqa: E402
from design_playbook.mcp.evidence.test_handoff import (  # noqa: E402
    DELIVERABLE_HTML, _fake_capture_runner, _make_run, _passing_gate_runner,
)


class HandoffLocaleTests(unittest.TestCase):
    def test_chinese_environment_localizes_page_not_machine_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            run = _make_run(tmp)
            deliverable = tmp / "filled-ui.html"
            deliverable.write_text(DELIVERABLE_HTML, encoding="utf-8")
            with patch.dict("os.environ", {"DPB_PREVIEW_LANG": "zh-CN"}):
                result = build_static_handoff(
                    run, deliverable, capture_runner=_fake_capture_runner,
                    gate_runner=_passing_gate_runner,
                )
            page = result.index_html.read_text(encoding="utf-8")
            self.assertIn('<html lang="zh-CN">', page)
            self.assertIn("静态交付", page)
            self.assertIn("下载 ZIP", page)
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"], "Pass")
            self.assertEqual(payload["gateStatuses"][0], "pass")
            self.assertEqual(result.deliverable_html.read_text(encoding="utf-8"), DELIVERABLE_HTML)


@pytest.mark.parametrize("locale", ["en", "en_US.UTF-8", "zh-CN", "zh_CN.UTF-8"])
def test_explicit_locale_preserves_author_text_and_machine_data(tmp_path, monkeypatch, locale):
    monkeypatch.setenv("DPB_PREVIEW_LANG", "zh-CN" if locale.startswith("en") else "en")
    run = _make_run(tmp_path)
    deliverable = tmp_path / "filled-ui.html"
    deliverable.write_text(DELIVERABLE_HTML, encoding="utf-8")
    summary = 'Author %PROFILE% </script><script>alert("x")</script>'
    entry_path = run / "preview" / decision_name(1)
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["outcome"]["feedback"] = summary
    entry_path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    result = build_static_handoff(
        run, deliverable, locale=locale, summary=summary,
        capture_runner=_fake_capture_runner, gate_runner=_passing_gate_runner,
    )
    page = result.index_html.read_text(encoding="utf-8")
    assert f'<html lang="{resolve_ui_locale(locale)}">' in page
    assert ("Static Handoff" if locale.startswith("en") else "静态交付") in page
    assert html.escape(summary, quote=False).replace('"', '&quot;') in page
    assert '<script>alert(' not in page
    raw = re.search(r'<script type="application/json">(.*?)</script>', page, re.S)
    assert raw is not None
    assert json.loads(raw[1]) == result.payload
    with ZipFile(result.zip_path) as archive:
        assert json.loads(archive.read("disclosure-review.json")) == result.payload
    assert result.payload["verdict"] == "Pass"
    assert result.payload["authority"] == "confirmed-user"
    assert html.escape(json.dumps(result.payload, ensure_ascii=False, indent=2), quote=False).replace('"', '&quot;') in page


@pytest.mark.parametrize("environment, expected", [
    ({}, "zh-CN"), ({"LANG": "en_US.UTF-8"}, "en"),
    ({"LANG": "fr_FR.UTF-8"}, "zh-CN"),
    ({"DPB_PREVIEW_LANG": "zh-CN", "LANG": "en_US.UTF-8"}, "zh-CN"),
])
def test_preview_and_handoff_share_environment_locale_policy(environment, expected):
    with patch.dict("os.environ", environment, clear=True):
        assert resolve_ui_locale() == lang() == expected


def test_invalid_explicit_locale_fails_before_writing(tmp_path):
    with pytest.raises(ValueError, match="Unsupported UI locale"):
        build_static_handoff(tmp_path, tmp_path / "absent.html", locale="fr")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_explicit_locale_falls_back_like_unspecified(blank):
    """A blank explicit locale encodes absence (form/MCP callers), not a
    bad locale: it must follow the env policy, not raise."""
    with patch.dict("os.environ", {"LANG": "en_US.UTF-8"}, clear=True):
        assert resolve_ui_locale(blank) == "en"
    with patch.dict("os.environ", {}, clear=True):
        assert resolve_ui_locale(blank) == "zh-CN"


def test_cli_exposes_explicit_locale(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    assert "--lang" in capsys.readouterr().out


def test_run_handoff_forwards_explicit_locale(tmp_path, monkeypatch):
    monkeypatch.setenv("DPB_PREVIEW_LANG", "zh-CN")
    run = _make_run(tmp_path)
    (run / "filled-ui.html").write_text(DELIVERABLE_HTML, encoding="utf-8")
    with (run / "plan.md").open("a", encoding="utf-8") as plan:
        plan.write("\nfill: filled-ui.html\n")
    result = run_handoff(
        run, locale="en", capture_runner=_fake_capture_runner,
        gate_runner=_passing_gate_runner,
    )
    assert '<html lang="en">' in result.index_html.read_text(encoding="utf-8")
