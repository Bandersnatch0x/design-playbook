"""Drift gate for the generated snapshot shape contract.

``snapshot_v1.schema.json`` is the single owner of the seven-part snapshot
shape. ``scripts/generate_snapshot_contract.py`` derives the Console client's
copy from it, so a section added to the schema and missed by the client turns
this file red instead of leaving the client silently accepting a partial shape.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_PKG = _ROOT / "packages" / "design-playbook"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

_ARTIFACT = _PKG / "mcp" / "run_console" / "snapshot_contract.js"
_SCHEMA = _PKG / "mcp" / "run_console" / "snapshot_v1.schema.json"
_GENERATOR = _ROOT / "scripts" / "generate_snapshot_contract.py"
_APP_JS = _PKG / "mcp" / "run_console" / "app.js"
_APP_HTML = _PKG / "mcp" / "run_console" / "app.html"


class SnapshotContractDriftGate(unittest.TestCase):
    def test_regeneration_is_byte_identical_to_the_committed_artifact(self) -> None:
        committed = _ARTIFACT.read_bytes()
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fresh_path = Path(tmp) / "snapshot_contract.js"
            result = subprocess.run(
                [sys.executable, str(_GENERATOR), "--out", str(fresh_path)],
                capture_output=True, text=True, cwd=str(_ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            fresh = fresh_path.read_bytes()
        self.assertEqual(
            fresh, committed,
            "regenerated artifact drifted from the committed file; run "
            "scripts/generate_snapshot_contract.py after changing the schema")

    def test_the_artifact_carries_the_schema_required_list(self) -> None:
        import json

        schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
        text = _ARTIFACT.read_text(encoding="utf-8")
        sections = [name for name in schema["required"] if name != "schemaVersion"]
        self.assertIn(
            "REQUIRED_SECTIONS: [" + ", ".join(f'"{n}"' for n in sections) + "],",
            text)
        self.assertIn(
            f'SCHEMA_VERSION: {schema["properties"]["schemaVersion"]["const"]},',
            text)

    def test_the_client_reads_the_contract_and_does_not_reliteralize_it(self) -> None:
        text = _APP_JS.read_text(encoding="utf-8")
        for literal in (
            '["identity", "intent", "execution", "evaluation", "nextActions"',
            "body.schemaVersion !== 1",
        ):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, text)
        self.assertIn("DPBUI.snapshotContract.REQUIRED_SECTIONS", text)

    def test_the_shell_loads_the_contract_ahead_of_the_client(self) -> None:
        html = _APP_HTML.read_text(encoding="utf-8")
        contract_at = html.find('src="snapshot_contract.js"')
        client_at = html.find('src="app.js"')
        self.assertGreater(contract_at, -1, "contract script missing from the shell")
        self.assertGreater(client_at, contract_at,
                           "the contract must load before the client that reads it")


if __name__ == "__main__":
    unittest.main()
