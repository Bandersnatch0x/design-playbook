#!/usr/bin/env python3
"""Lockstep test: adapter digest agrees with validator digest.

The G5 prototype hash is computed by the bundled preview adapter at
record-write time (``mcp/preview/util.py``) and re-verified by the
validator (``scripts/_preview_integrity.py``) on another host. The two
copies are comment-locked ("Must stay in lockstep with …") — this test
turns that comment into a failing test over a byte corpus, so a
normalization drift (e.g. adding ``strip()``, treating lone ``\\r``
differently, or touching the digest algorithm) breaks CI instead of
silently flipping G5 integrity between the writing machine and a Linux
CI runner (issue 02 / T01).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCRIPTS_DIR = ROOT / "packages" / "design-playbook" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_PREVIEW_DIR = ROOT / "packages" / "design-playbook" / "mcp" / "preview"
if str(_PREVIEW_DIR) not in sys.path:
    sys.path.insert(0, str(_PREVIEW_DIR))

from _preview_integrity import prototype_html_digest as validator_digest  # noqa: E402
from util import prototype_html_digest as adapter_digest  # noqa: E402

CORPUS = [
    b"",
    b"<html></html>",
    b"<html>\n</html>",
    b"<html>\r\n</html>",
    b"<html>\r</html>",
    b"<p>line one\nline two</p>",
    b"<p>line one\r\nline two</p>",
    b"\r\n\r\n",
    "太挤了".encode("utf-8"),
    "安师大".encode("utf-8"),
    bytes(range(256)),  # binary content
]


class DigestLockstepTest(unittest.TestCase):
    def test_copies_agree_over_corpus(self) -> None:
        for raw in CORPUS:
            with self.subTest(raw=raw[:24]):
                self.assertEqual(adapter_digest(raw), validator_digest(raw))

    def test_normalization_ignores_line_endings(self) -> None:
        lf = b"<div>a\nb</div>"
        crlf = b"<div>a\r\nb</div>"
        cr = b"<div>a\rb</div>"
        expected = validator_digest(lf)
        self.assertEqual(adapter_digest(crlf), expected)
        self.assertEqual(adapter_digest(cr), expected)


if __name__ == "__main__":
    unittest.main()
