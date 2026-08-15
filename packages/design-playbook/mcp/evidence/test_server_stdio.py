#!/usr/bin/env python3
"""Evidence MCP transport and capture-runtime interface tests.

``EvidencePurePathTests`` covers the narrow JSON-RPC wire/schema mapping and
path validation that short-circuits before Playwright. ``EvidenceRuntimeTests``
exercises the public runtime interface with a fake browser adapter.
``EvidenceCaptureTests`` exercises that same interface with the production
Playwright adapter for screenshot, a11y, and trace captures.
"""
from __future__ import annotations

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

from design_playbook.mcp.evidence import capture_runtime  # noqa: E402

SERVER = Path(__file__).resolve().with_name("server.py")
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
