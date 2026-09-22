#!/usr/bin/env python3
"""Diagnostic export transaction at the HTTP boundary (ADR-0044, T-049).

Pins contract spec §4 at the real loopback server: S35 (routes live, prior
409 gate gone, no ad-hoc export route), S36 (source-set or preview-hash
mismatch rejects with zero filesystem effect; an injected mid-commit
failure rolls back to no partial pair), S37 (exactly one JSON/Markdown
pair named from the preview hash, evidence/Manifest/verdict untouched, a
full rebuild follows), the closed-payload rejection matrix, and the
zero-effect discipline on every failure path.
"""
from __future__ import annotations

import http.client
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from tests.run_console import test_http_server as harness  # noqa: E402
from design_playbook.mcp.run_console import (  # noqa: E402
    export_transaction,
)
from design_playbook.mcp.run_console.diagnostic_export import (  # noqa: E402
    canonical_json_bytes,
    preview_hash,
)

PREVIEW_ROUTE = "/api/v1/actions/diagnostic-export/preview"
WRITE_ROUTE = "/api/v1/actions/diagnostic-export/write"

_VALID_PREVIEW = {"schemaVersion": 1, "action": "diagnostic-export-preview"}


def _sha256_digest(hex_part: str) -> str:
    return f"sha256:{hex_part}"


class ExportServerTest(harness._ServerTestCase):
    """Real server, real session, ephemeral port per test."""

    def _post_json(self, path: str, payload: object, **kwargs) -> tuple:
        if kwargs.get("origin") is None:
            kwargs["origin"] = self.server.origin
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("Content-Type", "application/json")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        # The low-level http.client flow does not add Content-Length on its
        # own; the bounded-body policy reads it before any body byte.
        if body is not None:
            headers["Content-Length"] = str(len(body))
        kwargs["headers"] = headers
        return self._api("POST", path, body=body, **kwargs)

    def _assert_error(self, payload: bytes, code: str) -> dict:
        envelope = json.loads(payload)
        self.assertEqual(
            set(envelope), {"schemaVersion", "error"}, envelope
        )
        self.assertEqual(envelope["error"]["code"], code, envelope)
        return envelope

    def _preview(self, **kwargs) -> tuple:
        status, fields, payload = self._post_json(
            PREVIEW_ROUTE, dict(_VALID_PREVIEW), **kwargs
        )
        return status, fields, payload

    def _preview_ok(self) -> dict:
        status, _, payload = self._preview()
        self.assertEqual(status, 200, payload)
        return json.loads(payload)

    def _write_body(self, view: dict, *, reviewed: bool = True) -> dict:
        return {
            "schemaVersion": 1,
            "action": "diagnostic-export-write",
            "expectedSourceSetHash": view["expectedSourceSetHash"],
            "previewHash": view["previewHash"],
            "participantReviewed": reviewed,
        }

    # -- S35 ------------------------------------------------------------

    def test_s35_preview_is_live_and_writes_nothing(self) -> None:
        digest_before = harness._tree_digest(self.run_root)
        view = self._preview_ok()
        self.assertEqual(
            set(view),
            {
                "schemaVersion",
                "action",
                "previewHash",
                "expectedSourceSetHash",
                "json",
                "markdown",
            },
        )
        self.assertEqual(view["action"], "diagnostic-export-preview")
        candidate = view["json"]
        self.assertEqual(
            view["previewHash"], preview_hash(candidate)
        )
        self.assertEqual(
            view["expectedSourceSetHash"],
            self._snapshot_document()["sources"]["sourceSetHash"],
        )
        self.assertIn("# Diagnostic export", view["markdown"])
        self.assertEqual(
            harness._tree_digest(self.run_root), digest_before
        )

    def test_s35_write_is_reachable_but_rejects_an_unreviewed_request(self) -> None:
        view = self._preview_ok()
        status, _, payload = self._post_json(
            WRITE_ROUTE, self._write_body(view, reviewed=False)
        )
        self.assertEqual(status, 400, payload)
        self._assert_error(payload, "ACTION_PAYLOAD_INVALID")
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_s35_ad_hoc_export_routes_stay_404(self) -> None:
        for path in (
            "/api/v1/actions/diagnostic-export",
            "/api/v1/actions/export",
            "/api/v1/actions/trial-export",
            "/api/v1/export",
            "/api/v1/exports",
            "/api/v1/diagnostic-export",
        ):
            with self.subTest(path=path):
                status, _, payload = self._post_json(
                    path, {"schemaVersion": 1, "action": "x"}
                )
                self.assertEqual(status, 404, path)
                self._assert_error(payload, "ROUTE_NOT_FOUND")

    def test_s35_role_attestation_capability_stays_absent(self) -> None:
        from design_playbook.mcp.run_console.actions import capability_names
        self.assertNotIn("role-attestation", capability_names())
        self.assertNotIn("attest-role", capability_names())

    # -- closed payload matrix ------------------------------------------

    def test_preview_payload_rejections(self) -> None:
        cases = [
            ("missing action", {"schemaVersion": 1}),
            ("missing version", {"action": "diagnostic-export-preview"}),
            ("unknown field", dict(_VALID_PREVIEW, force=True)),
            ("wrong action", {"schemaVersion": 1, "action": "refresh"}),
            ("wrong version", {"schemaVersion": 2, "action": "diagnostic-export-preview"}),
            ("bool version", {"schemaVersion": True, "action": "diagnostic-export-preview"}),
            ("non-string ref", dict(_VALID_PREVIEW, participantRef=7)),
            ("empty ref", dict(_VALID_PREVIEW, participantRef="")),
            ("oversized ref", dict(_VALID_PREVIEW, participantRef="P" * 65)),
            ("control ref", dict(_VALID_PREVIEW, participantRef="P\nT")),
        ]
        for label, payload in cases:
            with self.subTest(case=label):
                status, _, response = self._post_json(PREVIEW_ROUTE, payload)
                self.assertEqual(status, 400, (label, response))
                self._assert_error(response, "ACTION_PAYLOAD_INVALID")

    def test_write_payload_rejections(self) -> None:
        view = self._preview_ok()
        good = self._write_body(view)
        cases = [
            ("missing reviewed", {k: v for k, v in good.items() if k != "participantReviewed"}),
            ("reviewed false", dict(good, participantReviewed=False)),
            ("reviewed one", dict(good, participantReviewed=1)),
            ("reviewed string", dict(good, participantReviewed="true")),
            ("missing hash", {k: v for k, v in good.items() if k != "previewHash"}),
            ("missing source hash", {k: v for k, v in good.items() if k != "expectedSourceSetHash"}),
            ("unknown field", dict(good, force=True)),
            ("wrong action", dict(good, action="diagnostic-export-preview")),
            ("plain source hash", dict(good, expectedSourceSetHash=good["expectedSourceSetHash"].split(":", 1)[1])),
            ("bad preview hex", dict(good, previewHash="z" * 64)),
            ("short preview hash", dict(good, previewHash="a" * 63)),
        ]
        for label, payload in cases:
            with self.subTest(case=label):
                status, _, response = self._post_json(WRITE_ROUTE, payload)
                self.assertEqual(status, 400, (label, response))
                self._assert_error(response, "ACTION_PAYLOAD_INVALID")
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_transport_rejections_match_the_action_contract(self) -> None:
        # GET is 405 with Allow: POST on both routes.
        for path in (PREVIEW_ROUTE, WRITE_ROUTE):
            with self.subTest(route=path):
                status, fields, payload = self._api("GET", path)
                self.assertEqual(status, 405)
                self.assertEqual(fields.get("allow"), "POST")
                self._assert_error(payload, "METHOD_NOT_ALLOWED")
        # A query string is rejected (typed actions take no parameters).
        status, _, payload = self._post_json(PREVIEW_ROUTE + "?x=1", dict(_VALID_PREVIEW))
        self.assertEqual(status, 400)
        # A non-JSON content type is 415; a non-JSON body is 400 MALFORMED.
        status, _, payload = self._post_json(
            PREVIEW_ROUTE,
            dict(_VALID_PREVIEW),
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 415)
        status, _, payload = self._post_json(
            PREVIEW_ROUTE, None, headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        self._assert_error(payload, "MALFORMED_JSON")
        # Unauthenticated requests fail before any route logic.
        status, _, payload = self._post_json(
            PREVIEW_ROUTE, dict(_VALID_PREVIEW), token="A" * 43
        )
        self.assertEqual(status, 401)
        self._assert_error(payload, "SESSION_TOKEN_INVALID")

    # -- S36 ------------------------------------------------------------

    def test_s36_source_set_change_between_preview_and_write_rejects(self) -> None:
        view = self._preview_ok()
        # Change the run tree, then refresh so the served snapshot re-binds
        # a new source set; the write's expected hash is now stale.
        point_back = self.run_root / "point-back.md"
        original = point_back.read_text(encoding="utf-8")
        point_back.write_text(original + "\n<!-- changed after preview -->\n", encoding="utf-8")
        status, _, _ = self._post_json(
            "/api/v1/actions/refresh", {"schemaVersion": 1, "action": "refresh"}
        )
        self.assertEqual(status, 200)
        digest_before = harness._tree_digest(self.run_root)
        status, _, payload = self._post_json(WRITE_ROUTE, self._write_body(view))
        self.assertEqual(status, 409, payload)
        self._assert_error(payload, "EXPORT_PREVIEW_MISMATCH")
        self.assertEqual(harness._tree_digest(self.run_root), digest_before)
        self.assertFalse((self.run_root / "trial-export").exists())

    def test_s36_tampered_preview_hash_rejects(self) -> None:
        view = self._preview_ok()
        body = self._write_body(view)
        body["previewHash"] = "a" * 64
        digest_before = harness._tree_digest(self.run_root)
        status, _, payload = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 409, payload)
        self._assert_error(payload, "EXPORT_PREVIEW_MISMATCH")
        self.assertEqual(harness._tree_digest(self.run_root), digest_before)

    def test_s36_mid_commit_failure_rolls_back_to_no_pair(self) -> None:
        view = self._preview_ok()
        body = self._write_body(view)
        digest_before = harness._tree_digest(self.run_root)
        real_replace = export_transaction.os.replace
        calls = {"n": 0}

        def failing_replace(src, dst, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("injected second-rename failure")
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(export_transaction.os, "replace", failing_replace):
            status, _, payload = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 500, payload)
        self._assert_error(payload, "EXPORT_WRITE_FAILED")
        trial = self.run_root / "trial-export"
        if trial.exists():
            leftovers = sorted(p.name for p in trial.rglob("*"))
            self.assertEqual(leftovers, [], leftovers)
        self.assertEqual(
            harness._tree_digest(self.run_root), digest_before,
            "a rolled-back transaction must leave the tree unchanged",
        )

    # -- S37 ------------------------------------------------------------

    def test_s37_write_commits_exactly_one_pair_and_rebuilds(self) -> None:
        view = self._preview_ok()
        evidence_digest = harness._tree_digest(self.run_root / "evidence")
        status, _, payload = self._post_json(WRITE_ROUTE, self._write_body(view))
        self.assertEqual(status, 200, payload)
        response = json.loads(payload)
        self.assertEqual(
            set(response), {"schemaVersion", "action", "written", "snapshot"}
        )
        self.assertEqual(response["action"], "diagnostic-export-write")
        stem = "export-" + view["previewHash"][:12]
        self.assertEqual(
            response["written"],
            [f"trial-export/{stem}.json", f"trial-export/{stem}.md"],
        )
        json_path = self.run_root / "trial-export" / f"{stem}.json"
        md_path = self.run_root / "trial-export" / f"{stem}.md"
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertEqual(
            json_path.read_bytes(), canonical_json_bytes(view["json"])
        )
        self.assertEqual(
            md_path.read_text(encoding="utf-8"), view["markdown"]
        )
        # Evidence, manifest, and verdict facts are untouched.
        self.assertEqual(harness._tree_digest(self.run_root / "evidence"), evidence_digest)
        self.assertEqual(
            response["snapshot"]["evaluation"]["verdict"]["result"],
            self._snapshot_document()["evaluation"]["verdict"]["result"],
        )
        # The write response's snapshot is the now-served document.
        self.assertEqual(
            self._snapshot_document(), response["snapshot"]
        )

    def test_s37_a_second_write_of_the_same_review_fails_closed(self) -> None:
        # The pair itself enters the next snapshot's source set (run-facts /
        # run-status read the run tree), so a repeat write with the old
        # binding is the typed mismatch — and content-addressed names mean
        # repeated exports are new pairs, never overwrites (contract spec
        # §4.3).
        view = self._preview_ok()
        body = self._write_body(view)
        status, _, first = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 200, first)
        status, _, payload = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 409, payload)
        self._assert_error(payload, "EXPORT_PREVIEW_MISMATCH")
        pairs = sorted(p.name for p in (self.run_root / "trial-export").glob("*"))
        self.assertEqual(len(pairs), 2, pairs)

    def test_s37_a_partial_pair_fails_closed(self) -> None:
        # Exactly one member of the pair existing on disk (an interrupted
        # older transaction) fails the write instead of guessing.
        view = self._preview_ok()
        stem = "export-" + view["previewHash"][:12]
        trial = self.run_root / "trial-export"
        trial.mkdir()
        (trial / f"{stem}.json").write_bytes(b"{}")
        status, _, payload = self._post_json(WRITE_ROUTE, self._write_body(view))
        self.assertEqual(status, 500, payload)
        self._assert_error(payload, "EXPORT_WRITE_FAILED")
        self.assertEqual(
            sorted(p.name for p in trial.glob("*")), [f"{stem}.json"]
        )

    def test_s36_a_ticking_clock_never_breaks_the_binding(self) -> None:
        # The candidate is a pure function of (snapshot, participantRef):
        # no clock inside the hashed bytes. A preview taken at time T must
        # still be writable at T+Δ — reviewing plus checking the consent
        # box takes a human more than one second, so a clock-sensitive
        # binding would make the shipped flow never succeed.
        minutes = {"n": 0}

        def ticking() -> str:
            value = f"2026-08-25T10:{minutes['n']:02d}:00Z"
            minutes["n"] += 1
            return value

        session = harness.RunConsoleSession(
            run_root=self.run_root, package_root=harness._PKG_ROOT, now_fn=ticking
        )
        server = harness.serve_run_console(
            session, bind_host=self.bind_host, port=0
        )
        self.addCleanup(server.stop)
        conn = http.client.HTTPConnection(server.bind_host, server.port, timeout=10)
        try:
            def call(method, path, body):
                conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
                conn.putheader("Host", server.authority)
                conn.putheader("Origin", server.origin)
                conn.putheader("Authorization", f"Bearer {session.token}")
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(body)))
                conn.endheaders(body)
                response = conn.getresponse()
                return response.status, response.read()

            preview_body = json.dumps(_VALID_PREVIEW).encode("utf-8")
            status, payload = call("POST", PREVIEW_ROUTE, preview_body)
            self.assertEqual(status, 200, payload)
            view = json.loads(payload)
            write_body = json.dumps(self._write_body(view)).encode("utf-8")
            # No clock call belongs to the candidate path: the write
            # re-derives the identical pair no matter how long the review
            # took (the old generatedAt-in-hash shape failed exactly here).
            status, payload = call("POST", WRITE_ROUTE, write_body)
            self.assertEqual(status, 200, payload)
            self.assertEqual(len(json.loads(payload)["written"]), 2)
        finally:
            conn.close()

    def test_s36_a_staging_failure_leaves_no_temp_and_no_pair(self) -> None:
        # An OSError from the staged write is the typed atomic failure
        # (contract spec §4.3): no partial pair AND no stray .staged file.
        view = self._preview_ok()
        body = self._write_body(view)
        digest_before = harness._tree_digest(self.run_root)

        def failing_write(self, data):
            raise OSError("injected staging failure")

        with mock.patch.object(Path, "write_bytes", failing_write):
            status, _, payload = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 500, payload)
        self._assert_error(payload, "EXPORT_WRITE_FAILED")
        trial = self.run_root / "trial-export"
        if trial.exists():
            leftovers = sorted(p.name for p in trial.rglob("*"))
            self.assertEqual(leftovers, [], leftovers)
        self.assertEqual(harness._tree_digest(self.run_root), digest_before)

    def test_s37_participant_ref_is_echoed_into_the_pair(self) -> None:
        preview = dict(_VALID_PREVIEW, participantRef="P-E2E-1")
        status, _, payload = self._post_json(PREVIEW_ROUTE, preview)
        self.assertEqual(status, 200, payload)
        view = json.loads(payload)
        self.assertEqual(view["json"]["participantRef"], "P-E2E-1")
        self.assertIn("P-E2E-1", view["markdown"])
        status, _, payload = self._post_json(
            WRITE_ROUTE, dict(self._write_body(view), participantRef="P-E2E-1")
        )
        self.assertEqual(status, 200, payload)
        stem = "export-" + view["previewHash"][:12]
        written = json.loads(
            (self.run_root / "trial-export" / f"{stem}.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(written["participantRef"], "P-E2E-1")
        # The product never persists the ref anywhere else.
        marker = b"P-E2E-1"
        for path in self.run_root.rglob("*"):
            if path.is_file() and "trial-export" not in path.parts:
                self.assertNotIn(marker, path.read_bytes(), path)

    def test_failure_paths_leave_zero_partial_effects(self) -> None:
        digest_before = harness._tree_digest(self.run_root)
        rejections = [
            (PREVIEW_ROUTE, {"schemaVersion": 1}),
            (PREVIEW_ROUTE, {"schemaVersion": 1, "action": "nope"}),
            (WRITE_ROUTE, {"schemaVersion": 1, "action": "diagnostic-export-write"}),
        ]
        for path, payload in rejections:
            with self.subTest(path=path, payload=json.dumps(payload)):
                status, _, response = self._post_json(path, payload)
                self.assertEqual(status, 400, response)
        # A write bound to a wrong source hash is a 409 with zero effect.
        body = {
            "schemaVersion": 1,
            "action": "diagnostic-export-write",
            "expectedSourceSetHash": _sha256_digest("c" * 64),
            "previewHash": "d" * 64,
            "participantReviewed": True,
        }
        status, _, response = self._post_json(WRITE_ROUTE, body)
        self.assertEqual(status, 409, response)
        self._assert_error(response, "EXPORT_PREVIEW_MISMATCH")
        self.assertEqual(harness._tree_digest(self.run_root), digest_before)


if __name__ == "__main__":
    unittest.main()
