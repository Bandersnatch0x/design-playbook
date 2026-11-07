#!/usr/bin/env python3
"""Evidence MCP transport and capture-runtime interface tests.

``EvidencePurePathTests`` covers the narrow JSON-RPC wire/schema mapping and
path validation that short-circuits before Playwright. ``EvidenceRuntimeTests``
exercises the public runtime interface with a fake browser adapter.
``EvidenceCaptureTests`` exercises that same interface with the production
Playwright adapter for screenshot, a11y, and trace captures.
"""
from __future__ import annotations

import pytest

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
# The MCP runtime stays at mcp/evidence/; the suite lives under tests/evidence/.
_COMPONENT_DIR = _PKG_ROOT / "mcp" / "evidence"

from design_playbook.mcp.evidence import capture_runtime  # noqa: E402
from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    DESIGN_AXES,
)
from design_playbook.mcp.evidence.page_defects import (  # noqa: E402
    probe_render_tokens,
)

SERVER = _COMPONENT_DIR / "server.py"
FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>evidence-fixture</title></head>
<body data-state="error">
  <h1 id="title">Export jobs</h1>
  <button id="submit" type="button">Retry</button>
  <p id="msg" class="error" hidden>failed</p>
  <script>
    document.getElementById("submit").addEventListener("click", () => {
      document.getElementById("msg").hidden = false;
      document.body.dataset.state = "error";
    });
  </script>
</body>
</html>
"""


def _run_stdio(
    requests: list[dict],
    timeout: float = 30,
    *,
    cwd: Path | None = None,
    no_site: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    wire_input = "".join(
        json.dumps(request, ensure_ascii=False) + "\n" for request in requests
    )
    command = [sys.executable]
    if no_site:
        command.append("-S")
    command.append(str(SERVER))
    return subprocess.run(
        command,
        input=wire_input,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
        env=env,
    )


def _run_wire(wire_input: bytes, timeout: float = 5) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(SERVER)],
        input=wire_input,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _responses(completed: subprocess.CompletedProcess[str]) -> list[dict]:
    return [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    ]




def _v1_capture_args(**overrides):
    """Minimal capture-contract v1 payload for process-boundary tests."""
    args = {
        "schemaVersion": 1,
        "url": "about:blank",
        "type": "screenshot",
        "state": "ok",
        "actions": [],
        "artifact_path": "evidence/x.png",
        "viewport": {
            "width": 390,
            "height": 844,
            "devicePixelRatio": 2.0,
            "colorScheme": "light",
        },
    }
    args.update(overrides)
    return args

def _structured(call_response: dict) -> dict:
    result = call_response["result"]
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = result["content"][0]["text"]
    return json.loads(text)


class _RecordingPage:
    def __init__(self) -> None:
        self.waits: list[tuple[str, int]] = []

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.waits.append((selector, timeout))


class EvidencePurePathTests(unittest.TestCase):
    """No-chromium transport and direct runtime-interface tests."""

    def test_wait_for_state_combines_selector_and_state(self) -> None:
        page = _RecordingPage()
        capture_runtime._action_wait_for_state(
            page,
            {"do": "wait_for_state", "selector": "body", "state": "ready"},
            0,
            "wait_for_state",
        )
        self.assertEqual(page.waits, [('body[data-state="ready"]', 10_000)])

    def test_wait_for_state_without_selector_targets_any_matching_state(self) -> None:
        page = _RecordingPage()
        capture_runtime._action_wait_for_state(
            page,
            {"do": "wait_for_state", "state": "ready"},
            0,
            "wait_for_state",
        )
        self.assertEqual(page.waits, [('[data-state="ready"]', 10_000)])

    def test_parse_capture_contract_requires_schema_and_viewport(self) -> None:
        from design_playbook.mcp.evidence import capture_contract

        with self.assertRaises(ValueError) as missing:
            capture_contract.parse_capture_contract({"url": "about:blank"})
        self.assertIn("schemaVersion is required", str(missing.exception))
        self.assertIn("recapture", str(missing.exception).lower())

        with self.assertRaises(ValueError) as unknown:
            capture_contract.parse_capture_contract({
                "schemaVersion": 99,
                "viewport": {
                    "width": 1,
                    "height": 1,
                    "devicePixelRatio": 1,
                    "colorScheme": "light",
                },
            })
        self.assertIn("unsupported capture schemaVersion", str(unknown.exception))

        parsed = capture_contract.parse_capture_contract({
            "schemaVersion": 1,
            "viewport": {
                "width": 390,
                "height": 844,
                "devicePixelRatio": 2,
                "colorScheme": "dark",
            },
        })
        self.assertEqual(parsed["schemaVersion"], 1)
        self.assertEqual(parsed["viewport"]["colorScheme"], "dark")
        self.assertTrue(parsed["freeze"]["enabled"])
        self.assertFalse(parsed["freeze"]["networkIdle"])

    def test_missing_schema_version_maps_to_failed_stdio_payload(self) -> None:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "execute_capture_plan",
                    "arguments": {
                        "url": "about:blank",
                        "type": "screenshot",
                        "state": "ok",
                        "actions": [],
                        "artifact_path": "evidence/x.png",
                    },
                },
            },
        ]
        completed = _run_stdio(requests, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = _structured(_responses(completed)[1])
        self.assertEqual(payload["result"], "failed")
        self.assertIn("schemaVersion", payload["error"])
        self.assertIn("recapture", payload["error"].lower())

    def test_tools_list_exposes_execute_capture_plan(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        completed = _run_stdio(requests, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = _responses(completed)
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"],
            "design-playbook-evidence",
        )
        tools = responses[1]["result"]["tools"]
        self.assertEqual([tool["name"] for tool in tools], ["execute_capture_plan"])
        schema = tools[0]["inputSchema"]
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertIn("viewport", schema["required"])
        self.assertIn("freeze", schema["properties"])
        # DEF-4: the dev-mode run-root escape hatch must be discoverable.
        self.assertIn("run_root", schema["properties"])
        # T-155: the optional declared-design binding is advertised (composed
        # from the contract fragment, not hand-written here).
        self.assertEqual(
            set(schema["properties"]["design"]["properties"]),
            set(DESIGN_AXES),
        )
        self.assertNotIn("design", schema["required"])

    def test_declared_output_schema_matches_a_real_payload(self) -> None:
        # T-145: the advertised outputSchema must describe what the runtime
        # actually returns, not a hand-written approximation.
        from design_playbook.mcp._schema import violations
        from design_playbook.mcp.evidence import server as evidence_server

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan.md").write_text("# plan", encoding="utf-8")
            with mock.patch.object(
                capture_runtime, "_run_root", return_value=Path(tmp)
            ):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(artifact_path="evidence/ok.png"),
                    _FakeBrowserAdapter(),
                )

        output_schema = evidence_server._tool_schema()["outputSchema"]
        self.assertEqual(violations(payload, output_schema), [])

        # The failure payload shares the same five required keys.
        failed = capture_runtime.execute_capture_plan(
            _v1_capture_args(schemaVersion=2), _FakeBrowserAdapter()
        )
        self.assertEqual(violations(failed, output_schema), [])

    def test_runtime_rejects_unknown_fields(self) -> None:
        for forbidden in ("criterion", "criterion_ref", "criterion_id", "unexpected"):
            with self.subTest(forbidden=forbidden), self.assertRaisesRegex(
                ValueError, forbidden
            ):
                capture_runtime.execute_capture_plan(
                    _v1_capture_args(**{forbidden: "L6.3"}),
                    _FakeBrowserAdapter(),
                )

    def test_runtime_rejects_manifest_variants_and_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / f"{root.name}-outside.png"
            cases = [
                "evidence/manifest.jsonl",
                "evidence/Manifest.JSONL",
                "../" + outside.name,
                str(outside.resolve()),
            ]
            for artifact_path in cases:
                with self.subTest(artifact_path=artifact_path), mock.patch.object(
                    capture_runtime, "_run_root", return_value=root
                ):
                    payload = capture_runtime.execute_capture_plan(
                        _v1_capture_args(artifact_path=artifact_path),
                        _FakeBrowserAdapter(),
                    )
                self.assertEqual(payload["result"], "failed")
                self.assertEqual(payload["observed_state"], "unknown")
            self.assertFalse(outside.exists())

    def test_runtime_run_root_warning_respects_marker_and_warns_once(self) -> None:
        import contextlib
        import io

        args = _v1_capture_args(artifact_path="spec.md")
        env = {key: value for key, value in os.environ.items()
               if key != capture_runtime.RUN_ROOT_ENV}
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp)
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                capture_runtime.Path, "cwd", return_value=bare.resolve()
            ), mock.patch.object(
                capture_runtime, "_warned_run_root", False
            ), contextlib.redirect_stderr(stderr):
                capture_runtime.execute_capture_plan(args, _FakeBrowserAdapter())
                capture_runtime.execute_capture_plan(args, _FakeBrowserAdapter())
            self.assertEqual(
                stderr.getvalue().count("DESIGN_PLAYBOOK_RUN_ROOT is unset or '.'"),
                1,
            )

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "plan.md").write_text("# plan", encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                capture_runtime.Path, "cwd", return_value=run_dir.resolve()
            ), mock.patch.object(
                capture_runtime, "_warned_run_root", False
            ), contextlib.redirect_stderr(stderr):
                capture_runtime.execute_capture_plan(args, _FakeBrowserAdapter())
            self.assertNotIn("DESIGN_PLAYBOOK_RUN_ROOT is unset", stderr.getvalue())

    def test_captured_payload_flags_misrooted_run_root(self) -> None:
        env = {key: value for key, value in os.environ.items()
               if key != capture_runtime.RUN_ROOT_ENV}
        request = {"schemaVersion": 1}
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                capture_runtime.Path, "cwd", return_value=bare.resolve()
            ):
                payload = capture_runtime._captured(
                    "evidence/x.png", "ok", str(bare / "evidence" / "x.png"), request
                )
            self.assertIn("warnings", payload)
            self.assertIn("DESIGN_PLAYBOOK_RUN_ROOT", payload["warnings"][0])

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "plan.md").write_text("# plan", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                capture_runtime.Path, "cwd", return_value=run_dir.resolve()
            ):
                payload = capture_runtime._captured(
                    "evidence/x.png", "ok", str(run_dir / "evidence" / "x.png"), request
                )
            self.assertNotIn("warnings", payload)

    def test_unexpanded_interpolation_token_falls_back_like_unset(self) -> None:
        # ADR-0009: the Claude .mcp.json forwards ${DESIGN_PLAYBOOK_RUN_ROOT:-}.
        # A host that fails to expand it would set the literal token as the
        # value; _run_root() must treat that as unset (cwd fallback) and never
        # resolve a bogus "${...}" directory. A real path is still honored.
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp).resolve()
            literal = "${DESIGN_PLAYBOOK_RUN_ROOT:-}"
            with mock.patch.dict(
                os.environ, {capture_runtime.RUN_ROOT_ENV: literal}
            ), mock.patch.object(capture_runtime.Path, "cwd", return_value=bare):
                self.assertEqual(capture_runtime._run_root(), bare)
                self.assertTrue(capture_runtime._run_root_misrooted())
            with mock.patch.dict(
                os.environ, {capture_runtime.RUN_ROOT_ENV: str(bare)}
            ):
                self.assertEqual(capture_runtime._run_root(), bare)
                self.assertFalse(capture_runtime._run_root_misrooted())

    def test_run_root_argument_redirects_one_capture(self) -> None:
        # DEF-4: a `--plugin-dir` dev host cannot edit DESIGN_PLAYBOOK_RUN_ROOT
        # after the server starts. `run_root` binds the run root for one call so
        # evidence lands inside the run tree; the next call falls back again.
        env = {key: value for key, value in os.environ.items()
               if key != capture_runtime.RUN_ROOT_ENV}
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            run_dir = workspace / ".scratch" / "run-1"
            (run_dir / "evidence").mkdir(parents=True)
            (run_dir / "plan.md").write_text("# plan", encoding="utf-8")
            fake = _FakeBrowserAdapter("ready")
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(
                capture_runtime.Path, "cwd", return_value=workspace
            ):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(run_root=str(run_dir)), fake
                )
                self.assertEqual(payload["result"], "captured", payload)
                self.assertTrue((run_dir / "evidence" / "x.png").is_file())
                self.assertNotIn("warnings", payload)
                stray = capture_runtime.execute_capture_plan(
                    _v1_capture_args(artifact_path="evidence/y.png"), fake
                )
            self.assertEqual(stray["result"], "captured", stray)
            self.assertIn("warnings", stray)
            self.assertIn("run_root", stray["warnings"][0])
            self.assertTrue((workspace / "evidence" / "y.png").is_file())

    def test_run_root_argument_rejects_roots_that_are_not_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            bare = workspace / "not-a-run"
            bare.mkdir()
            cases = [
                ("non-string", 7, "non-empty absolute path string"),
                ("relative path", "evidence", "absolute"),
                ("missing directory", str(workspace / "nope"), "not an existing directory"),
                ("markerless directory", str(bare), "run marker"),
            ]
            for label, value, expected in cases:
                with self.subTest(case=label):
                    payload = capture_runtime.execute_capture_plan(
                        _v1_capture_args(run_root=value), _FakeBrowserAdapter()
                    )
                    self.assertEqual(payload["result"], "failed", payload)
                    self.assertIn(expected, payload["error"])
            self.assertFalse((bare / "evidence").exists())
            self.assertFalse((workspace / "evidence").exists())

    def test_interaction_trace_must_be_named_zip(self) -> None:
        # DEF-6: the adapter writes a Playwright trace ZIP, so a `.json` name
        # promises bytes that never exist (RC run had to sniff the binary).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                bad = capture_runtime.execute_capture_plan(
                    _v1_capture_args(
                        type="interaction trace", artifact_path="evidence/t.json"
                    ),
                    _FakeBrowserAdapter(),
                )
                good = capture_runtime.execute_capture_plan(
                    _v1_capture_args(
                        type="interaction trace",
                        artifact_path="evidence/t.trace.zip",
                    ),
                    _FakeBrowserAdapter(),
                )
            self.assertEqual(bad["result"], "failed", bad)
            self.assertIn(".zip", bad["error"])
            self.assertEqual(good["result"], "captured", good)
            self.assertTrue((root / "evidence" / "t.trace.zip").is_file())
            self.assertFalse((root / "evidence" / "t.json").exists())

    def test_runtime_rejects_non_evidence_subtree_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            cases = ["spec.md", "../spec.md", "evidence/../spec.md", "skills/x"]
            for artifact_path in cases:
                with self.subTest(artifact_path=artifact_path), mock.patch.object(
                    capture_runtime, "_run_root", return_value=root
                ):
                    payload = capture_runtime.execute_capture_plan(
                        _v1_capture_args(artifact_path=artifact_path),
                        _FakeBrowserAdapter(),
                    )
                self.assertEqual(payload["result"], "failed", payload)
                self.assertEqual(payload["observed_state"], "unknown")
            self.assertFalse((root / "spec.md").exists())
            self.assertFalse((root / "skills").exists())

    def test_runtime_refuses_overwrite_without_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "evidence" / "L6.3-error.png"
            artifact.parent.mkdir()
            sentinel = b"pre-existing-by-hand"
            artifact.write_bytes(sentinel)
            fake = _FakeBrowserAdapter()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(
                        url=(root / "page.html").resolve().as_uri(),
                        state="error",
                        artifact_path="evidence/L6.3-error.png",
                    ),
                    fake,
                )
            self.assertEqual(payload["result"], "failed", payload)
            self.assertEqual(payload["observed_state"], "unknown")
            self.assertEqual(artifact.read_bytes(), sentinel)
            self.assertEqual(fake.calls, [])

    def test_malformed_messages_return_parse_error_and_server_continues(self) -> None:
        ping = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode()
        newline = _run_wire(b"{not-json}\n" + ping + b"\n")
        self.assertEqual(newline.returncode, 0, newline.stderr.decode(errors="replace"))
        newline_responses = [json.loads(line) for line in newline.stdout.splitlines()]
        self.assertEqual(newline_responses[0]["error"]["code"], -32700)
        self.assertEqual(newline_responses[1]["id"], 2)

        bad = b"{bad-json}"
        framed = (
            f"Content-Length: {len(bad)}\r\n\r\n".encode()
            + bad
            + f"Content-Length: {len(ping)}\r\n\r\n".encode()
            + ping
        )
        content_length = _run_wire(framed)
        self.assertEqual(
            content_length.returncode,
            0,
            content_length.stderr.decode(errors="replace"),
        )
        raw = content_length.stdout
        bodies = []
        while raw:
            header, raw = raw.split(b"\r\n\r\n", 1)
            length = int(header.split(b":", 1)[1].strip())
            bodies.append(json.loads(raw[:length]))
            raw = raw[length:]
        self.assertEqual(bodies[0]["error"]["code"], -32700)
        self.assertEqual(bodies[1]["id"], 2)

class _FakeBrowserAdapter:
    def __init__(self, observed_state: str = "rendered", error: Exception | None = None):
        self.observed_state = observed_state
        self.error = error
        self.calls: list[dict] = []

    def capture(self, **request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        request["out_path"].parent.mkdir(parents=True, exist_ok=True)
        request["out_path"].write_bytes(b"fake-artifact")
        return self.observed_state


class _FakeProbeAdapter:
    """Probe seam with the real render-token parser and a scripted page.

    Only ``page.evaluate`` is faked: ``probe_render_tokens`` builds the real
    probe JS from whatever declaration the runtime threaded through, so a test
    can read the JS back and see whether the binding arrived.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.probe_js: list[str] = []

    def capture_and_probe(self, **request):
        self.calls.append(request)
        request["out_path"].parent.mkdir(parents=True, exist_ok=True)
        request["out_path"].write_bytes(b"fake-artifact")

        def evaluate(js: str) -> dict:
            self.probe_js.append(js)
            return {"findings": [], "undecidable": [], "distinctFontSizes": [16.0]}

        return {
            "observed_state": "rendered",
            "render_tokens": probe_render_tokens(evaluate, request.get("design")),
        }


class EvidenceRuntimeTests(unittest.TestCase):
    """Capture behavior through the runtime interface and a fake adapter."""

    def test_runtime_writes_through_adapter_and_returns_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _FakeBrowserAdapter("ready")
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(
                        url="file:///fixture.html",
                        actions=[{"do": "click", "selector": "#submit"}],
                    ),
                    fake,
                )

            self.assertEqual(payload["result"], "captured")
            self.assertEqual(payload["observed_state"], "ready")
            self.assertEqual(payload["artifact"], "evidence/x.png")
            self.assertEqual(len(fake.calls), 1)
            self.assertEqual(fake.calls[0]["url"], "file:///fixture.html")
            self.assertEqual(fake.calls[0]["capture_type"], "screenshot")
            self.assertEqual(
                fake.calls[0]["actions"],
                [{"do": "click", "selector": "#submit"}],
            )
            self.assertEqual(
                fake.calls[0]["viewport"],
                payload["request"]["viewport"],
            )

    def test_runtime_adapter_failure_preserves_failed_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = _FakeBrowserAdapter(error=RuntimeError("capture unavailable"))
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(_v1_capture_args(), fake)

            self.assertEqual(payload["result"], "failed")
            self.assertEqual(payload["observed_state"], "unknown")
            self.assertEqual(payload["error"], "capture unavailable")
            self.assertFalse((root / "evidence" / "x.png").exists())

    def test_runtime_refuses_existing_artifact_before_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "evidence" / "x.png"
            artifact.parent.mkdir()
            artifact.write_bytes(b"original")
            fake = _FakeBrowserAdapter()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(_v1_capture_args(), fake)

            self.assertEqual(payload["result"], "failed")
            self.assertIn("artifact already exists", payload["error"])
            self.assertEqual(fake.calls, [])
            self.assertEqual(artifact.read_bytes(), b"original")

    def test_declared_design_reaches_probe_and_sidecar(self) -> None:
        declared = {
            "fontSizes": [14, 16, 20, 24],
            "colors": ["#1a1a1a", "#f5f5f5"],
            "radii": [4, 8, 12, 20],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            fake = _FakeProbeAdapter()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(design=declared), fake
                )

            self.assertEqual(payload["result"], "captured", payload)
            # The declaration travels verbatim, and the manifest-bound
            # snapshot keeps the same value the probe ran against.
            self.assertEqual(payload["request"]["design"], declared)
            self.assertEqual(fake.calls[0]["design"], payload["request"]["design"])
            # The JS the page was asked to evaluate carries the declaration.
            self.assertEqual(len(fake.probe_js), 1)
            self.assertIn('"rgb(26, 26, 26)"', fake.probe_js[0])

            sidecar = json.loads(
                (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sidecar["design"], payload["request"]["design"])
            self.assertEqual(sidecar["renderTokens"]["measurement_status"], "measured")
            self.assertEqual(sidecar["renderTokens"]["measurement_error"], "")
            self.assertEqual(sidecar["renderTokens"]["findings"], [])
            self.assertEqual(sidecar["renderTokens"]["undecidable"], [])
            self.assertEqual(sidecar["renderTokens"]["distinctFontSizes"], [16.0])

    def test_unbound_capture_succeeds_with_every_axis_undecidable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            fake = _FakeProbeAdapter()
            with mock.patch.object(capture_runtime, "_run_root", return_value=root):
                payload = capture_runtime.execute_capture_plan(
                    _v1_capture_args(), fake
                )

            # No binding is not a failure: the screenshot still lands.
            self.assertEqual(payload["result"], "captured", payload)
            self.assertNotIn("design", payload["request"])
            self.assertNotIn("design", fake.calls[0])
            sidecar = json.loads(
                (root / "evidence" / "x.probe.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("design", sidecar)
            self.assertEqual(sidecar["renderTokens"]["measurement_status"], "measured")
            # Measured, but every axis says why it could not be judged.
            self.assertEqual(sidecar["renderTokens"]["findings"], [])
            self.assertEqual(
                [note["axis"] for note in sidecar["renderTokens"]["undecidable"]],
                ["font-size", "radius", "color"],
            )

    def test_malformed_design_is_rejected_before_the_browser(self) -> None:
        cases = (
            (None, "design must be an object"),
            ({"fontSizes": 16}, "design.fontSizes must be an array of literals"),
            ({"colors": {"text": "#000"}}, "design.colors must be an array"),
            ({"spacing": [8]}, "design.spacing is not a declared token axis"),
        )
        for design, expected in cases:
            with self.subTest(design=design):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "evidence").mkdir()
                    fake = _FakeProbeAdapter()
                    with mock.patch.object(
                        capture_runtime, "_run_root", return_value=root
                    ):
                        payload = capture_runtime.execute_capture_plan(
                            _v1_capture_args(design=design), fake
                        )

                    self.assertEqual(payload["result"], "failed")
                    self.assertIn(expected, payload["error"])
                    self.assertEqual(fake.calls, [])
                    self.assertFalse((root / "evidence" / "x.png").exists())
                    self.assertFalse((root / "evidence" / "x.probe.json").exists())


# This module drives a real browser: the no-chromium CI job deselects it by marker.
@pytest.mark.browser
class EvidenceCaptureTests(unittest.TestCase):
    """Production Playwright adapter integration; requires chromium."""

    @staticmethod
    def _capture(root: Path, arguments: dict) -> dict:
        """Exercise the production runtime with its real browser adapter."""
        with mock.patch.object(capture_runtime, "_run_root", return_value=root):
            return capture_runtime.execute_capture_plan(
                arguments,
                capture_runtime.PlaywrightBrowserAdapter(),
            )

    def test_screenshot_sidecar_recalls_planted_defects(self) -> None:
        planted = _COMPONENT_DIR / "fixtures" / "planted-defects.html"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=planted.resolve().as_uri(),
                    state="ok",
                    artifact_path="evidence/planted.png",
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            sidecar_path = root / "evidence" / "planted.probe.json"
            self.assertTrue(sidecar_path.is_file(), payload)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertGreater(sidecar["layout"]["hOverflow"], 0)
            self.assertEqual(sidecar["layout"]["measurement_status"], "measured")
            self.assertEqual(sidecar["defects"]["measurement_status"], "measured")
            self.assertEqual(sidecar["console"]["measurement_status"], "measured")
            kinds = {row["kind"] for row in sidecar["leaks"]}
            self.assertEqual(
                kinds,
                {"undefined", "NaN", "[object Object]", "lorem ipsum"},
            )
            self.assertFalse(
                any(row["kind"] == "NaN" and "banana" in row["text"]
                    for row in sidecar["leaks"])
            )
            self.assertTrue(sidecar["tapFails"])
            self.assertTrue(
                any("planted-console" in err for err in sidecar["consoleErrors"]),
                sidecar["consoleErrors"],
            )
            self.assertEqual(sidecar["layout"]["measurement_error"], "")
            self.assertEqual(sidecar["defects"]["measurement_error"], "")
            self.assertEqual(sidecar["console"]["measurement_error"], "")
            self.assertEqual(
                set(sidecar["defects"]),
                {"measurement_status", "measurement_error"},
            )
            self.assertEqual(
                set(sidecar["console"]),
                {"measurement_status", "measurement_error"},
            )

    def test_screenshot_sidecar_clean_page_is_measured_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "clean.html"
            html.write_text(
                "<!doctype html><html><body data-state='ok'><p>ok</p></body></html>",
                encoding="utf-8",
            )
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=html.resolve().as_uri(),
                    state="ok",
                    artifact_path="evidence/clean.png",
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            sidecar = json.loads(
                (root / "evidence" / "clean.probe.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sidecar["layout"]["measurement_status"], "measured")
            self.assertEqual(sidecar["defects"]["measurement_status"], "measured")
            self.assertEqual(sidecar["defects"]["measurement_error"], "")
            self.assertEqual(sidecar["leaks"], [])
            self.assertEqual(sidecar["tapFails"], [])
            self.assertEqual(sidecar["console"]["measurement_status"], "measured")
            self.assertEqual(sidecar["layout"]["measurement_error"], "")
            self.assertEqual(sidecar["console"]["measurement_error"], "")

    def test_screenshot_sidecar_legal_undefined_is_candidate_not_failure(self) -> None:
        page = _COMPONENT_DIR / "fixtures" / "legal-undefined.html"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=page.resolve().as_uri(),
                    state="ok",
                    artifact_path="evidence/legal.png",
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            sidecar = json.loads(
                (root / "evidence" / "legal.probe.json").read_text(encoding="utf-8")
            )
            kinds = {row["kind"] for row in sidecar["leaks"]}
            self.assertIn("undefined", kinds)
            self.assertEqual(sidecar["defects"]["measurement_status"], "measured")

    # The declaration the two render-token fixtures are written against.
    DECLARED = {
        "fontSizes": [14, 16, 20, 24],
        "colors": ["#f5f5f5", "#ffffff", "#1a1a1a", "#0b6bcb"],
        "radii": [4, 8, 12, 20],
    }
    _RENDER_VIEWPORT = {
        "width": 1280,
        "height": 900,
        "devicePixelRatio": 1.0,
        "colorScheme": "light",
    }

    def _render_capture(self, fixture: str, **overrides) -> tuple[dict, dict]:
        """Capture one render-token fixture through the public runtime entry."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=(_COMPONENT_DIR / "fixtures" / fixture).resolve().as_uri(),
                    state="ok",
                    artifact_path="evidence/render.png",
                    viewport=dict(self._RENDER_VIEWPORT),
                    **overrides,
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            sidecar = json.loads(
                (root / "evidence" / "render.probe.json").read_text(encoding="utf-8")
            )
            return payload, sidecar

    def test_declared_binding_legal_page_reports_no_findings(self) -> None:
        payload, sidecar = self._render_capture(
            "render-tokens-legal.html", design=self.DECLARED
        )
        # The declaration is bound on the request snapshot and the sidecar.
        self.assertEqual(payload["request"]["design"], self.DECLARED)
        self.assertEqual(sidecar["design"], self.DECLARED)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        self.assertEqual(render["undecidable"], [])
        self.assertEqual(render["findings"], [])
        self.assertEqual(render["distinctFontSizes"], [16.0, 20.0])

    def test_declared_binding_deviation_reports_findings(self) -> None:
        _payload, sidecar = self._render_capture(
            "render-tokens-deviant.html", design=self.DECLARED
        )
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        self.assertEqual(
            {(row["axis"], row["kind"], row["value"]) for row in render["findings"]},
            {
                ("font-size", "off-scale-size", "17"),
                ("color", "off-palette-color", "rgb(0, 0, 238)"),
                ("radius", "inner-radius-not-concentric", "12"),
                ("radius", "inner-radius-exceeds-outer", "20"),
            },
        )

    def test_unbound_capture_is_undecidable_not_clean(self) -> None:
        # The same legal page, captured without a declaration: the screenshot
        # still lands, but an empty finding list is explicitly not conformance.
        payload, sidecar = self._render_capture("render-tokens-legal.html")
        self.assertNotIn("design", payload["request"])
        self.assertNotIn("design", sidecar)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        self.assertEqual(render["findings"], [])
        self.assertEqual(
            sorted(note["axis"] for note in render["undecidable"]),
            ["color", "font-size", "radius"],
        )

    def _capture_under_design(
        self, design: dict, *, fixture: str = "render-tokens-legal.html",
        html: str | None = None,
    ) -> tuple[dict, dict]:
        """Capture the legal render-token fixture under one declaration."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            if html is not None:
                page = root / "page.html"
                page.write_text(html, encoding="utf-8")
                url = page.resolve().as_uri()
            else:
                url = (_COMPONENT_DIR / "fixtures" / fixture).resolve().as_uri()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=url,
                    state="ok",
                    artifact_path="evidence/render.png",
                    viewport=dict(self._RENDER_VIEWPORT),
                    design=design,
                ),
            )
            sidecar_path = root / "evidence" / "render.probe.json"
            self.assertTrue(sidecar_path.is_file(), payload)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertTrue((root / "evidence" / "render.png").is_file(), payload)
            return payload, sidecar

    def test_declared_non_finite_px_literals_stay_undecidable(self) -> None:
        design = {
            **self.DECLARED,
            "fontSizes": [14, 16, 20, 24, "NaNpx", "Infinitypx", "1e309px"],
        }
        payload, sidecar = self._capture_under_design(design)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        # The legal sizes still resolve, and the non-finite literals are named
        # rather than silently absent from a "clean" result.
        self.assertEqual(render["findings"], [])
        reasons = " ".join(
            note["reason"]
            for note in render["undecidable"]
            if note["axis"] == "font-size"
        )
        for literal in ("NaNpx", "Infinitypx", "1e309px"):
            self.assertIn(repr(literal), reasons)

    def test_declared_translucent_colors_stay_undecidable(self) -> None:
        design = {
            **self.DECLARED,
            "colors": [
                "#f5f5f5",
                "#ffffff",
                "#0b6bcb",
                "rgb(26 26 26 / 10%)",
                "rgba(26, 26, 26, 0.1)",
            ],
        }
        payload, sidecar = self._capture_under_design(design)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        reasons = [
            note["reason"]
            for note in render["undecidable"]
            if note["axis"] == "color"
        ]
        self.assertEqual(len(reasons), 2, render["undecidable"])
        for literal in ("rgb(26 26 26 / 10%)", "rgba(26, 26, 26, 0.1)"):
            self.assertTrue(
                any(repr(literal) in reason for reason in reasons), reasons
            )
        # The painted text color is opaque 26,26,26 and no comparable declared
        # entry covers it; the page is not called clean.
        self.assertIn(
            ("color", "off-palette-color", "rgb(26, 26, 26)"),
            {(row["axis"], row["kind"], row["value"]) for row in render["findings"]},
        )

    def test_declared_overflow_color_channel_keeps_capture_and_undecidable(self) -> None:
        design = {**self.DECLARED, "colors": ["rgb(1e309,0,0)"]}
        payload, sidecar = self._capture_under_design(design)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        reasons = [
            note["reason"]
            for note in render["undecidable"]
            if note["axis"] == "color"
        ]
        # No usable palette entry (the axis note) plus the unreadable literal;
        # an empty finding list is therefore not conformance.
        self.assertEqual(len(reasons), 2, render["undecidable"])
        self.assertTrue(
            any("'rgb(1e309,0,0)'" in reason for reason in reasons), reasons
        )

    def test_declared_non_css_numeric_literals_stay_undecidable(self) -> None:
        # float() reads "1_6px" as 16 and "rgb(2_6,...)" as 26; neither is a
        # CSS number, so the browser paints nothing and the owner must say so.
        design = {
            **self.DECLARED,
            "fontSizes": [14, 16, 20, 24, "1_6px"],
            "colors": ["#f5f5f5", "#ffffff", "rgb(2_6,26,26)", "#0b6bcb"],
        }
        payload, sidecar = self._capture_under_design(design)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        reasons = " ".join(note["reason"] for note in render["undecidable"])
        self.assertIn("'1_6px'", reasons)
        self.assertIn("'rgb(2_6,26,26)'", reasons)
        # The painted text colour is opaque 26,26,26 and no comparable entry
        # covers it: the page is not called clean.
        self.assertIn(
            ("color", "off-palette-color", "rgb(26, 26, 26)"),
            {(row["axis"], row["kind"], row["value"]) for row in render["findings"]},
        )

    def test_declared_non_css_whitespace_literals_stay_undecidable(self) -> None:
        # NBSP and vertical tab are not CSS whitespace; the browser rejects
        # both literals, so the owner must name them instead of trimming.
        design = {
            **self.DECLARED,
            "fontSizes": [14, 16, 20, 24, "\u00a016px"],
            "colors": ["#f5f5f5", "#ffffff", "rgb(26\u000b26 26)", "#0b6bcb"],
        }
        payload, sidecar = self._capture_under_design(design)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        reasons = " ".join(note["reason"] for note in render["undecidable"])
        self.assertIn("'\\xa016px'", reasons)
        self.assertIn("'rgb(26\\x0b26 26)'", reasons)
        self.assertIn(
            ("color", "off-palette-color", "rgb(26, 26, 26)"),
            {(row["axis"], row["kind"], row["value"]) for row in render["findings"]},
        )

    def test_declared_fractional_color_matches_the_painted_color(self) -> None:
        # The browser paints rgb(12.5,12.5,12.5) as rgb(13, 13, 13); a banker's
        # round would map the declaration to rgb(12, 12, 12) and report a false
        # deviation.
        html = (
            "<!doctype html><html><head><meta charset='utf-8'></head>"
            "<body style='color: rgb(12.5,12.5,12.5); background: #ffffff;"
            " margin: 0' data-state='ok'><p>fractional</p></body></html>"
        )
        design = {"colors": ["#ffffff", "rgb(12.5,12.5,12.5)"]}
        payload, sidecar = self._capture_under_design(design, html=html)
        self.assertEqual(payload["result"], "captured", payload)
        render = sidecar["renderTokens"]
        self.assertEqual(render["measurement_status"], "measured", render)
        self.assertEqual(render["findings"], [])
        self.assertEqual(
            [note for note in render["undecidable"] if note["axis"] == "color"],
            [],
        )

    def test_async_init_wait_for_state_reaches_ok(self) -> None:
        page = _COMPONENT_DIR / "fixtures" / "async-init.html"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=page.resolve().as_uri(),
                    state="ok",
                    actions=[{"do": "wait_for_state", "state": "ok"}],
                    artifact_path="evidence/async.png",
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            self.assertEqual(payload["observed_state"], "ok")

    def test_wrong_page_selector_fails_closed(self) -> None:
        page = _COMPONENT_DIR / "fixtures" / "login-wrong-page.html"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=page.resolve().as_uri(),
                    state="ok",
                    actions=[{"do": "wait_for_selector", "selector": "#app"}],
                    artifact_path="evidence/login.png",
                ),
            )
            self.assertEqual(payload["result"], "failed", payload)
            self.assertTrue(payload["error"])

    def test_synthetic_storage_state_loads_without_copying_session(self) -> None:
        page = _COMPONENT_DIR / "fixtures" / "legal-undefined.html"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            (root / "session.json").write_text(
                json.dumps({"cookies": [], "origins": []}),
                encoding="utf-8",
            )
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=page.resolve().as_uri(),
                    state="ok",
                    artifact_path="evidence/sessioned.png",
                    storage_state="session.json",
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            dumped = json.dumps(payload)
            self.assertNotIn("cookies", dumped)
            self.assertNotIn("origins", dumped)
            self.assertNotIn("storage_state", payload.get("request", {}))

    def test_screenshot_capture_writes_artifact_never_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "page.html"
            html.write_text(FIXTURE_HTML, encoding="utf-8")
            evidence = root / "evidence"
            evidence.mkdir()
            artifact_rel = "evidence/L6.3-error.png"
            artifact_abs = root / artifact_rel

            payload = self._capture(
                root,
                _v1_capture_args(
                    url=html.resolve().as_uri(),
                    state="error",
                    actions=[{"do": "click", "selector": "#submit"}],
                    artifact_path=artifact_rel,
                ),
            )
            self.assertEqual(payload["result"], "captured")
            self.assertEqual(payload["observed_state"], "error")
            self.assertEqual(payload["error"], "")
            self.assertTrue(artifact_abs.is_file(), f"missing {artifact_abs}")
            self.assertGreater(artifact_abs.stat().st_size, 100)
            self.assertFalse((evidence / "manifest.jsonl").exists())
            self.assertEqual(payload["artifact"], artifact_rel)
            self.assertIn("written_path", payload)
            self.assertEqual(
                Path(payload["written_path"]).resolve(),
                artifact_abs.resolve(),
            )

    def test_capture_without_explicit_page_state_reports_unknown(self) -> None:
        """Requested state is intent, not an observed fact."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "page.html"
            html.write_text(
                "<html><body><h1>No state marker</h1></body></html>",
                encoding="utf-8",
            )
            artifact_rel = "evidence/L6.1-ok.png"
            payload = self._capture(
                root,
                _v1_capture_args(
                    url=html.resolve().as_uri(),
                    state="ok",
                    artifact_path=artifact_rel,
                ),
            )
            self.assertEqual(payload["result"], "captured")
            self.assertEqual(payload["observed_state"], "unknown")

    def test_a11y_tree_and_interaction_trace_write_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "page.html"
            html.write_text(FIXTURE_HTML, encoding="utf-8")
            a11y = root / "evidence" / "L6.4-a11y.json"
            trace = root / "evidence" / "L6.5-trace.zip"
            calls = [
                ("a11y tree", [], a11y),
                (
                    "interaction trace",
                    [{"do": "click", "selector": "#submit"}],
                    trace,
                ),
            ]
            for capture_type, actions, artifact in calls:
                with self.subTest(capture_type=capture_type):
                    payload = self._capture(
                        root,
                        _v1_capture_args(
                            url=html.resolve().as_uri(),
                            type=capture_type,
                            state="error",
                            actions=actions,
                            artifact_path=artifact.relative_to(root).as_posix(),
                        ),
                    )
                    self.assertEqual(payload["result"], "captured", payload)
                    self.assertTrue(artifact.is_file(), artifact)
                    if capture_type == "a11y tree":
                        parsed = json.loads(artifact.read_text(encoding="utf-8"))
                        # DEF-6: documented envelope, not a node/role tree.
                        self.assertEqual(parsed["format"], "aria_snapshot")
                        self.assertIn("Export jobs", parsed["tree"])
                        serialized = json.dumps(parsed, ensure_ascii=False)
                        self.assertIn("Export jobs", serialized)
                        self.assertIn("Retry", serialized)
                    else:
                        with zipfile.ZipFile(artifact) as archive:
                            names = archive.namelist()
                        self.assertTrue(any(name.endswith("trace.trace") for name in names))

    def test_select_option_action_drives_native_select(self) -> None:
        """select_option drives a native <select> by value or label."""
        select_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>select-fixture</title></head>
<body data-state="idle">
  <label for="pick">Industry</label>
  <select id="pick">
    <option value="">Choose</option>
    <option value="a">Software / Internet</option>
    <option value="b">Manufacturing</option>
  </select>
  <script>
    document.getElementById("pick").addEventListener("change", (e) => {
      document.body.dataset.state = e.target.value || "idle";
    });
  </script>
</body>
</html>
"""
        cases = [
            ("by value", {"do": "select_option", "selector": "#pick", "value": "b"}, "b"),
            (
                "by label",
                {"do": "select_option", "selector": "#pick", "label": "Software / Internet"},
                "a",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "page.html"
            html.write_text(select_html, encoding="utf-8")
            (root / "evidence").mkdir()
            for label, action, expected_state in cases:
                with self.subTest(label=label):
                    artifact_rel = f"evidence/select-{label.replace(' ', '')}.png"
                    payload = self._capture(
                        root,
                        _v1_capture_args(
                            url=html.resolve().as_uri(),
                            state=expected_state,
                            actions=[action],
                            artifact_path=artifact_rel,
                        ),
                    )
                    self.assertEqual(payload["result"], "captured", payload)
                    self.assertEqual(payload["observed_state"], expected_state, payload)
                    self.assertTrue((root / artifact_rel).is_file())

    def test_failure_paths_never_echo_requested_state_as_observed(self) -> None:
        base_arguments = _v1_capture_args(
            url="http://127.0.0.1:1/unreachable",
            state="requested-error",
            artifact_path="evidence/failure.png",
        )
        cases = [
            ("navigation failure", base_arguments, False),
            (
                "action failure",
                {
                    **base_arguments,
                    "url": "about:blank",
                    "actions": [{"do": "click", "selector": "#missing"}],
                },
                False,
            ),
            ("playwright unavailable", {**base_arguments, "url": "about:blank"}, True),
        ]
        for label, arguments, unavailable in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if unavailable:
                    with mock.patch.object(
                        capture_runtime,
                        "PlaywrightBrowserAdapter",
                        side_effect=ImportError("playwright unavailable"),
                    ), mock.patch.object(
                        capture_runtime, "_run_root", return_value=root
                    ):
                        payload = capture_runtime.execute_capture_plan(arguments)
                else:
                    payload = self._capture(root, arguments)
                self.assertEqual(payload["result"], "failed")
                self.assertEqual(payload["observed_state"], "unknown")

    def test_provider_overwrites_when_opted_in(self) -> None:
        """G6 write boundary: overwrite=true explicitly opts in to replace."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            html = root / "page.html"
            html.write_text(FIXTURE_HTML, encoding="utf-8")
            artifact_rel = "evidence/L6.3-error.png"
            artifact = root / artifact_rel
            artifact.write_bytes(b"pre-existing-by-hand")

            payload = self._capture(
                root,
                _v1_capture_args(
                    url=html.resolve().as_uri(),
                    state="error",
                    artifact_path=artifact_rel,
                    overwrite=True,
                ),
            )
            self.assertEqual(payload["result"], "captured", payload)
            self.assertGreater(artifact.stat().st_size, 100)
            self.assertNotEqual(artifact.read_bytes(), b"pre-existing-by-hand")

if __name__ == "__main__":
    unittest.main()
