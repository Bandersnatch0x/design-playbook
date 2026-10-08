"""Real HTTP/source host loop. Candidate input is labeled, not model-generated.

No LLM, network service, or plugin source writer is simulated. The standalone
host applier is a real subprocess and requires a diff-bound stdin confirmation.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from .conftest import expand_inspector_section
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[2]
FIXTURE = PACKAGE / "tests" / "fixtures" / "visual-edit-host"
for directory in (PACKAGE, PACKAGE / "tests", FIXTURE):
    sys.path.insert(0, str(directory))

from playwright.sync_api import expect, sync_playwright  # noqa: E402
from preview_e2e_helpers import dismiss_onboarding  # noqa: E402
from host import create_server, source_hash  # noqa: E402
from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.live_route import observe_visual_source  # noqa: E402
from design_playbook.mcp.preview.transaction import run_preview_transaction  # noqa: E402
from design_playbook.mcp.preview.visual_batch import VisualBatchError, validate_batch_current  # noqa: E402
from design_playbook.mcp.preview.visual_handoff import VisualHandoffError, build_agent_handoff  # noqa: E402

EDITS = [("#queue-title", "background-color", "rgb(221, 238, 226)"),
         ("#next-read", "padding", "24px")]


class LiveReviewBrowser:
    """Synchronous real-browser adapter; the plugin HTTP server runs its own thread."""
    def __init__(self, route: str, *, stale_batch: dict | None = None):
        self.route = route
        self.stale_batch = stale_batch
        self.observed: dict = {}

    def open(self, url: str) -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(10000)
                requests = []
                page.on("request", lambda request: requests.append(request.url))
                page.goto(url, wait_until="networkidle")
                dismiss_onboarding(page)
                iframe = page.locator("iframe.dpb-proto-frame")
                assert iframe.get_attribute("src") == self.route
                assert iframe.get_attribute("srcdoc") is None
                assert iframe.get_attribute("sandbox") == "allow-scripts"
                frame = page.frame_locator("iframe.dpb-proto-frame")
                assert frame.locator("#queue-title").inner_text() == "Reading queue"
                assert self.route + "styles.css" in requests
                assert all(item.startswith("http://127.0.0.1:") for item in requests), requests
                self.observed["requests"] = requests
                self.observed["iframe"] = {"src": self.route, "srcdoc": False,
                                          "sandbox": "allow-scripts"}
                assert frame.locator("body").evaluate("""() => {
                  try { return parent.document.body.tagName; }
                  catch (error) { return error.name; }
                }""") == "SecurityError"
                # A script in the child cannot pose as the parent bridge driver.
                frame.locator("body").evaluate("""() => window.postMessage({dpbVisualEdit: {
                  type: 'set-style', selector: '#queue-title', property: 'color', value: 'red'
                }}, '*')""")
                page.wait_for_timeout(100)
                assert frame.locator("#queue-title").evaluate("el => el.style.color") == ""
                token = page.locator('[name="dpb_token"]').input_value()
                assert len(token) >= 32
                # Missing-token request must not end/confirm the session.
                page.request.post(url + "decide", form={"choice": "Confirm", "dpb_round": "1"})
                if self.stale_batch is None:
                    page.locator("#dpb-tab-visual").click()
                    for index, (selector, property_name, value) in enumerate(EDITS, 1):
                        frame.locator(selector).click(position={"x": 5, "y": 5})
                        expect(page.locator(".dpb-react-selection")).to_have_text(selector)
                        expand_inspector_section(page, property_name)
                        field = page.locator(
                            f'.dpb-react-field[data-property="{property_name}"] input')
                        field.fill(value)
                        page.wait_for_function("""count => {
                          const batch = JSON.parse(document.querySelector('#dpb-visual-edits-json').value);
                          return batch.edits.length === count;
                        }""", arg=index)
                        assert frame.locator(selector).evaluate(
                            "(el, key) => el.style.getPropertyValue(key)", property_name) == value
                    self.observed["batch"] = json.loads(page.locator("#dpb-visual-edits-json").input_value())
                else:
                    for selector, property_name, value in EDITS:
                        assert frame.locator(selector).evaluate(
                            "(el, key) => getComputedStyle(el).getPropertyValue(key)", property_name) == value
                    self.observed["refreshedHash"] = page.evaluate("window.DPB_VISUAL_EDIT_BATCH.sourceHash")
                    page.locator("#dpb-visual-edits-json").evaluate(
                        "(el, batch) => { el.value = JSON.stringify(batch); }", self.stale_batch)
                fields = page.locator("#dpb-decide-form").evaluate(
                    "el => Object.fromEntries(new FormData(el))")
                page.locator("#dpb-feedback").fill("Host candidate requires separate source-diff confirmation.")
                with page.expect_response(lambda response: response.url.endswith("/decide")):
                    page.locator("#dpb-btn-approve").click()
                page.wait_for_load_state("domcontentloaded")
                self.observed["response"] = page.locator("body").inner_text()
                # First-decision-wins: an abort replay with the consumed token
                # cannot overwrite the decision just made in the actual UI.
                fields.update({"choice": "__abort__", "dpb_token": token})
                page.request.post(url + "decide", form=fields)
                self.observed["g5"] = "parent-only; opaque sandbox; missing token rejected; replay cannot overwrite"
            finally:
                browser.close()

    def close(self, _handle: object) -> None:
        pass  # Browser lifetime is wholly inside open(), including failures.


def stage_review(root: Path, preview: Path, route: str, *, stale_batch: dict | None = None) -> tuple[dict, dict]:
    preview.mkdir(parents=True)
    prototype = preview / "index.html"
    shutil.copyfile(root / "index.html", prototype)
    # The detached artifact must observe the same HOST declaration as the applier.
    if (root / "assets.json").exists():
        (preview / "visual-source.json").write_text(json.dumps({
            "sourceRoot": str(root.resolve()), "assetMap": "assets.json",
        }), encoding="utf-8")
    adapter = LiveReviewBrowser(route, stale_batch=stale_batch)
    source_before = {name: (root / name).read_bytes() for name in ("index.html", "styles.css")}
    audit = {"active": True, "sourceWrites": []}

    def protect_source(event, args):
        if not audit["active"]:
            return
        paths = []
        if event == "open" and isinstance(args[0], (str, bytes)) and args[2] & (os.O_WRONLY | os.O_RDWR):
            paths = [args[0]]
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename"):
            paths = args[:2] if event == "os.rename" else args[:1]
        for raw in paths:
            path = Path(os.fsdecode(raw)).resolve()
            if path.is_relative_to(root.resolve()):
                audit["sourceWrites"].append(str(path))
                raise AssertionError(f"Plugin attempted a host source write: {event} {path}")

    sys.addaudithook(protect_source)
    try:
        with patch.dict(os.environ, {"DESIGN_PLAYBOOK_PREVIEW_LEDGER_DIR": str(preview / "ledger")}):
            result = run_preview_transaction(
                path_arg=str(prototype), html=None, summary="Real local reading queue host",
                round_n=1, report_ref="host-review.md", options=["Confirm", "Revise"],
                live_route_url=route,
                collect=lambda *args, **kwargs: review_session.collect_review(
                    *args, browser_adapter=adapter, **kwargs),
            )
    finally:
        audit["active"] = False
    assert audit["sourceWrites"] == []
    assert source_before == {name: (root / name).read_bytes() for name in source_before}
    adapter.observed["pluginSourceWrites"] = audit["sourceWrites"]
    adapter.observed["pluginArtifacts"] = sorted(
        str(path.relative_to(preview)) for path in preview.rglob("*") if path.is_file())
    return result, adapter.observed


def host_cli(action: str, root: Path, handoff: Path, candidate: Path, route: str,
             confirmation: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(FIXTURE / "applier.py"), action,
         "--root", str(root), "--handoff", str(handoff), "--candidate", str(candidate),
         "--route-url", route], input=confirmation, text=True, encoding="utf-8",
        capture_output=True, timeout=20, check=False,
    )


class VisualEditHostEndToEndTests(unittest.TestCase):
    def test_real_http_host_candidate_diff_confirm_write_refresh_and_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "host-source"
            root.mkdir()
            for name in ("index.html", "styles.css"):
                shutil.copyfile(FIXTURE / name, root / name)
            host = create_server(root)
            thread = threading.Thread(target=host.serve_forever, daemon=True)
            thread.start()
            route = f"http://127.0.0.1:{host.server_port}/"
            try:
                before = {name: (root / name).read_bytes() for name in ("index.html", "styles.css")}
                before_hash = source_hash(root)
                result, observation = stage_review(root, workspace / "preview", route)
                self.assertTrue(result["confirmed"])
                self.assertFalse(result["aborted"])
                handoff = Path(result["confirm_record_path"])
                record_bytes = handoff.read_bytes()
                record = json.loads(record_bytes)
                batch = record["visual_edits"]
                self.assertEqual(record["visual_handoff"], result["visual_handoff"])
                self.assertEqual(record["visual_handoff"]["status"], "pending-review")
                self.assertFalse(record["visual_handoff"]["writesSource"])
                self.assertTrue(record["visual_handoff"]["requiresUserConfirmation"])
                self.assertEqual(len(batch["edits"]), 2)
                self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
                print("BROWSER " + json.dumps(observation))
                # Explicit deterministic AGENT-CANDIDATE INPUT. Neither the
                # plugin nor this test claims to call a model or map source.
                candidate = workspace / "agent-candidate.css"
                candidate.write_bytes(before["styles.css"] + b"\n#queue-title { background-color: rgb(221, 238, 226); }\n#next-read { padding: 24px; }\n")
                reviewed = host_cli("review", root, handoff, candidate, route)
                self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
                proposal = json.loads(reviewed.stdout)
                self.assertEqual(proposal["sourceHash"], batch["sourceHash"])
                self.assertEqual(proposal["batchHash"], batch["batchHash"])
                self.assertEqual(proposal["routeUrl"], route)
                self.assertEqual(proposal["edits"], batch["edits"])
                self.assertIn("+++ b/styles.css", proposal["diff"])
                print("AGENT-CANDIDATE INPUT: deterministic CSS; no model invocation")
                print(proposal["diff"], end="")
                for confirmation in ("", "yes\n", "APPLY wrong-hash\n"):
                    refused = host_cli("apply", root, handoff, candidate, route, confirmation)
                    self.assertEqual(refused.returncode, 2, refused.stdout)
                    self.assertIn("explicit hash-bound host confirmation required", refused.stderr)
                    self.assertEqual(before, {name: (root / name).read_bytes() for name in before})
                print("UNCONFIRMED " + refused.stderr.strip())
                # An old confirmation cannot authorize a modified candidate.
                candidate_bytes = candidate.read_bytes()
                candidate.write_bytes(candidate_bytes + b"/* changed after diff review */\n")
                refused = host_cli("apply", root, handoff, candidate, route, proposal["confirmation"] + "\n")
                self.assertEqual(refused.returncode, 2)
                self.assertEqual(source_hash(root), before_hash)
                candidate.write_bytes(candidate_bytes)
                # Handoff edits cannot be swapped independently of batchHash.
                tampered = workspace / "tampered.json"
                bad_record = json.loads(record_bytes)
                bad_record["visual_handoff"]["edits"][0]["newValue"] = "red"
                tampered.write_text(json.dumps(bad_record), encoding="utf-8")
                refused = host_cli("review", root, tampered, candidate, route)
                self.assertEqual(refused.returncode, 2)
                self.assertIn("handoff does not match", refused.stderr)
                self.assertEqual(source_hash(root), before_hash)
                applied = host_cli("apply", root, handoff, candidate, route, proposal["confirmation"] + "\n")
                self.assertEqual(applied.returncode, 0, applied.stderr)
                receipt = json.loads(applied.stdout.splitlines()[-1])
                self.assertEqual((root / "styles.css").read_bytes(), candidate_bytes)
                self.assertEqual((root / "index.html").read_bytes(), before["index.html"])
                self.assertNotEqual(source_hash(root), before_hash)
                self.assertEqual(receipt["beforeSourceHash"], batch["sourceHash"])
                self.assertNotEqual(receipt["beforeSourceHash"], receipt["afterSourceHash"])
                self.assertNotEqual(receipt["beforeStylesHash"], receipt["afterStylesHash"])
                print("CONFIRMED " + proposal["confirmation"])
                print("HOST-WRITE " + json.dumps(receipt))
                current = observe_visual_source(root / "index.html", route)
                with self.assertRaisesRegex(VisualBatchError, "stale"):
                    validate_batch_current(batch, current, current_route_url=route)
                with self.assertRaisesRegex(VisualHandoffError, "stale"):
                    build_agent_handoff(batch, current_source_hash=current, route_url=route)
                replay = host_cli("apply", root, handoff, candidate, route, proposal["confirmation"] + "\n")
                self.assertEqual(replay.returncode, 2)
                self.assertIn("stale", replay.stderr)
                # Fresh real iframe loads the applied CSS, then its real /decide
                # handler receives the OLD batch and visibly rejects it.
                refreshed, fresh_observation = stage_review(root, workspace / "refreshed-preview", route, stale_batch=batch)
                self.assertEqual(fresh_observation["refreshedHash"], current)
                self.assertIn("stale", fresh_observation["response"])
                self.assertIn("stale", refreshed["visual_edits_error"])
                self.assertNotIn("visual_handoff", refreshed)
                self.assertEqual((root / "styles.css").read_bytes(), candidate_bytes)
                self.assertEqual(handoff.read_bytes(), record_bytes)
                print("REFRESH old batch rejected: " + refreshed["visual_edits_error"])
                print("BOUNDARY pluginSourceWrites=[]; source unchanged until host confirmation; old handoff remains pending")
            finally:
                host.shutdown()
                host.server_close()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
