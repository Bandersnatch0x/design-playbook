#!/usr/bin/env python3
"""Regression guard for the Preview versions compatibility-only freeze.

ADR-0027 placed Preview versions (``versions.py``) in a compatibility-only
lifecycle: no new authoring command, caller, schema, or feature behavior may
be introduced, while existing read behavior and log projection stay
compatible. These tests lock that frozen state so a future change cannot
silently expand the retired surface. Physical removal of the module is out of
scope until v1.0.0; see ``docs/deprecations/preview-versions.md``.
"""
from __future__ import annotations

import inspect
import re
import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview import versions  # noqa: E402

# Repo root = packages/<pkg>/<...>/this file -> parents[4].
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEPRECATION_DOC = _REPO_ROOT / "docs" / "deprecations" / "preview-versions.md"

# ADR-0027 freeze: functions that author (create/write) version artifacts.
# This set must not grow; new authoring entry points are forbidden.
FROZEN_AUTHORING = frozenset({"create_named_version", "fork"})

# ADR-0027 freeze: the full public function surface of versions.py. Adding any
# new public function would be new behavior and must fail this test. Read-only
# helpers are listed because they are part of the frozen compatible surface,
# not because new read helpers are permitted.
FROZEN_PUBLIC_FUNCTIONS = frozenset({
    "create_named_version",
    "fork",
    "state_at",
    "timeline",
    "list_versions",
    "render_versions_log",
    "refresh_version_projection",
})

# ADR-0027 freeze: schema constants defining the version-<seq>.json record.
FROZEN_SCHEMA_VERSION = 1
FROZEN_VALID_KINDS = frozenset({"confirmed", "revised", "custom"})


def _production_files() -> list[Path]:
    """Shipped .py files under the package, excluding tests and versions.py."""
    files: list[Path] = []
    for py in _PKG_ROOT.rglob("*.py"):
        if py.name.startswith("test_") or py.name == "conftest.py":
            continue
        rel = py.relative_to(_PKG_ROOT).as_posix()
        if rel == "mcp/preview/versions.py":
            continue
        files.append(py)
    return files


def _references_authoring(text: str) -> bool:
    """True if ``text`` calls or imports a versions authoring function.

    ``create_named_version`` is a unique token. ``fork`` is a common word, so
    it only counts as a violation when the same file also references the
    versions module (qualified call or import), which avoids false positives
    on unrelated uses of the word "fork". The module-reference check covers
    all three import forms: ``from .versions import ...``,
    ``from design_playbook.mcp.preview.versions import ...``, and
    ``from design_playbook.mcp.preview import versions`` / ``from . import
    versions`` (module-import then ``versions.fork(...)`` qualified call).
    """
    if re.search(r"\bcreate_named_version\b", text):
        return True
    if re.search(r"\bfork\b", text) and re.search(
        r"design_playbook\.mcp\.preview\.versions"
        r"|from\s+\.versions\b"
        r"|from\s+design_playbook\.mcp\.preview\s+import\s+versions"
        r"|from\s+\.\s+import\s+versions",
        text,
    ):
        return True
    return False


class VersionsFreezeGuardTests(unittest.TestCase):
    def test_version_schema_version_is_frozen(self) -> None:
        self.assertEqual(
            versions.VERSION_SCHEMA_VERSION, FROZEN_SCHEMA_VERSION)

    def test_version_record_kinds_are_frozen(self) -> None:
        self.assertEqual(
            frozenset(versions.VALID_KINDS), FROZEN_VALID_KINDS)

    def test_public_function_surface_is_frozen(self) -> None:
        defined = {
            name for name, obj in vars(versions).items()
            if not name.startswith("_")
            and inspect.isfunction(obj)
            and getattr(obj, "__module__", None) == versions.__name__
        }
        self.assertEqual(defined, FROZEN_PUBLIC_FUNCTIONS)

    def test_authoring_surface_is_frozen(self) -> None:
        # The authoring subset must be exactly these two and must not grow.
        self.assertEqual(
            FROZEN_AUTHORING,
            FROZEN_AUTHORING & FROZEN_PUBLIC_FUNCTIONS)
        for name in FROZEN_AUTHORING:
            self.assertTrue(
                callable(getattr(versions, name, None)),
                msg=f"authoring function {name!r} disappeared")

    def test_no_new_production_caller_of_authoring_functions(self) -> None:
        hits: list[str] = []
        for py in _production_files():
            try:
                text = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _references_authoring(text):
                hits.append(py.relative_to(_PKG_ROOT).as_posix())
        self.assertEqual(
            hits, [],
            "ADR-0027 freeze broken: a production file references a versions "
            f"authoring function (create_named_version/fork): {hits}")

    def test_transaction_still_imports_log_projection(self) -> None:
        # ADR-0027 keeps read/projection compatible through the dedicated
        # compatibility owner.
        transaction_path = (
            _PKG_ROOT / "mcp" / "preview" / "transaction.py")
        text = transaction_path.read_text(encoding="utf-8")
        self.assertIn("render_versions_log", text)
        self.assertIn("preview.compatibility", text)
        self.assertNotIn("preview.versions", text)

    def test_module_docstring_marks_deprecation(self) -> None:
        doc = (versions.__doc__ or "").strip()
        self.assertIn("ADR-0027", doc)
        self.assertIn("compatibility-only", doc.lower())
        self.assertIn("docs/deprecations/preview-versions.md", doc)

    def test_authoring_functions_carry_deprecation_markers(self) -> None:
        for name in FROZEN_AUTHORING:
            doc = (getattr(versions, name).__doc__ or "").strip()
            self.assertIn(
                "ADR-0027", doc,
                msg=f"{name} docstring missing ADR-0027 deprecation marker")

    def test_deprecation_doc_exists_and_names_owner_and_policy(self) -> None:
        self.assertTrue(
            DEPRECATION_DOC.is_file(),
            f"deprecation doc missing: {DEPRECATION_DOC}")
        text = DEPRECATION_DOC.read_text(encoding="utf-8")
        # Long-lived owner for compatibility reading + log projection.
        self.assertIn("compatibility.py", text)
        self.assertIn("transaction", text)
        self.assertIn("render_versions_log", text)
        # v1.0.0 is project migration policy, not a SemVer requirement.
        self.assertIn("v1.0.0", text)
        self.assertIn("project", text.lower())
        # A removal checklist must exist.
        self.assertIn("checklist", text.lower())
        # Physical removal is out of scope this cycle.
        self.assertIn("out of scope", text.lower())


if __name__ == "__main__":
    unittest.main()
