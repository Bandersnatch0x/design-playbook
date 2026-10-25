"""Drift gate for the generated visual-edit wire contract (ADR-0048 P2).

The server module ``visual_batch.py`` is the single authority for the wire
constants; ``scripts/generate_visual_contract.py`` derives the committed JS
artifact from it. These tests pin three things: the committed artifact equals a
fresh generation byte for byte, the artifact actually attaches the namespace
the four consumers read, and no consumer has re-literalized a contract value
the generator owns.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_PKG = _ROOT / "packages" / "design-playbook"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))
if str(_PKG / "tests") not in sys.path:
    sys.path.insert(0, str(_PKG / "tests"))

_ARTIFACT = _PKG / "mcp" / "preview" / "visual_contract.js"
_GENERATOR = _ROOT / "scripts" / "generate_visual_contract.py"


def _node_available() -> bool:
    import shutil

    return shutil.which("node") is not None


class TestVisualContractDriftGate(unittest.TestCase):
    def test_regeneration_is_byte_identical_to_the_committed_artifact(self) -> None:
        committed = _ARTIFACT.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "committed.js"
            backup.write_bytes(committed)
            try:
                result = subprocess.run(
                    [sys.executable, str(_GENERATOR)],
                    capture_output=True, text=True, cwd=str(_ROOT),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                fresh = _ARTIFACT.read_bytes()
            finally:
                backup_bytes = backup.read_bytes()
            # Restore before asserting so a failing run leaves the tree clean.
            _ARTIFACT.write_bytes(backup_bytes)
        self.assertEqual(fresh, backup_bytes,
                         "regenerated artifact drifted from the committed file; "
                         "run scripts/generate_visual_contract.py after changing "
                         "visual_batch.py")

    def test_the_artifact_attaches_the_namespace_the_consumers_read(self) -> None:
        if not _node_available():
            self.skipTest("node is required for JavaScript execution")
        source = _ARTIFACT.read_text(encoding="utf-8")
        payload = (
            "var window = globalThis;\n"
            + source
            + "\nconsole.log(JSON.stringify({"
            + "v: window.DPBUI.visualContract.SCHEMA_VERSION,"
            + " pending: window.DPBUI.visualContract.STATUS_PENDING,"
            + " stale: window.DPBUI.visualContract.STATUS_STALE,"
            + " kinds: window.DPBUI.visualContract.CHANGE_KINDS,"
            + " cssKinds: window.DPBUI.visualContract.CSS_KINDS,"
            + " viewports: window.DPBUI.visualContract.VIEWPORTS,"
            + " sources: window.DPBUI.visualContract.EDIT_SOURCES,"
            + " shell: window.DPBUI.visualContract.SHELL_SOURCE[0],"
            + " content: window.DPBUI.visualContract.CONTENT_PROPERTIES,"
            + " maxEdits: window.DPBUI.visualContract.MAX_EDITS}));"
        )
        script = Path(tempfile.mkdtemp()) / "contract_check.js"
        script.write_text(payload, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script)], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            '{"v":1,"pending":"pending","stale":"stale",'
            '"kinds":["style","layout","content","responsive","structure"],'
            '"cssKinds":["style","layout","responsive"],'
            '"viewports":["desktop","tablet","mobile","any"],'
            '"sources":["shell","frame","agent","unknown"],'
            '"shell":"shell",'
            '"content":["text","placeholder","aria-label"],'
            '"maxEdits":200}',
        )

    def test_consumers_read_the_contract_and_do_not_reliteralize_it(self) -> None:
        # The four hand-copied sites the generator replaced. A literal here
        # means a consumer regressed to a private copy of a contract value.
        cases = [
            ("control.js", ['"desktop", "tablet", "mobile"]']),
            ("control.review.js", ['batch.status !== "pending"', 'e.source !== "shell"']),
            ("control.react.js", ['schemaVersion: 1']),
            ("control.edits.js", []),
        ]
        for name, forbidden in cases:
            text = (_PKG / "mcp" / "preview" / name).read_text(encoding="utf-8")
            for literal in forbidden:
                with self.subTest(file=name, literal=literal):
                    self.assertNotIn(literal, text)

    def test_the_shell_assembly_inlines_the_contract_ahead_of_its_readers(self) -> None:
        from design_playbook.mcp.preview import control

        shared_core = control._load_shared_core()
        contract = control._load_visual_contract()
        self.assertLess(
            shared_core.find("DPBUI.visualContract"),
            len(shared_core),
        )
        self.assertIn("DPBUI.visualContract", contract)
        # The server pages assemble shared core, then contract, then every
        # reader; a reader that loads first would see an empty namespace.
        page = control._build_control(round_n=3, summary="drift gate", options=["confirm"])
        core_at = page.find("DPBUI.theme")
        contract_at = page.find("DPBUI.visualContract = {")
        self.assertGreater(contract_at, core_at, "contract must ship after the shared core")
        for reader in ("DPBUI.visualContract.VIEWPORTS", "DPBUI.visualContract.SCHEMA_VERSION"):
            self.assertIn(reader, page, f"{reader} missing from the assembled page")


if __name__ == "__main__":
    unittest.main()
