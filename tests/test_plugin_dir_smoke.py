#!/usr/bin/env python3
"""Deterministic tests for scripts/plugin_dir_smoke.py (no live host, no network)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plugin_dir_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "dpb_plugin_dir_smoke_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_module()

FIXTURE_PLUGIN_DIR = Path("/fixture/plugins/design-playbook")
FIXTURE_EXPECTED = {
    "version": "0.10.0",
    "skills": ["design-playbook", "ui-picker", "ux-spec"],
    "commands": ["design-io", "ux-spec"],
    "scripts": [],
    "mcp_servers": ["design-playbook-evidence", "design-playbook-preview"],
    "mcp_entrypoints": {
        "design-playbook-evidence": "mcp/evidence/server.py",
        "design-playbook-preview": "mcp/preview/server.py",
    },
}
FIXTURE_COMPONENTS = sorted(FIXTURE_EXPECTED["skills"] + FIXTURE_EXPECTED["commands"])


def _fixture_list_payload(**overrides) -> str:
    payload = {
        "id": "design-playbook@inline",
        "version": FIXTURE_EXPECTED["version"],
        "scope": "session",
        "enabled": True,
        "installPath": str(FIXTURE_PLUGIN_DIR),
        "mcpServers": {
            name: {"command": "python", "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{path}"]}
            for name, path in FIXTURE_EXPECTED["mcp_entrypoints"].items()
        },
    }
    payload.update(overrides)
    return json.dumps([payload])


def _render_details(version: str, components: list[str], mcp_servers: list[str]) -> str:
    return "\n".join(
        [
            f"design-playbook {version}",
            "  Description: fixture",
            "  Source: design-playbook@inline",
            "",
            "Component inventory",
            f"  Skills ({len(components)})  " + ", ".join(components),
            "  Agents (0)",
            "  Hooks (0)",
            f"  MCP servers ({len(mcp_servers)})  "
            + ", ".join(mcp_servers)
            + "  (tool schemas resolved at runtime; not counted)",
            "  LSP servers (0)",
            "",
            "Projected token cost",
            "  Always-on:   ~42 tok   added to every session",
            "",
        ]
    )


def _fixture_details(**overrides) -> str:
    fields = {
        "version": FIXTURE_EXPECTED["version"],
        "components": FIXTURE_COMPONENTS,
        "mcp_servers": list(FIXTURE_EXPECTED["mcp_servers"]),
    }
    fields.update(overrides)
    return _render_details(
        fields["version"], fields["components"], fields["mcp_servers"]
    )


class PluginListParserTests(unittest.TestCase):
    def test_valid_session_entry_parses(self) -> None:
        parsed = smoke._parse_plugin_list(
            _fixture_list_payload(), FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED
        )

        self.assertEqual(parsed["id"], "design-playbook@inline")
        self.assertEqual(parsed["version"], "0.10.0")
        self.assertEqual(parsed["scope"], "session")
        self.assertTrue(parsed["enabled"])
        self.assertEqual(parsed["mcp_servers"], FIXTURE_EXPECTED["mcp_servers"])
        self.assertEqual(parsed["mcp_entrypoints"], FIXTURE_EXPECTED["mcp_entrypoints"])

    def test_empty_list_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "exactly one loaded plugin"):
            smoke._parse_plugin_list("[]", FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED)

    def test_extra_plugin_fails_closed(self) -> None:
        stdout = json.dumps(
            [json.loads(_fixture_list_payload()), json.loads(_fixture_list_payload())]
        )
        with self.assertRaisesRegex(smoke.SmokeFailure, "exactly one loaded plugin"):
            smoke._parse_plugin_list(stdout, FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED)

    def test_version_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "loaded version mismatch"):
            smoke._parse_plugin_list(
                _fixture_list_payload(version="9.9.9"),
                FIXTURE_PLUGIN_DIR,
                FIXTURE_EXPECTED,
            )

    def test_scope_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "scope must be session"):
            smoke._parse_plugin_list(
                _fixture_list_payload(scope="user"),
                FIXTURE_PLUGIN_DIR,
                FIXTURE_EXPECTED,
            )

    def test_install_path_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "installPath mismatch"):
            smoke._parse_plugin_list(
                _fixture_list_payload(installPath="/somewhere/else"),
                FIXTURE_PLUGIN_DIR,
                FIXTURE_EXPECTED,
            )

    def test_entrypoint_drift_fails_closed(self) -> None:
        payload = json.loads(_fixture_list_payload())
        payload[0]["mcpServers"]["design-playbook-preview"]["args"] = [
            "${CLAUDE_PLUGIN_ROOT}/mcp/other/server.py"
        ]
        with self.assertRaisesRegex(smoke.SmokeFailure, "mcp entrypoints mismatch"):
            smoke._parse_plugin_list(
                json.dumps(payload), FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED
            )

    def test_missing_mcp_servers_fails_closed(self) -> None:
        payload = json.loads(_fixture_list_payload())
        del payload[0]["mcpServers"]["design-playbook-evidence"]
        with self.assertRaisesRegex(smoke.SmokeFailure, "mcpServers mismatch"):
            smoke._parse_plugin_list(
                json.dumps(payload), FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED
            )

    def test_invalid_json_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "invalid JSON"):
            smoke._parse_plugin_list("not json", FIXTURE_PLUGIN_DIR, FIXTURE_EXPECTED)


class PluginDetailsParserTests(unittest.TestCase):
    def test_valid_details_parse_merged_components_as_multiset(self) -> None:
        parsed = smoke._parse_plugin_details(_fixture_details(), FIXTURE_EXPECTED)

        self.assertEqual(parsed["version"], "0.10.0")
        self.assertEqual(parsed["components"], FIXTURE_COMPONENTS)
        self.assertEqual(
            parsed["components"].count("ux-spec"),
            2,
            "skill ux-spec and command ux-spec must both be kept",
        )
        self.assertEqual(parsed["mcp_servers"], FIXTURE_EXPECTED["mcp_servers"])

    def test_not_found_output_fails_closed(self) -> None:
        """The host CLI exits 0 on not-found; only content checks can fail."""
        stdout = (
            'Plugin "design-playbook" not found. Run `claude plugin list` to see '
            "installed plugins, or pass --plugin-dir <path> to load one from disk.\n"
        )
        with self.assertRaisesRegex(smoke.SmokeFailure, "lacks component inventory"):
            smoke._parse_plugin_details(stdout, FIXTURE_EXPECTED)

    def test_missing_skills_line_fails_closed(self) -> None:
        stdout = _fixture_details().replace(
            f"  Skills ({len(FIXTURE_COMPONENTS)})  "
            + ", ".join(FIXTURE_COMPONENTS)
            + "\n",
            "",
        )
        with self.assertRaisesRegex(smoke.SmokeFailure, "Skills line missing"):
            smoke._parse_plugin_details(stdout, FIXTURE_EXPECTED)

    def test_missing_mcp_line_fails_closed(self) -> None:
        stdout = _fixture_details()
        for line in stdout.splitlines():
            if line.strip().startswith("MCP servers ("):
                stdout = stdout.replace(line + "\n", "")
                break
        with self.assertRaisesRegex(smoke.SmokeFailure, "MCP servers line missing"):
            smoke._parse_plugin_details(stdout, FIXTURE_EXPECTED)

    def test_missing_component_fails_closed(self) -> None:
        dropped = [name for name in FIXTURE_COMPONENTS if name != "ui-picker"]
        with self.assertRaisesRegex(smoke.SmokeFailure, "components mismatch"):
            smoke._parse_plugin_details(
                _fixture_details(components=dropped), FIXTURE_EXPECTED
            )

    def test_renamed_component_fails_closed(self) -> None:
        renamed = [
            name + "-renamed" if name == "ui-picker" else name
            for name in FIXTURE_COMPONENTS
        ]
        with self.assertRaisesRegex(smoke.SmokeFailure, "components mismatch"):
            smoke._parse_plugin_details(
                _fixture_details(components=renamed), FIXTURE_EXPECTED
            )

    def test_mcp_server_rename_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "MCP servers mismatch"):
            smoke._parse_plugin_details(
                _fixture_details(mcp_servers=["design-playbook-other"]),
                FIXTURE_EXPECTED,
            )

    def test_count_names_disagreement_fails_closed(self) -> None:
        stdout = _fixture_details().replace(
            f"Skills ({len(FIXTURE_COMPONENTS)})", "Skills (3)"
        )
        with self.assertRaisesRegex(smoke.SmokeFailure, "count 3"):
            smoke._parse_plugin_details(stdout, FIXTURE_EXPECTED)

    def test_header_version_drift_fails_closed(self) -> None:
        with self.assertRaisesRegex(smoke.SmokeFailure, "details version mismatch"):
            smoke._parse_plugin_details(
                _fixture_details(version="9.9.9"), FIXTURE_EXPECTED
            )


class SkipSemanticsTests(unittest.TestCase):
    def test_absent_host_records_skip_and_runs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_root = Path(tmp) / "work"
            config = smoke.PluginDirSmokeConfig(
                version=smoke._source_expectations()["version"],
                plugin_dir=smoke.PKG,
                output_dir=Path(tmp) / "evidence",
            )
            with (
                mock.patch.object(smoke, "_host_available", return_value=None),
                mock.patch.object(
                    smoke,
                    "_run_command",
                    side_effect=AssertionError("host commands must not run on skip"),
                ),
            ):
                result = smoke.run_smoke(config, temp_root=work_root)

        self.assertEqual(result["status"], "skip")
        self.assertIn("not found on PATH", result["skip_reason"])
        self.assertIsNone(result["error"])
        statuses = {check["status"] for check in result["checks"]}
        self.assertIn("skip", statuses)
        self.assertNotIn("pass", statuses, "skip must never be silent green")

    def test_cli_skip_exits_two_and_writes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            with mock.patch.object(smoke, "_host_available", return_value=None):
                exit_code = smoke.main(["--output-dir", str(output)])
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            markdown = (output / "result.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "skip")
        self.assertIn("## Skip reason", markdown)


class OrchestrationTests(unittest.TestCase):
    def _fake_command(self, expected, *, details_components=None):
        def run(
            cmd: list[str],
            *,
            env: dict | None = None,
            cwd: Path | None = None,
            timeout: int = 180,
            input_text: str | None = None,
        ) -> subprocess.CompletedProcess[str]:
            del cwd, timeout, input_text
            assert cmd[0] == "claude"
            assert cmd[1] == "--plugin-dir"
            assert cmd[2] == str(smoke.PKG)
            assert env is not None
            assert Path(env["CLAUDE_CONFIG_DIR"]).is_dir()
            assert "DESIGN_PLAYBOOK_RUN_ROOT" in env
            if cmd[3:6] == ["plugin", "list", "--json"]:
                stdout = json.dumps(
                    [
                        {
                            "id": "design-playbook@inline",
                            "version": expected["version"],
                            "scope": "session",
                            "enabled": True,
                            "installPath": str(smoke.PKG),
                            "mcpServers": {
                                name: {
                                    "command": "python",
                                    "args": [f"${{CLAUDE_PLUGIN_ROOT}}/{path}"],
                                    "timeout": 3600000,
                                }
                                for name, path in expected["mcp_entrypoints"].items()
                            },
                        }
                    ]
                )
            elif cmd[3:6] == ["plugin", "details", smoke.PLUGIN_NAME]:
                components = (
                    details_components
                    if details_components is not None
                    else sorted(expected["skills"] + expected["commands"])
                )
                stdout = _render_details(
                    expected["version"], components, expected["mcp_servers"]
                )
            else:
                raise AssertionError(f"unexpected host command: {cmd}")
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        return run

    def _run_flow(self, expected, *, details_components=None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            work_root = Path(tmp) / "work"
            config = smoke.PluginDirSmokeConfig(
                version=expected["version"],
                plugin_dir=smoke.PKG,
                output_dir=Path(tmp) / "evidence",
            )
            fake = self._fake_command(expected, details_components=details_components)
            with (
                mock.patch.object(
                    smoke, "_host_available", return_value="fixture-claude"
                ),
                mock.patch.object(smoke, "_run_command", side_effect=fake),
                mock.patch.object(
                    smoke, "_tool_version", return_value="fixture-claude 2.1.0"
                ),
                mock.patch.object(
                    smoke,
                    "_probe_mcp",
                    side_effect=lambda _root, name, tool, **_kwargs: {
                        "server": name,
                        "tools": [tool],
                    },
                ),
            ):
                return smoke.run_smoke(config, temp_root=work_root)

    def test_mocked_full_flow_passes_and_collects_all_surfaces(self) -> None:
        expected = smoke._source_expectations()
        result = self._run_flow(expected)

        self.assertEqual(result["status"], "pass", result.get("error"))
        self.assertEqual(result["loaded"]["id"], "design-playbook@inline")
        self.assertEqual(result["loaded"]["scope"], "session")
        self.assertEqual(result["runtime"]["claude"], "fixture-claude 2.1.0")
        self.assertEqual(
            result["details"]["components"],
            sorted(expected["skills"] + expected["commands"]),
        )
        self.assertEqual(len(result["mcp"]), 2)
        self.assertEqual(
            sorted(probe["server"] for probe in result["mcp"]),
            sorted(expected["mcp_servers"]),
        )
        self.assertFalse(
            [check for check in result["checks"] if check["status"] != "pass"]
        )

    def test_component_drift_fails_the_flow(self) -> None:
        expected = smoke._source_expectations()
        drifted = sorted(expected["skills"] + expected["commands"])
        drifted[0] = drifted[0] + "-renamed"
        result = self._run_flow(expected, details_components=drifted)

        self.assertEqual(result["status"], "fail")
        self.assertIn("components mismatch", result["error"])
        self.assertEqual(result["checks"][-1]["status"], "fail")
        self.assertEqual(result["checks"][-1]["name"], "plugin details")

    def test_cli_version_mismatch_writes_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            exit_code = smoke.main(["--version", "9.9.9", "--output-dir", str(output)])
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertIn("requested version 9.9.9", payload["error"])


class EvidenceTests(unittest.TestCase):
    def test_writes_json_and_markdown_for_pass(self) -> None:
        result = {
            "schema_version": 1,
            "status": "pass",
            "started_at": "2026-08-27T00:00:00+00:00",
            "completed_at": "2026-08-27T00:00:01+00:00",
            "plugin_dir": "/fixture/plugins/design-playbook",
            "expected": {"version": "0.10.0"},
            "runtime": {"claude": "fixture"},
            "checks": [
                {"name": "isolated config", "status": "pass", "detail": "empty"}
            ],
            "loaded": {
                "id": "design-playbook@inline",
                "version": "0.10.0",
                "scope": "session",
                "enabled": True,
                "install_path": "/fixture/plugins/design-playbook",
            },
            "details": {
                "version": "0.10.0",
                "components": ["design-io", "ux-spec"],
                "mcp_servers": ["design-playbook-preview"],
            },
            "mcp": [
                {"server": "design-playbook-preview", "tools": ["preview_prototype"]}
            ],
            "temporary_root": {"path": "/tmp/x", "retained": False, "owned": True},
            "warnings": [],
            "error": None,
            "skip_reason": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = smoke.write_evidence(result, Path(tmp))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "pass")
        self.assertIn("**Status:** **PASS**", markdown)
        self.assertIn("| isolated config | PASS |", markdown)
        self.assertIn("- ID: `design-playbook@inline`", markdown)
        self.assertIn("- design-playbook-preview: preview_prototype", markdown)


if __name__ == "__main__":
    unittest.main()
