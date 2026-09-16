"""Operator evidence hardening: finding identity, storage_state, probe sidecar."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.mcp.evidence import (  # noqa: E402
    capture_runtime,
    evidence_preflight as ep,
)
from design_playbook.mcp.evidence.capture_snapshot import (  # noqa: E402
    capture_call_snapshot,
)
from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    parse_capture_contract,
)
from design_playbook.mcp.evidence.disclosure import ViewportMetrics  # noqa: E402
from design_playbook.mcp.evidence.page_defects import DefectFacts  # noqa: E402
from design_playbook.scripts.finding_syntax import (  # noqa: E402
    closure_targets,
    finding_is_currently_closed,
    parse_findings,
)
from design_playbook.scripts.g2_g4_pointback import check_pointback  # noqa: E402
from design_playbook.scripts.g6_evidence import check_evidence  # noqa: E402
from design_playbook.scripts.repair_rounds import check_rounds  # noqa: E402

ORCH = PKG / "skills" / "design-playbook" / "SKILL.md"
EVALUATOR = PKG / "skills" / "ui-evaluator" / "SKILL.md"


def _rules(findings) -> set[str]:
    return {item.rule_id for item in findings}


def _pointback(*, issue: str = "overflow", finding_id: str = "",
               status: str = "", extra_finding: str = "",
               closure: str = "", verdict: str = "**Pass.**") -> str:
    fields = [
        f"issue:    {issue}",
        "source:   spec",
        "fix:      constrain width",
        "severity: S3",
        "disposition: blocking",
        "track:    product",
    ]
    if finding_id:
        fields.append(f"id:       {finding_id}")
    if status:
        fields.append(f"status:   {status}")
    if extra_finding:
        fields.append(extra_finding)
    body = "\n".join(fields)
    close = closure or issue
    return (
        "# pb\n\n## Evidence ledger\n\n"
        "criterion: L6.1\nrequired:  layout probe\n"
        "observed:  evidence/x.probe.json\nresult:    pass\n\n"
        f"## Findings\n\n```text\n{body}\n```\n\n"
        "## Positive findings\n\nnone\n\n"
        "## Coverage statement\n\nexhaustive\n\n"
        "## Limitations statement\n\nnone\n\n"
        f"## Verdict\n\n{verdict}\n\n"
        f"- closes: {close} -> recirculate -> fix -> re-eval -> 0 blocking\n"
    )


def _v1(**overrides):
    args = {
        "schemaVersion": 1,
        "url": "http://127.0.0.1:9/x",
        "type": "screenshot",
        "state": "ok",
        "actions": [],
        "artifact_path": "evidence/x.png",
        "viewport": {
            "width": 390,
            "height": 844,
            "devicePixelRatio": 1.0,
            "colorScheme": "light",
        },
    }
    args.update(overrides)
    return args


class _CaptureOnlyFake:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def capture(self, **request):
        self.calls.append(request)
        request["out_path"].parent.mkdir(parents=True, exist_ok=True)
        request["out_path"].write_bytes(b"fake-png")
        return "ok"


class _ProbingFake(_CaptureOnlyFake):
    def capture_and_probe(self, **request):
        self.capture(**request)
        return {
            "observed_state": "ok",
            "metrics": ViewportMetrics(
                sw=2000, innerH=844, hOverflow=80, inFold=True
            ),
            "defects": DefectFacts(
                leaks=({"kind": "undefined", "text": "undefined"},),
                tap_fails=({"tag": "button", "width": 10, "height": 10},),
            ),
            "console_errors": ["planted-console"],
        }


class FindingIdentityTests(unittest.TestCase):
    def test_parses_id_and_status(self) -> None:
        parsed = parse_findings(
            "issue: overflow\nsource: spec\nfix: x\nseverity: S3\n"
            "id: F-1\nstatus: regression\n"
        )
        self.assertEqual(parsed[0]["id"], ["F-1"])
        self.assertEqual(parsed[0]["status"], ["regression"])

    def test_g4_closes_by_id(self) -> None:
        text = _pointback(issue="horizontal overflow on mobile",
                          finding_id="F-1", closure="F-1")
        self.assertEqual(_rules(check_pointback(text, 1)), set())

    def test_g4_still_closes_by_issue_text(self) -> None:
        text = _pointback(issue="horizontal overflow on mobile")
        self.assertEqual(_rules(check_pointback(text, 1)), set())

    def test_invalid_status_and_duplicate_id(self) -> None:
        bad_status = _pointback(status="maybe", verdict="**Recirculate.**")
        self.assertIn(
            "G2.finding_invalid_status", _rules(check_pointback(bad_status, 1))
        )
        dup = (
            "# pb\n\n## Evidence ledger\n\n"
            "criterion: L6.1\nrequired: x\nobserved: evidence/x.png\n"
            "result: fail\n\n## Findings\n\n"
            "issue: a\nsource: spec\nfix: x\nseverity: S3\n"
            "disposition: blocking\nid: F-1\n\n"
            "issue: b\nsource: spec\nfix: y\nseverity: S3\n"
            "disposition: blocking\nid: F-1\n\n"
            "## Verdict\n\n**Recirculate.**\n"
        )
        self.assertIn("G2.finding_duplicate_id", _rules(check_pointback(dup, 1)))

    def test_two_id_lines_on_one_finding_are_repeated_field(self) -> None:
        text = (
            "# pb\n\n## Evidence ledger\n\n"
            "criterion: L6.1\nrequired: x\nobserved: evidence/x.png\n"
            "result: fail\n\n## Findings\n\n"
            "issue: a\nsource: spec\nfix: x\nseverity: S3\n"
            "disposition: blocking\nid: F-1\nid: F-2\n\n"
            "## Verdict\n\n**Recirculate.**\n"
        )
        self.assertIn("G2.finding_repeated_field", _rules(check_pointback(text, 1)))

    def test_empty_id_is_structural(self) -> None:
        text = _pointback(extra_finding="id:   ", verdict="**Recirculate.**")
        self.assertIn("G2.finding_empty_id", _rules(check_pointback(text, 1)))

    def test_rounds_treat_id_close_as_current(self) -> None:
        text = _pointback(
            issue="rewritten overflow copy",
            finding_id="F-1",
            closure="F-1",
            extra_finding="rounds: 2",
            verdict="**Recirculate.**",
        )
        text += "\nclose_reason: pass\n"
        self.assertEqual(check_rounds(text), [])

    def test_rounds_stop_when_id_unclosed(self) -> None:
        text = (
            "# pb\n\n## Evidence ledger\n\n"
            "criterion: L6.1\nrequired: x\nobserved: evidence/x.png\n"
            "result: fail\n\n## Findings\n\n"
            "issue: overflow\nsource: spec\nfix: x\nseverity: S3\n"
            "disposition: blocking\nid: F-1\nrounds: 2\n\n"
            "## Verdict\n\n**Recirculate.**\n"
        )
        self.assertIn("G4.round_stop_missing", _rules(check_rounds(text)))

    def test_history_prefix_is_not_current_close(self) -> None:
        hist = (
            "issue: overflow\nid: F-1\nstatus: regression\n"
            "history: round-1 closed F-1 against evidence/old.probe.json\n"
        )
        self.assertEqual(closure_targets(hist), [])
        closed = hist + "- closes: F-1 -> recirculate -> fix -> re-eval -> 0 blocking\n"
        self.assertEqual(closure_targets(closed), ["f-1"])

    def test_omitted_status_does_not_void_close(self) -> None:
        text = _pointback(issue="overflow", finding_id="F-1", closure="F-1")
        self.assertEqual(_rules(check_pointback(text, 1)), set())

    def test_a2_old_report_closes_by_issue_for_both_consumers(self) -> None:
        text = _pointback(issue="overflow")
        self.assertEqual(_rules(check_pointback(text, 1)), set())
        self.assertEqual(check_rounds(text), [])

    def test_a2_round_two_id_close_is_closed_for_both_consumers(self) -> None:
        text = _pointback(
            issue="rewritten overflow copy",
            finding_id="F-1",
            closure="F-1",
            extra_finding="rounds: 2",
        )
        text = text.replace("## Verdict\n\n**Pass.**",
                            "## Verdict\n\nclose_reason: pass\n\n**Pass.**")
        self.assertEqual(_rules(check_pointback(text, 1)), set())
        self.assertEqual(check_rounds(text), [])

    def test_a2_regression_history_is_not_current_close(self) -> None:
        text = (
            "# pb\n\n## Evidence ledger\n\n"
            "criterion: L6.1\nrequired: x\nobserved: evidence/x.png\n"
            "result: fail\n\n## Findings\n\n"
            "issue: overflow after patch\nsource: spec\nfix: x\nseverity: S3\n"
            "disposition: blocking\nid: F-1\nstatus: regression\nrounds: 2\n"
            "history: round-1 closed F-1 against evidence/old.probe.json\n\n"
            "## Verdict\n\n**Recirculate.**\n"
        )
        self.assertEqual(closure_targets(text), [])
        self.assertIn("G4.round_stop_missing", _rules(check_rounds(text)))
        closed = (
            text.replace("**Recirculate.**", "**Pass.**")
            .replace("result: fail", "result: pass")
            + "\n- closes: F-1 -> recirculate -> fix -> re-eval -> 0 blocking\n"
        )
        closed = closed.replace(
            "## Verdict\n\n**Pass.**",
            "## Verdict\n\nclose_reason: pass\n\n**Pass.**",
        )
        self.assertEqual(closure_targets(closed), ["f-1"])
        self.assertEqual(_rules(check_pointback(closed, 1)), set())
        self.assertEqual(check_rounds(closed), [])

    def test_status_open_does_not_void_current_close(self) -> None:
        text = _pointback(
            issue="overflow", finding_id="F-1", status="open", closure="F-1"
        )
        self.assertEqual(_rules(check_pointback(text, 1)), set())
        parsed = parse_findings(text)[0]
        self.assertTrue(
            finding_is_currently_closed(parsed, closure_targets(text))
        )

    def test_resolved_status_without_closes_cannot_pass(self) -> None:
        text = _pointback(
            issue="overflow",
            finding_id="F-1",
            status="resolved",
            extra_finding="rounds: 1",
            verdict="**Pass.**",
        )
        text = text.replace(
            "- closes: overflow -> recirculate -> fix -> re-eval -> 0 blocking\n",
            "",
        )
        self.assertTrue(_rules(check_pointback(text, 1)) & {
            "G4.missing_closure_trail", "G4.unmatched_closure",
        })

    def test_two_identical_id_closes_are_not_a_unique_current_close(self) -> None:
        text = _pointback(
            issue="overflow",
            finding_id="F-1",
            closure="F-1",
            extra_finding="rounds: 2",
            verdict="**Recirculate.**",
        )
        text += "- closes: F-1 -> recirculate -> fix -> re-eval -> 0 blocking\n"
        parsed = parse_findings(text)[0]
        targets = closure_targets(text)
        self.assertEqual(targets.count("f-1"), 2)
        self.assertFalse(finding_is_currently_closed(parsed, targets))
        self.assertIn("G4.round_stop_missing", _rules(check_rounds(text)))
        passing = text.replace("**Recirculate.**", "**Pass.**")
        self.assertIn("G4.duplicate_closure", _rules(check_pointback(passing, 1)))

    def test_id_and_issue_closes_are_two_matches_not_unique(self) -> None:
        text = _pointback(
            issue="overflow",
            finding_id="F-1",
            closure="F-1",
            extra_finding="rounds: 2",
            verdict="**Recirculate.**",
        )
        text += "- closes: overflow -> recirculate -> fix -> re-eval -> 0 blocking\n"
        parsed = parse_findings(text)[0]
        targets = closure_targets(text)
        self.assertEqual(len(targets), 2)
        self.assertFalse(finding_is_currently_closed(parsed, targets))
        self.assertIn("G4.round_stop_missing", _rules(check_rounds(text)))
        passing = text.replace("**Recirculate.**", "**Pass.**")
        self.assertIn("G4.duplicate_closure", _rules(check_pointback(passing, 1)))


class ProbeSidecarTests(unittest.TestCase):
    def test_sidecar_resolve_refuses_reserved_manifest_name(self) -> None:
        fake = _ProbingFake()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                with mock.patch.object(
                    capture_runtime,
                    "probe_sidecar_rel",
                    return_value="evidence/manifest.jsonl",
                ):
                    payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "failed")
            self.assertIn("manifest.jsonl", payload["error"])
            self.assertEqual(fake.calls, [])
            self.assertFalse((root / "evidence" / "manifest.jsonl").exists())

    def test_capture_only_adapter_skips_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "captured")
            self.assertNotIn("probe_artifact", payload)
            self.assertFalse((root / "evidence" / "x.probe.json").exists())

    def test_probing_adapter_writes_sidecar_facts_not_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _ProbingFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "captured")
            self.assertEqual(payload["probe_artifact"], "evidence/x.probe.json")
            sidecar = json.loads(
                (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sidecar["schema"], "page-probe/v1")
            self.assertEqual(sidecar["layout"]["hOverflow"], 80)
            self.assertEqual(sidecar["leaks"][0]["kind"], "undefined")
            self.assertEqual(sidecar["tapFails"][0]["width"], 10)
            self.assertEqual(sidecar["consoleErrors"], ["planted-console"])
            self.assertEqual(sidecar["layout"]["measurement_status"], "measured")
            self.assertEqual(sidecar["defects"]["measurement_status"], "measured")
            self.assertEqual(sidecar["console"]["measurement_status"], "measured")
            self.assertEqual(sidecar["defects"]["measurement_error"], "")
            source = (
                PKG / "mcp" / "evidence" / "page_defects.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("Pass", source)
            self.assertNotIn("Recirculate", source)

    def test_blocked_defects_sidecar_differs_from_clean(self) -> None:
        class _Blocked(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(
                        measurement_status="blocked",
                        measurement_error="evaluate failed",
                    ),
                    "console_errors": [],
                }

        class _Clean(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(),
                    "console_errors": [],
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                capture_runtime.execute_capture_plan(_v1(), _Blocked())
                blocked = (root / "evidence" / "x.probe.json").read_text(
                    encoding="utf-8"
                )
                (root / "evidence" / "x.probe.json").unlink()
                (root / "evidence" / "x.png").unlink()
                capture_runtime.execute_capture_plan(_v1(), _Clean())
                clean = (root / "evidence" / "x.probe.json").read_text(
                    encoding="utf-8"
                )
        self.assertNotEqual(json.loads(blocked), json.loads(clean))
        self.assertEqual(
            json.loads(blocked)["defects"]["measurement_status"], "blocked"
        )
        self.assertEqual(
            json.loads(clean)["defects"]["measurement_status"], "measured"
        )
        self.assertEqual(set(json.loads(blocked)["defects"]), {
            "measurement_status", "measurement_error",
        })
        self.assertEqual(set(json.loads(blocked)["console"]), {
            "measurement_status", "measurement_error",
        })

    def test_missing_probe_keys_are_unmeasured_not_clean(self) -> None:
        class _Partial(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {"observed_state": "ok"}

        class _Clean(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(),
                    "console_errors": [],
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                capture_runtime.execute_capture_plan(_v1(), _Partial())
                partial = json.loads(
                    (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
                )
                (root / "evidence" / "x.probe.json").unlink()
                (root / "evidence" / "x.png").unlink()
                capture_runtime.execute_capture_plan(_v1(), _Clean())
                clean = json.loads(
                    (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
                )
        self.assertNotEqual(partial, clean)
        self.assertEqual(partial["layout"]["measurement_status"], "unmeasured")
        self.assertTrue(partial["layout"]["measurement_error"])
        self.assertEqual(partial["defects"]["measurement_status"], "unmeasured")
        self.assertTrue(partial["defects"]["measurement_error"])
        self.assertEqual(partial["console"]["measurement_status"], "unmeasured")
        self.assertTrue(partial["console"]["measurement_error"])
        self.assertEqual(clean["layout"]["measurement_error"], "")
        self.assertEqual(clean["defects"]["measurement_error"], "")
        self.assertEqual(clean["console"]["measurement_error"], "")

    def test_console_errors_none_is_not_clean_measured(self) -> None:
        class _NoneConsole(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(),
                    "console_errors": None,
                }

        class _Clean(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(),
                    "console_errors": [],
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                capture_runtime.execute_capture_plan(_v1(), _NoneConsole())
                none_sidecar = json.loads(
                    (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
                )
                (root / "evidence" / "x.probe.json").unlink()
                (root / "evidence" / "x.png").unlink()
                capture_runtime.execute_capture_plan(_v1(), _Clean())
                clean = json.loads(
                    (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
                )
        self.assertNotEqual(none_sidecar, clean)
        self.assertIn(
            none_sidecar["console"]["measurement_status"],
            {"unmeasured", "blocked"},
        )
        self.assertTrue(none_sidecar["console"]["measurement_error"])
        self.assertEqual(clean["console"]["measurement_status"], "measured")
        self.assertEqual(clean["console"]["measurement_error"], "")

    def test_console_errors_bad_shape_is_blocked_not_clean(self) -> None:
        class _BadConsole(_CaptureOnlyFake):
            def capture_and_probe(self, **request):
                self.capture(**request)
                return {
                    "observed_state": "ok",
                    "metrics": ViewportMetrics(
                        sw=390, innerH=844, hOverflow=0, inFold=True
                    ),
                    "defects": DefectFacts(),
                    "console_errors": {"oops": True},
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                capture_runtime.execute_capture_plan(_v1(), _BadConsole())
                sidecar = json.loads(
                    (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
                )
        self.assertEqual(sidecar["console"]["measurement_status"], "blocked")
        self.assertTrue(sidecar["console"]["measurement_error"])
        self.assertEqual(sidecar["consoleErrors"], [])

    def test_probing_adapter_rejects_sidecar_path_before_browser(self) -> None:
        fake = _ProbingFake()
        real_resolve = capture_runtime._resolve_artifact_path

        def resolve(path: str):
            if str(path).endswith(".probe.json"):
                raise ValueError("artifact_path must stay under the evidence/ subtree")
            return real_resolve(path)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                with mock.patch.object(
                    capture_runtime, "_resolve_artifact_path", side_effect=resolve
                ):
                    payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "failed")
            self.assertIn("sidecar", payload["error"].casefold())
            self.assertEqual(fake.calls, [])
            self.assertFalse((root / "evidence" / "x.png").exists())
            self.assertNotIn("probe_artifact", payload)

    def test_write_sidecar_path_reject_fails_capture_not_silent_skip(self) -> None:
        fake = _ProbingFake()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                with mock.patch.object(
                    capture_runtime,
                    "_write_probe_sidecar",
                    side_effect=ValueError(
                        "artifact_path must stay under the evidence/ subtree"
                    ),
                ):
                    payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "failed")
            self.assertIn("sidecar", payload["error"].casefold())
            self.assertTrue(fake.calls)
            self.assertNotEqual(payload.get("probe_artifact", ""), "evidence/x.probe.json")

    def test_capture_only_still_skips_sidecar_when_probe_path_would_fail(self) -> None:
        fake = _CaptureOnlyFake()
        real_resolve = capture_runtime._resolve_artifact_path

        def resolve(path: str):
            if str(path).endswith(".probe.json"):
                raise ValueError("artifact_path must stay under the evidence/ subtree")
            return real_resolve(path)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                with mock.patch.object(
                    capture_runtime, "_resolve_artifact_path", side_effect=resolve
                ):
                    payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "captured")
            self.assertNotIn("probe_artifact", payload)
            self.assertTrue((root / "evidence" / "x.png").exists())
            self.assertEqual(len(fake.calls), 1)


class StorageStateTests(unittest.TestCase):
    def test_preflight_rejects_escaping_storage_state(self) -> None:
        entry = {
            "url": "http://127.0.0.1:8000/",
            "type": "screenshot",
            "state": "ok",
            "artifact_path": "evidence/x.png",
            "schemaVersion": 1,
            "viewport": {
                "width": 1280, "height": 800,
                "devicePixelRatio": 1, "colorScheme": "light",
            },
            "storage_state": "../secrets.json",
        }
        codes = {fact.code for fact in ep.preflight_plan([entry])}
        self.assertIn("bad_storage_state", codes)

    def test_runtime_loads_run_local_storage_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "storage-state.json"
            state.write_text("{}", encoding="utf-8")
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="storage-state.json"), fake
                )
            self.assertEqual(payload["result"], "captured")
            self.assertEqual(
                Path(fake.calls[0]["storage_state"]).resolve(),
                state.resolve(),
            )

    def test_preflight_missing_storage_state_file_is_not_an_error(self) -> None:
        entry = {
            "url": "http://127.0.0.1:8000/",
            "type": "screenshot",
            "state": "ok",
            "artifact_path": "evidence/x.png",
            "schemaVersion": 1,
            "viewport": {
                "width": 1280, "height": 800,
                "devicePixelRatio": 1, "colorScheme": "light",
            },
            "storage_state": "session.json",
        }
        codes = {fact.code for fact in ep.preflight_plan([entry])
                 if fact.severity == "error"}
        self.assertNotIn("bad_storage_state", codes)

    def test_runtime_rejects_invalid_storage_state_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text("{", encoding="utf-8")
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            self.assertEqual(payload["result"], "failed")
            self.assertIn("JSON", payload["error"])
            self.assertNotIn("{", payload["error"][payload["error"].find("JSON"):])
            self.assertEqual(fake.calls, [])

    def test_runtime_rejects_missing_storage_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="missing.json"), fake
                )
            self.assertEqual(payload["result"], "failed")
            self.assertIn("storage_state", payload["error"])
            self.assertEqual(fake.calls, [])

    def test_runtime_rejects_nonstandard_json_constants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text(
                '{"cookies": [], "origins": [], "flag": NaN}',
                encoding="utf-8",
            )
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            self.assertEqual(payload["result"], "failed")
            self.assertIn("nonstandard", payload["error"])
            self.assertNotIn("NaN", json.dumps(payload))
            self.assertNotIn("cookies", payload["error"])
            self.assertEqual(fake.calls, [])

    def test_runtime_rejects_overflowing_storage_state_integer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text(
                '{"cookies": [], "origins": [], "n": 9007199254740993}',
                encoding="utf-8",
            )
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            self.assertEqual(payload["result"], "failed")
            self.assertIn("overflow", payload["error"])
            self.assertEqual(fake.calls, [])

    def test_capture_failure_diagnostic_omits_session_secrets(self) -> None:
        secret = "SECRET_TOKEN_DO_NOT_LEAK"

        class _Boom(_CaptureOnlyFake):
            def capture(self, **request):
                raise RuntimeError(f"timeout Call log: input.value={secret}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text(
                json.dumps({
                    "cookies": [{
                        "name": "session",
                        "value": secret,
                        "domain": "127.0.0.1",
                        "path": "/",
                    }],
                    "origins": [],
                }),
                encoding="utf-8",
            )
            fake = _Boom()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            dumped = json.dumps(payload)
            self.assertEqual(payload["result"], "failed")
            self.assertNotIn(secret, dumped)
            self.assertIn("RuntimeError", payload["error"])
            self.assertIn("operator", payload["error"])

    def test_capture_snapshot_keeps_session_path_not_bytes(self) -> None:
        request = _v1(storage_state="sessions/valid.json")
        snap = capture_call_snapshot(request)
        self.assertEqual(snap["storage_state"], "sessions/valid.json")
        self.assertEqual(snap["url"], request["url"])
        self.assertNotIn("cookies", json.dumps(snap))

    def test_runtime_rejects_non_object_storage_state_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text("[]", encoding="utf-8")
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            self.assertEqual(payload["result"], "failed")
            self.assertIn("JSON object", payload["error"])
            self.assertEqual(fake.calls, [])

    def test_storage_state_secret_bytes_do_not_enter_payload(self) -> None:
        secret = "SECRET_TOKEN_DO_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.json").write_text(
                json.dumps({
                    "cookies": [{
                        "name": "session",
                        "value": secret,
                        "domain": "127.0.0.1",
                        "path": "/",
                    }],
                    "origins": [],
                }),
                encoding="utf-8",
            )
            fake = _CaptureOnlyFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1(storage_state="session.json"), fake
                )
            dumped = json.dumps(payload)
            self.assertEqual(payload["result"], "captured")
            self.assertNotIn(secret, dumped)
            self.assertNotIn("storage_state", payload.get("request", {}))
            self.assertEqual(
                set(payload["request"]),
                {"schemaVersion", "viewport", "freeze"},
            )


_CANONICAL_CAPTURE = {
    "url": "http://127.0.0.1:4173/settings",
    "type": "screenshot",
    "state": "ok",
    "actions": [{"do": "wait_for_state", "state": "ok"}],
    "artifact_path": "evidence/L6.4-ok.png",
}
_CANONICAL_REQUEST = {
    "schemaVersion": 1,
    "viewport": {
        "width": 390,
        "height": 844,
        "devicePixelRatio": 1.0,
        "colorScheme": "light",
    },
    "freeze": {"enabled": True, "waitFonts": True, "networkIdle": False},
}


def _g6_pointback(*rows: tuple[str, str, str]) -> str:
    blocks = []
    for criterion, observed, result in rows:
        blocks.append(
            f"criterion: {criterion}\nrequired:  proof\n"
            f"observed:  {observed}\nresult:    {result}\n"
        )
    return (
        "# pb\n\n## Evidence ledger\n\n"
        + "\n".join(blocks)
        + "\n## Findings\n\nfindings: none\n\n"
        "## Positive findings\n\nnone\n\n"
        "## Coverage statement\n\nexhaustive\n\n"
        "## Limitations statement\n\nnone\n\n"
        "## Verdict\n\n**Recirculate.**\n"
    )


def _manifest_line(criterion: str, artifact: str, **extra: object) -> dict:
    line = {
        "criterion": criterion,
        "artifact": artifact,
        "observed_state": "ok",
        "result": "captured",
        "ts": extra.pop("ts", "2026-09-16T12:00:00Z"),
        "capture": dict(_CANONICAL_CAPTURE),
        "request": dict(_CANONICAL_REQUEST),
        "method": "runtime-observation",
        "observation": extra.pop("observation", "layout.hOverflow=80 at 390x844"),
        "interpretation": extra.pop(
            "interpretation", "Then (no overflow) does not hold"
        ),
        "scope": extra.pop("scope", "viewport 390x844, settings ok"),
    }
    line.update(extra)
    return line


class G6BindTests(unittest.TestCase):
    def test_canonical_probe_binding_has_no_g6_no_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "L6.4-ok.png").write_bytes(b"png")
            (evidence / "L6.4-ok.probe.json").write_text("{}", encoding="utf-8")
            (evidence / "manifest.jsonl").write_text(
                json.dumps(_manifest_line(
                    "L6.4",
                    "L6.4-ok.probe.json",
                    probe_artifact="evidence/L6.4-ok.probe.json",
                )) + "\n",
                encoding="utf-8",
            )
            findings = check_evidence(
                _g6_pointback(
                    ("L6.4", "evidence/L6.4-ok.probe.json", "fail")
                ),
                1,
                evidence,
                root,
            )
        self.assertFalse(
            any(item.rule_id == "G6.no_binding" for item in findings), findings
        )
        self.assertEqual(_CANONICAL_REQUEST, parse_capture_contract({
            **_CANONICAL_CAPTURE,
            **_CANONICAL_REQUEST,
        }))
        self.assertNotIn("type", _CANONICAL_REQUEST)

    def test_echo_only_probe_artifact_is_g6_no_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "L6.4-ok.png").write_bytes(b"png")
            (evidence / "L6.4-ok.probe.json").write_text("{}", encoding="utf-8")
            (evidence / "manifest.jsonl").write_text(
                json.dumps(_manifest_line(
                    "L6.4",
                    "L6.4-ok.png",
                    probe_artifact="evidence/L6.4-ok.probe.json",
                )) + "\n",
                encoding="utf-8",
            )
            findings = check_evidence(
                _g6_pointback(
                    ("L6.4", "evidence/L6.4-ok.probe.json", "fail")
                ),
                1,
                evidence,
                root,
            )
        self.assertIn("G6.no_binding", _rules(findings))

    def test_one_capture_two_criteria_bind_distinct_leaves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "L6.4-ok.png").write_bytes(b"png")
            (evidence / "L6.4-ok.probe.json").write_text("{}", encoding="utf-8")
            (evidence / "manifest.jsonl").write_text(
                json.dumps(_manifest_line(
                    "L6.4",
                    "L6.4-ok.probe.json",
                    probe_artifact="evidence/L6.4-ok.probe.json",
                    ts="2026-09-16T12:00:00Z",
                )) + "\n"
                + json.dumps(_manifest_line(
                    "L6.1",
                    "L6.4-ok.png",
                    probe_artifact="evidence/L6.4-ok.probe.json",
                    ts="2026-09-16T12:00:01Z",
                    observation="settings ok state rendered at 390x844",
                    interpretation="visible-state Then uses the screenshot",
                )) + "\n",
                encoding="utf-8",
            )
            findings = check_evidence(
                _g6_pointback(
                    ("L6.1", "evidence/L6.4-ok.png", "pass"),
                    ("L6.4", "evidence/L6.4-ok.probe.json", "fail"),
                ),
                4,
                evidence,
                root,
            )
        self.assertFalse(
            any(item.rule_id.startswith("G6.") for item in findings), findings
        )

    def test_overflow_sidecar_does_not_make_g6_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "L6.4-ok.probe.json").write_text(
                json.dumps({"schema": "page-probe/v1", "layout": {"hOverflow": 80}}),
                encoding="utf-8",
            )
            (evidence / "manifest.jsonl").write_text(
                json.dumps(_manifest_line("L6.4", "L6.4-ok.probe.json")) + "\n",
                encoding="utf-8",
            )
            findings = check_evidence(
                _g6_pointback(
                    ("L6.4", "evidence/L6.4-ok.probe.json", "fail")
                ),
                1,
                evidence,
                root,
            )
        self.assertFalse(
            any(item.rule_id == "G6.no_binding" for item in findings), findings
        )

    def test_provider_return_has_no_criterion_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _ProbingFake()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(_v1(), fake)
            self.assertEqual(payload["result"], "captured")
            self.assertNotIn("criterion", payload)
            self.assertNotIn("type", payload)
            self.assertEqual(
                set(payload["request"]),
                {"schemaVersion", "viewport", "freeze"},
            )
            self.assertEqual(
                payload["request"], parse_capture_contract(_v1())
            )
            self.assertFalse((root / "evidence" / "manifest.jsonl").exists())


class SkillLockstepTests(unittest.TestCase):
    def test_orchestrator_names_web_viewports_and_probe_sidecar(self) -> None:
        text = ORCH.read_text(encoding="utf-8")
        self.assertIn("WEB_VIEWPORTS", text)
        self.assertIn("probe.json", text)
        self.assertIn("storage_state", text)
        self.assertIn("wait_for_state", text)
        self.assertIn("leaf", text)
        self.assertIn("measurement_status", text)
        self.assertIn("P1 does not require that seed", text)
        self.assertIn("Dark / 压力包 are not default seeds", text)
        self.assertIn("run-handoff", text)
        self.assertIn("not covered by another viewport's pass", text)
        self.assertIn("capture.storage_state", text)

    def test_evaluator_names_id_and_status(self) -> None:
        text = EVALUATOR.read_text(encoding="utf-8")
        self.assertIn("id:", text)
        self.assertIn("open|resolved|new|regression", text)
        self.assertIn("measurement_status", text)
        self.assertNotIn("omit = open", text)
        self.assertIn("not a second closure authority", text)
        self.assertIn("history:", text)
        self.assertIn("seen, omitted", text)


if __name__ == "__main__":
    unittest.main()
