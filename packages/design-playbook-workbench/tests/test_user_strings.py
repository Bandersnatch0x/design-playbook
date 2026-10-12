"""U-19: user-visible workbench text carries no implementation vocabulary."""
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"
BLACKLIST = re.compile(r"bootstrap|\bowner\b|waiting-for-agent|tokens 文档|agent", re.I)
CJK = re.compile(r"[一-鿿]")


def html_text(source):
    source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    out = re.sub(r"<[^>]+>", "\n", source)
    out += "\n".join(re.findall(r'(?:aria-label|title|placeholder)="([^"]*)"', source))
    return out.splitlines()


def js_strings(source):
    for line in source.splitlines():
        for match in re.findall(r'"([^"\n]*)"|`([^`\n]*)`', line):
            text = re.sub(r"\$\{[^}]*\}", "", "".join(match))
            if CJK.search(text):
                yield text


class UserStringTest(unittest.TestCase):
    def test_html_text_has_no_implementation_words(self):
        hits = [t.strip() for t in html_text((WEB / "app.html").read_text("utf-8"))
                if BLACKLIST.search(t)]
        self.assertEqual(hits, [])

    def test_js_strings_have_no_implementation_words(self):
        hits = [t for t in js_strings((WEB / "app.js").read_text("utf-8"))
                if BLACKLIST.search(t)]
        self.assertEqual(hits, [])
