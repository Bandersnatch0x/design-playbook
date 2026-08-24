#!/usr/bin/env python3
"""Audit-preference write-back and first-ask tests (issue #69, ADR-0033).

Split from tests/test_audit_preferences.py (file-size budget): this module
owns the persistence half - declaration write-back (repo/local scope,
this-run-only exemption, gitignore hygiene) and the one-time first-ask
projection. The parsing/merge and skeleton/marker halves live in
test_audit_preferences.py and test_audit_skeleton.py.

Acceptance coverage (issue #69):
* write-back round trips: a declaration writes back as the new default
  (repo or local scope); "this run only" exempts the stage choices but
  still sets the asked bit;
* local override respected and documented as gitignored;
* corrupt file -> absent semantics -> the one-time first ask is
  retriggered (module projection).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts import audit_preferences  # noqa: E402


def _write_prefs(repo: Path, text: str, *, local: bool = False) -> None:
    name = "preferences.local.yaml" if local else "preferences.yaml"
    target = repo / ".design-playbook" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _resolve(repo: Path, declaration=None):
    return audit_preferences.resolve_preferences(repo, declaration)


class WriteBackTests(unittest.TestCase):
    """Issue #69 / ADR-0033 D11: a user declaration writes back as the new
    default unless the user says "this run only"; the asked bit is set by
    every write-back. Output stays in the locked flat schema - hand-written
    lines, no YAML library."""

    def test_declaration_writes_back_as_new_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            path = audit_preferences.write_back(repo, {"craft_guard": False})
            self.assertEqual(
                path, repo / ".design-playbook" / "preferences.yaml")
            prefs = audit_preferences.load_preferences_file(path)
            self.assertIsNotNone(prefs)
            self.assertIs(prefs.craft_guard, False)
            self.assertIsNone(prefs.observe)
            self.assertIsNone(prefs.ui_evaluator)
            self.assertIs(prefs.asked, True)
            # Round trip: the written default now resolves from the repo
            # layer and the one-time question is consumed.
            effective = _resolve(repo)
        self.assertFalse(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "repo")
        self.assertTrue(effective.observe.runs)
        self.assertTrue(effective.asked)
        self.assertFalse(audit_preferences.needs_first_ask(effective))

    def test_full_declaration_round_trips_every_stage(self) -> None:
        declaration = {
            "craft_guard": False, "observe": False, "ui_evaluator": True}
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            audit_preferences.write_back(repo, declaration)
            effective = _resolve(repo)
        for stage, value in declaration.items():
            resolution = getattr(effective, stage)
            self.assertEqual(resolution.runs, value, stage)
            self.assertEqual(resolution.source, "repo", stage)

    def test_write_back_preserves_untouched_existing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "observe: false\n")
            audit_preferences.write_back(repo, {"craft_guard": False})
            prefs = audit_preferences.load_preferences_file(
                repo / ".design-playbook" / "preferences.yaml")
        self.assertIsNotNone(prefs)
        self.assertIs(prefs.craft_guard, False)
        self.assertIs(prefs.observe, False)  # untouched key survives
        self.assertIs(prefs.asked, True)

    def test_write_back_overwrites_corrupt_file_with_clean_record(self) -> None:
        # Fail-closed reads treat damage as absent; write-back recovers the
        # layer with a clean locked-schema record.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "observe: [broken\n")
            audit_preferences.write_back(repo, {"observe": False})
            effective = _resolve(repo)
        self.assertFalse(effective.observe.runs)
        self.assertEqual(effective.observe.source, "repo")
        self.assertTrue(effective.asked)
        self.assertEqual(effective.invalid_files, ())

    def test_this_run_only_exemption_keeps_defaults_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "craft_guard: true\nasked: true\n")
            audit_preferences.write_back(
                repo, {"craft_guard": False}, this_run_only=True)
            effective = _resolve(repo)
        # The one-off exception never rewrites the remembered default.
        self.assertTrue(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "repo")
        self.assertTrue(effective.asked)

    def test_this_run_only_without_prior_record_sets_asked_only(self) -> None:
        # The stage choices are exempt, but the question itself was asked:
        # persisting asked-only keeps D2's "ask once" without leaking a
        # one-off choice into the defaults.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            audit_preferences.write_back(
                repo, {"observe": False}, this_run_only=True)
            prefs = audit_preferences.load_preferences_file(
                repo / ".design-playbook" / "preferences.yaml")
            effective = _resolve(repo)
        self.assertIsNotNone(prefs)
        self.assertIsNone(prefs.observe)  # exempted choice not persisted
        self.assertIs(prefs.asked, True)
        self.assertTrue(effective.observe.runs)  # pipeline default holds
        self.assertEqual(effective.observe.source, "default")
        self.assertTrue(effective.asked)

    def test_local_scope_writes_the_gitignored_override_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "craft_guard: true\nasked: true\n")
            path = audit_preferences.write_back(
                repo, {"craft_guard": False}, scope="local")
            self.assertEqual(
                path, repo / ".design-playbook" / "preferences.local.yaml")
            gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(
                audit_preferences.LOCAL_GITIGNORE_ENTRY,
                gitignore.splitlines(),
            )
            # The shared default under version control is untouched.
            repo_prefs = audit_preferences.load_preferences_file(
                repo / ".design-playbook" / "preferences.yaml")
            effective = _resolve(repo)
        self.assertIs(repo_prefs.craft_guard, True)
        self.assertFalse(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "local")
        self.assertTrue(effective.asked)

    def test_local_scope_preserves_existing_gitignore_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".gitignore").write_text("dist/\n", encoding="utf-8")
            audit_preferences.write_back(repo, {"observe": False}, scope="local")
            lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["dist/", audit_preferences.LOCAL_GITIGNORE_ENTRY])

    def test_local_scope_does_not_rewrite_crlf_gitignore_line_endings(self) -> None:
        # A CRLF-committed Windows repository must see a one-line addition,
        # not a whole-file line-ending flip in `git status`.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".gitignore").write_bytes(b"dist/\r\nbuild/\r\n")
            audit_preferences.write_back(repo, {"observe": False}, scope="local")
            raw = (repo / ".gitignore").read_bytes()
        self.assertTrue(raw.startswith(b"dist/\r\nbuild/\r\n"))
        self.assertIn(audit_preferences.LOCAL_GITIGNORE_ENTRY.encode("ascii"),
                      raw)
        self.assertNotIn(b"\r\n\n", raw)  # no mixed endings introduced

    def test_local_scope_tolerates_trailing_space_on_existing_entry(self) -> None:
        # git ignores trailing whitespace on ignore entries; the write-back
        # must not append a duplicate line behind one.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            entry = audit_preferences.LOCAL_GITIGNORE_ENTRY + " \n"
            (repo / ".gitignore").write_text(entry, encoding="utf-8")
            audit_preferences.write_back(repo, {"observe": False}, scope="local")
            lines = (repo / ".gitignore").read_text(
                encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)  # no duplicate appended
        self.assertEqual(lines[0].strip(),
                         audit_preferences.LOCAL_GITIGNORE_ENTRY)

    def test_symlinked_preference_file_is_not_followed_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            prefs_dir = repo / ".design-playbook"
            prefs_dir.mkdir()
            outside = repo / "outside.yaml"
            outside.write_text("observe: true\n", encoding="utf-8")
            link = prefs_dir / "preferences.yaml"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            with self.assertRaisesRegex(ValueError, "symlinked preference file"):
                audit_preferences.write_back(repo, {"observe": False})
            self.assertEqual(outside.read_text(encoding="utf-8"), "observe: true\n")

    def test_invalid_scope_and_declaration_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            with self.assertRaises(ValueError):
                audit_preferences.write_back(
                    repo, {"craft_guard": False}, scope="team")
            with self.assertRaises(ValueError):
                audit_preferences.write_back(repo, {"craftguard": False})
            self.assertFalse((repo / ".design-playbook").exists())

    def test_written_text_stays_in_the_locked_flat_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            audit_preferences.write_back(
                repo, {"craft_guard": True, "observe": False,
                       "ui_evaluator": True})
            text = (repo / ".design-playbook" /
                    "preferences.yaml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            self.assertRegex(
                line, r"^(craft_guard|observe|ui_evaluator|asked): "
                      r"(true|false)$")


class FirstAskProjectionTests(unittest.TestCase):
    """Issue #69: corrupt file -> absent semantics -> the one-time question
    is retriggered. The prose consumption face lands with #70; here the
    module projection (needs_first_ask) is pinned."""

    def test_absent_everything_needs_the_first_ask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            effective = _resolve(Path(tmp))
        self.assertTrue(audit_preferences.needs_first_ask(effective))

    def test_valid_asked_record_consumes_the_first_ask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_prefs(Path(tmp), "asked: true\n")
            effective = _resolve(Path(tmp))
        self.assertFalse(audit_preferences.needs_first_ask(effective))

    def test_corrupt_file_retriggers_the_first_ask(self) -> None:
        # Damage destroys the asked record along with everything else:
        # treated as absent, the orchestrator must ask again.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "asked: true\ncraft_guard: maybe\n")
            effective = _resolve(repo)
        self.assertEqual(effective.invalid_files, ("repo",))
        self.assertTrue(audit_preferences.needs_first_ask(effective))

    def test_corrupt_local_with_valid_repo_asked_keeps_no_ask(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "asked: true\n")
            _write_prefs(repo, "observe: [broken\n", local=True)
            effective = _resolve(repo)
        self.assertEqual(effective.invalid_files, ("local",))
        self.assertFalse(audit_preferences.needs_first_ask(effective))


if __name__ == "__main__":
    unittest.main()
