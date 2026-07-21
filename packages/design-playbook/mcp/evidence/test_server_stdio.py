#!/usr/bin/env python3
"""Process-boundary tests for the evidence MCP stdio transport."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

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


def _structured(call_response: dict) -> dict:
    result = call_response["result"]
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    text = result["content"][0]["text"]
    return json.loads(text)


class EvidenceMcpStdioTests(unittest.TestCase):
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
        self.assertEqual([r["id"] for r in responses], [1, 2])
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"],
            "design-playbook-evidence",
        )
        self.assertEqual(
            [tool["name"] for tool in responses[1]["result"]["tools"]],
            ["execute_capture_plan"],
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
            url = html.resolve().as_uri()

            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "execute_capture_plan",
                        "arguments": {
                            "url": url,
                            "type": "screenshot",
                            "state": "error",
                            "actions": [
                                {"do": "click", "selector": "#submit"},
                            ],
                            "artifact_path": artifact_rel,
                        },
                    },
                },
            ]
            completed = _run_stdio(requests, timeout=45, cwd=root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            responses = _responses(completed)
            self.assertEqual([r["id"] for r in responses], [1, 2])
            self.assertFalse(responses[1]["result"].get("isError", False), responses[1])
            payload = _structured(responses[1])
            self.assertEqual(payload["result"], "captured")
            self.assertEqual(payload["observed_state"], "error")
            self.assertEqual(payload["error"], "")
            self.assertTrue(artifact_abs.is_file(), f"missing {artifact_abs}")
            self.assertGreater(artifact_abs.stat().st_size, 100)
            # Provider must never write manifest.
            self.assertFalse((evidence / "manifest.jsonl").exists())
            self.assertEqual(payload["artifact"], artifact_rel)
            # P0-1: absolute written_path so RUN_ROOT/cwd misconfig is visible
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
            artifact = root / artifact_rel
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "execute_capture_plan",
                        "arguments": {
                            "url": html.resolve().as_uri(),
                            "type": "screenshot",
                            "state": "ok",
                            "actions": [],
                            "artifact_path": artifact_rel,
                        },
                    },
                },
            ]
            completed = _run_stdio(requests, timeout=45, cwd=root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = _structured(_responses(completed)[1])
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
            for request_id, (capture_type, actions, artifact) in enumerate(
                calls, start=2
            ):
                with self.subTest(capture_type=capture_type):
                    requests = [
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {"protocolVersion": "2025-06-18"},
                        },
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {
                                "name": "execute_capture_plan",
                                "arguments": {
                                    "url": html.resolve().as_uri(),
                                    "type": capture_type,
                                    "state": "error",
                                    "actions": actions,
                                    "artifact_path": artifact.relative_to(root).as_posix(),
                                },
                            },
                        },
                    ]
                    completed = _run_stdio(requests, timeout=45, cwd=root)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = _structured(_responses(completed)[1])
                    self.assertEqual(payload["result"], "captured", payload)
                    self.assertTrue(artifact.is_file(), artifact)
                    if capture_type == "a11y tree":
                        parsed = json.loads(artifact.read_text(encoding="utf-8"))
                        self.assertIn("Export jobs", json.dumps(parsed, ensure_ascii=False))
                        self.assertIn("Retry", json.dumps(parsed, ensure_ascii=False))
                    else:
                        with zipfile.ZipFile(artifact) as archive:
                            names = archive.namelist()
                        self.assertTrue(any(name.endswith("trace.trace") for name in names))

    def test_select_option_action_drives_native_select(self) -> None:
        """select_option drives a native <select> by value or label (issue 02)."""
        select_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>select-fixture</title></head>
<body data-state="idle">
  <label for="pick">行业</label>
  <select id="pick">
    <option value="">请选择</option>
    <option value="a">软件 / 互联网</option>
    <option value="b">制造业</option>
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
            ("by label", {"do": "select_option", "selector": "#pick", "label": "软件 / 互联网"}, "a"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html = root / "page.html"
            html.write_text(select_html, encoding="utf-8")
            (root / "evidence").mkdir()
            for label, action, expected_state in cases:
                with self.subTest(label=label):
                    artifact_rel = f"evidence/select-{label.replace(' ', '')}.png"
                    requests = [
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "initialize",
                            "params": {"protocolVersion": "2025-06-18"},
                        },
                        {
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {
                                "name": "execute_capture_plan",
                                "arguments": {
                                    "url": html.resolve().as_uri(),
                                    "type": "screenshot",
                                    "state": expected_state,
                                    "actions": [action],
                                    "artifact_path": artifact_rel,
                                },
                            },
                        },
                    ]
                    completed = _run_stdio(requests, timeout=45, cwd=root)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = _structured(_responses(completed)[1])
                    self.assertEqual(payload["result"], "captured", payload)
                    # select_option fired change -> body[data-state] reflects it
                    self.assertEqual(payload["observed_state"], expected_state, payload)
                    self.assertTrue((root / artifact_rel).is_file())

    def test_provider_rejects_criterion_field(self) -> None:
        """Provider does not accept criterion (ticket 02 / map premise 9)."""
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
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
                        "criterion": "L6.3",
                    },
                },
            },
        ]
        completed = _run_stdio(requests, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = _responses(completed)
        result = responses[1]["result"]
        # Either isError or structured result=failed — never silently accept criterion.
        if result.get("isError"):
            text = result["content"][0]["text"].lower()
            self.assertIn("criterion", text)
        else:
            payload = _structured(responses[1])
            self.assertEqual(payload["result"], "failed")
            self.assertIn("criterion", payload["error"].lower())

    def test_failure_paths_never_echo_requested_state_as_observed(self) -> None:
        base_arguments = {
            "url": "http://127.0.0.1:1/unreachable",
            "type": "screenshot",
            "state": "requested-error",
            "actions": [],
            "artifact_path": "evidence/failure.png",
        }
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
        for label, arguments, no_site in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                requests = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "execute_capture_plan", "arguments": arguments},
                    },
                ]
                completed = _run_stdio(
                    requests,
                    timeout=45,
                    cwd=Path(tmp),
                    no_site=no_site,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                payload = _structured(_responses(completed)[1])
                self.assertEqual(payload["result"], "failed")
                self.assertEqual(payload["observed_state"], "unknown")

    def test_provider_rejects_manifest_variants_and_path_escape(self) -> None:
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
                with self.subTest(artifact_path=artifact_path):
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
                                    "artifact_path": artifact_path,
                                },
                            },
                        },
                    ]
                    completed = _run_stdio(requests, timeout=15, cwd=root)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = _structured(_responses(completed)[1])
                    self.assertEqual(payload["result"], "failed")
                    self.assertEqual(payload["observed_state"], "unknown")
            self.assertFalse(outside.exists())

    def test_provider_rejects_non_evidence_subtree_paths(self) -> None:
        """G6 containment: artifact_path must already live under evidence/."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            cases = [
                "spec.md",              # would land at run root, not evidence/
                "../spec.md",           # explicit .. segment
                "evidence/../spec.md",  # .. segment that resolves out of evidence/
                "skills/x",             # sibling subtree, not evidence/
            ]
            for artifact_path in cases:
                with self.subTest(artifact_path=artifact_path):
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
                                    "artifact_path": artifact_path,
                                },
                            },
                        },
                    ]
                    completed = _run_stdio(requests, timeout=15, cwd=root)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    payload = _structured(_responses(completed)[1])
                    self.assertEqual(payload["result"], "failed", payload)
                    self.assertEqual(payload["observed_state"], "unknown")
            # None of these wrote anywhere outside evidence/.
            self.assertFalse((root / "spec.md").exists())
            self.assertFalse((root / "skills").exists())

    def test_provider_refuses_overwrite_without_opt_in(self) -> None:
        """G6 write boundary: existing artifact is not overwritten by default."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence").mkdir()
            html = root / "page.html"
            html.write_text(FIXTURE_HTML, encoding="utf-8")
            artifact_rel = "evidence/L6.3-error.png"
            sentinel = b"pre-existing-by-hand"
            (root / artifact_rel).write_bytes(sentinel)

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "execute_capture_plan",
                        "arguments": {
                            "url": html.resolve().as_uri(),
                            "type": "screenshot",
                            "state": "error",
                            "actions": [],
                            "artifact_path": artifact_rel,
                        },
                    },
                },
            ]
            completed = _run_stdio(requests, timeout=45, cwd=root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = _structured(_responses(completed)[1])
            self.assertEqual(payload["result"], "failed", payload)
            self.assertEqual(payload["observed_state"], "unknown")
            # Pre-existing bytes preserved (write boundary held).
            self.assertEqual((root / artifact_rel).read_bytes(), sentinel)

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

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "execute_capture_plan",
                        "arguments": {
                            "url": html.resolve().as_uri(),
                            "type": "screenshot",
                            "state": "error",
                            "actions": [],
                            "artifact_path": artifact_rel,
                            "overwrite": True,
                        },
                    },
                },
            ]
            completed = _run_stdio(requests, timeout=45, cwd=root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = _structured(_responses(completed)[1])
            self.assertEqual(payload["result"], "captured", payload)
            # Sentinel replaced with a real screenshot (>100 bytes).
            self.assertGreater(artifact.stat().st_size, 100)
            self.assertNotEqual(artifact.read_bytes(), b"pre-existing-by-hand")

    def test_provider_rejects_unknown_and_criterion_ref_fields(self) -> None:
        for forbidden in ("criterion", "criterion_ref", "criterion_id", "unexpected"):
            with self.subTest(forbidden=forbidden):
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
                                forbidden: "L6.3",
                            },
                        },
                    },
                ]
                completed = _run_stdio(requests, timeout=15)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = _responses(completed)[1]["result"]
                self.assertTrue(result.get("isError"), result)
                self.assertIn(forbidden, result["content"][0]["text"])

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


if __name__ == "__main__":
    unittest.main()
