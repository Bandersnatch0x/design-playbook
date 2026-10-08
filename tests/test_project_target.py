#!/usr/bin/env python3
"""A02: the slash-side project resolver and its coverage across commands.

The resolver script is what makes "explicit project target" checkable
instead of aspirational: scope comes from adapter metadata or explicit
configuration, a user-level install must name the target every time, the
answer comes from the local service, and an offline service yields
``unavailable`` rather than an offline copy of the project.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "packages" / "design-playbook"
WORKBENCH_DIR = REPO_ROOT / "packages" / "design-playbook-workbench"
for candidate in (PLUGIN_DIR, WORKBENCH_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from design_playbook.scripts import project_target as pt  # noqa: E402
from design_playbook_workbench.launcher import start_runtime  # noqa: E402

WORKBENCH_TESTS = WORKBENCH_DIR / "tests"


def _load_workbench_harness():
    """Load the workbench test harness by path, never by package name.

    `tests` is a regular package in two plugin directories: the plugin's own
    `packages/design-playbook/tests` and the workbench's. A test that imports
    `tests.run_console` binds the shared name to the plugin package for the
    rest of the session, and any later `tests.harness` import then fails, so
    this file loads the harness from its path instead.
    """
    spec = importlib.util.spec_from_file_location(
        "dp_workbench_harness", WORKBENCH_TESTS / "harness.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HARNESS = _load_workbench_harness()

#: R02 names these commands as the project-touching surface; `doctor` is a
#: no-project help surface and must not gain a targeting requirement.
PROJECT_COMMANDS = (
    "design-io",
    "ux-spec",
    "component-distill",
    "ui-review",
    "run-review",
    "run-status",
    "run-handoff",
)
NO_PROJECT_COMMANDS = ("doctor",)
CONTRACT_MARKER = "project_target.py"


class HarnessLoadingTest(unittest.TestCase):
    """The harness must not load through the shared `tests` package name."""

    def test_harness_is_loaded_without_the_shared_tests_package_name(self) -> None:
        # tests/test_operator_continuation_e2e.py and
        # tests/test_t006_continuation_acceptance_matrix.py bind the name
        # `tests` to packages/design-playbook/tests for the rest of the
        # session, so importing the harness through that name fails late in a
        # full run. Loading it by path is the contract that keeps it working.
        source = Path(__file__).read_text(encoding="utf-8")
        # Split so this assertion does not match its own literal.
        banned = "from tests.harness" + " import"
        self.assertNotIn(banned, source)
        self.assertTrue(callable(HARNESS.http_request))


class ArgumentParsingTest(unittest.TestCase):
    def test_the_text_convention_accepts_spaces_and_cjk(self) -> None:
        parsed = pt.parse_request_arguments(
            'project="D:\\设计 项目\\alpha" request="req_01H"'
        )
        self.assertEqual(parsed["project"], "D:\\设计 项目\\alpha")
        self.assertEqual(parsed["request"], "req_01H")

    def test_unquoted_and_single_quoted_values_work(self) -> None:
        self.assertEqual(
            pt.parse_request_arguments("project=/tmp/plain request=req_2"),
            {"project": "/tmp/plain", "request": "req_2"},
        )
        self.assertEqual(
            pt.parse_request_arguments("project='/tmp/with space'"),
            {"project": "/tmp/with space"},
        )

    def test_other_text_is_ignored_and_broken_values_are_refused(self) -> None:
        parsed = pt.parse_request_arguments("please run the thing project=/tmp/p now")
        self.assertEqual(parsed, {"project": "/tmp/p"})
        with self.assertRaises(pt.TargetRefused):
            pt.parse_request_arguments('project="unterminated')

    def test_values_are_never_assembled_into_a_shell_string(self) -> None:
        parsed = pt.parse_request_arguments(r'project="/tmp/a; rm -rf /" request=x')
        # The value is carried as data: no shell is involved anywhere in
        # this module, so metacharacters stay literal.
        self.assertEqual(parsed["project"], "/tmp/a; rm -rf /")
        self.assertNotIn("shell=True", Path(pt.__file__).read_text(encoding="utf-8"))


class StaleReceiptTest(unittest.TestCase):
    def test_explicit_directory_without_request_survives_stale_service_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(pt, "read_session_record", return_value={"authority": "http://127.0.0.1:1"}), \
                 mock.patch.object(pt, "_http_get", side_effect=pt.ServiceUnavailable("offline")):
                result = pt.resolve_target(project=tmp)
                self.assertEqual(result["mode"], "offline")
                self.assertIsNone(result["project"]["projectId"])
                with self.assertRaises(pt.ServiceUnavailable):
                    pt.resolve_target(project=tmp, request_id="request-required")


class InstallScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_explicit_configuration_wins_and_is_validated(self) -> None:
        scope, root = pt.detect_install_scope(
            plugin_root=None,
            cwd=None,
            environ={"DESIGN_PLAYBOOK_INSTALL_SCOPE": "user-level"},
        )
        self.assertEqual(scope, pt.SCOPE_USER)
        self.assertIsNone(root)
        scope, root = pt.detect_install_scope(
            plugin_root=None,
            cwd=None,
            environ={
                "DESIGN_PLAYBOOK_INSTALL_SCOPE": "project-level",
                "DESIGN_PLAYBOOK_PROJECT_ROOT": str(self.base),
            },
        )
        self.assertEqual(scope, pt.SCOPE_PROJECT)
        self.assertEqual(Path(root), self.base)
        for environ in (
            {"DESIGN_PLAYBOOK_INSTALL_SCOPE": "project-level"},
            {"DESIGN_PLAYBOOK_INSTALL_SCOPE": "somewhere-else"},
        ):
            with self.subTest(environ=environ):
                with self.assertRaises(pt.TargetRefused):
                    pt.detect_install_scope(plugin_root=None, cwd=None, environ=environ)

    def test_a_project_level_install_is_recognised_from_adapter_metadata(self) -> None:
        project = self.base / "customer-app"
        (project / ".claude").mkdir(parents=True)
        (project / ".claude" / "settings.json").write_text(
            json.dumps({"plugins": ["design-playbook"]}), encoding="utf-8"
        )
        scope, root = pt.detect_install_scope(plugin_root=None, cwd=project, environ={})
        self.assertEqual(scope, pt.SCOPE_PROJECT)
        self.assertEqual(Path(root), project)

    def test_the_current_working_directory_alone_is_not_an_install_scope(self) -> None:
        empty = self.base / "unrelated"
        empty.mkdir()
        scope, root = pt.detect_install_scope(
            plugin_root=PLUGIN_DIR, cwd=empty, environ={}
        )
        self.assertEqual(scope, pt.SCOPE_USER)
        self.assertIsNone(root)

    def test_a_marker_without_this_plugin_does_not_claim_the_project(self) -> None:
        project = self.base / "other-tool"
        (project / ".claude").mkdir(parents=True)
        (project / ".claude" / "settings.json").write_text(
            json.dumps({"plugins": ["something-else"]}), encoding="utf-8"
        )
        scope, _ = pt.detect_install_scope(plugin_root=None, cwd=project, environ={})
        self.assertEqual(scope, pt.SCOPE_USER)


class ResolverIntegrationTest(unittest.TestCase):
    """The script against a real workbench service and a real record."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = self.base / "data"
        self.runtime = start_runtime(data_dir=self.data_dir, port=0)
        self.directory = self.base / "设计 项目 alpha"
        self.directory.mkdir()
        http_request = HARNESS.http_request

        session = self.runtime.session.token
        candidate = http_request(
            self.runtime,
            "/api/v1/projects/probe",
            method="POST",
            body={"path": str(self.directory)},
            token=session,
            origin=self.runtime.origin,
        ).json["candidate"]
        registered = http_request(
            self.runtime,
            "/api/v1/projects",
            method="POST",
            body={
                "path": candidate["canonicalPath"],
                "candidateId": candidate["candidateId"],
                "name": "Alpha",
                "operation": {
                    "operationId": "op_pt_register_1",
                    "payload": {"action": "register-project"},
                },
            },
            token=session,
            origin=self.runtime.origin,
        )
        assert registered.status == 200, registered.text
        self.project = registered.json["result"]
        self.session = session

    def tearDown(self) -> None:
        self.runtime.stop()
        self._tmp.cleanup()

    def test_resolution_uses_the_os_protected_record(self) -> None:
        record = pt.read_session_record(self.data_dir)
        self.assertEqual(record["authority"], self.runtime.origin)
        self.assertEqual(record["sessionToken"], self.session)
        payload = pt.resolve_target(
            project=str(self.directory), data_dir=self.data_dir
        )
        self.assertEqual(payload["project"]["projectId"], self.project["projectId"])
        self.assertEqual(payload["authority"], self.runtime.origin)

    def test_spaces_and_cjk_paths_resolve(self) -> None:
        payload = pt.resolve_target(
            project=str(self.directory), data_dir=self.data_dir
        )
        self.assertEqual(payload["project"]["name"], "Alpha")

    def test_missing_targets_and_unknown_directories_are_refused(self) -> None:
        with self.assertRaises(pt.TargetRefused) as caught:
            pt.resolve_target(data_dir=self.data_dir)
        self.assertEqual(caught.exception.code, "invalid-target")
        with self.assertRaises(pt.TargetRefused) as caught:
            pt.resolve_target(
                project=str(self.base / "not-registered"), data_dir=self.data_dir
            )
        self.assertEqual(caught.exception.code, "invalid-target")

    def test_a_disconnected_project_is_refused_not_rematched(self) -> None:
        moved = self.base / "moved"
        self.directory.rename(moved)
        with self.assertRaises(pt.TargetRefused) as caught:
            pt.resolve_target(project=str(self.directory), data_dir=self.data_dir)
        self.assertEqual(caught.exception.code, "disconnected")

    def test_an_offline_service_still_resolves_an_explicit_directory(self) -> None:
        self.runtime.stop()
        before = sorted(
            str(p.relative_to(self.data_dir)) for p in self.data_dir.rglob("*")
        )
        payload = pt.resolve_target(
            project=str(self.directory), data_dir=self.data_dir
        )
        self.assertTrue(payload["resolved"])
        self.assertEqual(payload["mode"], "offline")
        self.assertIsNone(payload["project"]["projectId"])
        self.assertEqual(
            Path(payload["project"]["canonicalPath"]), self.directory.resolve()
        )
        after = sorted(
            str(p.relative_to(self.data_dir)) for p in self.data_dir.rglob("*")
        )
        self.assertEqual(before, after)

    def test_an_offline_service_with_a_request_reports_unavailable(self) -> None:
        self.runtime.stop()
        with self.assertRaises(pt.ServiceUnavailable):
            pt.resolve_target(
                project=str(self.directory),
                request_id="req_offline",
                data_dir=self.data_dir,
            )

    def test_an_offline_service_refuses_an_unusable_directory(self) -> None:
        self.runtime.stop()
        with self.assertRaises(pt.TargetRefused) as caught:
            pt.resolve_target(
                project=str(self.base / "not-there"), data_dir=self.data_dir
            )
        self.assertEqual(caught.exception.code, "invalid-target")
        with self.assertRaises(pt.TargetRefused) as caught:
            pt.resolve_target(project="relative/dir", data_dir=self.data_dir)
        self.assertEqual(caught.exception.code, "invalid-target")

    def test_a_missing_or_stale_record_reports_unavailable(self) -> None:
        with self.assertRaises(pt.ServiceUnavailable):
            pt.read_session_record(self.base / "no-such-data-dir")
        broken = self.base / "broken-data"
        (broken / "session").mkdir(parents=True)
        (broken / "session" / "session.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(pt.ServiceUnavailable):
            pt.read_session_record(broken)

    def test_cli_exit_codes_and_json_output(self) -> None:
        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer):
            code = pt.main(
                ["--project", str(self.directory), "--data-dir", str(self.data_dir)]
            )
        self.assertEqual(code, pt.EXIT_OK)
        self.assertEqual(
            json.loads(buffer.getvalue())["project"]["projectId"],
            self.project["projectId"],
        )

        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer):
            code = pt.main(["--data-dir", str(self.data_dir)])
        self.assertEqual(code, pt.EXIT_REFUSED)
        self.assertEqual(json.loads(buffer.getvalue())["code"], "invalid-target")

        self.runtime.stop()
        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer):
            code = pt.main(
                ["--project", str(self.directory), "--data-dir", str(self.data_dir)]
            )
        self.assertEqual(code, pt.EXIT_OK)
        self.assertIsNone(json.loads(buffer.getvalue())["project"]["projectId"])

        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer):
            code = pt.main(
                [
                    "--project",
                    str(self.directory),
                    "--request",
                    "req_offline",
                    "--data-dir",
                    str(self.data_dir),
                ]
            )
        self.assertEqual(code, pt.EXIT_UNAVAILABLE)
        self.assertEqual(json.loads(buffer.getvalue())["code"], "unavailable")

    def test_cli_reads_the_slash_argument_text(self) -> None:
        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer):
            code = pt.main(
                [
                    "--arguments",
                    f'project="{self.directory}" request=""',
                    "--data-dir",
                    str(self.data_dir),
                ]
            )
        self.assertEqual(code, pt.EXIT_OK)
        self.assertEqual(
            json.loads(buffer.getvalue())["project"]["name"], "Alpha"
        )

    def test_describe_scope_reports_the_detected_form(self) -> None:
        buffer = io.StringIO()
        with mock.patch.object(sys, "stdout", buffer), mock.patch.dict(
            os.environ, {"DESIGN_PLAYBOOK_INSTALL_SCOPE": "user-level"}, clear=False
        ):
            code = pt.main(["--describe-scope"])
        self.assertEqual(code, pt.EXIT_OK)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["installScope"], "user-level")
        self.assertTrue(payload["explicitTargetRequired"])


class CommandCoverageTest(unittest.TestCase):
    def test_every_project_touching_command_states_the_same_contract(self) -> None:
        commands_dir = PLUGIN_DIR / "commands"
        for name in PROJECT_COMMANDS:
            with self.subTest(command=name):
                text = (commands_dir / f"{name}.md").read_text(encoding="utf-8")
                self.assertIn(CONTRACT_MARKER, text)
                self.assertIn("absolute-directory", text)
                self.assertIn("unavailable", text)
        missing = [
            name
            for name in PROJECT_COMMANDS
            if not (commands_dir / f"{name}.md").is_file()
        ]
        self.assertEqual(missing, [])

    def test_no_project_commands_do_not_gain_a_targeting_requirement(self) -> None:
        commands_dir = PLUGIN_DIR / "commands"
        for name in NO_PROJECT_COMMANDS:
            with self.subTest(command=name):
                text = (commands_dir / f"{name}.md").read_text(encoding="utf-8")
                self.assertNotIn(CONTRACT_MARKER, text)

    def test_the_resolver_script_ships_with_the_package(self) -> None:
        script = PLUGIN_DIR / "scripts" / "project_target.py"
        self.assertTrue(script.is_file())
        manifest = json.loads(
            (PLUGIN_DIR / "package.json").read_text(encoding="utf-8")
        )
        self.assertIn("scripts", manifest["files"])


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
