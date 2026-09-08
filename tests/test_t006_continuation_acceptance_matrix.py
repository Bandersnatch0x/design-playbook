#!/usr/bin/env python3
"""T-006: Run Operator Continuation local acceptance matrix.

One matrix, real seams, no duplicated business logic:

- **completed**: status -> continuation -> Console snapshot -> Repair
  Packet -> static handoff (journey order from the spec).
- **blocked**: blocker source, next owner, invalidated evidence, repair
  narration, and no false Pass.
- **stale / inconsistent / hash-mismatched**: visible states, no older
  successful snapshot substitution, no false Pass.
- **capability-mismatch**: implementation present while the public claim
  stays experimental / trial-gated (real package inventory).
- **missing-prerequisite**: ineligible open-console with reason and
  fallback, no doomed command.
- **Pending-handoff**: handoff output exists while Pending stays Pending.

Journey-level safety assertions: no silent server launch, no repair, no
rerun, no acceptance write, no run mutation beyond the explicit handoff
output subtree. Every fixture goes through the real projections
(``run_status`` CLI, ``RunConsoleSession.build_snapshot``,
``derive_repair_packet``, ``run_handoff``) and every handoff runs the
builder's real default gate seam — the canonical ``validate_run`` gate
over the run directory; gate success is never stubbed. The Pass in the
completed journey is earned by real source fixture artifacts (a
capture-contract v1 manifest binding, a confirm record whose report_ref
resolves). The one substituted interaction is the five-viewport capture:
an offline runner writes real files through the builder's own artifact and
containment path — a browser-interaction substitute, explicitly not real
visual acceptance (that leg belongs to the run_console browser suite).

Pure-Python: the browser-security leg of the journey is already covered by
the run_console browser suite; this matrix exercises the same seams through
the session + HTTP server in-process (no Playwright dependency), so it runs
in the plain pytest gate.
"""

from __future__ import annotations

import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "mcp"))

from mcp.run_console import test_http_server as console_harness  # noqa: E402
from design_playbook.mcp.run_console.actions import (  # noqa: E402
    capability_names,
    copy_command_is_eligible,
)
from design_playbook.mcp.run_console.repair_packet import derive_repair_packet  # noqa: E402
from design_playbook.mcp.run_console.http_server import serve_run_console  # noqa: E402
from design_playbook.mcp.run_console.session import RunConsoleSession  # noqa: E402
from design_playbook.scripts import run_status as run_status_mod  # noqa: E402
from design_playbook.scripts.run_handoff import run_handoff  # noqa: E402

FIXTURES = PKG / "mcp" / "run_console" / "fixtures"
RUN_STATUS = PKG / "scripts" / "run_status.py"
RUN_CONSOLE = PKG / "scripts" / "run_console.py"
DELIVERABLE_HTML = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    "<title>deliverable</title></head><body><main><h1>Deliverable</h1>"
    "</main></body></html>"
)
_INVALIDATED_BLOCK = """
invalidated:
  - criterion: L6.1
    artifacts: [evidence/L6.1-cap-error.png]
    reason: Fill fix changed the cap-limit toast; rendered evidence stale
  - criterion: L6.2
    artifacts: []
    reason: capture provider session loss; R5 capture-plan revision
"""
_DECISION_REPORT = (
    "# Decision report\n"
    "\n"
    "Round 1: the queue-monitor prototype was reviewed against the spec\n"
    "and confirmed by the user.\n"
)
# The provider-echoed capture request snapshot the manifest must carry for
# the bound artifact to satisfy the read-side capture contract (G6).
_CAPTURE_REQUEST = {
    "schemaVersion": 1,
    "viewport": {
        "width": 1280,
        "height": 900,
        "devicePixelRatio": 1,
        "colorScheme": "light",
    },
    "freeze": {"enabled": True, "waitFonts": True, "networkIdle": False},
}


def _make_matrix_run(
    base: Path,
    name: str,
    *,
    point_back: str = "point-back-pass-closed.md",
    invalidated: bool = False,
) -> Path:
    """One real run root from the existing console fixtures."""
    root = console_harness._make_root(base, name)
    (root / "point-back.md").write_text(
        (FIXTURES / point_back).read_text(encoding="utf-8")
        + (_INVALIDATED_BLOCK if invalidated else ""),
        encoding="utf-8",
    )
    return root


def _declare_fill(root: Path, fill: str = "surface.html") -> None:
    """Add a column-0 ``fill:`` declaration to the run's plan.md."""
    plan = root / "plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8") + f"\nfill: {fill}\n", encoding="utf-8"
    )
    (root / fill).write_text(DELIVERABLE_HTML, encoding="utf-8")


def _bind_capture_contract(root: Path) -> None:
    """Re-bind the fixture evidence artifact with a capture-contract v1
    request snapshot — the real G6 condition. The harness's stock entry is
    pre-contract and fails the read-side validator on purpose; runs that
    must pass the real gate rebind it."""
    entry = {
        "criterion": "L6.3",
        "artifact": "L6.3-error.png",
        "ts": "2026-08-25T09:00:00+08:00",
        "request": _CAPTURE_REQUEST,
    }
    (root / "evidence" / "manifest.jsonl").write_text(
        json.dumps(entry) + "\n", encoding="utf-8"
    )


def _confirm_preview(root: Path) -> None:
    """A G5 confirm round whose facts all resolve: digest-matched prototype
    and a report_ref pointing at a decision report that exists on disk (the
    real G5 condition)."""
    from design_playbook.mcp.preview.integrity import prototype_html_digest

    (root / "decision-report.md").write_text(_DECISION_REPORT, encoding="utf-8")
    prototype = root / "preview" / "round-1.html"
    prototype.write_text(DELIVERABLE_HTML, encoding="utf-8")
    record = {
        "round": 1,
        "report_ref": "decision-report.md",
        "confirmed": True,
        "floor_pass": True,
        "selected_options": ["确认通过"],
        "feedback": "ship it",
        "timestamp": "2026-08-24 00:00:00 +0000",
        "prototype_path": "preview/round-1.html",
        "prototype_html_hash": prototype_html_digest(DELIVERABLE_HTML.encode("utf-8")),
        "decision_id": "dd-0001",
    }
    (root / "preview" / "confirm-round-1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8"
    )


def _capture_runner(*, url: str, out_dir: Path) -> dict[str, dict[str, object]]:
    """Offline capture substitute: real files on disk, no browser.

    Scope: only the browser interaction is substituted. The builder still
    owns artifact paths, containment, and the completeness proof. This is
    NOT real visual acceptance — the rendered-evidence leg is covered by
    the run_console browser suite (mirrors tests/test_t004_run_handoff.py's
    approach).
    """
    del url
    out_dir.mkdir(parents=True, exist_ok=True)
    refs = {
        "1280x900": (1280, 900),
        "768x1024": (768, 1024),
        "390x844": (390, 844),
        "360x800": (360, 800),
        "print": (960, 650),
    }
    matrix: dict[str, dict[str, object]] = {}
    for name, (sw, inner_h) in refs.items():
        screenshot = out_dir / f"viewport-{name}.png"
        screenshot.write_bytes(b"\x89PNG matrix-fixture")
        matrix[name] = {
            "metrics": {
                "sw": sw,
                "innerH": inner_h,
                "hOverflow": 0,
                "disclosure": {"inFold": True},
                "measurementStatus": "measured",
            },
            "screenshot": str(screenshot.resolve()),
        }
    return matrix


def _handoff(root: Path):
    # No gate_runner: the handoff must run the builder's real default gate
    # seam (the canonical validate_run gate). Only the browser interaction
    # of the capture is substituted (see _capture_runner).
    return run_handoff(
        root,
        round_n=1,
        summary="matrix handoff",
        capture_runner=_capture_runner,
    )


def _tree_digest(root: Path) -> dict[str, object]:
    """Relative path -> (kind, sha256) for every entry under root."""
    import hashlib

    digest: dict[str, object] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_file():
            digest[rel] = ("f", hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            digest[rel] = ("d", "")
    return digest


def _run_status_payload(run_root: Path) -> dict:
    """The real CLI as the operator runs it, in-process for speed."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = run_status_mod.render(run_root, as_json=True)
    assert code == 0, buffer.getvalue()
    return json.loads(buffer.getvalue())


def _no_launch_patches():
    """Fail the test the moment a server/process spawn is attempted."""
    return (
        patch("socket.socket.bind", side_effect=AssertionError("bind")),
        patch(
            "http.server.HTTPServer.__init__",
            side_effect=AssertionError("http-server"),
        ),
        patch("subprocess.Popen", side_effect=AssertionError("popen")),
    )


class MatrixCompletedJourneyTest(unittest.TestCase):
    """completed run: status -> continuation -> Console -> packet -> handoff."""

    def test_completed_run_full_journey_with_no_mutation_or_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-completed")
            _bind_capture_contract(root)
            _declare_fill(root)
            _confirm_preview(root)
            before = _tree_digest(root)

            # Leg 1: run-status reports completion with no false Pass and
            # no side effect (no launch, no artifact write).
            with (
                _no_launch_patches()[0],
                _no_launch_patches()[1],
                _no_launch_patches()[2],
            ):
                payload = _run_status_payload(root)
            self.assertEqual(payload["verdict"], "Pass")
            self.assertIn("complete", payload["next"].lower())
            continuation = payload["continuation"]
            self.assertEqual(continuation["phase"]["key"], "accept")
            self.assertIsNone(continuation["blocker"])
            self.assertEqual(continuation["integrity"]["state"], "current")
            self.assertEqual(
                continuation["next_action"]["action_id"], "action.stop-after-pass"
            )
            self.assertEqual(
                continuation["next_action"]["owner"]["actor"], "run-operator"
            )
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertEqual(
                Path(continuation["open_console"]["argv"][2]).resolve(),
                root.resolve(),
            )
            self.assertEqual(_tree_digest(root), before)

            # Leg 2: the emitted open-console command is the real launcher
            # entrypoint naming exactly this run — run in-process here as
            # the session (the browser leg is covered by the browser suite).
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            snapshot = session.build_snapshot()
            self.assertEqual(snapshot["identity"]["snapshot"]["buildState"], "current")
            self.assertEqual(snapshot["intent"]["summary"]["availability"], "known")
            self.assertEqual(snapshot["evaluation"]["verdict"]["result"], "Pass")
            self.assertEqual(
                snapshot["nextActions"]["primary"]["result"]["actionId"],
                "action.stop-after-pass",
            )

            # Leg 3: the derived Repair Packet keeps the verdict honest and
            # shows gaps, not invented repair.
            packet = derive_repair_packet(snapshot)
            self.assertEqual(packet["intent"]["availability"], "known")
            self.assertEqual(packet["verdict"]["value"], "Pass")
            self.assertEqual(packet["finding"]["availability"], "unknown")
            self.assertIn("No blocking finding", packet["finding"]["reason"]["message"])
            self.assertEqual(packet["nextOwner"]["value"]["actor"], "run-operator")
            # The packet's next command is a real gap: the owner projects no
            # copyable agent command for the stop action, so the packet must
            # report unknown / not-produced — exporting it is never a
            # productive command copy.
            primary_result = snapshot["nextActions"]["primary"]["result"]
            self.assertIsNone(primary_result["copyableAgentCommand"])
            self.assertEqual(packet["nextCommand"]["availability"], "unknown")
            self.assertIsNone(packet["nextCommand"]["value"])
            self.assertEqual(packet["nextCommand"]["reason"]["code"], "not-produced")
            self.assertIn("copy only", packet["copyText"])

            # Leg 4: explicit static handoff completes the journey through
            # the real default canonical gate seam (no gate stub). The Pass
            # is earned by the fixture artifacts — capture-contract v1
            # manifest binding (G6), a confirm record whose report_ref
            # resolves (G5), a valid digest-matched confirm — while G7/G8
            # stay honestly not-applicable (the handoff wires no contract
            # paths; the run has no craft-guard.md) and never count as
            # passes. The only substituted interaction is the offline
            # capture runner (browser interaction, not visual acceptance).
            result = _handoff(root)
            self.assertEqual(result.verdict, "Pass")
            self.assertEqual(result.authority, "confirmed-user")
            self.assertEqual(result.confirmation_source, "confirm-record")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            # The wrapper reports exactly what the disclosure payload says.
            self.assertEqual(payload["verdict"], result.verdict)
            self.assertEqual(payload["authority"], result.authority)
            self.assertEqual(payload["confirmationSource"], result.confirmation_source)
            self.assertEqual(payload["gateStatus"], "passed")
            self.assertEqual(payload["gatesPassed"], 6)
            self.assertEqual(
                payload["gateStatuses"],
                ["pass"] * 6 + ["not-applicable"] * 2,
            )
            self.assertNotIn("gateError", payload)
            self.assertTrue(result.index_html.is_file())
            self.assertTrue(result.zip_path.is_file())
            after = _tree_digest(root)
            added = {
                rel
                for rel in after
                if rel not in before and not rel.startswith("evidence/static-handoff")
            }
            self.assertEqual(added, set())
            changed = {
                rel for rel in before if rel in after and before[rel] != after[rel]
            }
            self.assertEqual(changed, set())
            session.close()


class MatrixBlockedJourneyTest(unittest.TestCase):
    """blocked run: blocker source, owner, invalidated evidence, no false Pass."""

    def test_blocked_run_names_owner_blocker_and_invalidated_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(
                base,
                "run-blocked",
                point_back="point-back-recirculate.md",
                invalidated=True,
            )
            _declare_fill(root)
            before = _tree_digest(root)

            with (
                _no_launch_patches()[0],
                _no_launch_patches()[1],
                _no_launch_patches()[2],
            ):
                payload = _run_status_payload(root)
            self.assertEqual(payload["verdict"], "Recirculate")
            self.assertFalse(payload["invalidated_evidence"] is False)
            self.assertEqual(payload["invalidated_evidence"], True)
            continuation = payload["continuation"]
            self.assertEqual(continuation["blocker"]["source"], "owner")
            self.assertEqual(
                continuation["blocker"]["action_id"],
                "action.repair-after-recirculate",
            )
            self.assertEqual(continuation["next_action"]["owner"]["actor"], "agent")
            # T-008: the owner emits one exact copyable agent command for
            # the blocked repair path; run-status preserves it verbatim.
            self.assertEqual(
                continuation["next_action"]["kind"], "agent-command"
            )
            command = continuation["next_action"]["copyable_agent_command"]
            self.assertIsInstance(command, str)
            self.assertIn("/design-playbook:design-io", command)
            self.assertIn("ui-evaluator", command)
            self.assertNotIn(root.as_posix(), command)
            self.assertEqual(continuation["integrity"]["state"], "current")
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertEqual(_tree_digest(root), before)

            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            self.addCleanup(session.close)
            snapshot = session.build_snapshot()
            packet = derive_repair_packet(snapshot)
            self.assertEqual(packet["verdict"]["value"], "Recirculate")
            finding = packet["finding"]["value"]
            self.assertIn("destructive action has no confirmation", finding["issue"])
            self.assertEqual(finding["disposition"], "blocking")
            self.assertEqual(packet["blockerSource"]["value"]["blockingCount"], 1)
            self.assertEqual(packet["declarationOwner"]["value"]["kind"], "declaration")
            self.assertEqual(
                packet["repairIntent"]["value"],
                "add a consequence-confirmation dialog",
            )
            self.assertEqual(packet["nextOwner"]["value"]["actor"], "agent")
            # Spec rule 19: resume stage is a gap, never inferred.
            self.assertEqual(packet["resumeStage"]["availability"], "unknown")
            self.assertIsNone(packet["resumeStage"]["value"])
            # T-008: the owner now emits the repair command, and the
            # snapshot/packet preserve it verbatim — neither synthesizes,
            # parses, executes, nor mutates anything. The command carries
            # no path, so the document stays inside the parity S19
            # path-free boundary.
            primary_result = snapshot["nextActions"]["primary"]["result"]
            self.assertEqual(primary_result["kind"], "agent-command")
            snapshot_command = primary_result["copyableAgentCommand"]
            self.assertIsInstance(snapshot_command, str)
            self.assertNotIn(root.name, snapshot_command)
            self.assertEqual(
                packet["nextCommand"]["availability"], "known"
            )
            self.assertEqual(packet["nextCommand"]["value"], snapshot_command)
            self.assertIn(snapshot_command, packet["copyText"])
            # The primary journey advances past the copy step: the known
            # owner command is copy-eligible under the closed UI rule.
            self.assertTrue(
                copy_command_is_eligible("known", snapshot_command)
            )
            self.assertEqual(_tree_digest(root), before)

    def test_blocked_run_handoff_never_passes_and_writes_no_acceptance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(
                base,
                "run-blocked-handoff",
                point_back="point-back-recirculate.md",
            )
            _declare_fill(root)
            before = _tree_digest(root)
            result = _handoff(root)
            # The blocked run never yields a Pass at the handoff seam...
            self.assertNotEqual(result.verdict, "Pass")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertNotEqual(payload["verdict"], "Pass")
            # ...and the wrapper reports exactly what the disclosure says.
            self.assertEqual(payload["verdict"], result.verdict)
            self.assertEqual(payload["authority"], result.authority)
            self.assertEqual(payload["confirmationSource"], result.confirmation_source)
            # No acceptance write: the point-back owner verdict stays the
            # fixture's Recirculate, and the only run-tree delta is the
            # handoff output subtree.
            self.assertEqual(
                (root / "point-back.md").read_text(encoding="utf-8"),
                (FIXTURES / "point-back-recirculate.md").read_text(encoding="utf-8"),
            )
            after = _tree_digest(root)
            added = {
                rel
                for rel in after
                if rel not in before and not rel.startswith("evidence/static-handoff")
            }
            self.assertEqual(added, set())
            changed = {
                rel for rel in before if rel in after and before[rel] != after[rel]
            }
            self.assertEqual(changed, set())

    def test_confirmed_recirculate_run_never_ships_pass(self) -> None:
        # Decision 25 end-to-end through the real canonical gate: the
        # point-back owner verdict gates the delivery Pass. A confirmed
        # round with complete capture, bound evidence, and a fully resolved
        # real gate result still cannot ship an open blocking finding
        # (Recirculate) as Pass.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(
                base,
                "run-confirmed-recirculate",
                point_back="point-back-recirculate.md",
            )
            _bind_capture_contract(root)
            _declare_fill(root)
            _confirm_preview(root)
            result = _handoff(root)
            self.assertEqual(result.verdict, "Recirculate")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"], "Recirculate")
            self.assertEqual(payload["authority"], "confirmed-user")
            self.assertEqual(payload["confirmationSource"], "confirm-record")
            self.assertEqual(payload["gateStatus"], "pending")
            # Gate evaluation is still reported honestly and separately
            # from the verdict: real passes count, G7/G8 not-applicable.
            self.assertEqual(payload["gatesPassed"], 6)
            self.assertEqual(
                payload["gateStatuses"],
                ["pass"] * 6 + ["not-applicable"] * 2,
            )


class MatrixStaleStateTest(unittest.TestCase):
    """stale / inconsistent / hash-mismatched runs stay honest."""

    def test_hash_mismatch_run_is_not_replaced_by_its_pass_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-mismatch")
            _declare_fill(root)
            # Tamper the prototype AFTER the confirm record was written: the
            # confirm's digest no longer matches the artifact on disk.
            _confirm_preview(root)
            (root / "preview" / "round-1.html").write_text(
                "<html>tampered</html>", encoding="utf-8"
            )
            with (
                _no_launch_patches()[0],
                _no_launch_patches()[1],
                _no_launch_patches()[2],
            ):
                payload = _run_status_payload(root)
            self.assertEqual(payload["verdict"], "Pass")  # owner text is Pass
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "hash-mismatched")
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertEqual(continuation["blocker"]["state"], "hash-mismatched")

            # The Console keeps the mismatch visible at its owning seam:
            # the integrity owner reports the confirm as invalid, never
            # upgraded to confirmed (parity spec §2).
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            self.addCleanup(session.close)
            snapshot = session.build_snapshot()
            preview = snapshot["execution"]["preview"]["result"]
            self.assertEqual(preview["state"], "invalid")

    def test_stale_bind_run_reports_stale_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-stale-bind")
            _declare_fill(root)
            bind = json.loads((root / "contract-bind.json").read_text(encoding="utf-8"))
            bind["stale_fields"] = ["nav.item-count"]
            (root / "contract-bind.json").write_text(json.dumps(bind), encoding="utf-8")
            payload = _run_status_payload(root)
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "stale")
            self.assertIn("nav.item-count", continuation["integrity"]["reason"])
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertEqual(continuation["blocker"]["state"], "stale")
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertEqual(Path(continuation["open_console"]["argv"][2]), root)
            self.assertEqual(continuation["capability"]["fallback"]["kind"], "evidence-gap")
            self.assertIn("G-RO-TRIAL-PASS", continuation["capability"]["fallback"]["detail"])

    def test_inconsistent_bind_run_never_yields_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-inconsistent")
            _declare_fill(root)
            bind = json.loads((root / "contract-bind.json").read_text(encoding="utf-8"))
            bind["open_fields"] = ["nav.item-count"]
            bind["assumed_fields"] = ["nav.item-count"]
            (root / "contract-bind.json").write_text(json.dumps(bind), encoding="utf-8")
            payload = _run_status_payload(root)
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "inconsistent")
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertTrue(continuation["open_console"]["eligible"])
            self.assertEqual(Path(continuation["open_console"]["argv"][2]), root)
            self.assertEqual(continuation["capability"]["fallback"]["kind"], "evidence-gap")
            self.assertIn("G-RO-TRIAL-PASS", continuation["capability"]["fallback"]["detail"])
            # The Console marks the run degraded and shows the owning
            # assertion as inconsistent (never silently current).
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            self.addCleanup(session.close)
            snapshot = session.build_snapshot()
            self.assertEqual(snapshot["identity"]["snapshot"]["buildState"], "degraded")
            contract = snapshot["intent"]["contract"]
            self.assertEqual(contract["availability"], "inconsistent")
            self.assertIsNone(contract["result"])


class MatrixCapabilityMismatchTest(unittest.TestCase):
    """implementation present while the public claim stays gated."""

    def test_real_package_console_is_experimental_and_trial_gated(self) -> None:
        # The strongest mismatch case uses the shipped package inventory:
        # run-console is implemented and tested locally, yet the public
        # claim stays experimental with the trial gate named as the gap.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-capability")
            payload = _run_status_payload(root)
        capability = payload["continuation"]["capability"]
        self.assertEqual(capability["capability"], "run-console")
        status = capability["status"]
        self.assertEqual(status["implementation"], "present")
        self.assertEqual(status["validation"], "tested")
        self.assertEqual(status["availability"], "local")
        self.assertEqual(status["publicClaim"], "experimental")
        self.assertIn("trial-gated", capability["evidenceGap"] or "")
        # Honest gap, not a safe path: the trial gate is unsatisfied and no
        # fallback upgrades it.
        self.assertEqual(capability["fallback"]["kind"], "evidence-gap")
        self.assertIn("G-RO-TRIAL-PASS", capability["fallback"]["detail"])

    def test_missing_runtime_downgrades_to_not_shipped_with_fallback(self) -> None:
        # The other mismatch face: a package without the Console runtime
        # reports absent / not-shipped with a safe fallback — never a
        # doomed open-console command.
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-no-runtime")
            fake_pkg = base / "pkg"
            fake_pkg.mkdir()
            from design_playbook.scripts.run_continuation import (
                continuation_for_run,
            )

            continuation = continuation_for_run(root, fake_pkg)
            payload = continuation.to_dict()
        self.assertEqual(payload["capability"]["status"]["implementation"], "absent")
        self.assertEqual(payload["capability"]["status"]["publicClaim"], "not-shipped")
        open_console = payload["open_console"]
        self.assertFalse(open_console["eligible"])
        self.assertNotIn("command", open_console)
        self.assertIn("missing Console runtime prerequisites", open_console["reason"])
        self.assertIn("run-status JSON", open_console["fallback"])


class MatrixMissingPrerequisiteTest(unittest.TestCase):
    """missing prerequisite: reason + fallback, no doomed command."""

    def test_malformed_confirm_blocker_names_the_resume_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-malformed")
            _declare_fill(root)
            (root / "preview" / "round-1.html").write_text(
                DELIVERABLE_HTML, encoding="utf-8"
            )
            (root / "preview" / "confirm-round-1.json").write_text(
                "{not json", encoding="utf-8"
            )
            payload = _run_status_payload(root)
            continuation = payload["continuation"]
            self.assertEqual(continuation["integrity"]["state"], "malformed")
            self.assertEqual(continuation["blocker"]["source"], "integrity")
            self.assertIn("invalid confirm record", continuation["blocker"]["reason"])
            self.assertTrue(continuation["open_console"]["eligible"])
            # The malformed record yields no canonical confirm at all, so
            # the Console's preview stays open — never confirmed.
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            self.addCleanup(session.close)
            snapshot = session.build_snapshot()
            self.assertEqual(
                snapshot["execution"]["preview"]["result"]["state"], "open"
            )


class MatrixPendingHandoffTest(unittest.TestCase):
    """Pending handoff: output exists, Pending stays Pending."""

    def test_pending_handoff_output_preserves_pending_and_writes_no_acceptance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-pending")
            _declare_fill(root)
            # No confirm record: the verdict must be exactly Pending
            # (unsubstantiated) — never Pass, and never a hedged maybe.
            before = _tree_digest(root)
            result = _handoff(root)
            self.assertEqual(result.verdict, "Pending")
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            # The wrapper reports exactly what the disclosure payload says.
            self.assertEqual(payload["verdict"], result.verdict)
            self.assertEqual(payload["authority"], result.authority)
            self.assertEqual(payload["confirmationSource"], result.confirmation_source)
            self.assertEqual(payload["authority"], "pending-user")
            self.assertEqual(payload["confirmationSource"], "unsubstantiated")
            self.assertIn("no confirm record", payload["confirmationNote"])
            # The gate is never reported passed while the run is Pending.
            self.assertEqual(payload["gateStatus"], "pending")
            # Honest outputs exist even while Pending (spec story 42).
            self.assertTrue(result.index_html.is_file())
            self.assertTrue(result.deliverable_html.is_file())
            # No acceptance write: the point-back owner text is unchanged,
            # and the only run-tree delta is the handoff output subtree.
            self.assertEqual(
                (root / "point-back.md").read_text(encoding="utf-8"),
                (FIXTURES / "point-back-pass-closed.md").read_text(encoding="utf-8"),
            )
            after = _tree_digest(root)
            added = {
                rel
                for rel in after
                if rel not in before and not rel.startswith("evidence/static-handoff")
            }
            self.assertEqual(added, set())
            changed = {
                rel for rel in before if rel in after and before[rel] != after[rel]
            }
            self.assertEqual(changed, set())

    def test_missing_fill_declaration_fails_with_repair_guidance(self) -> None:
        from design_playbook.scripts.run_handoff import RunHandoffError

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-no-fill")
            with self.assertRaises(RunHandoffError) as raised:
                _handoff(root)
            message = str(raised.exception).casefold()
            self.assertIn("fill:", message)
            self.assertIn("plan.md", message)
            self.assertFalse((root / "evidence" / "static-handoff").exists())


class MatrixSafetyTest(unittest.TestCase):
    """Journey-level safety: nothing runs, repairs, or writes by itself."""

    def test_console_action_allowlist_stays_closed(self) -> None:
        self.assertEqual(
            capability_names(),
            ("refresh", "view-source", "copy-agent-command"),
        )

    def test_status_render_launches_no_process_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(
                base,
                "run-safety",
                point_back="point-back-recirculate.md",
            )
            before = _tree_digest(root)
            with (
                _no_launch_patches()[0],
                _no_launch_patches()[1],
                _no_launch_patches()[2],
            ):
                payload = _run_status_payload(root)
            self.assertEqual(payload["verdict"], "Recirculate")
            self.assertEqual(_tree_digest(root), before)

    def test_console_reads_do_not_mutate_the_run_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(
                base,
                "run-console-read",
                point_back="point-back-recirculate.md",
                invalidated=True,
            )
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            server = serve_run_console(session, bind_host="127.0.0.1", port=0)
            self.addCleanup(server.stop)
            before = _tree_digest(root)

            conn = http.client.HTTPConnection(server.bind_host, server.port, timeout=10)
            try:
                # Read API: snapshot + a refresh (the only POST action) —
                # neither may touch the run tree.
                conn.request(
                    "GET",
                    "/api/v1/snapshot",
                    headers={
                        "Host": server.authority,
                        "Authorization": f"Bearer {session.token}",
                        "Origin": server.origin,
                    },
                )
                response = conn.getresponse()
                body = response.read()
                self.assertEqual(response.status, 200)
                snapshot = json.loads(body)
                self.assertEqual(
                    snapshot["evaluation"]["verdict"]["result"], "Recirculate"
                )
                conn.request(
                    "POST",
                    "/api/v1/actions/refresh",
                    body=json.dumps({"schemaVersion": 1, "action": "refresh"}),
                    headers={
                        "Host": server.authority,
                        "Authorization": f"Bearer {session.token}",
                        "Origin": server.origin,
                        "Content-Type": "application/json",
                    },
                )
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
            finally:
                conn.close()
            self.assertEqual(_tree_digest(root), before)

    def test_repair_action_routes_do_not_exist(self) -> None:
        from design_playbook.mcp.run_console.request_security import (
            ROUTE_NOT_FOUND,
        )

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-no-repair-routes")
            session = RunConsoleSession(
                run_root=root, now_fn=lambda: "2026-08-25T10:00:00Z"
            )
            server = serve_run_console(session, bind_host="127.0.0.1", port=0)
            self.addCleanup(server.stop)
            for route in (
                "/api/v1/actions/repair",
                "/api/v1/actions/rerun",
                "/api/v1/actions/accept",
                "/api/v1/actions/mutate",
            ):
                with self.subTest(route=route):
                    conn = http.client.HTTPConnection(
                        server.bind_host, server.port, timeout=10
                    )
                    try:
                        conn.request(
                            "POST",
                            route,
                            body=json.dumps({"schemaVersion": 1, "action": "x"}),
                            headers={
                                "Host": server.authority,
                                "Authorization": f"Bearer {session.token}",
                                "Origin": server.origin,
                                "Content-Type": "application/json",
                            },
                        )
                        response = conn.getresponse()
                        payload = response.read()
                        self.assertEqual(response.status, 404)
                        envelope = json.loads(payload)
                        self.assertEqual(envelope["error"]["code"], ROUTE_NOT_FOUND)
                    finally:
                        conn.close()
            session.close()


class MatrixCliJourneyTest(unittest.TestCase):
    """The CLI seam the operator actually types, run as a subprocess."""

    def test_run_status_cli_completed_run_emits_open_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = _make_matrix_run(base, "run-cli")
            _declare_fill(root)
            _confirm_preview(root)
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            result = subprocess.run(
                [sys.executable, str(RUN_STATUS), str(root), "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Pass")
            continuation = payload["continuation"]
            self.assertTrue(continuation["open_console"]["eligible"])
            argv = continuation["open_console"]["argv"]
            self.assertEqual(Path(argv[1]).resolve(), RUN_CONSOLE.resolve())
            self.assertEqual(Path(argv[2]).resolve(), root.resolve())

    def test_open_console_launcher_requires_explicit_run(self) -> None:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [sys.executable, str(RUN_CONSOLE)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
