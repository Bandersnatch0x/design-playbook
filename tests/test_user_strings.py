"""U-19: Chinese user-visible strings in Preview and Run Console carry no implementation vocabulary."""
import re
import unittest
from pathlib import Path

MCP = Path(__file__).resolve().parents[1] / "packages" / "design-playbook" / "mcp"
FILES = ["run_console/app.js", "run_console/app.html", "preview/control.react.js",
         "preview/control.html", "preview/i18n.py", "preview/control.review.js"]
BLACKLIST = re.compile(r"bootstrap|\bowner\b|waiting-for-agent|tokens 文档|agent", re.I)
CJK = re.compile(r"[一-鿿]")


class ChineseUserStringTest(unittest.TestCase):
    def test_chinese_strings_have_no_implementation_words(self):
        hits = []
        for name in FILES:
            for no, line in enumerate((MCP / name).read_text("utf-8").splitlines(), 1):
                if line.strip().startswith(("//", "*", "#", "<!--")):
                    continue
                for text in re.findall(r'"([^"\n]*)"', line):
                    if CJK.search(text) and BLACKLIST.search(text):
                        hits.append(f"{name}:{no}: {text[:60]}")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
