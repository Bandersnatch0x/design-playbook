#!/usr/bin/env python3
"""Deterministic tests for scripts/install_smoke.py (no live network)."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("dpb_install_smoke_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_module()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_inventory_tree(
    root: Path,
    *,
    version: str = "0.10.0",
    skills: tuple[str, ...] = ("design-playbook", "ui-picker"),
    commands: tuple[str, ...] = ("design-io", "run-review"),
    scripts: tuple[str, ...] = ("audit_preferences.py", "validate_run.py"),
    with_manifest: bool = True,
) -> None:
    _write_json(root / "package.json", {"name": "design-playbook", "version": version})
    for name in skills:
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    for name in commands:
        command = root / "commands" / f"{name}.md"
        command.parent.mkdir(parents=True, exist_ok=True)
        command.write_text(f"# {name}\n", encoding="utf-8")
    for name in scripts:
        script = root / "scripts" / name
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("# fixture\n", encoding="utf-8")
    for short in ("preview", "evidence"):
        server = root / "mcp" / short / "server.py"
        server.parent.mkdir(parents=True, exist_ok=True)
        server.write_text("# fixture\n", encoding="utf-8")
    if with_manifest:
        _write_json(
            root / ".mcp.json",
            {
                "mcpServers": {
                    "design-playbook-preview": {
                        "command": "python",
                        "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/preview/server.py"],
                    },
                    "design-playbook-evidence": {
                        "command": "python",
                        "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/evidence/server.py"],
                    },
                }
            },
        )


class InventoryTests(unittest.TestCase):
    def test_plugin_and_npm_inventory_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugin"
            _make_inventory_tree(root)

            plugin = smoke._inspect_plugin_inventory(root)
            npm = smoke._inspect_npm_inventory(root)

        expected = {
            "version": "0.10.0",
            "skills": ["design-playbook", "ui-picker"],
            "commands": ["design-io", "run-review"],
            "scripts": ["audit_preferences", "validate_run"],
            "mcp_servers": [
                "design-playbook-evidence",
                "design-playbook-preview",
            ],
        }
        for inventory in (plugin, npm):
            self.assertEqual(
                {key: inventory[key] for key in ("version", "skills", "commands", "scripts", "mcp_servers")},
                expected,
            )
        self.assertEqual(set(plugin["mcp_entrypoints"]), set(expected["mcp_servers"]))
        self.assertEqual(set(npm["mcp_entrypoints"]), set(expected["mcp_servers"]))
        self.assertEqual(plugin["mcp_entrypoints"], npm["mcp_entrypoints"])

    def test_mcp_entrypoint_drift_fails_closed(self) -> None:
        expected = {
            "version": "0.10.0",
            "skills": [],
            "commands": [],
            "mcp_servers": ["design-playbook-preview"],
            "mcp_entrypoints": {
                "design-playbook-preview": "mcp/preview/server.py"
            },
        }
        actual = {
            **expected,
            "mcp_entrypoints": {
                "design-playbook-preview": "mcp/other/server.py"
            },
        }
        with self.assertRaisesRegex(smoke.SmokeFailure, "mcp_entrypoints mismatch"):
            smoke._assert_inventory(actual, expected, "installed plugin")

    def test_inventory_mismatch_fails_with_named_surface(self) -> None:
        expected = {
            "version": "0.10.0",
            "skills": ["one"],
            "commands": ["design-io"],
            "mcp_servers": [],
        }
        actual = {**expected, "commands": ["design-io", "extra"]}

        with self.assertRaisesRegex(smoke.SmokeFailure, "commands mismatch"):
            smoke._assert_inventory(actual, expected, "installed plugin")

    def test_scripts_drift_fails_closed(self) -> None:
        """Issue #71: the shipped scripts surface (incl. audit_preferences)
        is part of the precise inventory; a dropped module must fail the
        install smoke, not pass silently."""
        expected = {
            "version": "0.10.0",
            "skills": [],
            "commands": [],
            "scripts": ["audit_preferences", "validate_run"],
            "mcp_servers": [],
        }
        actual = {**expected, "scripts": ["validate_run"]}

        with self.assertRaisesRegex(smoke.SmokeFailure, "scripts mismatch"):
            smoke._assert_inventory(actual, expected, "installed plugin")

    def test_source_expectations_include_audit_preferences(self) -> None:
        expected = smoke._source_expectations()
        self.assertIn("audit_preferences", expected["scripts"])
        self.assertIn("validate_run", expected["scripts"])


class InstalledMetadataTests(unittest.TestCase):
    def test_reads_enabled_user_install_inside_isolated_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "claude"
            install = config / "plugins" / "cache" / "design-playbook" / "0.10.0"
            install.mkdir(parents=True)
            _write_json(
                config / "plugins" / "installed_plugins.json",
                {
                    "version": 2,
                    "plugins": {
                        smoke.PLUGIN_ID: [
                            {
                                "scope": "user",
                                "installPath": str(install),
                                "version": "0.10.0",
                                "gitCommitSha": "abc123",
                            }
                        ]
                    },
                },
            )
            _write_json(
                config / "settings.json",
                {"enabledPlugins": {smoke.PLUGIN_ID: True}},
            )

            metadata = smoke._installed_metadata(config, "0.10.0")

        self.assertTrue(metadata["enabled"])
        self.assertEqual(metadata["scope"], "user")
        self.assertEqual(metadata["git_commit_sha"], "abc123")

    def test_rejects_install_path_outside_isolated_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "claude"
            outside = root / "outside"
            outside.mkdir()
            _write_json(
                config / "plugins" / "installed_plugins.json",
                {
                    "plugins": {
                        smoke.PLUGIN_ID: [
                            {
                                "scope": "user",
                                "installPath": str(outside),
                                "version": "0.10.0",
                            }
                        ]
                    }
                },
            )
            _write_json(
                config / "settings.json",
                {"enabledPlugins": {smoke.PLUGIN_ID: True}},
            )

            with self.assertRaisesRegex(smoke.SmokeFailure, "escapes isolated"):
                smoke._installed_metadata(config, "0.10.0")


class McpProbeTests(unittest.TestCase):
    def test_initialize_and_tools_list_over_real_process_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = root / "fake_server.py"
            server.write_text(
                """import json, sys
for line in sys.stdin:
    request = json.loads(line)
    if request[\"method\"] == \"initialize\":
        result = {\"serverInfo\": {\"name\": \"design-playbook-preview\", \"version\": \"1\"}}
    else:
        result = {\"tools\": [{\"name\": \"preview_prototype\"}]}
    print(json.dumps({\"jsonrpc\": \"2.0\", \"id\": request[\"id\"], \"result\": result}), flush=True)
""",
                encoding="utf-8",
            )
            _write_json(
                root / ".mcp.json",
                {
                    "mcpServers": {
                        "design-playbook-preview": {
                            "command": sys.executable,
                            "args": ["${CLAUDE_PLUGIN_ROOT}/fake_server.py"],
                        }
                    }
                },
            )

            result = smoke._probe_mcp(
                root,
                "design-playbook-preview",
                "preview_prototype",
                env=dict(),
                cwd=root,
                timeout=10,
            )

        self.assertEqual(result["tools"], ["preview_prototype"])


class EvidenceTests(unittest.TestCase):
    def test_writes_bounded_json_and_markdown(self) -> None:
        result = {
            "schema_version": 1,
            "status": "pass",
            "started_at": "2026-08-04T00:00:00+00:00",
            "completed_at": "2026-08-04T00:01:00+00:00",
            "source": smoke.DEFAULT_SOURCE,
            "marketplace_head": "abc123",
            "expected": {"version": "0.10.0"},
            "checks": [
                {"name": "installed inventory", "status": "pass", "detail": "8 | 4 | 2"}
            ],
            "installed": {
                "version": "0.10.0",
                "enabled": True,
                "inventory": {
                    "skills": list(range(8)),
                    "commands": list(range(4)),
                    "mcp_servers": list(range(2)),
                },
            },
            "npm": {
                "version": "0.10.0",
                "shasum": "deadbeef",
                "inventory": {
                    "skills": list(range(8)),
                    "commands": list(range(4)),
                    "mcp_servers": list(range(2)),
                },
            },
            "temporary_root": {"path": "/tmp/x", "retained": False},
            "error": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = smoke.write_evidence(result, Path(tmp))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = md_path.read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "pass")
        self.assertIn("**Status:** **PASS**", markdown)
        self.assertIn("8 \\| 4 \\| 2", markdown)
        self.assertIn("Shasum: `deadbeef`", markdown)

    def test_cleanup_updates_retention_after_evidence_can_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owned"
            path.mkdir()
            result = {
                "temporary_root": {
                    "path": str(path),
                    "retained": True,
                    "owned": True,
                },
                "warnings": [],
            }

            smoke.cleanup_temporary_root(result)

            self.assertFalse(path.exists())
            self.assertFalse(result["temporary_root"]["retained"])
            self.assertEqual(result["warnings"], [])

    def test_cleanup_failure_is_warning_not_smoke_failure(self) -> None:
        result = {
            "temporary_root": {
                "path": "fixture-path",
                "retained": True,
                "owned": True,
            },
            "warnings": [],
        }
        with mock.patch.object(smoke.shutil, "rmtree", side_effect=OSError("busy")):
            smoke.cleanup_temporary_root(result)

        self.assertTrue(result["temporary_root"]["retained"])
        self.assertIn("cleanup failed", result["warnings"][0])


class OrchestrationTests(unittest.TestCase):
    def _fake_command(self, expected: dict, work_root: Path):
        def run(
            cmd: list[str],
            *,
            env: dict[str, str] | None = None,
            cwd: Path | None = None,
            timeout: int = 180,
            input_text: str | None = None,
        ) -> subprocess.CompletedProcess[str]:
            del timeout, input_text
            stdout = ""
            if cmd[1:] == ["--version"]:
                stdout = "fixture-version\n"
            elif cmd[1:4] == ["plugin", "marketplace", "add"]:
                assert env is not None
                config = Path(env["CLAUDE_CONFIG_DIR"])
                market = config / "plugins" / "marketplaces" / smoke.MARKETPLACE_NAME
                market.mkdir(parents=True)
                _write_json(
                    config / "plugins" / "known_marketplaces.json",
                    {
                        smoke.MARKETPLACE_NAME: {
                            "source": {"source": "git", "url": smoke.DEFAULT_SOURCE},
                            "installLocation": str(market),
                        }
                    },
                )
            elif cmd[1:3] == ["plugin", "install"]:
                assert env is not None
                config = Path(env["CLAUDE_CONFIG_DIR"])
                install = (
                    config / "plugins" / "cache" / "design-playbook" / expected["version"]
                )
                shutil.copytree(smoke.PKG, install)
                _write_json(
                    config / "plugins" / "installed_plugins.json",
                    {
                        "plugins": {
                            smoke.PLUGIN_ID: [
                                {
                                    "scope": "user",
                                    "installPath": str(install),
                                    "version": expected["version"],
                                    "gitCommitSha": "fixture-sha",
                                }
                            ]
                        }
                    },
                )
                settings_path = config / "settings.json"
                settings = _write_settings_source(settings_path)
                settings["enabledPlugins"] = {smoke.PLUGIN_ID: True}
                _write_json(settings_path, settings)
            elif cmd[0] == "git":
                stdout = "fixture-sha\n"
            elif cmd[0] == "npm" and cmd[1:3] == ["install", "--ignore-scripts"]:
                assert cwd is not None
                target = cwd / "node_modules" / smoke.NPM_PACKAGE
                shutil.copytree(smoke.PKG, target)
            elif cmd[0] == "npm" and cmd[1:3] == [
                "view",
                f"{smoke.NPM_PACKAGE}@{expected['version']}",
            ]:
                stdout = json.dumps(
                    {
                        "version": expected["version"],
                        "dist.shasum": "fixture-sum",
                        "dist.tarball": "https://registry.example/pkg.tgz",
                    }
                )
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

        return run

    def test_mocked_full_flow_passes_and_collects_all_surfaces(self) -> None:
        expected = smoke._source_expectations()
        with tempfile.TemporaryDirectory() as tmp:
            work_root = Path(tmp) / "work"
            config = smoke.SmokeConfig(
                version=expected["version"],
                source=smoke.DEFAULT_SOURCE,
                output_dir=Path(tmp) / "evidence",
                claude_bin="claude",
                npm_bin="npm",
                git_bin="git",
            )
            fake = self._fake_command(expected, work_root)
            with mock.patch.object(smoke, "_run_command", side_effect=fake), mock.patch.object(
                smoke,
                "_probe_mcp",
                side_effect=lambda _root, name, tool, **_kwargs: {
                    "server": name,
                    "tools": [tool],
                },
            ):
                result = smoke.run_smoke(config, temp_root=work_root)

        self.assertEqual(result["status"], "pass", result.get("error"))
        self.assertEqual(result["marketplace_head"], "fixture-sha")
        self.assertEqual(result["npm"]["shasum"], "fixture-sum")
        self.assertEqual(len(result["installed"]["mcp"]), 2)
        self.assertFalse([c for c in result["checks"] if c["status"] != "pass"])

    def test_cli_version_mismatch_still_writes_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            exit_code = smoke.main(
                ["--version", "9.9.9", "--output-dir", str(output)]
            )
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertIn("requested version 9.9.9", payload["error"])

    def test_cli_failure_is_printable_on_gbk_console(self) -> None:
        result = {
            "schema_version": 1,
            "status": "fail",
            "started_at": "2026-08-07T00:00:00+00:00",
            "completed_at": "2026-08-07T00:00:01+00:00",
            "source": smoke.DEFAULT_SOURCE,
            "expected": {"version": smoke._source_expectations()["version"]},
            "runtime": {},
            "checks": [],
            "installed": None,
            "npm": None,
            "temporary_root": {"path": "", "retained": False, "owned": False},
            "warnings": [],
            "error": "marketplace failed: \u2718 clone error",
        }
        stdout_bytes = io.BytesIO()
        stdout = io.TextIOWrapper(stdout_bytes, encoding="gbk", errors="strict")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            smoke, "run_smoke", return_value=result
        ), mock.patch.object(sys, "stdout", stdout):
            output = Path(tmp) / "evidence"
            exit_code = smoke.main(["--output-dir", str(output)])
            stdout.flush()
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))

        console = stdout_bytes.getvalue().decode("gbk")
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"], "marketplace failed: \u2718 clone error")
        self.assertIn(r"\u2718 clone error", console)

    def test_failure_is_recorded_in_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_root = Path(tmp) / "work"
            config = smoke.SmokeConfig(
                version=smoke._source_expectations()["version"],
                source=smoke.DEFAULT_SOURCE,
                output_dir=Path(tmp) / "evidence",
            )

            def fail_marketplace(cmd: list[str], **_kwargs):
                if "marketplace" in cmd:
                    raise smoke.SmokeFailure("fixture marketplace failure")
                return subprocess.CompletedProcess(cmd, 0, stdout="fixture\n", stderr="")

            with mock.patch.object(smoke, "_run_command", side_effect=fail_marketplace):
                result = smoke.run_smoke(config, temp_root=work_root)

        self.assertEqual(result["status"], "fail")
        self.assertIn("fixture marketplace failure", result["error"])
        self.assertEqual(result["checks"][-1]["status"], "fail")


def _write_settings_source(path: Path) -> dict:
    payload = {
        "extraKnownMarketplaces": {
            smoke.MARKETPLACE_NAME: {
                "source": {"source": "git", "url": smoke.DEFAULT_SOURCE}
            }
        }
    }
    _write_json(path, payload)
    return payload


if __name__ == "__main__":
    unittest.main()
