#!/usr/bin/env python3
"""Shape checks for reference-intake example fixtures (ADR-0011)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "packages" / "design-playbook" / "examples" / "reference-intake"
REQUIRED_HEADINGS = [
    "## Source summary",
    "## Evidence (observed)",
    "## Inferred (labeled)",
    "## Keep",
    "## Change",
    "## Do not copy",
    "## Functional constraints for ux-spec",
    "## Visual cues for ui-picker",
    "## License / brand risks",
    "## Unresolved questions",
]
REQUIRED_CONSTRAINT_MARKERS = (
    "always / ask / never hints:",
    "Captured at",
)
KINDS = {"screenshot", "url", "design_file", "product_analogy", "other"}


class ReferenceIntakeFixtureTests(unittest.TestCase):
    def test_three_fixtures_present(self) -> None:
        for name in ("screenshot", "url", "product-analogy"):
            case = EXAMPLES / name
            self.assertTrue((case / "contract.md").is_file(), name)
            self.assertTrue((case / "manifest.json").is_file(), name)

    def test_contract_headings_and_manifest_shape(self) -> None:
        for case_dir in sorted(p for p in EXAMPLES.iterdir() if p.is_dir()):
            contract = (case_dir / "contract.md").read_text(encoding="utf-8")
            for heading in REQUIRED_HEADINGS:
                self.assertIn(heading, contract, f"{case_dir.name} missing {heading}")
            for marker in REQUIRED_CONSTRAINT_MARKERS:
                self.assertIn(marker, contract, f"{case_dir.name} missing {marker}")
            for section in ("## Keep", "## Change", "## Do not copy"):
                # Third-party fixtures must not leave Keep/Change/Do not copy empty.
                idx = contract.index(section)
                rest = contract[idx + len(section) :]
                next_h = rest.find("\n## ")
                body = rest if next_h < 0 else rest[:next_h]
                bullets = [ln for ln in body.splitlines() if ln.strip().startswith("- ")]
                self.assertTrue(bullets, f"{case_dir.name} empty {section}")
            manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("schema"), "design-playbook.reference.manifest/v1")
            self.assertIn("sources", manifest)
            self.assertTrue(manifest["sources"])
            for src in manifest["sources"]:
                self.assertIn(src.get("kind"), KINDS)
                self.assertTrue(src.get("id"))
                self.assertTrue(src.get("locator"))


if __name__ == "__main__":
    unittest.main()
