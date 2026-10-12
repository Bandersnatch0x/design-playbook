"""U-30: radii come from tokens; blur backdrops give way under reduced transparency."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEETS = [
    "packages/design-playbook/mcp/preview/control.css",
    "packages/design-playbook/mcp/run_console/app.css",
    "packages/design-playbook-workbench/design_playbook_workbench/web/app.css",
]


def _css(rel):
    return re.sub(r"/\*.*?\*/", "", (ROOT / rel).read_text(encoding="utf-8"), flags=re.S)


def test_radius_literals_only_in_tokens():
    for rel in SHEETS:
        bad = re.findall(r"border(?:-[a-z]+)*-radius\s*:[^;}]*\d+px", _css(rel))
        assert not bad, (rel, bad[:5])


def test_radius_scale_tokens_defined():
    tokens = (ROOT / "packages/design-playbook/mcp/_shared/tokens.css").read_text(encoding="utf-8")
    for name in ("xs", "sm", "", "lg", "full"):
        token = "--dpb-radius" + ("-" + name if name else "")
        assert re.search(re.escape(token) + r":\s*\d", tokens), token


def test_blur_backdrops_drop_under_reduced_transparency():
    for rel in SHEETS:
        css = _css(rel)
        if "backdrop-filter: blur" not in css:
            continue
        m = re.search(r"@media \(prefers-reduced-transparency: reduce\)\s*\{(.*)", css, flags=re.S)
        assert m, rel
        assert "backdrop-filter: none" in m.group(1), rel
