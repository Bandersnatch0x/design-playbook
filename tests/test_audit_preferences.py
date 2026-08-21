#!/usr/bin/env python3
"""audit_preferences module tests (issues #66/#67, spec #65, ADR-0033).

In-process parser/merge tests following the tests/test_vnext_s1.py
precedent; the CLI face is exercised black-box through subprocess, the
same shape tests/test_request_routing.py uses for run_profile.py route.

Acceptance coverage (issue #66):
* schema parse / merge / asked-read — absent file, corrupt file
  fail-closed, local overrides repo, run declaration overrides both;
* no new dependencies (no yaml import anywhere);
* CLI resolves an effective plan for repo root + run declaration.

Acceptance coverage (issue #67):
* skeleton point-back satisfies the point-back gate parsers by
  construction (lockstep test pins template vs parsers);
* parse_audit_marker reports marker facts without policy;
* closed-loop anti-forgery round trip: skeleton generated -> marker
  parsed as unaudited -> non-strict validate passes / --strict and the
  --require-* flags reject -> run_status projects "not audited".

Acceptance coverage (issue #69):
* write-back round trips: a declaration writes back as the new default
  (repo or local scope); "this run only" exempts the stage choices but
  still sets the asked bit;
* local override respected and documented as gitignored;
* corrupt file -> absent semantics -> the one-time first ask is
  retriggered (module projection).
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

# Gate parsers the skeleton must satisfy by construction (issue #67): the
# module imports these rather than duplicating regexes, and the lockstep
# test below pins the template against the very same parsers.
from design_playbook.mcp.evidence.ledger_syntax import parse_ledger  # noqa: E402
from design_playbook.scripts.g1_spec import _l6_items  # noqa: E402
from design_playbook.scripts.g11_coverage import check_coverage  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import (  # noqa: E402
    _findings as pointback_findings,
    check_pointback,
)
from design_playbook.scripts.verdict_syntax import parse_verdict  # noqa: E402

MODULE_PATH = SCRIPTS / "audit_preferences.py"
VALIDATOR = PKG / "scripts" / "validate_run.py"
RUN_STATUS = PKG / "scripts" / "run_status.py"
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
    in, effective stage plan out — runnable and verifiable standalone."""

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
    """Acceptance 2: zero new dependencies — the repo has no yaml library
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


# Minimal G1-valid spec used by the skeleton tests: three L6 criteria, so
# the skeleton ledger must carry exactly three n/a rows.
SKELETON_SPEC = """# Spec - skeleton probe page

## L1 定位与意图

- Probe spec for the skeleton anti-forgery tests.

## L2 信息架构

- One list.

## L3 核心链路

- open -> reviewed

## L4 组件功能细节

- Row details.

## L5 边界条件

- Empty state shows a placeholder.

## L6 验收标准

- Given the probe list, When it opens, Then rows are visible.
- Given a row, When it is expanded, Then details are visible.
- Given no rows, When it opens, Then an empty state is visible.
"""


# The AUDIT.unaudited finding's stable message prefix — the text
# projection prints the message body (rule_id stays in the JSON face).
AUDIT_DIAGNOSTIC = "AUDIT: point-back carries 'audited: false'"


def _validate(spec: Path, pointback: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(spec), str(pointback), *extra],
        capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
    )


def _run_status_json(run_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUN_STATUS), str(run_root), "--json"],
        capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
    )


class SkeletonLockstepTests(unittest.TestCase):
    """Issue #67 acceptance 2: the skeleton satisfies the point-back gate
    parsers by construction — one lockstep test pins the template against
    the parsers the module imports (never duplicated regexes)."""

    def test_lockstep_template_vs_gate_parsers(self) -> None:
        skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
        n = len(_l6_items(SKELETON_SPEC))
        self.assertEqual(n, 3)
        # G2/G3/G4 accept the skeleton wholesale.
        self.assertEqual(check_pointback(skeleton, n), [])
        # Verdict facts: exactly one anchored heading, exactly one value,
        # canonical Recirculate (never a forged Pass).
        facts = parse_verdict(skeleton)
        self.assertEqual(facts.heading_count, 1)
        self.assertEqual(facts.value_count, 1)
        self.assertEqual(facts.canonical, "recirculate")
        # G11 (existence): the limitation sentence opts the skeleton into
        # the six-block shape; the coverage statement satisfies it.
        self.assertIn("## Limitations statement", skeleton)
        self.assertEqual(check_coverage(skeleton), [])
        self.assertEqual(check_coverage(skeleton, required=True), [])
        # Ledger shape: one n/a row per L6 criterion, no evidence/ binding.
        rows = parse_ledger(skeleton).rows
        self.assertEqual(len(rows), n)
        for index, row in enumerate(rows, 1):
            self.assertEqual(row.values("criterion"), (f"L6.{index}",))
            self.assertEqual(row.values("result"), ("n/a",))
            self.assertFalse(row.raw_observed.startswith("evidence/"))
        # One S0/info finding keeps G3.no_findings_without_pass silent.
        findings = pointback_findings(skeleton)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], ["S0"])
        self.assertEqual(findings[0]["disposition"], ["info"])
        # Fixed limitation sentence and marker are part of the template.
        self.assertIn(audit_preferences.SKELETON_LIMITATION_SENTENCE, skeleton)
        self.assertIn("audited: false", skeleton)

    def test_skeleton_generation_is_deterministic(self) -> None:
        self.assertEqual(
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
        )

    def test_skeleton_rejects_spec_without_criteria(self) -> None:
        with self.assertRaises(ValueError):
            audit_preferences.skeleton_pointback(
                "# Spec\n\n## L6 验收标准\n\nNo list items here.\n")


class AuditMarkerTests(unittest.TestCase):
    """Issue #67: parse_audit_marker reports facts only — no policy, the
    same creed as verdict_syntax's "parse, no policy"."""

    def test_absent_marker_reports_no_opinion(self) -> None:
        marker = audit_preferences.parse_audit_marker("# Report\n\nClean.\n")
        self.assertFalse(marker.present)
        self.assertIsNone(marker.audited)
        self.assertEqual(marker.marker_count, 0)

    def test_unaudited_marker_parses_false(self) -> None:
        marker = audit_preferences.parse_audit_marker(
            "# Report\n\naudited: false\n\nBody.\n")
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, False)
        self.assertEqual(marker.marker_count, 1)

    def test_audited_marker_parses_true(self) -> None:
        marker = audit_preferences.parse_audit_marker("audited: true\n")
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, True)

    def test_marker_value_is_case_insensitive(self) -> None:
        marker = audit_preferences.parse_audit_marker("audited: FALSE\n")
        self.assertIs(marker.audited, False)

    def test_repeated_marker_is_ambiguous_facts_only(self) -> None:
        marker = audit_preferences.parse_audit_marker(
            "audited: false\n\naudited: false\n")
        self.assertTrue(marker.present)
        self.assertIsNone(marker.audited)
        self.assertEqual(marker.marker_count, 2)

    def test_malformed_marker_candidate_is_present_but_ambiguous(self) -> None:
        for text in (
            "audited: false for now\n",
            " audited: false\n",
            "audited: false # forged comment\n",
        ):
            with self.subTest(text=text):
                marker = audit_preferences.parse_audit_marker(text)
                self.assertTrue(marker.present)
                self.assertIsNone(marker.audited)
                self.assertEqual(marker.marker_count, 1)

    def test_skeleton_round_trips_through_the_marker_parser(self) -> None:
        skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
        marker = audit_preferences.parse_audit_marker(skeleton)
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, False)


class ClosedLoopAntiForgeryTests(unittest.TestCase):
    """Issue #67 acceptance 1 + spec #65 centerpiece: skeleton generated ->
    marker parsed as unaudited -> non-strict validate passes / --strict and
    the --require-* flags reject -> run_status projects "not audited".
    Only the single deep module makes this round trip testable."""

    def _skeleton_pair(self, tmp: Path) -> tuple[Path, Path]:
        spec_path = tmp / "spec.md"
        pointback_path = tmp / "point-back.md"
        spec_path.write_text(SKELETON_SPEC, encoding="utf-8")
        pointback_path.write_text(
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
            encoding="utf-8",
        )
        return spec_path, pointback_path

    def test_non_strict_validation_passes_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_strict_rejects_the_skeleton_with_audit_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_evidence_rejects_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-evidence")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_coverage_rejects_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-coverage")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_preview_alone_does_not_reject_the_skeleton(self) -> None:
        # Preview may legitimately precede the audit; ADR-0033 D12 names
        # only --strict / --require-evidence / --require-coverage for the
        # AUDIT rejection. Without preview artifacts the run still fails
        # G5.require_preview — but never via the AUDIT finding.
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-preview")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("require-preview", result.stdout)
        self.assertNotIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_strict_rejection_names_the_audit_finding_rule_id(self) -> None:
        # The JSON projection carries the stable AUDIT.* rule ID (no new
        # G gate number) alongside the message.
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-coverage",
                               "--format", "json")
        self.assertEqual(result.returncode, 1, result.stdout)
        rule_ids = {entry["rule_id"] for entry in json.loads(result.stdout)}
        self.assertIn("AUDIT.unaudited", rule_ids)

    def test_strict_rejects_duplicate_marker_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            pointback.write_text(
                pointback.read_text(encoding="utf-8") + "\naudited: true\n",
                encoding="utf-8",
            )
            result = _validate(spec, pointback, "--require-coverage")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ambiguous or malformed 'audited:' marker", result.stdout)

    def test_strict_rejects_indented_or_commented_marker(self) -> None:
        for replacement in (
            " audited: false",
            "audited: false # hidden from exact parser",
        ):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                spec, pointback = self._skeleton_pair(Path(tmp))
                text = pointback.read_text(encoding="utf-8").replace(
                    "audited: false", replacement, 1)
                pointback.write_text(text, encoding="utf-8")
                result = _validate(spec, pointback, "--require-coverage")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("ambiguous or malformed 'audited:' marker", result.stdout)

    def test_run_status_suppresses_ambiguous_marker_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text(SKELETON_SPEC, encoding="utf-8")
            pointback = audit_preferences.skeleton_pointback(SKELETON_SPEC)
            (run_root / "point-back.md").write_text(
                pointback + "\naudited: true\n", encoding="utf-8")
            result = _run_status_json(run_root)
        payload = json.loads(result.stdout)
        self.assertIs(payload["audited"], False)
        self.assertEqual(payload["audit_marker_state"], "ambiguous")
        self.assertIsNone(payload["verdict"])
        self.assertIn("duplicate or malformed", payload["next"])

    def test_deleted_marker_cannot_hide_a_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            spec_path = tmp / "spec.md"
            pointback_path = tmp / "point-back.md"
            spec_path.write_text(SKELETON_SPEC, encoding="utf-8")
            skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
            pointback_path.write_text(
                skeleton.replace("audited: false\n\n", "", 1),
                encoding="utf-8",
            )
            strict = _validate(spec_path, pointback_path, "--require-coverage")
            status = _run_status_json(Path(tmp))
        self.assertEqual(strict.returncode, 1, strict.stdout)
        self.assertIn("ambiguous or malformed 'audited:' marker", strict.stdout)
        payload = json.loads(status.stdout)
        self.assertIs(payload["audited"], False)
        self.assertEqual(payload["audit_marker_state"], "ambiguous")
        self.assertIsNone(payload["verdict"])

    def test_run_status_projects_not_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text(SKELETON_SPEC, encoding="utf-8")
            (run_root / "point-back.md").write_text(
                audit_preferences.skeleton_pointback(SKELETON_SPEC),
                encoding="utf-8",
            )
            result = _run_status_json(run_root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertIs(payload["audited"], False)
        self.assertIsNone(payload["verdict"])
        self.assertNotIn("confirm ## Verdict", payload["next"])
        self.assertIn("not audited", payload["next"].casefold())

    def test_run_status_keeps_verdict_projection_for_real_reports(self) -> None:
        # Regression guard: the unaudited projection must not leak into
        # marker-less point-backs (the legacy majority).
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            (run_root / "point-back.md").write_text(
                "## Verdict\n\n**Pass.**\n", encoding="utf-8")
            result = _run_status_json(run_root)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["audited"])
        self.assertEqual(payload["verdict"], "Pass")


class WriteBackTests(unittest.TestCase):
    """Issue #69 / ADR-0033 D11: a user declaration writes back as the new
    default unless the user says "this run only"; the asked bit is set by
    every write-back. Output stays in the locked flat schema — hand-written
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
