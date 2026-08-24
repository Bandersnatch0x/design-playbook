#!/usr/bin/env python3
"""audit_preferences module tests (issue #66, spec #65, ADR-0033).

In-process parser/merge tests following the tests/test_vnext_s1.py
precedent; the CLI face is exercised black-box through subprocess, the
same shape tests/test_request_routing.py uses for run_profile.py route.

Split for the file-size budget: the skeleton/marker anti-forgery half
(issue #67) lives in tests/test_audit_skeleton.py and the write-back /
first-ask half (issue #69) in tests/test_audit_writeback.py.

Acceptance coverage (issue #66):
* schema parse / merge / asked-read - absent file, corrupt file
  fail-closed, local overrides repo, run declaration overrides both;
* no new dependencies (no yaml import anywhere);
* CLI resolves an effective plan for repo root + run declaration.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
SCRIPTS = PKG / "scripts"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts import audit_preferences  # noqa: E402

MODULE_PATH = SCRIPTS / "audit_preferences.py"
FULL_FILE = (
    "craft_guard: true\n"
    "observe: false\n"
    "ui_evaluator: true\n"
    "asked: true\n"
)


def _write_prefs(repo: Path, text: str, *, local: bool = False) -> None:
    name = "preferences.local.yaml" if local else "preferences.yaml"
    target = repo / ".design-playbook" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _resolve(repo: Path, declaration=None):
    return audit_preferences.resolve_preferences(repo, declaration)


class SchemaParseTests(unittest.TestCase):
    """The locked flat schema (ADR-0033 D9): exactly three stage booleans
    plus one asked bit, hand-parsed without a YAML library."""

    def test_full_file_parses_all_four_keys(self) -> None:
        prefs = audit_preferences.parse_preferences_text(FULL_FILE)
        self.assertIsNotNone(prefs)
        self.assertTrue(prefs.craft_guard)
        self.assertFalse(prefs.observe)
        self.assertTrue(prefs.ui_evaluator)
        self.assertTrue(prefs.asked)

    def test_subset_of_keys_parses(self) -> None:
        prefs = audit_preferences.parse_preferences_text("observe: false\n")
        self.assertIsNotNone(prefs)
        self.assertIsNone(prefs.craft_guard)
        self.assertFalse(prefs.observe)
        self.assertIsNone(prefs.ui_evaluator)
        self.assertIsNone(prefs.asked)

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        text = "# team audit defaults\n\ncraft_guard: false\n\n# trailing\n"
        prefs = audit_preferences.parse_preferences_text(text)
        self.assertIsNotNone(prefs)
        self.assertFalse(prefs.craft_guard)

    def test_boolean_values_are_case_insensitive(self) -> None:
        prefs = audit_preferences.parse_preferences_text(
            "craft_guard: TRUE\nobserve: False\n")
        self.assertIsNotNone(prefs)
        self.assertTrue(prefs.craft_guard)
        self.assertFalse(prefs.observe)

    def test_empty_file_carries_no_preference(self) -> None:
        self.assertIsNone(audit_preferences.parse_preferences_text(""))
        self.assertIsNone(
            audit_preferences.parse_preferences_text("# only a comment\n"))


class FailClosedTests(unittest.TestCase):
    """ADR-0033 D9 + spec user story 14: anything outside the locked flat
    schema is corrupt and must parse as absent, never partial or guessed."""

    CORRUPT_SAMPLES = [
        "unknown_key: true\n",                      # key outside locked schema
        "craft_guard: yes\n",                       # non true/false value
        "craft_guard: 1\n",
        "craft_guard:\n",                           # missing value
        "  craft_guard: true\n",                    # nested/indented structure
        "craft_guard: true\ncraft_guard: false\n",  # duplicate key
        "- craft_guard\n",                          # list form
        "craft_guard true\n",                       # missing colon
        "craft_guard: true # inline note\n",        # trailing garbage
        "{craft_guard: true}\n",                    # flow mapping
    ]

    def test_every_corrupt_shape_parses_as_absent(self) -> None:
        for sample in self.CORRUPT_SAMPLES:
            with self.subTest(sample=sample):
                self.assertIsNone(
                    audit_preferences.parse_preferences_text(sample))

    def test_unreadable_bytes_parse_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preferences.yaml"
            path.write_bytes(b"\xff\xfe\x00garbage")
            self.assertIsNone(audit_preferences.load_preferences_file(path))

    def test_oversized_file_is_rejected_without_unbounded_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preferences.yaml"
            path.write_bytes(b"#" * (audit_preferences.MAX_PREFERENCES_BYTES + 1))
            self.assertIsNone(audit_preferences.load_preferences_file(path))

    def test_absent_file_parses_as_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(audit_preferences.load_preferences_file(
                Path(tmp) / "preferences.yaml"))

    def test_utf8_bom_is_not_misread_as_corrupt(self) -> None:
        # A BOM written by Windows editors (legacy notepad, PowerShell 5
        # redirection) must not fail-closed away a valid preference file.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preferences.yaml"
            path.write_bytes(b"\xef\xbb\xbfcraft_guard: false\n")
            prefs = audit_preferences.load_preferences_file(path)
        self.assertIsNotNone(prefs)
        self.assertIs(prefs.craft_guard, False)


class MergePrecedenceTests(unittest.TestCase):
    """Three-level merge (ADR-0033 D2/D3/D6): run declaration >
    preferences.local.yaml > preferences.yaml; absent layer = no opinion."""

    def test_absent_everything_defaults_to_run_all_unasked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            effective = _resolve(Path(tmp))
        for name in audit_preferences.STAGE_KEYS:
            resolution = getattr(effective, name)
            self.assertTrue(resolution.runs, name)
            self.assertEqual(resolution.source, "default", name)
        self.assertFalse(effective.asked)
        self.assertEqual(effective.invalid_files, ())

    def test_repo_file_applies_when_local_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "craft_guard: false\nasked: true\n")
            effective = _resolve(repo)
        self.assertFalse(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "repo")
        self.assertTrue(effective.observe.runs)
        self.assertEqual(effective.observe.source, "default")
        self.assertTrue(effective.asked)

    def test_local_overrides_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "craft_guard: true\nobserve: true\nasked: true\n")
            _write_prefs(repo, "craft_guard: false\n", local=True)
            effective = _resolve(repo)
        self.assertFalse(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "local")
        # untouched key still falls through to the repo layer
        self.assertTrue(effective.observe.runs)
        self.assertEqual(effective.observe.source, "repo")

    def test_run_declaration_overrides_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, FULL_FILE)
            _write_prefs(repo, "observe: true\n", local=True)
            effective = _resolve(
                repo, {"observe": False, "ui_evaluator": False})
        self.assertTrue(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "repo")
        self.assertFalse(effective.observe.runs)
        self.assertEqual(effective.observe.source, "run")
        self.assertFalse(effective.ui_evaluator.runs)
        self.assertEqual(effective.ui_evaluator.source, "run")
        # asked is repository state; a per-run declaration never touches it
        self.assertTrue(effective.asked)

    def test_partial_declaration_falls_through_per_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "observe: false\n")
            effective = _resolve(repo, {"craft_guard": False})
        self.assertFalse(effective.craft_guard.runs)
        self.assertEqual(effective.craft_guard.source, "run")
        self.assertFalse(effective.observe.runs)
        self.assertEqual(effective.observe.source, "repo")
        self.assertTrue(effective.ui_evaluator.runs)
        self.assertEqual(effective.ui_evaluator.source, "default")

    def test_corrupt_local_is_fail_closed_but_repo_still_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "observe: false\nasked: true\n")
            _write_prefs(repo, "observe: maybe\n", local=True)
            effective = _resolve(repo)
        self.assertFalse(effective.observe.runs)
        self.assertEqual(effective.observe.source, "repo")
        self.assertTrue(effective.asked)
        self.assertEqual(effective.invalid_files, ("local",))

    def test_corrupt_repo_is_fail_closed_but_local_still_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "observe: [broken\n")
            _write_prefs(repo, "observe: false\n", local=True)
            effective = _resolve(repo)
        self.assertFalse(effective.observe.runs)
        self.assertEqual(effective.observe.source, "local")
        self.assertEqual(effective.invalid_files, ("repo",))

    def test_invalid_declaration_rejected_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for declaration in (
                {"craft_guard": "no"},          # non-boolean value
                {"craftguard": False},          # unknown stage name
                {"asked": True},                # asked is not a stage switch
                ["craft_guard"],                # not a mapping
            ):
                with self.subTest(declaration=declaration):
                    with self.assertRaises(ValueError):
                        _resolve(Path(tmp), declaration)


class AskedBitTests(unittest.TestCase):
    """The one-time question state (ADR-0033 D2/D10): read from the merged
    preference record; absent or corrupt means the orchestrator asks."""

    def test_repo_asked_true_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_prefs(Path(tmp), "asked: true\n")
            self.assertTrue(_resolve(Path(tmp)).asked)

    def test_local_asked_overrides_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "asked: true\n")
            _write_prefs(repo, "asked: false\n", local=True)
            self.assertFalse(_resolve(repo).asked)

    def test_corrupt_file_resets_to_unasked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_prefs(Path(tmp), "asked: true\ncraft_guard: maybe\n")
            self.assertFalse(_resolve(Path(tmp)).asked)


class CliTests(unittest.TestCase):
    """The CLI face (issue #66 acceptance 3): repo root + run declaration
    in, effective stage plan out - runnable and verifiable standalone."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *args],
            capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )

    def test_plan_defaults_when_repo_has_no_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_cli("plan", "--repo-root", tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        for name in ("craft_guard", "observe", "ui_evaluator"):
            self.assertEqual(
                payload["stages"][name], {"runs": True, "source": "default"})
        self.assertFalse(payload["asked"])
        self.assertEqual(payload["invalid_files"], [])

    def test_plan_resolves_files_and_declaration_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write_prefs(repo, "craft_guard: true\nasked: true\n")
            _write_prefs(repo, "craft_guard: false\n", local=True)
            result = self._run_cli(
                "plan", "--repo-root", tmp,
                "--declaration", json.dumps({"ui_evaluator": False}),
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["stages"]["craft_guard"],
            {"runs": False, "source": "local"})
        self.assertEqual(
            payload["stages"]["ui_evaluator"],
            {"runs": False, "source": "run"})
        self.assertEqual(
            payload["stages"]["observe"], {"runs": True, "source": "default"})
        self.assertTrue(payload["asked"])

    def test_invalid_declaration_reports_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for declaration in ("{not json", json.dumps({"craft_guard": "x"})):
                with self.subTest(declaration=declaration):
                    result = self._run_cli(
                        "plan", "--repo-root", tmp,
                        "--declaration", declaration)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("error", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_missing_repo_root_reports_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_cli(
                "plan", "--repo-root", str(Path(tmp) / "no-such-dir"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class DependencyTests(unittest.TestCase):
    """Acceptance 2: zero new dependencies - the repo has no yaml library
    and the locked schema is hand-parsed with the standard library only."""

    def test_module_never_imports_yaml(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import yaml", source)
        self.assertNotIn("yaml.", source)

    def test_module_imports_stdlib_or_package_only(self) -> None:
        # Issue #67 changes the constraint: skeleton generation must import
        # the existing gate parsers (g2_g4_pointback / verdict_syntax)
        # instead of duplicating regexes, so design_playbook-internal
        # imports are legal. Third-party dependencies remain forbidden.
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
        self.assertTrue(modules, "module must import something")
        allowed = sys.stdlib_module_names | {"design_playbook"}
        self.assertTrue(
            modules <= allowed,
            f"third-party imports found: {sorted(modules - allowed)}",
        )


if __name__ == "__main__":
    unittest.main()
