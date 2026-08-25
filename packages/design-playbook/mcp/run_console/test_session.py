#!/usr/bin/env python3
"""RCV1-006 slice 2: the process-owned single-run session (RED first).

Pins the session lifecycle at the API-independent boundary: one explicit
run root canonicalized once, a fresh >=256-bit token per session held only
in process memory, the snapshot/registry lifecycle with caching, locator
resolution through the RCV1-005 seams, injected-clock locator expiry, and
close-time invalidation of the token, registry, and document. Every
operation leaves the run tree byte-for-byte unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.projection import (  # noqa: E402
    SOURCE_LOCATOR_INVALID,
    SourceViewError,
)
from design_playbook.mcp.run_console.request_security import token_is_valid  # noqa: E402
from design_playbook.mcp.run_console.session import (  # noqa: E402
    RUN_ROOT_INVALID,
    SESSION_CLOSED,
    RunConsoleSession,
    RunConsoleSessionError,
    SourceView,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_NOW = "2026-08-25T10:00:00Z"
_LATER = "2026-08-25T11:00:00Z"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,}$")

_CONTRACT_BIND = {
    "ok": True,
    "schemaVersion": 1,
    "contract_sha": "a" * 64,
    "decision_log_sha": "b" * 64,
    "open_fields": [],
    "assumed_fields": [],
    "stale_fields": [],
    "blockers": [],
}
_MANIFEST_ENTRY = {
    "criterion": "L6.3",
    "artifact": "L6.3-error.png",
    "ts": "2026-08-25T09:00:00+08:00",
}
_ARTIFACT_BYTES = b"fake-png-bytes-run-006"


class _Clock:
    def __init__(self, now: str) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def _write(root: Path, relpath: str, text: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _make_root(base: Path, name: str = "run-a") -> Path:
    root = base / name
    root.mkdir(parents=True)
    _write(root, "spec.md", (_FIXTURES / "spec-script-summary.md").read_text(encoding="utf-8"))
    _write(root, "plan.md", (_FIXTURES / "plan-profile.md").read_text(encoding="utf-8"))
    _write(root, "point-back.md", (_FIXTURES / "point-back-pass-closed.md").read_text(encoding="utf-8"))
    _write(root, "contract-bind.json", json.dumps(_CONTRACT_BIND))
    _write(root, "evidence/manifest.jsonl", json.dumps(_MANIFEST_ENTRY) + "\n")
    (root / "evidence" / "L6.3-error.png").write_bytes(_ARTIFACT_BYTES)
    (root / "preview").mkdir()
    return root


def _record(document: dict, source_ref: str) -> dict:
    for item in document["sources"]["items"]:
        if item["sourceRef"] == source_ref:
            return item
    raise AssertionError(f"missing source record {source_ref}")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


class SessionConstructionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)

    def test_run_root_is_canonicalized_once(self) -> None:
        session = RunConsoleSession(
            run_root=self.base / "run-a" / ".", package_root=_PKG_ROOT
        )
        self.assertEqual(session.run_root, (self.base / "run-a").resolve())
        self.assertTrue(session.run_root.is_dir())
        self.assertFalse(session.closed)

    def test_string_run_root_is_accepted_and_canonicalized(self) -> None:
        session = RunConsoleSession(
            run_root=str(self.base / "run-a"), package_root=_PKG_ROOT
        )
        self.assertEqual(session.run_root, (self.base / "run-a").resolve())

    def test_missing_or_non_directory_run_root_is_rejected(self) -> None:
        for bad in (
            self.base / "missing",
            self.base / "run-a" / "spec.md",
            self.base / ".." / "no-such-run",
            None,
            123,
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(RunConsoleSessionError) as ctx:
                    RunConsoleSession(run_root=bad, package_root=_PKG_ROOT)
                self.assertEqual(ctx.exception.code, RUN_ROOT_INVALID)
                self.assertNotIn(str(bad), str(ctx.exception))

    def test_token_has_at_least_256_bits_of_fresh_entropy(self) -> None:
        session = RunConsoleSession(run_root=self.run_root, package_root=_PKG_ROOT)
        other = RunConsoleSession(run_root=self.run_root, package_root=_PKG_ROOT)
        self.assertRegex(session.token, _TOKEN_PATTERN)
        self.assertRegex(other.token, _TOKEN_PATTERN)
        self.assertNotEqual(session.token, other.token)
        # The token carries no run material.
        self.assertNotIn("run-a", session.token)

    def test_token_entropy_below_256_bits_is_rejected(self) -> None:
        for bad in (8, 31, "32", None, True):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    RunConsoleSession(
                        run_root=self.run_root,
                        package_root=_PKG_ROOT,
                        token_entropy_bytes=bad,
                    )

    def test_default_clock_builds_a_contract_valid_snapshot(self) -> None:
        session = RunConsoleSession(run_root=self.run_root, package_root=_PKG_ROOT)
        document = session.build_snapshot()
        self.assertEqual(validate_snapshot(document), document)


class SessionSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)
        self.clock = _Clock(_NOW)
        self.session = RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT, now_fn=self.clock
        )

    def test_build_snapshot_returns_contract_valid_document(self) -> None:
        document = self.session.build_snapshot()
        self.assertEqual(validate_snapshot(document), document)
        self.assertEqual(document["schemaVersion"], 1)

    def test_snapshot_is_built_once_and_cached(self) -> None:
        first = self.session.build_snapshot()
        second = self.session.build_snapshot()
        self.assertIs(first, second)

    def test_run_id_and_registry_follow_the_build(self) -> None:
        self.assertIsNone(self.session.run_id)
        self.assertIsNone(self.session.registry)
        self.session.build_snapshot()
        self.assertRegex(self.session.run_id, r"^run_[0-9a-f]{32}$")
        self.assertIsNotNone(self.session.registry)
        self.assertEqual(self.session.registry.selected_root, self.session.run_root)

    def test_resolve_source_returns_bound_excerpt_without_anchor(self) -> None:
        document = self.session.build_snapshot()
        record = _record(document, "source.specification")
        self.assertIsNotNone(record["locator"])
        view = self.session.resolve_source(record["locator"])
        self.assertIsInstance(view, SourceView)
        self.assertEqual(view.excerpt.source_ref, "source.specification")
        self.assertEqual(view.excerpt.content_hash, record["observedHash"])
        self.assertIsNone(view.anchor)
        self.assertTrue(view.excerpt.text)

    def test_resolve_source_before_build_is_uniformly_invalid(self) -> None:
        with self.assertRaises(SourceViewError) as ctx:
            self.session.resolve_source("src_" + "a" * 24)
        self.assertEqual(ctx.exception.code, SOURCE_LOCATOR_INVALID)

    def test_unknown_locator_is_uniformly_invalid(self) -> None:
        self.session.build_snapshot()
        with self.assertRaises(SourceViewError) as ctx:
            self.session.resolve_source("src_" + "z" * 24)
        self.assertEqual(ctx.exception.code, SOURCE_LOCATOR_INVALID)

    def test_locator_expiry_follows_the_injected_clock(self) -> None:
        document = self.session.build_snapshot()
        record = _record(document, "source.specification")
        self.assertTrue(self.session.resolve_source(record["locator"]).excerpt.text)
        self.clock.now = _LATER
        with self.assertRaises(SourceViewError) as ctx:
            self.session.resolve_source(record["locator"])
        self.assertEqual(ctx.exception.code, SOURCE_LOCATOR_INVALID)


class SessionCloseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)
        self.session = RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT, now_fn=_Clock(_NOW)
        )
        document = self.session.build_snapshot()
        self.locator = _record(document, "source.specification")["locator"]
        self.token = self.session.token

    def test_close_invalidates_token_registry_and_document(self) -> None:
        self.session.close()
        self.assertTrue(self.session.closed)
        self.assertIsNone(self.session.token)
        self.assertIsNone(self.session.registry)
        with self.assertRaises(RunConsoleSessionError) as ctx:
            self.session.build_snapshot()
        self.assertEqual(ctx.exception.code, SESSION_CLOSED)
        with self.assertRaises(RunConsoleSessionError) as ctx:
            self.session.resolve_source(self.locator)
        self.assertEqual(ctx.exception.code, SESSION_CLOSED)
        self.assertFalse(token_is_valid(self.session.token, self.token))

    def test_close_is_idempotent(self) -> None:
        self.session.close()
        self.session.close()
        self.assertTrue(self.session.closed)


class SessionReadOnlyTest(unittest.TestCase):
    def test_build_resolve_and_close_write_nothing_under_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_root(Path(tmp).resolve())
            session = RunConsoleSession(
                run_root=root, package_root=_PKG_ROOT, now_fn=_Clock(_NOW)
            )
            before = _tree_digest(root)
            document = session.build_snapshot()
            locator = _record(document, "source.specification")["locator"]
            session.resolve_source(locator)
            session.close()
            self.assertEqual(_tree_digest(root), before)


if __name__ == "__main__":
    unittest.main()
