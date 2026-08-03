#!/usr/bin/env python3
"""Lockstep test: run-review normalize rule (SSOT) vs aggregate_runs.normalize.

SSOT: ``packages/design-playbook/commands/run-review.md`` states the rule
inline (casefold + whitespace-collapsed, then char-for-char equality).
Follower: monorepo ``scripts/aggregate_runs.py`` ``normalize()`` — not
shipped in the installable package. This test locks the follower to the
stated rule so a silent drift (e.g. stripping punctuation, fuzzy match)
cannot invent or merge repeat blockers.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "packages" / "design-playbook" / "commands" / "run-review.md"
AGGREGATE = ROOT / "scripts" / "aggregate_runs.py"


def _load_normalize():
    spec = importlib.util.spec_from_file_location(
        "dpb_aggregate_runs_under_test", AGGREGATE
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Avoid executing CLI side effects; aggregate_runs only defines helpers
    # at import time (no main on import).
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.normalize


def ssot_normalize(text: str) -> str:
    """Reference impl of the rule stated in commands/run-review.md."""
    return " ".join(text.casefold().split())


CORPUS = [
    "",
    "   ",
    "blocked",
    "Blocked",
    "BLOCKED",
    "  blocked  ",
    "blocked\tby\ngate",
    "Blocked  by   gate",
    "blocked by gate",
    "mirror surface used",
    "Mirror  Surface\tUsed",
    "太挤了",
    "  太挤了  ",
    "A\u00a0B",  # nbsp — split() treats as whitespace
    "pass vs fail",
    "pass  vs   fail",
]


# Load once at import (plain function — do not hang on the class or
# unittest binds it as an instance method and double-passes self).
follower_normalize = _load_normalize()


class NormalizeLockstepTest(unittest.TestCase):
    def test_command_ssot_states_rule(self) -> None:
        """Prose SSOT must still name casefold + whitespace collapse."""
        text = COMMAND.read_text(encoding="utf-8")
        self.assertTrue(COMMAND.is_file(), f"missing SSOT command: {COMMAND}")
        self.assertIn("casefold", text.casefold())
        self.assertTrue(
            "whitespace" in text.casefold() or "空白" in text,
            "run-review.md must state whitespace collapse",
        )

    def test_follower_matches_ssot_over_corpus(self) -> None:
        for raw in CORPUS:
            with self.subTest(raw=raw[:40]):
                self.assertEqual(
                    follower_normalize(raw),
                    ssot_normalize(raw),
                    f"normalize drifted from SSOT rule for {raw!r}",
                )

    def test_equality_is_char_for_char_on_normalized(self) -> None:
        """Literal differences after normalize stay separate keys."""
        a = ssot_normalize("Blocked by gate")
        b = ssot_normalize("blocked  by\tgate")
        c = ssot_normalize("blocked by gate!")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(follower_normalize("Blocked by gate"), a)
        self.assertEqual(follower_normalize("blocked  by\tgate"), b)
        self.assertEqual(follower_normalize("blocked by gate!"), c)


if __name__ == "__main__":
    unittest.main()
