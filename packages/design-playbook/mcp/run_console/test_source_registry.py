#!/usr/bin/env python3
"""Source-bound registry tests: fixed allowlist, browser rejection, locators.

These tests pin the RCV1-005 slice-A contract for
``design_playbook.mcp.run_console.source_registry``:

- one selected canonical run root yields exactly the fixed fifteen logical
  Source registry keys from the parity specification, with stable source
  refs, authority keys, kinds, locator classes, and capture-target
  allowlists;
- browser-shaped input can never add a source or a target;
- locators are random opaque ``src_`` tokens bound server-side to the
  session, the one selected run, one allowlisted logical source (and
  canonical contained target), an optional semantic anchor, and the
  observed source hash.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.source_registry import (  # noqa: E402
    LOCATOR_INPUT_INVALID,
    SELECTED_RUN_INVALID,
    LocatorBinding,
    RegisteredSource,
    SourceRegistry,
    SourceRegistryError,
    select_source_registry,
)
from design_playbook.scripts.run_metadata import (  # noqa: E402
    project_selected_run,
)

_SESSION_SECRET = b"registry-test-session-secret-005"
_OTHER_SECRET = b"other-session-secret-005"
_RUN_FACTS_CAPTURE_TARGETS = (
    "spec.md",
    "01-spec.md",
    "point-back.md",
    "plan.md",
    "preview/",
    "evidence/",
    "design-baseline/state.json",
    "decision-report.md",
    "shaping/shaping-log.jsonl",
    "craft-guard.md",
)
# Parity specification section 2: the fixed fifteen logical registry keys.
_EXPECTED_KEYS = (
    "session.selected-run",
    "package.metadata",
    "run.profile",
    "intent.specification",
    "intent.contract",
    "execution.stage-registry",
    "execution.preview",
    "execution.repair",
    "evaluation.evaluator",
    "evaluation.ledger",
    "evaluation.manifest",
    "run.next-action",
    "run.limitations",
    "role-attestation.owner",
    "diagnostic-export",
)
_EXPECTED_SOURCES = {
    "session.selected-run": {
        "source_ref": "source.selected-run",
        "authority_key": "session.selected-run",
        "kind": "session-selection",
        "locator_class": "session-selection-summary",
        "capture_targets": (),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": False,
    },
    "package.metadata": {
        "source_ref": "source.package-metadata",
        "authority_key": "package.metadata",
        "kind": "package",
        "locator_class": "package-summary",
        "capture_targets": (".claude-plugin/plugin.json",),
        "root_scope": "package-root",
        "viewable": True,
        "mapped": True,
        "anchored": False,
    },
    "run.profile": {
        "source_ref": "source.run-profile",
        "authority_key": "run.profile",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": ("plan.md",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "intent.specification": {
        "source_ref": "source.specification",
        "authority_key": "intent.specification",
        "kind": "artifact",
        "locator_class": "artifact-excerpt",
        "capture_targets": ("spec.md", "01-spec.md"),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "intent.contract": {
        "source_ref": "source.contract-bind",
        "authority_key": "intent.contract",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": ("contract-bind.json",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "execution.stage-registry": {
        "source_ref": "source.run-facts",
        "authority_key": "execution.stage-registry",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": _RUN_FACTS_CAPTURE_TARGETS,
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "execution.preview": {
        "source_ref": "source.preview",
        "authority_key": "execution.preview",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": ("preview/",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "execution.repair": {
        "source_ref": "source.repair-report",
        "authority_key": "execution.repair",
        "kind": "artifact",
        "locator_class": "artifact-excerpt",
        "capture_targets": ("point-back.md",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "evaluation.evaluator": {
        "source_ref": "source.evaluator-report",
        "authority_key": "evaluation.evaluator",
        "kind": "artifact",
        "locator_class": "artifact-excerpt",
        "capture_targets": ("point-back.md",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "evaluation.ledger": {
        "source_ref": "source.evidence-ledger",
        "authority_key": "evaluation.ledger",
        "kind": "artifact",
        "locator_class": "artifact-excerpt",
        "capture_targets": ("point-back.md",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "evaluation.manifest": {
        "source_ref": "source.evidence-manifest",
        "authority_key": "evaluation.manifest",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": ("evidence/manifest.jsonl",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "run.next-action": {
        "source_ref": "source.run-status",
        "authority_key": "run.next-action",
        "kind": "authority-record",
        "locator_class": "authority-record-excerpt",
        "capture_targets": _RUN_FACTS_CAPTURE_TARGETS + ("contract-bind.json",),
        "root_scope": "run-root",
        "viewable": True,
        "mapped": True,
        "anchored": True,
    },
    "run.limitations": {
        "source_ref": "source.owner-limitations.run-metadata",
        "authority_key": "run.limitations",
        "kind": "authority-record",
        "locator_class": "non-viewable",
        "capture_targets": (),
        "root_scope": "run-root",
        "viewable": False,
        "mapped": True,
        "anchored": False,
    },
    "role-attestation.owner": {
        "source_ref": None,
        "authority_key": "role-attestation.owner",
        "kind": "authority-record",
        "locator_class": "non-viewable",
        "capture_targets": (),
        "root_scope": "run-root",
        "viewable": False,
        "mapped": False,
        "anchored": False,
    },
    "diagnostic-export": {
        "source_ref": None,
        "authority_key": "diagnostic-export",
        "kind": "authority-record",
        "locator_class": "non-viewable",
        "capture_targets": (),
        "root_scope": "run-root",
        "viewable": False,
        "mapped": False,
        "anchored": False,
    },
}
_SOURCE_REF_PATTERN = re.compile(
    r"^source\.[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)*$"
)
_LOCATOR_PATTERN = re.compile(r"^src_[A-Za-z0-9_-]{16,}$")
_HASH = "sha256:" + "a" * 64
_NOW = "2026-08-25T10:00:00Z"


def _make_run_root(base: Path, name: str) -> Path:
    """Create a minimal selected run root with real owner files present."""
    root = base / name
    (root / "preview").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "spec.md").write_text("# Spec\n\n```yaml\ncriteria:\n```\n", encoding="utf-8")
    (root / "point-back.md").write_text("## Verdict\n\n**Pass.**\n", encoding="utf-8")
    (root / "plan.md").write_text("# Plan\n", encoding="utf-8")
    return root


class _RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_run_root(self.base, "run-a")
        self.registry = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _fixed_table(self, registry: SourceRegistry) -> tuple[RegisteredSource, ...]:
        return registry.sources

    def _issue_spec_locator(self) -> str:
        return self.registry.issue_locator(
            source_ref="source.specification",
            expected_hash=_HASH,
            now=_NOW,
        )


class FixedRegistryTest(_RegistryTestCase):
    def test_keys_are_exactly_the_fixed_fifteen(self) -> None:
        self.assertEqual(self.registry.keys, _EXPECTED_KEYS)
        self.assertEqual(len(_EXPECTED_KEYS), 15)

    def test_every_key_matches_expected_registration(self) -> None:
        for key, expected in _EXPECTED_SOURCES.items():
            with self.subTest(key=key):
                source = self.registry.source(key)
                self.assertEqual(source.key, key)
                for field, value in expected.items():
                    self.assertEqual(
                        getattr(source, field),
                        value,
                        f"{key}.{field}",
                    )

    def test_sources_are_returned_in_fixed_key_order(self) -> None:
        self.assertEqual(
            tuple(source.key for source in self.registry.sources),
            _EXPECTED_KEYS,
        )

    def test_every_mapped_source_ref_is_a_valid_unique_source_ref(self) -> None:
        refs = [
            source.source_ref
            for source in self.registry.sources
            if source.source_ref is not None
        ]
        self.assertEqual(len(refs), len(set(refs)))
        for ref in refs:
            self.assertIsNotNone(_SOURCE_REF_PATTERN.match(ref), ref)

    def test_gate_keys_have_no_source_record(self) -> None:
        for key in ("role-attestation.owner", "diagnostic-export"):
            source = self.registry.source(key)
            self.assertIsNone(source.source_ref)
            self.assertFalse(source.mapped)
            self.assertFalse(source.viewable)
            self.assertEqual(source.locator_class, "non-viewable")
            self.assertEqual(source.capture_targets, ())

    def test_mapped_and_viewable_partitions(self) -> None:
        mapped = self.registry.mapped_sources
        self.assertEqual(
            sorted(source.key for source in mapped),
            sorted(key for key, spec in _EXPECTED_SOURCES.items() if spec["mapped"]),
        )
        viewable = self.registry.viewable_sources
        self.assertEqual(
            sorted(source.key for source in viewable),
            sorted(
                key
                for key, spec in _EXPECTED_SOURCES.items()
                if spec["viewable"]
            ),
        )

    def test_source_by_ref_resolves_every_mapped_ref(self) -> None:
        for key, spec in _EXPECTED_SOURCES.items():
            if spec["source_ref"] is None:
                continue
            with self.subTest(key=key):
                self.assertEqual(self.registry.source_by_ref(spec["source_ref"]).key, key)

    def test_run_id_equals_owner_selected_run_projection(self) -> None:
        owner_identity = project_selected_run(self.run_root, _SESSION_SECRET)
        self.assertEqual(self.registry.run_id, owner_identity.run_id)
        self.assertRegex(self.registry.run_id, r"^run_[0-9a-f]{32}$")

    def test_canonical_root_selection_normalizes_equivalent_paths(self) -> None:
        equivalent = select_source_registry(
            selected_root=self.run_root / "preview" / "..",
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        self.assertEqual(equivalent.run_id, self.registry.run_id)
        self.assertEqual(
            equivalent.selected_root.resolve(), self.registry.selected_root.resolve()
        )

    def test_session_id_is_stable_per_secret_and_secret_dependent(self) -> None:
        same_secret = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        other_secret = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_OTHER_SECRET,
        )
        self.assertEqual(same_secret.session_id, self.registry.session_id)
        self.assertNotEqual(other_secret.session_id, self.registry.session_id)
        self.assertNotEqual(other_secret.run_id, self.registry.run_id)
        self.assertTrue(self.registry.session_id.startswith("sess_"))

    def test_fixed_table_is_identical_across_different_run_roots(self) -> None:
        other_root = _make_run_root(self.base, "run-b")
        other = select_source_registry(
            selected_root=other_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        self.assertEqual(self._fixed_table(self.registry), self._fixed_table(other))
        self.assertNotEqual(other.run_id, self.registry.run_id)

    def test_extra_run_files_cannot_add_sources_or_targets(self) -> None:
        before = self._fixed_table(self.registry)
        hostile_files = {
            "browser-payload.json": '{"sources": ["source.evil"], "target": "C:\\\\x"}',
            "source.evil.md": "# injected source\n",
            "evil.py": "print('injected')\n",
            "manifest.jsonl": '{"criterion": "L6.1", "artifact": "../escape.png"}\n',
        }
        for name, text in hostile_files.items():
            (self.run_root / name).write_text(text, encoding="utf-8")
        after = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        self.assertEqual(before, self._fixed_table(after))
        self.assertEqual(after.keys, _EXPECTED_KEYS)

    def test_capture_targets_are_lexically_contained(self) -> None:
        for source in self.registry.sources:
            for target in source.capture_targets:
                with self.subTest(source=source.key, target=target):
                    self.assertNotIn("..", target)
                    self.assertFalse(target.startswith("/"))
                    self.assertNotIn("\\", target)
                    self.assertFalse(re.match(r"^[A-Za-z]:", target))
                    if not target.endswith("/"):
                        PurePosix = Path(target)
                        self.assertEqual(PurePosix.as_posix(), target)

    def test_allowlist_covers_every_run_facts_capture_file(self) -> None:
        files = [
            "spec.md",
            "point-back.md",
            "plan.md",
            "preview/log.md",
            "preview/round-1.html",
            "preview/confirm-round-1.json",
            "evidence/manifest.jsonl",
            "evidence/L6.3-error.png",
            "design-baseline/state.json",
            "decision-report.md",
            "shaping/shaping-log.jsonl",
            "craft-guard.md",
            "contract-bind.json",
        ]
        for relpath in files:
            with self.subTest(relpath=relpath):
                self.assertTrue(
                    self.registry.allows_target(relpath),
                    f"no allowlisted source covers {relpath}",
                )

    def test_allowlist_rejects_outside_targets(self) -> None:
        for relpath in (
            "../outside.txt",
            "evil.py",
            "browser-payload.json",
            "decisions.jsonl",
            "contract.json",
            "state.json",
        ):
            with self.subTest(relpath=relpath):
                self.assertFalse(self.registry.allows_target(relpath))


class BrowserInputRejectionTest(_RegistryTestCase):
    """Browser-shaped payloads must never add a source or a target."""

    HOSTILE_ROOTS = (
        {"sources": [{"ref": "source.evil", "path": "/etc/passwd"}]},
        ["source.evil", "../../etc/passwd"],
        12345,
        None,
        "http://127.0.0.1:8080/api/v1/sources/src_evil",
        "not-an-existing-path-xyz",
        "../outside-relative",
    )

    def test_hostile_selected_root_payloads_never_produce_a_registry(self) -> None:
        for payload in self.HOSTILE_ROOTS:
            with self.subTest(payload=repr(payload)[:60]):
                with self.assertRaises((SourceRegistryError, TypeError)):
                    select_source_registry(
                        selected_root=payload,  # type: ignore[arg-type]
                        package_root=_PKG_ROOT,
                        session_secret=_SESSION_SECRET,
                    )

    def test_missing_root_is_a_fixed_selection_error(self) -> None:
        with self.assertRaises(SourceRegistryError) as caught:
            select_source_registry(
                selected_root=self.base / "no-such-run",
                package_root=_PKG_ROOT,
                session_secret=_SESSION_SECRET,
            )
        self.assertEqual(caught.exception.code, SELECTED_RUN_INVALID)

    def test_invalid_session_secret_is_rejected(self) -> None:
        for secret in (b"", "not-bytes", None):
            with self.subTest(secret=repr(secret)):
                with self.assertRaises((SourceRegistryError, TypeError)):
                    select_source_registry(
                        selected_root=self.run_root,
                        package_root=_PKG_ROOT,
                        session_secret=secret,  # type: ignore[arg-type]
                    )

    def test_constructor_accepts_no_browser_supplied_source_input(self) -> None:
        browser_payload = {
            "sources": [{"sourceRef": "source.evil", "target": "/etc/passwd"}],
            "targets": ["../../etc/passwd"],
        }
        with self.assertRaises(TypeError):
            select_source_registry(
                selected_root=self.run_root,
                package_root=_PKG_ROOT,
                session_secret=_SESSION_SECRET,
                sources=browser_payload,  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            select_source_registry(
                self.run_root,  # type: ignore[misc]
                _PKG_ROOT,  # type: ignore[misc]
                _SESSION_SECRET,  # type: ignore[misc]
                browser_payload,  # type: ignore[misc]
            )

    def test_registry_exposes_no_source_registration_api(self) -> None:
        for name in (
            "register",
            "register_source",
            "add",
            "add_source",
            "append",
            "update",
            "set_source",
            "remove",
        ):
            self.assertFalse(
                hasattr(self.registry, name), f"registry must not expose {name}"
            )

    def test_registered_sources_are_immutable(self) -> None:
        source = self.registry.source("intent.specification")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            source.source_ref = "source.evil"  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            source.capture_targets = ("../../etc/passwd",)  # type: ignore[misc]

    def test_unknown_source_keys_and_refs_are_rejected(self) -> None:
        for key in ("browser.injected", "source.evil", "", None, 123):
            with self.subTest(key=repr(key)):
                with self.assertRaises(SourceRegistryError):
                    self.registry.source(key)  # type: ignore[arg-type]
        for ref in ("source.evil", "source.role-attestation.claim", "src_abc", ""):
            with self.subTest(ref=ref):
                with self.assertRaises(SourceRegistryError):
                    self.registry.source_by_ref(ref)

    HOSTILE_ISSUANCE_INPUTS = (
        {"source_ref": "source.evil"},
        {"source_ref": "source.../../etc/passwd"},
        {"source_ref": ""},
        {"source_ref": None},
        {"source_ref": 123},
        {"source_ref": "source.specification", "target": "../../etc/passwd"},
        {"source_ref": "source.specification", "target": "/etc/passwd"},
        {"source_ref": "source.specification", "target": "C:\\Windows\\system.ini"},
        {"source_ref": "source.specification", "target": "..\\..\\escape.txt"},
        {"source_ref": "source.specification", "target": "%2e%2e%2fevil.txt"},
        {"source_ref": "source.specification", "target": "file:///etc/passwd"},
        {"source_ref": "source.specification", "target": "point-back.md"},
        {"source_ref": "source.specification", "target": "preview/log.md"},
        {"source_ref": "source.specification", "expected_hash": "not-a-hash"},
        {"source_ref": "source.specification", "expected_hash": "sha256:XYZ"},
        {"source_ref": "source.specification", "expected_hash": 123},
        {"source_ref": "source.specification", "expected_hash": None},
        {"source_ref": "source.specification", "anchor": {"label": "Verdict"}},
        {"source_ref": "source.specification", "anchor": ""},
        {"source_ref": "source.specification", "anchor": 123},
        {"source_ref": "source.specification", "now": "not-a-timestamp"},
        {"source_ref": "source.specification", "now": None},
        {"source_ref": "source.selected-run", "anchor": "Verdict"},
        {"source_ref": "source.package-metadata", "anchor": "version"},
        {"source_ref": "source.owner-limitations.run-metadata"},
        {"source_ref": "diagnostic-export"},
        {"source_ref": "role-attestation.owner"},
    )

    def test_hostile_locator_issuance_input_is_uniformly_rejected(self) -> None:
        before = self._fixed_table(self.registry)
        for payload in self.HOSTILE_ISSUANCE_INPUTS:
            with self.subTest(payload=repr(payload)[:70]):
                kwargs = {"expected_hash": _HASH, "now": _NOW}
                kwargs.update(payload)
                with self.assertRaises(SourceRegistryError) as caught:
                    self.registry.issue_locator(**kwargs)  # type: ignore[arg-type]
                self.assertEqual(caught.exception.code, LOCATOR_INPUT_INVALID)
        self.assertEqual(before, self._fixed_table(self.registry))
        self.assertEqual(self.registry.keys, _EXPECTED_KEYS)

    def test_browser_payload_queries_cannot_mutate_the_registry(self) -> None:
        before = self._fixed_table(self.registry)
        for attack in (
            lambda: self.registry.source("browser.injected"),
            lambda: self.registry.source_by_ref("source.evil"),
            # A browser-shaped payload (not a plain relpath string) fails
            # loudly; traversal *strings* are simply not allowlisted
            # (asserted in test_allowlist_rejects_outside_targets).
            lambda: self.registry.allows_target({"target": "../../etc/passwd"}),
            lambda: self.registry.lookup_locator("src_../../etc/passwd"),
            lambda: self.registry.lookup_locator(None),
            lambda: self.registry.derive_evidence_artifact_source("../evil.png"),
        ):
            with self.assertRaises((SourceRegistryError, TypeError)):
                attack()
        self.assertEqual(before, self._fixed_table(self.registry))


class LocatorTest(_RegistryTestCase):
    def test_locator_tokens_match_the_opaque_grammar(self) -> None:
        for source_ref in (
            "source.selected-run",
            "source.package-metadata",
            "source.specification",
            "source.evidence-manifest",
        ):
            with self.subTest(source_ref=source_ref):
                token = self.registry.issue_locator(
                    source_ref=source_ref,
                    expected_hash=_HASH,
                    now=_NOW,
                )
                self.assertIsNotNone(_LOCATOR_PATTERN.match(token), token)

    def test_locator_tokens_are_random_and_unique(self) -> None:
        tokens = [
            self.registry.issue_locator(
                source_ref="source.specification",
                expected_hash=_HASH,
                anchor="L6.1",
                now=_NOW,
            )
            for _ in range(50)
        ]
        self.assertEqual(len(tokens), len(set(tokens)))

    def test_locator_tokens_are_not_derived_from_bound_values(self) -> None:
        token = self._issue_spec_locator()
        self.assertNotIn("source.specification", token)
        self.assertNotIn(_HASH, token)
        self.assertNotIn(self.registry.run_id, token)
        again = self._issue_spec_locator()
        self.assertNotEqual(token, again)
        # Two tokens issued for identical bindings must draw independently
        # from the full token alphabet: a deterministic encoding of the
        # binding (hex/base32-style) would use a much smaller character
        # set across both tokens.
        bodies = (token.removeprefix("src_"), again.removeprefix("src_"))
        self.assertGreaterEqual(
            len(set("".join(bodies))),
            20,
            "locator tokens look derived from a narrow encoding",
        )

    def test_binding_carries_session_run_source_anchor_and_hash(self) -> None:
        token = self.registry.issue_locator(
            source_ref="source.specification",
            expected_hash=_HASH,
            anchor="L6.1",
            now=_NOW,
        )
        binding = self.registry.lookup_locator(token, now=_NOW)
        self.assertIsInstance(binding, LocatorBinding)
        assert binding is not None
        self.assertEqual(binding.locator, token)
        self.assertEqual(binding.session_id, self.registry.session_id)
        self.assertEqual(binding.run_id, self.registry.run_id)
        self.assertEqual(binding.source_ref, "source.specification")
        self.assertEqual(binding.authority_key, "intent.specification")
        self.assertEqual(binding.kind, "artifact")
        self.assertEqual(binding.locator_class, "artifact-excerpt")
        self.assertEqual(binding.target, "spec.md")
        self.assertEqual(binding.anchor, "L6.1")
        self.assertEqual(binding.expected_hash, _HASH)
        self.assertEqual(binding.issued_at, _NOW)

    def test_binding_target_defaults_and_allows_allowlisted_targets(self) -> None:
        default_binding = self.registry.lookup_locator(
            self.registry.issue_locator(
                source_ref="source.specification",
                expected_hash=_HASH,
                now=_NOW,
            ),
            now=_NOW,
        )
        assert default_binding is not None
        self.assertEqual(default_binding.target, "spec.md")
        explicit = self.registry.lookup_locator(
            self.registry.issue_locator(
                source_ref="source.preview",
                expected_hash=_HASH,
                target="preview/confirm-round-1.json",
                now=_NOW,
            ),
            now=_NOW,
        )
        assert explicit is not None
        self.assertEqual(explicit.target, "preview/confirm-round-1.json")

    def test_viewable_authority_record_source_can_issue_a_locator(self) -> None:
        """run.profile is mapped, viewable, and anchored: issuance is legal.

        The hostile-issuance table must reject gate and non-viewable keys
        only; over-broad rejection of a viewable authority-record source
        would contradict the fixed registration table.
        """
        token = self.registry.issue_locator(
            source_ref="source.run-profile",
            expected_hash=_HASH,
            anchor="run-profile",
            now=_NOW,
        )
        binding = self.registry.lookup_locator(token, now=_NOW)
        assert binding is not None
        self.assertEqual(binding.source_ref, "source.run-profile")
        self.assertEqual(binding.authority_key, "run.profile")
        self.assertEqual(binding.target, "plan.md")

    def test_session_selection_binding_has_no_file_target(self) -> None:
        binding = self.registry.lookup_locator(
            self.registry.issue_locator(
                source_ref="source.selected-run",
                expected_hash=_HASH,
                now=_NOW,
            ),
            now=_NOW,
        )
        assert binding is not None
        self.assertIsNone(binding.target)
        self.assertIsNone(binding.anchor)

    def test_expiry_is_enforced_at_lookup(self) -> None:
        token = self.registry.issue_locator(
            source_ref="source.specification",
            expected_hash=_HASH,
            now="2026-08-25T10:00:00Z",
            ttl_seconds=900,
        )
        before = self.registry.lookup_locator(token, now="2026-08-25T10:14:59Z")
        self.assertIsNotNone(before)
        after = self.registry.lookup_locator(token, now="2026-08-25T10:15:01Z")
        self.assertIsNone(after)

    MALFORMED_LOCATORS = (
        "",
        "not-a-locator",
        "src_short",
        "src_abc def",
        "src_../../etc/passwd",
        "src_%2e%2e%2f",
        "SRC_ABCDEFGHIJKLMNOP",
        "src_../evidence/manifest.jsonl",
        "src_C:\\\\Windows\\\\system.ini",
        "src_\x00\x01\x02",
        "src_" + "a" * 15,
        "source.specification",
        "run_0123456789abcdef0123456789abcdef",
        123,
        None,
        ["src_abcdefghijklmnop"],
        {"locator": "src_abcdefghijklmnop"},
    )

    def test_lookup_of_malformed_or_unknown_locators_is_uniformly_none(self) -> None:
        for locator in self.MALFORMED_LOCATORS:
            with self.subTest(locator=repr(locator)[:50]):
                self.assertIsNone(
                    self.registry.lookup_locator(locator, now=_NOW)  # type: ignore[arg-type]
                )

    def test_lookup_requires_exact_token_equality(self) -> None:
        token = self._issue_spec_locator()
        mutated = token[:-1] + ("A" if token[-1] != "A" else "B")
        self.assertIsNone(self.registry.lookup_locator(mutated, now=_NOW))

    def test_locator_is_invalid_in_another_session(self) -> None:
        token = self._issue_spec_locator()
        other_session = select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_OTHER_SECRET,
        )
        self.assertIsNone(other_session.lookup_locator(token, now=_NOW))

    def test_locator_is_invalid_in_another_run(self) -> None:
        token = self._issue_spec_locator()
        other_root = _make_run_root(self.base, "run-b")
        other_run = select_source_registry(
            selected_root=other_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        self.assertIsNone(other_run.lookup_locator(token, now=_NOW))

    def test_no_locator_can_be_issued_for_gate_keys(self) -> None:
        for ref in (
            "source.owner-limitations.run-metadata",
            "source.role-attestation.claim.intent.x",
            "source.evidence-artifact.unknown-png",
        ):
            with self.subTest(ref=ref):
                with self.assertRaises(SourceRegistryError):
                    self.registry.issue_locator(
                        source_ref=ref,
                        expected_hash=_HASH,
                        now=_NOW,
                    )


class EvidenceArtifactSourceTest(_RegistryTestCase):
    def test_derived_artifact_source_is_allowlisted_and_stable(self) -> None:
        derived = self.registry.derive_evidence_artifact_source("L6.3-error.png")
        self.assertEqual(derived.key, "evaluation.manifest")
        self.assertEqual(derived.source_ref, "source.evidence-artifact.l6-3-error-png")
        self.assertEqual(derived.authority_key, "evaluation.manifest")
        self.assertEqual(derived.kind, "artifact")
        self.assertEqual(derived.locator_class, "artifact-excerpt")
        self.assertEqual(derived.capture_targets, ("evidence/L6.3-error.png",))
        self.assertTrue(derived.viewable)
        self.assertTrue(derived.mapped)
        self.assertTrue(derived.anchored)
        again = self.registry.derive_evidence_artifact_source("L6.3-error.png")
        self.assertEqual(derived, again)

    def test_derivation_does_not_extend_the_fixed_registry(self) -> None:
        self.registry.derive_evidence_artifact_source("L6.3-error.png")
        self.assertEqual(self.registry.keys, _EXPECTED_KEYS)
        self.assertEqual(len(self.registry.mapped_sources), 13)

    HOSTILE_ARTIFACT_NAMES = (
        "../manifest.jsonl",
        "..\\..\\escape.png",
        "/etc/passwd",
        "C:\\Windows\\system.ini",
        "sub/../../escape.png",
        "nested/dir/artifact.png",
        "..",
        ".",
        "",
        "%2e%2e%2fevil.png",
        "L6.3 error.png",
        "L6.3/ERROR.png",
        None,
        123,
    )

    def test_hostile_artifact_names_are_rejected(self) -> None:
        before = self._fixed_table(self.registry)
        for name in self.HOSTILE_ARTIFACT_NAMES:
            with self.subTest(name=repr(name)[:50]):
                with self.assertRaises((SourceRegistryError, TypeError)):
                    self.registry.derive_evidence_artifact_source(name)  # type: ignore[arg-type]
        self.assertEqual(before, self._fixed_table(self.registry))

    def test_derived_artifact_locator_binds_the_contained_target(self) -> None:
        token = self.registry.issue_locator(
            source_ref="source.evidence-artifact.l6-3-error-png",
            expected_hash=_HASH,
            now=_NOW,
        )
        binding = self.registry.lookup_locator(token, now=_NOW)
        assert binding is not None
        self.assertEqual(binding.target, "evidence/L6.3-error.png")
        self.assertEqual(binding.source_ref, "source.evidence-artifact.l6-3-error-png")

    def test_derived_artifact_locator_rejects_foreign_targets(self) -> None:
        for target in ("spec.md", "point-back.md", "../evil.png", "evidence/../plan.md"):
            with self.subTest(target=target):
                with self.assertRaises(SourceRegistryError):
                    self.registry.issue_locator(
                        source_ref="source.evidence-artifact.l6-3-error-png",
                        expected_hash=_HASH,
                        target=target,
                        now=_NOW,
                    )


class ReadOnlyTest(_RegistryTestCase):
    def _tree_digest(self, root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            digest.update(relative.encode("utf-8"))
            if path.is_file():
                digest.update(path.read_bytes())
        return digest.hexdigest()

    def test_registry_operations_write_nothing(self) -> None:
        before = self._tree_digest(self.run_root)
        select_source_registry(
            selected_root=self.run_root,
            package_root=_PKG_ROOT,
            session_secret=_SESSION_SECRET,
        )
        token = self._issue_spec_locator()
        self.registry.lookup_locator(token, now=_NOW)
        self.registry.lookup_locator("src_not-issued-at-all-123", now=_NOW)
        self.registry.derive_evidence_artifact_source("L6.3-error.png")
        self.assertEqual(before, self._tree_digest(self.run_root))

    def test_construction_reads_no_run_file_bytes(self) -> None:
        recorded: list[Path] = []
        original_read_text = Path.read_text
        original_read_bytes = Path.read_bytes

        def recording_read_text(self_path: Path, *args: object, **kwargs: object) -> str:
            recorded.append(self_path)
            return original_read_text(self_path, *args, **kwargs)  # type: ignore[arg-type]

        def recording_read_bytes(self_path: Path, *args: object) -> bytes:
            recorded.append(self_path)
            return original_read_bytes(self_path, *args)  # type: ignore[arg-type]

        Path.read_text = recording_read_text  # type: ignore[method-assign]
        Path.read_bytes = recording_read_bytes  # type: ignore[method-assign]
        try:
            select_source_registry(
                selected_root=self.run_root,
                package_root=_PKG_ROOT,
                session_secret=_SESSION_SECRET,
            )
        finally:
            Path.read_text = original_read_text  # type: ignore[method-assign]
            Path.read_bytes = original_read_bytes  # type: ignore[method-assign]
        for path in recorded:
            self.assertFalse(
                path.is_relative_to(self.run_root),
                f"registry construction must not read run bytes: {path}",
            )


class InterfaceStabilityTest(_RegistryTestCase):
    def test_error_is_a_value_error_with_a_safe_code(self) -> None:
        error = SourceRegistryError(SELECTED_RUN_INVALID)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, SELECTED_RUN_INVALID)
        self.assertNotIn(str(self.run_root), str(error))

    def test_module_constants_are_stable(self) -> None:
        self.assertEqual(SELECTED_RUN_INVALID, "selected-run-invalid")
        self.assertEqual(LOCATOR_INPUT_INVALID, "locator-input-invalid")


if __name__ == "__main__":
    unittest.main()
