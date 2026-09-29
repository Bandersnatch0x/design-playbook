#!/usr/bin/env python3
"""A03 (preview half): the isolated preview origin and its browser negatives.

The carrier under test is hostile: a page that tries to read its parent,
call the management API, and reach the internet. The preview origin must
deny all three while still showing the real content, and a static preview
must not run the script at all.
"""
from __future__ import annotations

import unittest
import urllib.error
import urllib.request

from design_playbook_workbench.preview import PREVIEW_PATH_PREFIX

from tests.harness import WorkbenchHarness

MALICIOUS_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>preview</title></head>
<body>
<h1>Carrier</h1>
<script>
  var probe = { parent: "unknown", api: "unknown", net: "unknown" };
  document.documentElement.dataset.ran = "1";
  try { probe.parent = "read:" + parent.document.title; }
  catch (error) { probe.parent = "blocked"; }
  fetch("/api/v1/projects")
    .then(function (response) { probe.api = "status:" + response.status; })
    .catch(function () { probe.api = "blocked"; });
  fetch("https://example.com/collect")
    .then(function () { probe.net = "reached"; })
    .catch(function () { probe.net = "blocked"; });
  window.__probe = probe;
  setTimeout(function () { document.title = JSON.stringify(probe); }, 300);
</script>
</body></html>
"""


class PreviewOriginHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.directory = self.h.make_directory("preview-project")
        (self.directory / "index.html").write_text(MALICIOUS_PAGE, encoding="utf-8")
        (self.directory / "notes.md").write_text("# Notes\n", encoding="utf-8")
        self.project = self.h.register(self.directory, name="Preview").json["result"]
        self.project_id = self.project["projectId"]
        granted = self.h.grant(self.project_id, ["read", "write"], expected_counter=0)
        assert granted.status == 200, granted.text
        self.page_asset = self.h.import_assets(self.project_id, ["index.html"]).json["result"]["asset"]
        self.notes_asset = self.h.import_assets(self.project_id, ["notes.md"]).json["result"]["asset"]

    def _preview_url(self, asset: dict, mode: str) -> str:
        descriptor = self.h.asset_preview(self.project_id, asset["assetId"]).json
        entry = descriptor["entry"] if "entry" in descriptor else None
        manifest = asset["manifest"][0]
        from design_playbook_workbench.preview import preview_media_type

        base = descriptor["staticUrl" if mode == "static" else "dynamicUrl"]
        assert base, descriptor
        url = base + "?type=" + preview_media_type(manifest["mediaType"])
        assert entry is not None
        return url

    def _raw_get(self, url: str, **headers) -> tuple[int, dict, bytes]:
        request = urllib.request.Request(url, method="GET")
        for name, value in headers.items():
            request.add_header(name.replace("_", "-"), value)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=15) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_static_preview_forbids_scripts_and_any_connection(self) -> None:
        url = self._preview_url(self.page_asset, "static")
        status, headers, body = self._raw_get(url)
        self.assertEqual(status, 200)
        policy = headers["Content-Security-Policy"]
        self.assertIn("script-src 'none'", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("sandbox", policy)
        # Only the management origin may frame a preview.
        self.assertIn(self.h.runtime.origin, policy)
        self.assertIn(b"Carrier", body)
        self.assertNotIn("Set-Cookie", headers)

    def test_the_preview_origin_has_no_management_api(self) -> None:
        for path in (
            "/api/v1/projects",
            "/api/v1/session",
            "/api/v1/resolve?project=x",
            PREVIEW_PATH_PREFIX,
        ):
            with self.subTest(path=path):
                status, _, _ = self._raw_get(self.h.preview_origin + path)
                self.assertEqual(status, 404)
        # Presenting the management session token changes nothing: the
        # preview origin does not authenticate, issue, or accept anything.
        status, headers, _ = self._raw_get(
            self.h.preview_origin + "/api/v1/projects",
            Authorization="Bearer " + self.h.token,
        )
        self.assertEqual(status, 404)
        self.assertNotIn("Set-Cookie", headers)

    def test_unknown_and_corrupt_blobs_are_never_served(self) -> None:
        status, _, body = self._raw_get(
            self.h.preview_origin + PREVIEW_PATH_PREFIX + "sha256:" + "0" * 64 + "/static"
        )
        self.assertEqual(status, 404)
        manifest = self.page_asset["manifest"][0]
        from design_playbook_workbench.blobs import BlobStore

        blobs = BlobStore(self.h.runtime.data_dir.blob_dir)
        blobs.path_for(manifest["contentHash"]).write_bytes(b"tampered")
        status, _, _ = self._raw_get(
            self.h.preview_origin
            + PREVIEW_PATH_PREFIX
            + manifest["contentHash"]
            + "/static"
        )
        self.assertEqual(status, 404)

    def test_descriptor_is_honest_about_what_is_available(self) -> None:
        static_only = self.h.asset_preview(self.project_id, self.notes_asset["assetId"])
        self.assertEqual(static_only.status, 200, static_only.text)
        payload = static_only.json
        self.assertFalse(payload["dynamicAvailable"])
        self.assertIsNone(payload["dynamicUrl"])
        self.assertEqual(payload["sandbox"], "")
        self.assertEqual(payload["policy"]["scripts"], "disabled")
        self.assertEqual(payload["policy"]["network"], "blocked")
        self.assertEqual(payload["policy"]["managementApi"], "blocked")
        self.assertEqual(payload["policy"]["sessionCredential"], "absent")
        self.assertIn("独立回环来源", payload["notes"])

        dynamic = self.h.asset_preview(self.project_id, self.page_asset["assetId"])
        self.assertTrue(dynamic.json["dynamicAvailable"])
        self.assertIsNone(dynamic.json["dynamicUrl"])
        enabled = self.h.asset_action(
            self.project_id, self.page_asset["assetId"], "preview-enable"
        )
        self.assertEqual(enabled.status, 200, enabled.text)
        after = self.h.asset_preview(self.project_id, self.page_asset["assetId"])
        self.assertIsNotNone(after.json["dynamicUrl"])
        self.assertEqual(after.json["sandbox"], "allow-scripts")
        self.assertEqual(after.json["policy"]["scripts"], "enabled")

    def test_dynamic_preview_requires_a_previewable_carrier_and_write_scope(self) -> None:
        missing = self.h.asset_action(
            self.project_id, self.notes_asset["assetId"], "preview-enable"
        )
        self.assertEqual(missing.status, 422)
        self.assertEqual(missing.error_code, "missing-dependency")
        capability = self.h.runtime.session.issue_capability(
            project_id=self.project_id, scopes=["read"]
        )
        denied = self.h.asset_action(
            self.project_id,
            self.page_asset["assetId"],
            "preview-enable",
            capability=capability,
        )
        self.assertEqual(denied.status, 401)

    def test_import_is_maintainer_only_no_capability_may_run_it(self) -> None:
        # Import enumerates and reads maintainer-selected project files into
        # the asset library; it is a maintainer curation action. An Agent
        # capability never holds arbitrary file read or import, regardless of
        # scope (R03/R11) — only the browser session imports.
        for scopes in (["read"], ["write"], ["read", "write"]):
            cap = self.h.runtime.session.issue_capability(
                project_id=self.project_id, scopes=scopes
            )
            denied = self.h.import_assets(
                self.project_id, ["notes.md"], capability=cap
            )
            self.assertEqual(denied.status, 401, f"{scopes}: {denied.text}")
        allowed = self.h.import_assets(self.project_id, ["notes.md"])
        self.assertEqual(allowed.status, 200, allowed.text)


class PreviewBrowserTest(unittest.TestCase):
    # Chromium is launched per class, not at module scope: PreviewOriginHttpTest
    # above is pure urllib and must collect and run in the always-required gate
    # even when Playwright is not installed (same split as the evidence
    # PurePathTests / CaptureTests groups).
    @classmethod
    def setUpClass(cls) -> None:
        from playwright.sync_api import sync_playwright

        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._browser.close()
        cls._playwright.stop()

    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.page = self._browser.new_page()
        self.addCleanup(self.page.close)
        self.directory = self.h.make_directory("hostile")
        (self.directory / "index.html").write_text(MALICIOUS_PAGE, encoding="utf-8")
        self.project = self.h.register(self.directory, name="Hostile").json["result"]
        self.project_id = self.project["projectId"]
        granted = self.h.grant(self.project_id, ["read", "write"], expected_counter=0)
        assert granted.status == 200, granted.text
        self.asset = self.h.import_assets(self.project_id, ["index.html"]).json["result"]["asset"]
        self.h.asset_action(self.project_id, self.asset["assetId"], "preview-enable")
        self.descriptor = self.h.asset_preview(
            self.project_id, self.asset["assetId"]
        ).json

    def _frame_url(self, mode: str) -> str:
        base = (
            self.descriptor["staticUrl"]
            if mode == "static"
            else self.descriptor["dynamicUrl"]
        )
        return base + "?type=text/html"

    def _load_frame(self, mode: str):
        # The management origin is the only allowed frame ancestor, so the
        # frame is created from a page served by that origin.
        self.page.goto(self.h.runtime.bootstrap_url)
        self.page.wait_for_selector("#session-state")
        self.page.evaluate(
            """(url) => {
                const frame = document.createElement('iframe');
                frame.id = 'probe-frame';
                frame.src = url;
                document.body.appendChild(frame);
            }""",
            self._frame_url(mode),
        )
        self.page.wait_for_selector("#probe-frame")
        frame = self.page.frame_locator("#probe-frame")
        return frame

    def _preview_frame(self, mode: str):
        """The loaded preview frame, located by its own origin.

        The frame URL only appears once navigation has committed, so the
        lookup polls instead of assuming an index (the shell also contains
        its own not-yet-used preview iframe).
        """
        self._load_frame(mode)
        deadline = 10.0
        step = 0.1
        waited = 0.0
        while waited < deadline:
            for frame in self.page.frames:
                if frame.url.startswith(self.h.preview_origin):
                    return frame
            self.page.wait_for_timeout(int(step * 1000))
            waited += step
        raise AssertionError("the preview frame did not load")

    def test_static_preview_does_not_execute_the_carrier_script(self) -> None:
        from playwright.sync_api import expect

        handle = self._preview_frame("static")
        frame = self.page.frame_locator("#probe-frame")
        expect(frame.locator("h1")).to_have_text("Carrier")
        # The script is present in the bytes but must never run.
        self.assertIsNone(handle.evaluate("() => window.__probe"))
        self.assertIsNone(
            handle.evaluate("() => document.documentElement.dataset.ran || null")
        )

    def test_dynamic_preview_runs_the_script_but_isolates_the_document(self) -> None:
        from playwright.sync_api import expect

        handle = self._preview_frame("dynamic")
        frame = self.page.frame_locator("#probe-frame")
        expect(frame.locator("h1")).to_have_text("Carrier")
        # The script runs (dynamic preview is explicitly enabled) ...
        handle.wait_for_function(
            "() => document.documentElement.dataset.ran === '1'", timeout=10000
        )
        handle.wait_for_function(
            "() => window.__probe && window.__probe.net !== 'unknown'", timeout=10000
        )
        probe = handle.evaluate("() => window.__probe")
        # ... and every escape attempt is blocked.
        self.assertEqual(probe["parent"], "blocked")
        self.assertEqual(probe["net"], "blocked")
        self.assertIn(probe["api"], ("blocked", "status:404"))

    def test_the_management_origin_still_works_while_preview_is_isolated(self) -> None:
        handle = self._preview_frame("dynamic")
        handle.wait_for_function(
            "() => document.documentElement.dataset.ran === '1'", timeout=10000
        )
        listing = self.page.evaluate(
            "async () => (await fetch('/api/v1/projects')).status"
        )
        self.assertEqual(listing, 401)
        # ... and the token the management page holds never reaches the
        # preview origin.
        frame_origin = self.h.preview_origin
        self.assertNotEqual(frame_origin, self.h.runtime.origin)
        self.assertNotIn("session", self.descriptor)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
