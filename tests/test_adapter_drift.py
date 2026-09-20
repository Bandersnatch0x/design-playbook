"""T-038: shared adapter snapshot drift compare (spec 2026-09-20 D3).

One compare algorithm lives in the packaged ``adapter_drift`` module; the
root validate.py gate (blocking) and root doctor report (read-only) are
thin consumers. These tests pin the compare semantics directly.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

sys.path.insert(0, str(PKG / "scripts"))

import adapter_drift  # noqa: E402
import adapter_matrix  # noqa: E402
from generate_adapter import render_entries  # noqa: E402


def _write_fresh(target: Path) -> None:
    """Write codex's fresh render into *target* as committed files."""
    _version, _out, entries = render_entries("codex", target)
    for rel, content in entries:
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


class CompareSnapshotTests(unittest.TestCase):
    def test_clean_tree(self) -> None:
        rows = adapter_drift.compare_snapshots(PKG)
        self.assertTrue(rows, "codex is the tier-1 snapshot agent")
        self.assertTrue(all(r["status"] == "clean" for r in rows))

    def test_tier1_agents_drive_the_loop(self) -> None:
        # The gate iterates TIER1_SNAPSHOT_AGENTS — the "codex" hardcode in
        # both former gate copies is gone; a second tier-1 snapshot agent
        # would appear here without editing either consumer.
        agents = {r["agent"] for r in adapter_drift.compare_snapshots(PKG)}
        self.assertEqual(agents, set(adapter_matrix.TIER1_SNAPSHOT_AGENTS))

    def test_missing_snapshot(self) -> None:
        # A nonexistent root: every committed snapshot reads as missing.
        with tempfile.TemporaryDirectory() as tmp:
            rows = adapter_drift.compare_snapshots(Path(tmp) / "no-such-root")
        missing = {r["path"] for r in rows if r["status"] == "missing"}
        self.assertIn(".codex-plugin/plugin.json", missing)
        aggregate = next(r for r in rows if r["path"] is None)
        self.assertEqual(aggregate["status"], "drifted")

    def test_drifted_snapshot(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_fresh(root)
            victim = root / "codex" / "AGENTS.md"
            victim.write_text(
                victim.read_text(encoding="utf-8") + "\ntampered\n",
                encoding="utf-8", newline="\n",
            )
            rows = adapter_drift.compare_snapshots(root)
        drifted = {r["path"] for r in rows if r["status"] == "drifted" and r["path"]}
        self.assertEqual(drifted, {"codex/AGENTS.md"})
        drift_row = next(r for r in rows if r["status"] == "drifted" and r["path"])
        self.assertIn("generate_adapter.py codex", drift_row["repair"])
        aggregate = next(r for r in rows if r["path"] is None)
        self.assertEqual(aggregate["status"], "drifted")

    def test_crlf_checkout_is_clean(self) -> None:
        # A CRLF checkout of a clean snapshot is not drift (LF-normalized
        # compare on both sides).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _version, _out, entries = render_entries("codex", root)
            for rel, content in entries:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
            rows = adapter_drift.compare_snapshots(root)
        self.assertTrue(all(r["status"] == "clean" for r in rows))

    def test_render_error_row(self) -> None:
        def _boom(agent, out_dir=None):
            raise ValueError("nope")

        original = adapter_drift.render_entries
        adapter_drift.render_entries = _boom
        try:
            rows = adapter_drift.compare_snapshots(PKG)
        finally:
            adapter_drift.render_entries = original
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "error")
        self.assertIn("nope", rows[0]["message"])


if __name__ == "__main__":
    unittest.main()
