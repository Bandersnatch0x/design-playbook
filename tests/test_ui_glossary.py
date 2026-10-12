import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "packages" / "design-playbook" / "mcp"
PAIR = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*):\s*"((?:[^"\\]|\\.)*)"', re.M)


class UiGlossaryTest(unittest.TestCase):
    def terms(self):
        return json.loads((MCP / "_shared" / "glossary.json").read_text("utf-8"))["terms"]

    def test_run_console_strings_use_glossary_terms(self):
        text = (MCP / "run_console" / "app.js").read_text("utf-8")
        seen: dict[str, list[str]] = {}
        for key, value in PAIR.findall(text):
            seen.setdefault(key, []).append(value)
        checked = 0
        for key, values in seen.items():
            if len(values) != 2:
                continue
            en, zh = values
            en = re.sub(r"snapshot v\d+", "", en, flags=re.I)
            for term in self.terms():
                if term["en"] in en.lower():
                    checked += 1
                    self.assertIn(term["zh"], zh, f"{key}: {zh}")
        self.assertGreater(checked, 3)

    def test_run_console_reload_buttons_are_named_by_action(self):
        html = (MCP / "run_console" / "app.html").read_text("utf-8")
        labels = re.findall(r'data-reload id="[^"]+">([^<]+)<', html)
        self.assertEqual(len(labels), len(set(labels)), labels)
        js = (MCP / "run_console" / "app.js").read_text("utf-8")
        header = re.search(r'id="reload-button"[^>]*>([^<]+)<', html).group(1)
        self.assertNotIn(header, labels)


if __name__ == "__main__":
    unittest.main()
