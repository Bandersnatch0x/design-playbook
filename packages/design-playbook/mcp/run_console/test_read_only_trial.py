#!/usr/bin/env python3
"""RCV1-008: deterministic read-only trial rehearsal — TRIAL_NOT_RUN.

This module is a READINESS REHEARSAL, not a trial. It proves the Console
can present the four fixed comprehension answers on the rendered page for
every rehearsal scenario; it never simulates a participant, never
measures how long anything takes, and never produces participant
evidence. The external gate G-RO-TRIAL-PASS cannot be satisfied here:
the module ends with TRIAL_STATUS = "TRIAL_NOT_RUN" and a final test
asserting the rehearsal never flips it and never emits a satisfied
gate record anywhere.

Five scenarios are constructed as real temporary run roots using only
the existing RCV1-005/006/007 mechanisms (shared fixtures, the test
server root builder, the parity mid-build mutation, a dropped
contract-bind.json, and the parity conflicting contract-bind record):

- pass          — current Pass point-back fixture
- recirculate   — Recirculate point-back fixture with one blocking finding
- stale         — point-back.md replaced mid-build, so the build itself
                  observes the change and marks the verdict and next
                  action stale (source-changed-during-build)
- missing       — contract-bind.json absent: unknown contract assertion
                  with the source-missing reason and a degraded build
- inconsistent  — contract-bind record violating its invariant:
                  inconsistent contract assertion with its conflict

Each scenario starts a real session and loopback HTTP server on an
ephemeral 127.0.0.1 port, opens the real UI in Chromium exactly the way
an operator does (page.goto(origin + "/#token=" + token)), and asserts
the four source-bound answers — intent, source verdict, blocker source,
next owner — are discoverable on the rendered page, with every expected
string derived from the served Snapshot document itself (never from raw
files). Stale and inconsistent values must carry their labels; a stale
Pass must not present as current; a missing value must render its
availability and reason.

Zero side effects are asserted per scenario: the run tree digest is
byte-for-byte identical before and after; no file is created anywhere
under the rehearsal base; browser storage stays empty; every network
request stays on the authenticated loopback origin; and no request is
anything but a read (GET/HEAD). The rehearsal base lives in the system
temporary directory and is removed when the module finishes; nothing is
written to .scratch/ or the repository.
"""
from __future__ import annotations

import ast
import contextlib
import io
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mcp.run_console import test_http_server as harness  # noqa: E402
from design_playbook.mcp.run_console import session as session_module  # noqa: E402
from design_playbook.mcp.run_console.http_server import serve_run_console  # noqa: E402
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402

TRIAL_STATUS = "TRIAL_NOT_RUN"
GATE = "G-RO-TRIAL-PASS"

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PROTOCOL = _REPO_ROOT / "docs" / "agents" / "run-console-read-only-trial.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_NOW = "2026-08-25T10:00:00Z"
_SCENARIOS = ("pass", "recirculate", "stale", "missing", "inconsistent")
_FORBIDDEN_NAME_FRAGMENTS = ("participant", "timing", "elapsed", "trial-export")

_PLAYWRIGHT = None
_BROWSER = None
_BASE_TMP = None
_BASE = None
_ROOT_SEQ = itertools.count(1)


def setUpModule() -> None:
    global _PLAYWRIGHT, _BROWSER, _BASE_TMP, _BASE
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch()
    _BASE_TMP = tempfile.TemporaryDirectory(prefix="rcv1-008-rehearsal-")
    _BASE = Path(_BASE_TMP.name).resolve()


def tearDownModule() -> None:
    _BROWSER.close()
    _PLAYWRIGHT.stop()
    _BASE_TMP.cleanup()


def _inventory(base: Path) -> set[str]:
    """Every file under the rehearsal base, as forward-slash paths."""
    return {
        str(path.relative_to(base)).replace("\\", "/")
        for path in base.rglob("*")
        if path.is_file()
    }


def _trial_artifact_violations(base: Path) -> list[str]:
    """Any rehearsal-created file that looks like a trial record.

    The rehearsal may not manufacture participant, measurement, export,
    or gate-pass artifacts. Every file under the rehearsal base is
    checked by name and by content.
    """
    violations: list[str] = []
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = str(path.relative_to(base)).replace("\\", "/")
        lowered = rel.lower()
        for fragment in _FORBIDDEN_NAME_FRAGMENTS:
            if fragment in lowered:
                violations.append(f"forbidden trial artifact name: {rel}")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - defensive
            violations.append(f"unreadable rehearsal file: {rel}")
            continue
        if GATE in content:
            violations.append(f"gate record inside rehearsal file: {rel}")
    return violations


class RehearsalHarness:
    """One scenario run root, real session, and real loopback server.

    Scenario construction reuses only existing mechanisms: the RCV1-006
    root builder and shared fixtures, the RCV1-005 parity mid-build
    mutation for the stale case, and the parity conflicting
    contract-bind record for the inconsistent case. The snapshot is
    built once here through the session (the same call the server's API
    route makes), so the digest captured below already includes any
    scenario construction write; everything the page then does must be
    read-only.
    """

    def __init__(self, scenario: str) -> None:
        if scenario not in _SCENARIOS:
            raise ValueError(f"unknown rehearsal scenario: {scenario}")
        self.scenario = scenario
        self.run_root = harness._make_root(
            _BASE, f"run-{scenario}-{next(_ROOT_SEQ)}"
        )
        if scenario == "recirculate":
            (self.run_root / "point-back.md").write_text(
                (_FIXTURES / "point-back-recirculate.md").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
        elif scenario == "missing":
            (self.run_root / "contract-bind.json").unlink()
        elif scenario == "inconsistent":
            conflicting = dict(harness._CONTRACT_BIND)
            conflicting["open_fields"] = ["nav.item-count"]
            conflicting["assumed_fields"] = ["nav.item-count"]
            (self.run_root / "contract-bind.json").write_text(
                json.dumps(conflicting), encoding="utf-8"
            )
        self.session = RunConsoleSession(
            run_root=self.run_root,
            now_fn=lambda: _NOW,
        )
        self.document = self._build_document()
        self.server = serve_run_console(self.session, bind_host="127.0.0.1", port=0)
        self.digest_before = harness._tree_digest(self.run_root)

    def _build_document(self) -> dict:
        if self.scenario != "stale":
            return self.session.build_snapshot()
        # The RCV1-005 parity mechanism for a source that changes while
        # the snapshot is being built: point-back.md is replaced under
        # the build, the build itself observes the change, and every
        # assertion bound to that source comes out stale. This write is
        # scenario construction, part of the captured digest below.
        root = self.run_root
        replacement = (
            _FIXTURES / "point-back-recirculate.md"
        ).read_text(encoding="utf-8")
        real_build = session_module._build_snapshot

        def mutating_build(**kwargs):
            def mutate() -> None:
                (root / "point-back.md").write_text(
                    replacement, encoding="utf-8"
                )

            return real_build(mid_build_hook=mutate, **kwargs)

        with mock.patch.object(
            session_module, "_build_snapshot", side_effect=mutating_build
        ):
            return self.session.build_snapshot()

    @property
    def origin(self) -> str:
        return self.server.origin

    @property
    def token(self) -> str:
        return self.session.token

    def url(self, fragment: str = "") -> str:
        return self.origin + "/" + fragment

    def close(self) -> None:
        # The run root stays on disk until tearDownModule so the final
        # gate test can scan every rehearsal file; the module temp base
        # removes it all afterwards.
        self.server.stop()


class RehearsalTestCase(unittest.TestCase):
    """One scenario harness, one fresh browser context, request log."""

    scenario = "pass"

    def setUp(self) -> None:
        self.output = io.StringIO()
        with contextlib.redirect_stdout(self.output):
            self.console = RehearsalHarness(self.scenario)
        self.addCleanup(self.console.close)
        self.inventory_before = _inventory(_BASE)
        self.context = _BROWSER.new_context(
            viewport={"width": 1280, "height": 800}
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.dialogs = []
        self.page.on("dialog", self._on_dialog)
        self.requests = []

        def record(route):
            self.requests.append({
                "method": route.request.method,
                "url": route.request.url,
                "authorization": route.request.headers.get("authorization"),
            })
            route.continue_()

        self.context.route("**/*", record)

    def _on_dialog(self, dialog) -> None:
        self.dialogs.append(dialog)
        dialog.dismiss()

    # -- page helpers (the operator's real path) -----------------------

    def open(self) -> None:
        token = self.console.token
        assert token is not None
        self.page.goto(self.console.url(f"#token={token}"))
        self.expect_ready()

    def expect_ready(self) -> None:
        expect(self.page.locator("#view-ready")).to_be_visible()
        expect(self.page.locator("#view-loading")).to_be_hidden()

    def fact(self, number: int):
        return self.page.locator(f"#fact-grid .fact:nth-child({number})")

    def body_text(self) -> str:
        return self.page.locator("body").inner_text()

    # -- rehearsal phases ----------------------------------------------

    def _assert_four_fact_frame(self) -> None:
        self.assertEqual(
            self.page.locator("#fact-grid h3").all_text_contents(),
            ["1. Intent", "2. Verdict", "3. Blocker", "4. Next action"],
        )
        for number in range(1, 5):
            expect(self.fact(number)).to_be_visible()

    def _assert_known_answers(self) -> None:
        """The four answers for a fully current snapshot (pass variant)."""
        doc = self.console.document
        self.assertEqual(doc["intent"]["summary"]["availability"], "known")
        self.assertIn(
            doc["intent"]["summary"]["result"], self.fact(1).inner_text()
        )
        self.assertIn(
            doc["evaluation"]["verdict"]["result"], self.fact(2).inner_text()
        )
        blocker = self.fact(3).inner_text()
        self.assertIn("No blocking findings", blocker)
        self.assertIn("2 recorded limitations", blocker)
        action = self.fact(4).inner_text()
        self.assertIn(doc["nextActions"]["primary"]["result"]["label"], action)
        self.assertIn("run-operator", action)
        self.assertIn("kind: stop", action)
        # The identity section shows the snapshot's own run id.
        self.assertIn(
            doc["identity"]["run"]["result"]["runId"],
            self.page.locator("#section-identity").inner_text(),
        )

    def _exercise_reads(self) -> None:
        """The only interactions a read-only participant needs."""
        self.page.locator("#reload-button").click()
        self.expect_ready()
        source = self.page.locator(
            "details.source", has_text="source.specification"
        )
        source.locator("summary").click()
        expect(source.locator("pre.excerpt")).to_be_visible(timeout=10000)

    def _assert_zero_side_effects(self) -> None:
        with self.subTest("run tree unchanged"):
            self.assertEqual(
                harness._tree_digest(self.console.run_root),
                self.console.digest_before,
            )
        with self.subTest("no file created anywhere in the rehearsal base"):
            self.assertEqual(_inventory(_BASE), self.inventory_before)
        with self.subTest("no trial records in any rehearsal file"):
            self.assertEqual(_trial_artifact_violations(_BASE), [])
        with self.subTest("browser storage empty"):
            storage = self.page.evaluate(
                """async () => ({
                    local: window.localStorage.length,
                    session: window.sessionStorage.length,
                    cookie: document.cookie,
                    databases: (await window.indexedDB.databases()).length,
                    workers: (await navigator.serviceWorker.getRegistrations()).length,
                })"""
            )
            self.assertEqual(storage, {
                "local": 0, "session": 0, "cookie": "",
                "databases": 0, "workers": 0,
            })
        with self.subTest("requests stay on the authenticated loopback origin"):
            self.assertTrue(self.requests, "no requests were recorded")
            for request in self.requests:
                self.assertTrue(
                    request["url"].startswith(self.console.origin),
                    request["url"],
                )
                self.assertNotIn(self.console.token, request["url"])
                # Read-only: no typed-action or other write call exists.
                self.assertIn(request["method"], ("GET", "HEAD"), request)
            api = [r for r in self.requests if "/api/v1/" in r["url"]]
            self.assertTrue(api, "no API request was recorded")
            for request in api:
                self.assertEqual(
                    request["authorization"],
                    "Bearer " + self.console.token,
                )
        with self.subTest("no dialogs were raised"):
            self.assertEqual(self.dialogs, [])


class CurrentPassScenarioTest(RehearsalTestCase):
    """A current Pass run: all four answers current on one page."""

    scenario = "pass"

    def test_current_pass_answers_and_zero_side_effects(self) -> None:
        self.assertEqual(
            self.console.document["evaluation"]["verdict"]["result"], "Pass"
        )
        self.open()
        self._assert_four_fact_frame()
        self._assert_known_answers()
        expect(self.page.locator("#build-state-banner")).to_contain_text(
            "Build state: current."
        )
        self._exercise_reads()
        self._assert_zero_side_effects()


class RecirculateScenarioTest(RehearsalTestCase):
    """A Recirculate run: blocking finding and the repair next owner."""

    scenario = "recirculate"

    def test_recirculate_answers_and_zero_side_effects(self) -> None:
        doc = self.console.document
        self.assertEqual(
            doc["evaluation"]["verdict"]["result"], "Recirculate"
        )
        self.open()
        self._assert_four_fact_frame()
        self.assertIn(
            doc["intent"]["summary"]["result"], self.fact(1).inner_text()
        )
        self.assertIn("Recirculate", self.fact(2).inner_text())
        blocker = self.fact(3).inner_text()
        self.assertIn(doc["evaluation"]["findings"][0]["result"]["issue"], blocker)
        self.assertIn("1 blocking finding", blocker)
        action = self.fact(4).inner_text()
        self.assertIn(doc["nextActions"]["primary"]["result"]["label"], action)
        self.assertIn("Owner: agent", action)
        self.assertIn("kind: continue", action)
        expect(self.page.locator("#build-state-banner")).to_contain_text(
            "Build state: current."
        )
        self._exercise_reads()
        self._assert_zero_side_effects()


class StaleScenarioTest(RehearsalTestCase):
    """A source changed during the build: stale answers stay labeled."""

    scenario = "stale"

    def test_stale_answers_labeled_and_zero_side_effects(self) -> None:
        doc = self.console.document
        verdict = doc["evaluation"]["verdict"]
        primary = doc["nextActions"]["primary"]
        # The served snapshot itself is the authority for the expectation.
        self.assertEqual(verdict["availability"], "stale")
        self.assertIsNone(verdict["result"])
        self.assertEqual(
            verdict["reason"]["code"], "source-changed-during-build"
        )
        self.assertEqual(primary["availability"], "stale")
        self.open()
        self._assert_four_fact_frame()
        # Answer 1 (intent) is still the snapshot value.
        self.assertIn(
            doc["intent"]["summary"]["result"], self.fact(1).inner_text()
        )
        # Answer 2 (verdict): labeled stale with its reason, never a
        # current-looking Pass.
        verdict_fact = self.fact(2).inner_text()
        self.assertIn("Stale", verdict_fact)
        self.assertIn("source-changed-during-build", verdict_fact)
        self.assertIn("The source changed during the build.", verdict_fact)
        self.assertNotIn("Pass", verdict_fact)
        # Answer 3 (blocker): the snapshot records no findings here.
        self.assertIn("No blocking findings", self.fact(3).inner_text())
        # Answer 4 (next owner): stale too, with no current owner line.
        action_fact = self.fact(4).inner_text()
        self.assertIn("Stale", action_fact)
        self.assertIn("source-changed-during-build", action_fact)
        self.assertNotIn("run-operator", action_fact)
        self.assertNotIn("Run complete", action_fact)
        # The degradation and the changed source are both disclosed.
        expect(self.page.locator("#build-state-banner")).to_contain_text(
            "Build state: degraded."
        )
        body = self.body_text()
        self.assertIn("freshness: changed", body)
        self.assertIn("the next action itself is stale", body)
        self.assertIn("Stale", self.page.locator("#section-evaluation").inner_text())
        self._exercise_reads()
        self._assert_zero_side_effects()


class MissingScenarioTest(RehearsalTestCase):
    """A bound source is missing: unknown value with its reason."""

    scenario = "missing"

    def test_missing_unknown_answers_and_zero_side_effects(self) -> None:
        doc = self.console.document
        contract = doc["intent"]["contract"]
        self.assertEqual(contract["availability"], "unknown")
        self.assertIsNone(contract["result"])
        self.assertEqual(contract["reason"]["code"], "source-missing")
        self.open()
        self._assert_four_fact_frame()
        # Answer 1 (intent) is unaffected by the missing contract source.
        self.assertIn(
            doc["intent"]["summary"]["result"], self.fact(1).inner_text()
        )
        # The contract assertion renders unknown with its reason.
        intent_section = self.page.locator("#section-intent").inner_text()
        self.assertIn("Unknown", intent_section)
        self.assertIn("source-missing", intent_section)
        self.assertIn(
            "The source bound to this assertion is missing.", intent_section
        )
        # The missing source itself states why no excerpt exists: it has
        # no server-issued locator, because it could not be read.
        sources_section = self.page.locator("#section-sources").inner_text()
        self.assertIn("source.contract-bind", sources_section)
        self.assertIn(
            "Excerpt unavailable: this source has no server-issued locator.",
            sources_section,
        )
        # Answers 2-4 are still the snapshot's current values.
        self.assertIn("Pass", self.fact(2).inner_text())
        action = self.fact(4).inner_text()
        self.assertIn(doc["nextActions"]["primary"]["result"]["label"], action)
        self.assertIn("run-operator", action)
        self.assertIn("kind: stop", action)
        expect(self.page.locator("#build-state-banner")).to_contain_text(
            "Build state: degraded."
        )
        self._exercise_reads()
        self._assert_zero_side_effects()


class InconsistentScenarioTest(RehearsalTestCase):
    """A source violates its invariant: inconsistent with the conflict."""

    scenario = "inconsistent"

    def test_inconsistent_answers_labeled_and_zero_side_effects(self) -> None:
        doc = self.console.document
        contract = doc["intent"]["contract"]
        conflict = contract["reason"]["conflicts"][0]
        self.assertEqual(contract["availability"], "inconsistent")
        self.assertIsNone(contract["result"])
        self.assertEqual(contract["reason"]["code"], "invariant-violation")
        self.open()
        self._assert_four_fact_frame()
        self.assertIn(
            doc["intent"]["summary"]["result"], self.fact(1).inner_text()
        )
        # The contract assertion renders inconsistent with its conflict,
        # never as a known contract table.
        intent_section = self.page.locator("#section-intent").inner_text()
        self.assertIn("Inconsistent", intent_section)
        self.assertIn("invariant-violation", intent_section)
        self.assertIn(conflict["sourceRef"], intent_section)
        self.assertIn(conflict["summary"], intent_section)
        self.assertNotIn("Open fields", intent_section)
        # Answers 2-4 are still the snapshot's current values.
        self.assertIn("Pass", self.fact(2).inner_text())
        action = self.fact(4).inner_text()
        self.assertIn(doc["nextActions"]["primary"]["result"]["label"], action)
        self.assertIn("run-operator", action)
        self.assertIn("kind: stop", action)
        expect(self.page.locator("#build-state-banner")).to_contain_text(
            "Build state: degraded."
        )
        self._exercise_reads()
        self._assert_zero_side_effects()


class TrialNotRunTest(RehearsalTestCase):
    """The rehearsal asserts readiness only; it cannot become a trial."""

    scenario = "pass"

    def test_rehearsal_cannot_emit_trial_pass_or_gate_pass(self) -> None:
        # One more full end-to-end open, then every readiness-only
        # guarantee is re-asserted on the repeat run.
        self.open()
        self._assert_four_fact_frame()
        self._assert_known_answers()
        self._exercise_reads()
        self._assert_zero_side_effects()
        # The module's explicit status marker is still the honest one.
        self.assertEqual(TRIAL_STATUS, "TRIAL_NOT_RUN")
        # No rehearsal artifact anywhere claims the external gate passed.
        self.assertEqual(_trial_artifact_violations(_BASE), [])
        # Nothing the rehearsal printed claims the gate passed either.
        self.assertNotIn(GATE, self.output.getvalue())
        # The rehearsal measures no participant: this module imports no
        # clock module at all, so nothing here can record elapsed usage.
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertNotIn("time", imported)
        self.assertNotIn("timeit", imported)
        # The protocol document and this rehearsal agree on the status.
        self.assertTrue(_PROTOCOL.is_file())
        self.assertIn("TRIAL_NOT_RUN", _PROTOCOL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
