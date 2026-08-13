#!/usr/bin/env python3
"""Process-boundary tests for the preview MCP stdio transport."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
# Browser behavior is tested through its owning adapter, not server re-exports.
from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402


SERVER = Path(__file__).with_name("server.py")


# G5: the parent page embeds a one-time dpb_token + dpb_round as hidden fields.
# Tests that POST /decide must GET / first and lift them — the same path a real
# human submit takes through the trusted control form (not a forged fetch).
def _load_server_module():
    spec = importlib.util.spec_from_file_location("dpb_preview_server", SERVER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PreviewMcpStdioTests(unittest.TestCase):
    def test_claude_code_newline_json_can_initialize_and_list_tools(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        wire_input = "".join(
            json.dumps(request, ensure_ascii=False) + "\n" for request in requests
        )

        completed = subprocess.run(
            [sys.executable, str(SERVER)],
            input=wire_input,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [
            json.loads(line)
            for line in completed.stdout.splitlines()
            if line.strip()
        ]
        self.assertEqual([response["id"] for response in responses], [1, 2])
        self.assertEqual(
            responses[0]["result"]["serverInfo"]["name"],
            "design-playbook-preview",
        )
        self.assertEqual(
            [tool["name"] for tool in responses[1]["result"]["tools"]],
            ["preview_prototype"],
        )

    def test_active_lock_returns_structured_error_over_stdio(self) -> None:
        html = "<html><body>locked</body></html>"
        options = ["确认通过", "需要修改"]
        binding = transaction.compute_binding_digest(
            round_n=1,
            prototype_html_hash=prototype_html_digest(html.encode("utf-8")),
            report_ref="report.md", summary="review", options=options,
        )
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / ".scratch" / "preview-adapter" / "preview"
            preview.mkdir(parents=True)
            lock = preview / "decision-round-1.lock"
            lock.write_text(json.dumps({
                "owner_id": "active", "decision_id": "existing-id",
                "binding_digest": binding["digest"], "heartbeat": time.time(),
            }), encoding="utf-8")
            request = {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {
                    "name": "preview_prototype",
                    "arguments": {
                        "html": html, "summary": "review", "round": 1,
                        "report_ref": "report.md", "options": options,
                    },
                },
            }
            completed = subprocess.run(
                [sys.executable, str(SERVER)],
                input=json.dumps(request, ensure_ascii=False) + "\n",
                text=True, encoding="utf-8", capture_output=True,
                cwd=tmp, timeout=5, check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)["result"]
        self.assertTrue(result["isError"])
        self.assertIn("already active", result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["round"], 1)
        self.assertEqual(result["structuredContent"]["decision_id"], "existing-id")
        self.assertTrue(result["structuredContent"]["retryable"])


class PreviewStructuredErrorTests(unittest.TestCase):
    def test_handler_maps_recovery_error_to_structured_tool_error(self) -> None:
        server_mod = _load_server_module()
        domain_error = transaction.PreviewTransactionError(
            "repair required", retryable=True, round_n=2,
            decision_id="abc", artifact="decision-round-2.json",
        )
        with mock.patch.object(
            server_mod, "run_preview_transaction", side_effect=domain_error
        ):
            with self.assertRaises(server_mod.ToolError) as caught:
                server_mod.handle_preview_prototype({
                    "html": "<html></html>", "summary": "review", "round": 2,
                    "report_ref": "report.md",
                })

        self.assertEqual(str(caught.exception), "repair required")
        self.assertEqual(caught.exception.structured_content, domain_error.details)


class PreviewLogRejectionTests(unittest.TestCase):
    """LOW-4 (secure-ship-0.4.4): a rejected decision's rejection reason
    must persist to preview_dir/log.md so a fail-closed G5 event (forged
    token / replay / round mismatch) is auditable on disk, not just in the
    in-memory MCP payload that vanishes when the call returns.
    """

    def _run_handle(self, server_mod: object, tmp: str, decision: dict) -> dict:
        proto = Path(tmp) / "proto.html"
        proto.write_text("<html></html>", encoding="utf-8")
        with mock.patch.object(review_session, "collect_review",
                               return_value=decision):
            return server_mod.handle_preview_prototype(
                {
                    "path": str(proto),
                    "summary": "summary",
                    "round": 1,
                    "report_ref": "report-1",
                }
            )

    def test_rejected_decision_writes_rejection_line_to_log(self) -> None:
        server_mod = _load_server_module()
        rejected_decision = {
            "choice": "",
            "feedback": "forged",
            "aborted": True,
            "anchors": [],
            "rejected": True,
            "rejection": "invalid_token",
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._run_handle(server_mod, tmp, rejected_decision)
            log_text = (Path(tmp) / "log.md").read_text(encoding="utf-8")

        self.assertFalse(payload["confirmed"])
        self.assertIn("- rejected: true", log_text)
        self.assertIn("- rejection: invalid_token", log_text)

    def test_confirmed_decision_does_not_write_rejection_line(self) -> None:
        server_mod = _load_server_module()
        confirmed_decision = {
            "choice": "确认通过",
            "feedback": "ok",
            "aborted": False,
            "anchors": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._run_handle(server_mod, tmp, confirmed_decision)
            log_text = (Path(tmp) / "log.md").read_text(encoding="utf-8")

        self.assertTrue(payload["confirmed"])
        self.assertNotIn("rejected:", log_text)
        self.assertNotIn("rejection:", log_text)


if __name__ == "__main__":
    unittest.main()
