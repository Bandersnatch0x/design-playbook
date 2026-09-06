#!/usr/bin/env python3
"""T-003: derived Repair Packet projection, render, and copy-only UI.

Covers completed, blocked, stale, inconsistent, and unavailable snapshots;
copy-only behavior; and the existing locator/allowlist security boundary.
The packet is a derived view of a validated Snapshot — never a schema or
persisted run state.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sys
import unittest
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.contract import (  # noqa: E402
    SnapshotContractError,
    validate_snapshot,
)
from design_playbook.mcp.run_console.repair_packet import (  # noqa: E402
    MSG_NO_BLOCKING,
    MSG_NO_COMMAND,
    MSG_NO_INVALIDATED,
    MSG_NO_RECAPTURE,
    MSG_NO_RESUME_STAGE,
    NOT_PRODUCED,
    PACKET_KEYS,
    derive_repair_packet,
    format_packet_copy_text,
)
from design_playbook.mcp.run_console.ui import UIResources  # noqa: E402
from mcp.run_console import test_contract as contract_fixtures  # noqa: E402
from mcp.run_console import test_ui_browser as browser_harness  # noqa: E402

_DIR = Path(__file__).resolve().parent
_JS = (_DIR / "app.js").read_text(encoding="utf-8")
_HTML = (_DIR / "app.html").read_text(encoding="utf-8")
_CSS = (_DIR / "app.css").read_text(encoding="utf-8")
_COMMAND = "qoder run --resume run_example --next ui-evaluator"

_PLAYWRIGHT = None
_BROWSER = None


def setUpModule() -> None:
    global _PLAYWRIGHT, _BROWSER
    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch()
    browser_harness._BROWSER = _BROWSER


def tearDownModule() -> None:
    _BROWSER.close()
    _PLAYWRIGHT.stop()
    browser_harness._BROWSER = None


def _valid() -> dict[str, object]:
    return deepcopy(contract_fixtures._valid_snapshot())


def _reason(code: str, source_refs: list[str], **kwargs: object) -> dict[str, object]:
    return contract_fixtures._reason(code, source_refs, **kwargs)


def _bind_source_set_hash(document: dict[str, object]) -> None:
    items = document["sources"]["items"]  # type: ignore[index]
    retained = [
        {
            key: item[key]
            for key in (
                "sourceRef",
                "authorityKey",
                "readState",
                "observedHash",
                "verifiedHash",
                "freshness",
            )
        }
        for item in items  # type: ignore[union-attr]
    ]
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            retained, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    document["sources"]["sourceSetHash"] = digest  # type: ignore[index]
    document["identity"]["snapshot"]["sourceSetHash"] = digest  # type: ignore[index]


def _blocking_snapshot(*, command: str | None = None) -> dict[str, object]:
    document = _valid()
    document["evaluation"]["verdict"]["result"] = "Recirculate"  # type: ignore[index]
    finding = document["evaluation"]["findings"][0]  # type: ignore[index]
    finding["result"].update(  # type: ignore[index]
        disposition="blocking",
        severity="S3",
        issue="destructive action has no confirmation",
        repair="add a consequence-confirmation dialog",
        owner={
            "kind": "declaration",
            "domainId": "intent.summary",
            "sourceRef": "source.common",
        },
    )
    document["nextActions"]["primary"]["result"].update(  # type: ignore[index]
        actionId="action.repair-after-recirculate",
        kind="continue",
        label="Verdict is Recirculate — repair from point-back findings.",
        owner={"actor": "agent", "role": None},
        copyableAgentCommand=command,
    )
    return document


class RepairPacketProjectionTest(unittest.TestCase):
    """Python projection of owner-projected Snapshot facts."""

    def test_completed_pass_exposes_intent_verdict_and_honest_gaps(self) -> None:
        packet = derive_repair_packet(_valid())
        self.assertEqual(packet["intent"]["availability"], "known")
        self.assertEqual(packet["intent"]["value"], "Deliver a safe checkout.")
        self.assertEqual(packet["verdict"]["availability"], "known")
        self.assertEqual(packet["verdict"]["value"], "Pass")
        self.assertEqual(packet["finding"]["availability"], "unknown")
        self.assertEqual(packet["finding"]["reason"]["code"], NOT_PRODUCED)
        self.assertEqual(packet["finding"]["reason"]["message"], MSG_NO_BLOCKING)
        self.assertEqual(packet["repairIntent"]["value"], None)
        self.assertEqual(packet["invalidatedEvidence"]["reason"]["message"], MSG_NO_INVALIDATED)
        self.assertEqual(packet["recaptureRequirement"]["reason"]["message"], MSG_NO_RECAPTURE)
        self.assertEqual(packet["nextCommand"]["reason"]["message"], MSG_NO_COMMAND)
        self.assertEqual(packet["resumeStage"]["availability"], "unknown")
        self.assertIsNone(packet["resumeStage"]["value"])
        self.assertEqual(packet["resumeStage"]["reason"]["code"], NOT_PRODUCED)
        self.assertEqual(packet["resumeStage"]["reason"]["message"], MSG_NO_RESUME_STAGE)
        self.assertEqual(packet["nextOwner"]["value"]["actor"], "run-operator")
        self.assertNotIn(_COMMAND, packet["copyText"])
        self.assertIn("unavailable", packet["copyText"])

    def test_blocked_finding_projects_owner_repair_and_does_not_invent_command(self) -> None:
        packet = derive_repair_packet(_blocking_snapshot())
        self.assertEqual(packet["verdict"]["value"], "Recirculate")
        self.assertEqual(packet["finding"]["availability"], "known")
        self.assertEqual(
            packet["finding"]["value"]["issue"],
            "destructive action has no confirmation",
        )
        self.assertEqual(packet["declarationOwner"]["value"]["kind"], "declaration")
        self.assertEqual(packet["declarationOwner"]["value"]["domainId"], "intent.summary")
        self.assertEqual(
            packet["repairIntent"]["value"],
            "add a consequence-confirmation dialog",
        )
        self.assertEqual(packet["blockerSource"]["value"]["blockingCount"], 1)
        self.assertEqual(packet["nextOwner"]["value"]["actor"], "agent")
        self.assertIsNone(packet["nextCommand"]["value"])
        self.assertEqual(packet["nextCommand"]["reason"]["code"], NOT_PRODUCED)
        label = "Verdict is Recirculate — repair from point-back findings."
        self.assertNotEqual(packet["nextCommand"]["value"], label)
        self.assertEqual(packet["invalidatedEvidence"]["availability"], "unknown")
        self.assertEqual(packet["recaptureRequirement"]["availability"], "unknown")

    def test_owner_supplied_command_is_copied_verbatim(self) -> None:
        packet = derive_repair_packet(_blocking_snapshot(command=_COMMAND))
        self.assertEqual(packet["nextCommand"]["availability"], "known")
        self.assertEqual(packet["nextCommand"]["value"], _COMMAND)
        self.assertIn(_COMMAND, packet["copyText"])

    def test_resume_stage_is_a_gap_not_inferred_from_progress_or_command(self) -> None:
        """Spec rule 19: latest observed stage is not a resume target."""
        document = _blocking_snapshot(command=_COMMAND)
        progress = document["execution"]["progress"]  # type: ignore[index]
        progress["result"]["latestObservedStage"] = "fill"  # type: ignore[index]
        packet = derive_repair_packet(document)
        self.assertEqual(packet["resumeStage"]["availability"], "unknown")
        self.assertIsNone(packet["resumeStage"]["value"])
        self.assertEqual(packet["resumeStage"]["reason"]["code"], NOT_PRODUCED)
        self.assertEqual(packet["resumeStage"]["reason"]["message"], MSG_NO_RESUME_STAGE)
        rendered = json.dumps(packet["resumeStage"])
        self.assertNotIn("fill", rendered)
        self.assertNotIn("--resume", rendered)

    def test_stale_intent_is_stale_context_not_current(self) -> None:
        document = _valid()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        document["sources"]["items"][0].update(  # type: ignore[index]
            verifiedHash=contract_fixtures._HASH_2, freshness="changed"
        )
        _bind_source_set_hash(document)
        assertion = document["intent"]["summary"]  # type: ignore[index]
        assertion.update(
            availability="stale",
            reason=_reason(
                "source-changed-during-build",
                ["source.common"],
                observed_hashes=[contract_fixtures._HASH_1],
                verified_hashes=[contract_fixtures._HASH_2],
            ),
        )
        assertion["source"].update(verifiedSetHash=contract_fixtures._HASH_2)
        packet = derive_repair_packet(document)
        self.assertEqual(packet["intent"]["availability"], "stale")
        self.assertEqual(packet["intent"]["value"], "Deliver a safe checkout.")
        self.assertIn("stale context", packet["copyText"])
        self.assertEqual(packet["verdict"]["value"], "Pass")

    def test_inconsistent_verdict_does_not_surface_pass(self) -> None:
        document = _valid()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        assertion = document["evaluation"]["verdict"]  # type: ignore[index]
        assertion.update(
            availability="inconsistent",
            result=None,
            reason=_reason(
                "conflicting-authorities",
                ["source.common", "source.evaluator-report"],
                observed_hashes=[contract_fixtures._HASH_1, contract_fixtures._HASH_3],
                verified_hashes=[contract_fixtures._HASH_1, contract_fixtures._HASH_3],
                conflicts=[
                    {
                        "sourceRef": "source.evaluator-report",
                        "hash": contract_fixtures._HASH_3,
                        "summary": "verdict contradicts the findings ledger",
                    }
                ],
            ),
        )
        assertion["source"]["refs"] = ["source.common", "source.evaluator-report"]
        packet = derive_repair_packet(document)
        self.assertEqual(packet["verdict"]["availability"], "inconsistent")
        self.assertIsNone(packet["verdict"]["value"])
        self.assertNotIn("Verdict (inconsistent): Pass", packet["copyText"])

    def test_unknown_finding_disposition_is_not_treated_as_non_blocking(self) -> None:
        document = _valid()
        document["identity"]["snapshot"]["buildState"] = "degraded"  # type: ignore[index]
        finding = document["evaluation"]["findings"][0]  # type: ignore[index]
        finding.update(
            availability="unknown",
            result=None,
            reason=_reason("owner-unmapped", ["source.common"]),
        )
        packet = derive_repair_packet(document)
        self.assertEqual(packet["finding"]["availability"], "unknown")
        self.assertIsNone(packet["finding"]["value"])
        self.assertNotEqual(packet["finding"]["reason"]["message"], MSG_NO_BLOCKING)
        self.assertEqual(packet["declarationOwner"]["value"], None)

    def test_packet_is_not_persisted_state_and_does_not_mutate_input(self) -> None:
        document = _valid()
        before = json.dumps(document, sort_keys=True)
        packet = derive_repair_packet(document)
        self.assertEqual(json.dumps(document, sort_keys=True), before)
        self.assertEqual(validate_snapshot(document)["schemaVersion"], 1)
        for key in PACKET_KEYS:
            self.assertIn(key, packet)
        self.assertNotIn("schemaVersion", packet)
        serialized = json.dumps(packet)
        self.assertNotIn("src_", serialized)
        self.assertNotIn("C:\\", serialized)
        self.assertNotIn("/home/", serialized)

    def test_invalid_snapshot_fails_closed(self) -> None:
        with self.assertRaises(SnapshotContractError):
            derive_repair_packet({"schemaVersion": 1})

    def test_copy_text_is_plain_and_mentions_copy_only(self) -> None:
        text = format_packet_copy_text(derive_repair_packet(_valid()))
        self.assertTrue(text.startswith("Repair Packet"))
        self.assertIn("copy only", text)
        self.assertIn("nothing is executed", text)

    def test_projection_module_has_no_exec_or_network_primitive(self) -> None:
        source = (_DIR / "repair_packet.py").read_text(encoding="utf-8")
        for needle in (
            "subprocess", "socket", "urllib", "requests", "http.client",
            "os.system", "eval(", "exec(", "Path.write", "open(",
        ):
            self.assertNotIn(needle, source)


class RepairPacketRenderContractTest(unittest.TestCase):
    """Static UI contract: derived view, copy only, closed allowlist."""

    def test_shell_exposes_repair_packet_jump_and_section_id(self) -> None:
        self.assertIn('href="#section-repair-packet"', _HTML)
        self.assertIn("deriveRepairPacket", _JS)
        self.assertIn("section-repair-packet", _JS)
        self.assertIn("data-repair-packet", _JS)
        self.assertIn("packet-copy-summary", _JS)

    def test_packet_copy_is_clipboard_only_and_does_not_execute(self) -> None:
        self.assertIn("clipboard.writeText", _JS)
        self.assertIn("packet_copy_heading", _JS)
        self.assertNotIn("innerHTML", _JS)
        self.assertNotIn("/api/v1/actions/repair", _JS)
        self.assertNotIn("/api/v1/actions/rerun", _JS)
        self.assertNotIn("executeRepair", _JS)

    def test_resume_stage_is_a_static_gap_not_derived_from_progress(self) -> None:
        self.assertIn("packetGap(PACKET_MSG_NO_RESUME_STAGE)", _JS)
        self.assertIn("packet_not_produced_resume_stage", _JS)
        self.assertNotIn("packetResumeStage", _JS)

    def test_ui_route_table_is_unchanged(self) -> None:
        resources = UIResources()
        self.assertIsNotNone(resources.lookup("/"))
        self.assertIsNotNone(resources.lookup("/app.js"))
        self.assertIsNone(resources.lookup("/repair-packet"))
        self.assertIsNone(resources.lookup("/api/v1/repair-packet"))

    def test_packet_css_is_responsive_and_wraps(self) -> None:
        self.assertIn(".packet-grid", _CSS)
        self.assertIn("overflow-wrap: anywhere", _CSS)
        self.assertIn("grid-template-columns: 1fr", _CSS)


class RepairPacketBrowserTest(browser_harness.BrowserTestCase):
    """Real console UI: completed/blocked/stale/copy/security."""

    def _packet(self):
        return self.page.locator("#section-repair-packet")

    def _field(self, key: str):
        return self.page.locator(f'#repair-packet-grid [data-packet-field="{key}"]')

    def test_completed_run_shows_packet_gaps_not_invented_repair(self) -> None:
        self.open()
        packet = self._packet()
        expect(packet).to_be_visible()
        self.assertIn("Repair Packet", packet.locator("h2").inner_text())
        self.assertIn("derived view", packet.inner_text())
        intent = self._field("intent").inner_text()
        self.assertIn("查看所有模拟运行的队列监控页", intent)
        self.assertIn("<script>alert(1)</script>", intent)
        self.assertIn("Pass", self._field("verdict").inner_text())
        self.assertIn("Unknown", self._field("finding").inner_text())
        self.assertIn("No blocking finding", self._field("finding").inner_text())
        self.assertIn("not project an invalidated-evidence set",
                      self._field("invalidatedEvidence").inner_text())
        self.assertIn("not project a recapture requirement",
                      self._field("recaptureRequirement").inner_text())
        self.assertIn("no copyable agent command",
                      self._field("nextCommand").inner_text())
        progress = self.console.snapshot()["execution"]["progress"]["result"]
        stage_id = progress["latestObservedStage"]
        resume = self._field("resumeStage").inner_text()
        self.assertIn("Unknown", resume)
        self.assertIn("not project an explicit resume stage", resume)
        self.assertNotIn(str(stage_id), resume)
        copy_cmd = self.page.get_by_role(
            "button", name="Copy next Agent command"
        )
        self.assertTrue(copy_cmd.is_disabled())
        self.assertNotIn(_COMMAND, packet.inner_text())

    def test_blocked_run_shows_finding_owner_and_repair_intent(self) -> None:
        self.console.close()
        self.console = browser_harness.ConsoleHarness(
            point_back="point-back-recirculate.md"
        )
        self.addCleanup(self.console.close)
        self.open()
        packet = self._packet().inner_text()
        self.assertIn("Recirculate", self._field("verdict").inner_text())
        self.assertIn("destructive action has no confirmation", packet)
        self.assertIn("add a consequence-confirmation dialog", packet)
        self.assertIn("declaration", self._field("declarationOwner").inner_text())
        self.assertIn("agent", self._field("nextOwner").inner_text())
        self.assertIn("not project an invalidated-evidence set", packet)
        self.assertIn("not project a recapture requirement", packet)
        self.assertNotIn("Pass", self._field("verdict").inner_text())

    def test_stale_and_inconsistent_facts_stay_honest_in_the_packet(self) -> None:
        snapshot = self.console.snapshot()
        snapshot["intent"]["summary"]["availability"] = "stale"
        snapshot["intent"]["summary"]["reason"] = {
            "code": "source-changed-during-build",
            "message": "The specification changed while the snapshot was built.",
            "sourceRefs": ["source.specification"],
            "observedHashes": [], "verifiedHashes": [], "conflicts": [],
        }
        verdict = snapshot["evaluation"]["verdict"]
        verdict["availability"] = "inconsistent"
        verdict["result"] = None
        verdict["reason"] = {
            "code": "conflicting-authorities",
            "message": "Two authorities disagree about the verdict.",
            "sourceRefs": ["source.evaluator-report"],
            "observedHashes": [], "verifiedHashes": [],
            "conflicts": [{
                "sourceRef": "source.evaluator-report",
                "hash": "sha256:" + "a" * 64,
                "summary": "verdict contradicts the findings ledger",
            }],
        }

        def fulfill(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(snapshot),
            )

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        intent = self._field("intent").inner_text()
        self.assertIn("Stale", intent)
        self.assertIn("not be read as current", intent)
        verdict_text = self._field("verdict").inner_text()
        self.assertIn("Inconsistent", verdict_text)
        self.assertNotIn("Pass", verdict_text)

    def test_copy_summary_and_command_are_plaintext_and_do_not_execute(self) -> None:
        self.context.grant_permissions(["clipboard-read", "clipboard-write"])
        snapshot = self.console.snapshot()
        snapshot["nextActions"]["primary"]["result"]["copyableAgentCommand"] = _COMMAND

        def fulfill(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(snapshot),
            )

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        self.page.get_by_role(
            "button", name="Copy packet summary (plain text)"
        ).click()
        expect(self.page.locator("#packet-copy-summary-status")).to_contain_text(
            "plain text"
        )
        summary = self.page.evaluate("() => navigator.clipboard.readText()")
        self.assertIn("Repair Packet", summary)
        self.assertIn("nothing is executed", summary)
        self.assertIn(_COMMAND, summary)
        self.assertIn("unavailable", summary.casefold() + summary)
        self.page.get_by_role(
            "button", name="Copy next Agent command (plain text)"
        ).click()
        clip = self.page.evaluate("() => navigator.clipboard.readText()")
        self.assertEqual(clip, _COMMAND)
        self.assertEqual(self.dialogs, [])

    def test_packet_keeps_source_locator_and_path_free_boundary(self) -> None:
        self.open()
        packet = self._packet().inner_text()
        self.assertNotIn("src_", packet)
        snapshot = self.console.snapshot()
        for item in snapshot["sources"]["items"]:
            locator = item.get("locator")
            if locator:
                self.assertNotIn(locator, packet)
        self.assertNotIn(str(self.console.run_root), packet)
        requests: list[str] = []

        def record(route):
            requests.append(route.request.url)
            route.continue_()

        self.context.route("**/*", record)
        self.page.get_by_role("button", name="Copy packet summary (plain text)").click()
        self.assertTrue(all(url.startswith(self.console.origin) for url in requests))
        self.assertFalse(any("/api/v1/actions/repair" in url for url in requests))

    def test_hostile_finding_issue_renders_as_text(self) -> None:
        snapshot = self.console.snapshot()
        snapshot["evaluation"]["verdict"]["result"] = "Recirculate"
        snapshot["evaluation"]["findings"] = [deepcopy(
            contract_fixtures._valid_snapshot()["evaluation"]["findings"][0]
        )]
        finding = snapshot["evaluation"]["findings"][0]
        finding["result"]["disposition"] = "blocking"
        finding["result"]["issue"] = "<script>alert(1)</script> destructive"
        finding["result"]["repair"] = "fix the declaration"

        def fulfill(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(snapshot),
            )

        self.page.route("**/api/v1/snapshot", fulfill)
        self.page.goto(self.console.url(f"#token={self.console.token}"))
        expect(self.page.locator("#view-ready")).to_be_visible()
        field = self._field("finding")
        self.assertIn("<script>alert(1)</script>", field.inner_text())
        self.assertEqual(field.locator("script").count(), 0)
        self.assertEqual(self.dialogs, [])

    def test_packet_layout_at_320px_does_not_overflow(self) -> None:
        self.page.set_viewport_size({"width": 320, "height": 720})
        self.open()
        expect(self._packet()).to_be_visible()
        width = self.page.evaluate("() => document.scrollingElement.scrollWidth")
        self.assertLessEqual(width, 320 + 2)
