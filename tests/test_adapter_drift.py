"""Snapshot drift compare for committed adapter output (spec 2026-09-20 D3).

One compare algorithm lives in the packaged ``adapter_drift`` module; the
root validate.py gate (blocking) and root doctor report (read-only) are
thin consumers. These tests pin the compare semantics directly.

T-156 adds the package-root ``agent-plugins`` bundle (``plugin.json`` +
``mcp.json``) to the same compare, so tampering with the committed portable
manifest is the same red gate as tampering with the codex snapshot.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

sys.path.insert(0, str(PKG / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))

import adapter_drift  # noqa: E402
import adapter_matrix  # noqa: E402
import generated_artifacts  # noqa: E402
from generate_adapter import SNAPSHOT_BUNDLES, render_entries  # noqa: E402


def _write_fresh(target: Path) -> None:
    """Write codex's fresh render into *target* as committed files."""
    _version, _out, entries = render_entries("codex", target)
    for rel, content in entries:
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def _stub_complete_root(root: Path) -> None:
    """The sibling paths the portable bundle references, as empty stubs."""
    for rel in ("skills/.keep", "mcp/preview/server.py", "mcp/evidence/server.py"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _write_fresh_bundle(root: Path) -> None:
    _version, _out, entries = render_entries("agent-plugins", root)
    for rel, content in entries:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


class CompareSnapshotTests(unittest.TestCase):
    def test_clean_tree(self) -> None:
        rows = adapter_drift.compare_snapshots(PKG)
        self.assertTrue(rows, "codex is the tier-1 snapshot agent")
        self.assertTrue(all(r["status"] == "clean" for r in rows))

    def test_snapshot_targets_drive_the_loop(self) -> None:
        # The gate iterates the matrix's tier-1 snapshot agents plus the
        # package-root bundles with committed snapshots; the former "codex"
        # hardcode in both gate copies is gone, and T-156 adds agent-plugins
        # to the same red/green path.
        agents = {r["agent"] for r in adapter_drift.compare_snapshots(PKG)}
        self.assertEqual(
            agents, set(adapter_matrix.TIER1_SNAPSHOT_AGENTS) | set(SNAPSHOT_BUNDLES)
        )

    def test_missing_snapshot(self) -> None:
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
            rows = [r for r in adapter_drift.compare_snapshots(root)
                    if r["agent"] == "codex"]
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
        self.assertEqual(
            len(rows),
            len(adapter_matrix.TIER1_SNAPSHOT_AGENTS) + len(SNAPSHOT_BUNDLES),
        )
        self.assertTrue(all(r["status"] == "error" for r in rows))
        self.assertIn("nope", rows[0]["message"])


class BundleSnapshotTests(unittest.TestCase):
    """T-156: the committed portable bundle is a real package-root snapshot."""

    def test_committed_bundle_is_clean(self) -> None:
        rows = [
            r for r in adapter_drift.compare_snapshots(PKG)
            if r["agent"] == "agent-plugins"
        ]
        self.assertTrue(rows, "agent-plugins must be a snapshot target")
        self.assertTrue(all(r["status"] == "clean" for r in rows), rows)

    def test_tampered_bundle_snapshot_is_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _stub_complete_root(root)
            _write_fresh_bundle(root)
            victim = root / "plugin.json"
            victim.write_text(
                victim.read_text(encoding="utf-8") + "\ntampered\n",
                encoding="utf-8", newline="\n",
            )
            rows = [
                r for r in adapter_drift.compare_snapshots(root)
                if r["agent"] == "agent-plugins"
            ]
        drifted = [r for r in rows if r["status"] == "drifted" and r["path"]]
        self.assertEqual([r["path"] for r in drifted], ["plugin.json"])
        self.assertIn("generate_adapter.py agent-plugins", drifted[0]["repair"])
        aggregate = next(r for r in rows if r["path"] is None)
        self.assertEqual(aggregate["status"], "drifted")

    def test_register_lists_the_bundle_snapshot(self) -> None:
        # The generated-artifact register is what validate.py walks; without
        # this row the committed manifest could ship with no owner and no gate.
        row = next(
            e for e in generated_artifacts.ARTIFACTS
            if e.name == "agent plugins bundle snapshot"
        )
        self.assertEqual(
            row.generator, "packages/design-playbook/scripts/generate_adapter.py"
        )
        self.assertEqual(
            row.artifacts,
            (
                "packages/design-playbook/plugin.json",
                "packages/design-playbook/mcp.json",
            ),
        )
        self.assertEqual(row.gate, "tests/test_adapter_drift.py")


if __name__ == "__main__":
    unittest.main()
