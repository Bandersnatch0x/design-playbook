"""U-24: the abort control is quiet at rest, approve stays narrow, the ready pulse is finite."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[2] / "mcp/preview/control.css").read_text(encoding="utf-8")


def _decls(selector_re):
    out = []
    for m in re.finditer(r"(?m)^([^{}@/\n][^{}]*)\{([^}]*)\}", CSS):
        if re.search(selector_re, m.group(1).strip()):
            out.append((m.group(1).strip(), m.group(2)))
    return out


def test_abort_rest_color_is_not_danger():
    rules = _decls(r"^\.dpb-abort-btn, #dpb-abort$")
    assert rules
    for sel, body in rules:
        assert "var(--dpb-danger)" not in body, sel


def test_abort_hover_keeps_danger():
    hov = _decls(r"#dpb-abort:hover")
    assert hov and "var(--dpb-danger)" in hov[0][1]


def test_approve_min_width_at_most_160px():
    for sel, body in _decls(r"\.dpb-approve-btn"):
        m = re.search(r"min-width:\s*(\d+)px", body)
        if m:
            assert int(m.group(1)) <= 160, sel


def test_ready_pulse_runs_at_most_twice():
    rules = _decls(r"dpb-approve-ready \.dpb-approve-dot")
    assert rules
    for sel, body in rules:
        assert "infinite" not in body, sel
        if "dpb-ping" in body:
            assert re.search(r"dpb-ping[^;]*\s[12]\s*;", body), sel
