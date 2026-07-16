#!/usr/bin/env python3
"""Process-boundary tests for the preview MCP stdio transport."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


SERVER = Path(__file__).with_name("server.py")


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


if __name__ == "__main__":
    unittest.main()
