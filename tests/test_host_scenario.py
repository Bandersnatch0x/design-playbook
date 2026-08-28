#!/usr/bin/env python3
"""Deterministic tests for scripts/host_scenario.py (no live host, no network)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_scenario.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "dpb_host_scenario_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module()

SCENARIO = "ux-spec-slice"
RUN_ROOT_REL = ".scratch/host-scenario-ux-spec"
UI_SCENARIO = "ui-picker-slice"
UI_RUN_ROOT_REL = ".scratch/host-scenario-ui-picker"

# A six-layer ops-alert-inbox spec that satisfies every G1 rule including the
# spec-schema: 2 deep rules (duties table, path table, full five-state matrix,
# and L6 items with Given/When/Then plus reachable (path: P<n>) references).
FIXTURE_SPEC = """<!-- spec-schema: 2 -->
# 运维告警收件箱 设计规格

## L1 一句话定义
Outcome summary: 运维告警收件箱以表格展示告警（严重度、最近出现时间），每行提供一个主"确认"操作，空态/加载/失败/无权限均有下一步动作。

## L2 页面职责
### Page duties
| Page | Duty |
| --- | --- |
| 告警收件箱 | 展示告警表格（严重度、最近出现时间），提供单行主"确认"操作 |
| 告警详情抽屉 | 展示单条告警的完整上下文，支持从这里确认 |

## L3 路径
### Paths
| Path | Steps |
| --- | --- |
| P1 | 打开收件箱 → 浏览告警表格 → 确认一条告警 |
| P2 | 打开收件箱 → 触发刷新 → 查看空态或错误态 |

## L4 边界与非目标
- 非目标：不做告警路由规则配置，不做多选批量确认。
- Always：确认操作必须立即反馈结果。
- Never：无权限时不隐藏整页，而是给出说明与申请入口。

## L5 五态矩阵
| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| 告警收件箱 | 骨架屏 | 表格加载指示 | 告警表格与确认操作 | 错误提示与重试 | 空态引导与刷新入口 |
| 告警详情抽屉 | 抽屉骨架 | 内容加载中 | 完整告警上下文 | 加载失败与重试 | 未选中告警提示 |

## L6 验收标准
- Given 告警列表已加载 When 用户点击某行的"确认" Then 该行标记为已确认 (path: P1)
- Given 收件箱没有任何告警 When 页面加载完成 Then 显示空态引导与刷新入口 (path: P2)
- Given 告警加载请求失败 When 用户点击重试 Then 重新请求并恢复表格或再次提示错误 (path: P2)
- Given 当前账号缺少权限 When 用户打开收件箱 Then 显示无权限说明与申请入口 (path: P1)

## Worked snippet
本切片不产出实现代码。
"""

# Same spec with one L6 criterion missing its Given clause: the validator must
# report G1.missing_gwt and the scenario must fail on it.
BROKEN_SPEC = FIXTURE_SPEC.replace(
    "- Given 收件箱没有任何告警 When 页面加载完成 Then 显示空态引导与刷新入口 (path: P2)",
    "- When 页面加载完成 Then 显示空态引导与刷新入口 (path: P2)",
)

# ui-picker slice fixtures: the packaged dogfood pair is the known-good
# (spec, decision report) shape (machine-verified by tests/test_vnext_s6.py).
DOGFOOD_RUN = ROOT / "packages" / "design-playbook" / "examples" / "dogfood" / "run"
DOGFOOD_SPEC_BYTES = (DOGFOOD_RUN / "spec.md").read_bytes()

# G10-PASSING decision report for the dogfood spec, ground-truthed through
# the runner's exact invocation shape:
#   validate_run.py --format json <dogfood spec.md> <runner._point_back_stub
#   stub> --decision-report <this report> --format json
# exits 0 with findings []. The verbatim packaged report needed no trimming:
# its E-tier preview-round confirmations stay legal because G10's
# _preview_link_checks disengages without --preview-dir.
DECISION_REPORT_FIXTURE = (DOGFOOD_RUN / "decision-report.md").read_text(
    encoding="utf-8"
)

# Ground-truthed broken variant: DD-0002's tier outside
# record|compare|explore trips exactly one finding, G10.invalid_tier,
# under the same invocation.
BROKEN_DECISION_REPORT = DECISION_REPORT_FIXTURE.replace(
    "id: DD-0002\ntier: explore",
    "id: DD-0002\ntier: exotic",
)
assert BROKEN_DECISION_REPORT != DECISION_REPORT_FIXTURE


def _make_fill(run_root: Path) -> None:
    fill = run_root / "fill"
    fill.mkdir(parents=True, exist_ok=True)
    (fill / "draft.md").write_text("fill artifact", encoding="utf-8")


def _make_confirm_round(run_root: Path) -> None:
    (run_root / "confirm-round-1.json").write_text("{}", encoding="utf-8")


def _make_filled_ui(run_root: Path) -> None:
    (run_root / "filled-ui.md").write_text("filled ui", encoding="utf-8")


def _make_preview_round(run_root: Path) -> None:
    preview = run_root / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    (preview / "confirm-round-1.json").write_text("{}", encoding="utf-8")


def _claude_writer(spec_text: str, *, extras=()):
    """Fake headless CLI: writes the fixture run under the target cwd."""

    def behavior(cmd, *, env, cwd, timeout):
        del env, timeout
        run_root = Path(cwd) / RUN_ROOT_REL
        (run_root / "shaping").mkdir(parents=True, exist_ok=True)
        (run_root / "spec.md").write_text(spec_text, encoding="utf-8")
        (run_root / "shaping" / "shaping-log.jsonl").write_text(
            '{"event": "request_recorded"}\n', encoding="utf-8"
        )
        for make in extras:
            make(run_root)
        return subprocess.CompletedProcess(cmd, 0, stdout="spec.md emitted", stderr="")

    return behavior


def _ui_picker_claude_writer(report_text: str, *, extras=(), mutate_spec=None):
    """Fake headless CLI for the ui-picker slice.

    Asserts at call time that the runner already seeded the dogfood spec
    into the run root (seed-before-run ordering) and that its bytes equal
    the packaged spec, then emits the decision report. ``mutate_spec``
    simulates a host that violates the declaration-input contract.
    """

    def behavior(cmd, *, env, cwd, timeout):
        del env, timeout
        run_root = Path(cwd) / UI_RUN_ROOT_REL
        seeded = run_root / "spec.md"
        assert seeded.is_file(), "seeded spec.md must exist before claude runs"
        assert seeded.read_bytes() == DOGFOOD_SPEC_BYTES, (
            "seeded spec must equal the packaged dogfood spec bytes"
        )
        if mutate_spec is not None:
            seeded.write_text(mutate_spec, encoding="utf-8")
        (run_root / "decision-report.md").write_text(report_text, encoding="utf-8")
        for make in extras:
            make(run_root)
        return subprocess.CompletedProcess(
            cmd, 0, stdout="decision-report.md emitted", stderr=""
        )

    return behavior


def _claude_returns(returncode: int, stdout: str = "", stderr: str = ""):
    def behavior(cmd, *, env, cwd, timeout):
        del env, cwd, timeout
        return subprocess.CompletedProcess(
            cmd, returncode, stdout=stdout, stderr=stderr
        )

    return behavior


def _claude_raises(exc: Exception):
    def behavior(cmd, *, env, cwd, timeout):
        del cmd, env, cwd, timeout
        raise exc

    return behavior


def _fake_host_run(claude_behavior, *, validator="stub"):
    """Fake ``_run_host_command`` dispatching on cmd[0] / cmd[1].

    claude calls go to the behavior; validate_run.py calls either return a
    canned clean result ("stub") or execute the real validator subprocess
    ("real") so the G1/G10 contract is exercised end to end; run_status.py
    calls always execute the real subprocess so the stage check is real
    too (it only reads files under the temp run root).
    """
    calls: list[dict] = []

    def run(cmd, *, env=None, cwd=None, timeout=180, input_text=None):
        calls.append(
            {
                "cmd": cmd,
                "env": env,
                "cwd": cwd,
                "timeout": timeout,
                "input_text": input_text,
            }
        )
        if cmd[0] == "claude":
            return claude_behavior(cmd, env=env, cwd=cwd, timeout=timeout)
        assert cmd[0] == sys.executable, f"unexpected command: {cmd[0]}"
        if cmd[1] == str(runner.RUN_STATUS_SCRIPT):
            return subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        assert cmd[1] == str(runner.VALIDATOR_SCRIPT), f"unexpected script: {cmd[1]}"
        if validator == "real":
            return subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        assert validator == "stub"
        return subprocess.CompletedProcess(cmd, 0, stdout="[]\n", stderr="")

    return run, calls


@contextmanager
def _host_patch(claude_behavior, *, validator="stub"):
    fake, calls = _fake_host_run(claude_behavior, validator=validator)
    with (
        mock.patch.object(runner, "_host_available", return_value="fixture-claude"),
        mock.patch.object(runner, "_run_host_command", side_effect=fake),
    ):
        yield calls


@contextmanager
def _run_main(behavior, *, validator="stub", argv=()):
    """Run main() under the faked host inside a temp evidence directory."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "evidence"
        with _host_patch(behavior, validator=validator) as calls:
            code = runner.main(["run", "--output-dir", str(output), *argv])
        payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
        markdown = (output / "result.md").read_text(encoding="utf-8")
        yield code, payload, markdown, output, calls


class PromptTests(unittest.TestCase):
    def test_prompt_embeds_default_ask_verbatim(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn(runner.DEFAULT_ASK, prompt)
        self.assertEqual(prompt.splitlines()[0], runner.DEFAULT_ASK)

    def test_prompt_pins_spec_path_and_schema_marker(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn(f"{RUN_ROOT_REL}/spec.md", prompt)
        self.assertIn("spec-schema: 2", prompt)

    def test_prompt_declares_headless_semantics(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn("headless", prompt.lower())
        self.assertIn("interactive clarifying questions cannot be answered", prompt)
        self.assertIn("explicit-risk assumption", prompt)
        self.assertIn("CP-C", prompt)
        self.assertIn("never pause waiting for input", prompt)

    def test_prompt_restricted_to_ux_spec_only(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn("`ux-spec`", prompt)
        self.assertIn("no ui-picker", prompt)
        self.assertIn("no Fill", prompt)
        self.assertIn("no preview confirm", prompt)
        self.assertIn("no code scaffolding", prompt)

    def test_prompt_pins_shaping_artifacts_and_stop_directive(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn("shaping/shaping-log.jsonl", prompt)
        self.assertIn("shaping/queue.json", prompt)
        self.assertIn("S0-S6", prompt)
        self.assertIn("Stop immediately after emitting spec.md", prompt)

    def test_prompt_points_at_shadowed_skill_protocol_file(self) -> None:
        prompt = runner.SCENARIOS[SCENARIO].prompt

        self.assertIn(
            "same-named `ux-spec` command shadows",
            prompt,
            "the Skill tool resolves design-playbook:ux-spec to the thin "
            "command body (verified on Claude Code 2.1.245), so the prompt "
            "must hand the model the SKILL.md path directly",
        )
        self.assertIn(
            (runner.PKG / "skills" / "ux-spec" / "SKILL.md").as_posix(), prompt
        )

    def test_plugin_ux_spec_command_routes_to_skill_file(self) -> None:
        command = (runner.PKG / "commands" / "ux-spec.md").read_text(encoding="utf-8")

        self.assertIn("skills/ux-spec/SKILL.md", command)
        self.assertNotIn(
            "Run skill **ux-spec**",
            command,
            "name-based delegation is self-referential: the Skill tool "
            "injects this very command body for design-playbook:ux-spec",
        )


class RegistryTests(unittest.TestCase):
    def test_list_prints_scenario_and_pack_elements(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = runner.main(["list"])

        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn(SCENARIO, output)
        self.assertIn(RUN_ROOT_REL, output)
        self.assertIn("spec.md", output)
        self.assertIn("shaping/shaping-log.jsonl", output)
        self.assertIn("fill/**", output)
        self.assertIn("confirm-round-*.json", output)
        self.assertIn("2400", output)
        self.assertIn("600", output)
        self.assertIn(str(runner.VALIDATOR_SCRIPT), output)

    def test_default_run_name_resolves_ux_spec_slice(self) -> None:
        self.assertEqual(runner.DEFAULT_SCENARIO, SCENARIO)
        self.assertIn(SCENARIO, runner.SCENARIOS)
        with _run_main(_claude_returns(1, stdout="Not logged in\n")) as (
            code,
            payload,
            *_rest,
        ):
            self.assertEqual(code, 2)
            self.assertEqual(payload["scenario"], SCENARIO)


class SkipSemanticsTests(unittest.TestCase):
    def test_absent_host_records_skip_and_runs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_root = Path(tmp) / "work"
            config = runner.HostScenarioConfig(
                scenario=SCENARIO, output_dir=Path(tmp) / "evidence"
            )
            with (
                mock.patch.object(runner, "_host_available", return_value=None),
                mock.patch.object(
                    runner,
                    "_run_host_command",
                    side_effect=AssertionError("host commands must not run on skip"),
                ),
            ):
                result = runner.run_scenario(config, temp_root=work_root)

        self.assertEqual(result["status"], "skip")
        self.assertIn("not found on PATH", result["skip_reason"])
        self.assertIsNone(result["error"])
        self.assertIsNone(result["claude"])
        statuses = {check["status"] for check in result["checks"]}
        self.assertIn("skip", statuses)
        self.assertNotIn("pass", statuses, "skip must never be silent green")

    def test_cli_skip_exits_two_and_writes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "evidence"
            with mock.patch.object(runner, "_host_available", return_value=None):
                exit_code = runner.main(["run", "--output-dir", str(output)])
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            markdown = (output / "result.md").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "skip")
        self.assertIn("## Skip reason", markdown)

    def test_not_logged_in_stdout_skips_without_validator(self) -> None:
        behavior = _claude_returns(1, stdout="Not logged in · Please run /login\n")
        with _run_main(behavior) as (code, payload, _markdown, _output, calls):
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "skip")
            self.assertIn("Not logged in", payload["skip_reason"])
            self.assertEqual(payload["exit_code"], 1)
            self.assertIn("Not logged in", payload["claude"]["stdout"])
            self.assertIsNone(payload["validator"])
            self.assertEqual(
                [call for call in calls if call["cmd"][0] == sys.executable],
                [],
                "no validator call may happen on a credential skip",
            )


class FailSemanticsTests(unittest.TestCase):
    def test_timeout_fails(self) -> None:
        behavior = _claude_raises(
            runner.SmokeFailure(
                "command failed to start/finish: claude: Command "
                "'['claude', '-p']' timed out after 2400 seconds"
            )
        )
        with _run_main(behavior) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("timed out", payload["error"])
            headless = [
                check
                for check in payload["checks"]
                if check["name"] == "headless ux-spec run"
            ]
            self.assertEqual(headless[-1]["status"], "fail")

    def test_nonzero_exit_fails_with_bounded_output(self) -> None:
        behavior = _claude_returns(3, stdout="boom output", stderr="boom error")
        with _run_main(behavior) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("claude exited 3", payload["error"])
            self.assertIn("boom output", payload["error"])
            self.assertIn("boom error", payload["error"])

    def test_not_logged_in_text_on_success_exit_is_not_a_skip(self) -> None:
        behavior = _claude_returns(0, stdout="Not logged in? Anyway, done.")
        with _run_main(behavior) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIsNone(payload["skip_reason"])
            self.assertIn("required artifact missing", payload["error"])

    def test_missing_spec_fails(self) -> None:
        with _run_main(_claude_returns(0, stdout="done")) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("required artifact missing", payload["error"])
            self.assertIn("spec.md", payload["error"])

    def test_forbidden_fill_directory_fails(self) -> None:
        behavior = _claude_writer(FIXTURE_SPEC, extras=(_make_fill,))
        with _run_main(behavior) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("forbidden artifacts present", payload["error"])
            self.assertIn("fill", payload["error"])

    def test_forbidden_confirm_round_json_fails(self) -> None:
        behavior = _claude_writer(FIXTURE_SPEC, extras=(_make_confirm_round,))
        with _run_main(behavior) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("forbidden artifacts present", payload["error"])
            self.assertIn("confirm-round-1.json", payload["error"])


class CommandShapeTests(unittest.TestCase):
    def test_temporary_root_is_resolved_long_form(self) -> None:
        with _run_main(_claude_writer(FIXTURE_SPEC)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 0)
            root = Path(payload["temporary_root"]["path"])
            self.assertEqual(
                root,
                root.resolve(),
                "the work root must be normalized to its long form: an "
                "8.3 short-name segment (e.g. AMSTER~1) makes Claude "
                "Code's sandbox deny every headless write inside the "
                "target cwd",
            )

    def test_claude_command_shape_env_cwd_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            config = runner.HostScenarioConfig(
                scenario=SCENARIO, output_dir=Path(tmp) / "evidence"
            )
            with _host_patch(_claude_writer(FIXTURE_SPEC)) as calls:
                result = runner.run_scenario(config, temp_root=work)
            self.assertEqual(result["status"], "pass", result.get("error"))
            claude_calls = [call for call in calls if call["cmd"][0] == "claude"]

            self.assertEqual(len(claude_calls), 1)
            call = claude_calls[0]
            self.assertEqual(
                call["cmd"],
                [
                    "claude",
                    "--plugin-dir",
                    str(runner.PKG),
                    "--permission-mode",
                    "acceptEdits",
                    "--allowedTools",
                    f"Read({runner.PKG.as_posix()}/**)",
                    "-p",
                    runner.SCENARIOS[SCENARIO].prompt,
                ],
            )
            isolated = Path(call["env"]["CLAUDE_CONFIG_DIR"])
            self.assertEqual(isolated, work.resolve() / "claude-config")
            self.assertTrue(isolated.is_dir())
            ambient = os.environ.get("CLAUDE_CONFIG_DIR")
            if ambient:
                self.assertNotEqual(isolated.resolve(), Path(ambient).resolve())
            self.assertEqual(Path(call["cwd"]), work.resolve() / "target")
            self.assertEqual(call["timeout"], 2400)
            self.assertEqual(call["input_text"], "")

    def test_validator_command_shape_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            config = runner.HostScenarioConfig(
                scenario=SCENARIO, output_dir=Path(tmp) / "evidence"
            )
            with _host_patch(_claude_writer(FIXTURE_SPEC)) as calls:
                result = runner.run_scenario(config, temp_root=work)
            self.assertEqual(result["status"], "pass", result.get("error"))
            validator_calls = [
                call for call in calls if call["cmd"][0] == sys.executable
            ]

            self.assertEqual(len(validator_calls), 1)
            call = validator_calls[0]
            cmd = call["cmd"]
            self.assertEqual(cmd[0], sys.executable)
            self.assertEqual(cmd[1], str(runner.VALIDATOR_SCRIPT))
            self.assertEqual(cmd[2:4], ["--format", "json"])
            spec_arg = Path(cmd[4])
            pointback_arg = Path(cmd[5])
            self.assertTrue(spec_arg.is_absolute())
            self.assertTrue(pointback_arg.is_absolute())
            self.assertEqual(spec_arg.name, "spec.md")
            self.assertEqual(pointback_arg.name, "point-back-stub.md")
            self.assertEqual(spec_arg.parent, work.resolve() / "target" / RUN_ROOT_REL)
            for flag in runner.VALIDATOR_FORBIDDEN_FLAGS:
                self.assertNotIn(flag, cmd)
            self.assertNotIn("--decision-report", cmd)
            self.assertEqual(call["cwd"], runner.ROOT)


class PointBackStubTests(unittest.TestCase):
    def test_stub_labels_one_row_per_l6_item(self) -> None:
        stub, count = runner._point_back_stub(FIXTURE_SPEC, scenario=SCENARIO)

        self.assertEqual(count, 4)
        lines = stub.splitlines()
        self.assertIn("## Verdict", lines)
        self.assertIn("Pass", lines)
        for number in range(1, 5):
            self.assertEqual(lines.count(f"criterion: L6.{number}"), 1)
        observed = [line for line in lines if line.startswith("observed:")]
        self.assertEqual(len(observed), 4)
        for line in observed:
            self.assertFalse(
                line.startswith("observed: evidence/"),
                "stub observed must not pose as bound evidence",
            )
        for field in ("issue:", "source:", "fix:", "severity:"):
            self.assertNotIn(
                f"\n{field}", stub, "the stub must carry no findings paragraphs"
            )

    def test_l6_body_ends_at_any_heading(self) -> None:
        spec = (
            "## L6 验收标准\n"
            "- Given a When b Then c (path: P1)\n"
            "\n"
            "### Notes\n"
            "- Given x When y Then z (path: P1)\n"
        )

        self.assertEqual(runner._l6_items(spec), ["Given a When b Then c (path: P1)"])


class EndToEndValidatorTests(unittest.TestCase):
    """The critical seam: the real validate_run.py judges the fake host run."""

    def test_valid_fixture_passes_real_validator(self) -> None:
        with _run_main(_claude_writer(FIXTURE_SPEC), validator="real") as (
            code,
            payload,
            markdown,
            output,
            _calls,
        ):
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["validator"]["exit_code"], 0)
            self.assertEqual(payload["validator"]["findings"], [])
            self.assertEqual(payload["validator"]["g1_findings"], [])
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["point_back"]["l6_count"], 4)
            self.assertFalse(
                [check for check in payload["checks"] if check["status"] != "pass"]
            )
            self.assertIn("**Status:** **PASS**", markdown)
            for name in (
                "result.json",
                "result.md",
                "spec.md",
                "shaping-log.jsonl",
                "point-back-stub.md",
            ):
                self.assertTrue(
                    (output / name).is_file(), f"missing evidence copy: {name}"
                )
            self.assertEqual(
                payload["artifacts"]["audit_copied"],
                ["spec.md", "shaping-log.jsonl", "point-back-stub.md"],
            )
            self.assertFalse(payload["temporary_root"]["retained"])
            self.assertFalse(Path(payload["temporary_root"]["path"]).exists())

    def test_broken_fixture_fails_with_g1_finding(self) -> None:
        with _run_main(_claude_writer(BROKEN_SPEC), validator="real") as (
            code,
            payload,
            _markdown,
            output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["validator"]["exit_code"], 1)
            rule_ids = [item["rule_id"] for item in payload["validator"]["findings"]]
            self.assertIn("G1.missing_gwt", rule_ids)
            self.assertTrue(
                any(rule.startswith("G1") for rule in rule_ids),
                f"no G1 finding recorded: {rule_ids}",
            )
            self.assertEqual(
                payload["validator"]["g1_findings"],
                [
                    item
                    for item in payload["validator"]["findings"]
                    if item["rule_id"].startswith("G1")
                ],
            )
            self.assertIn("validator findings", payload["error"])
            self.assertTrue(
                (output / "spec.md").is_file(),
                "the failing spec must still be captured as evidence",
            )


class UiPickerPromptTests(unittest.TestCase):
    def test_prompt_pins_preexisting_spec_as_declaration_input(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn(f"{UI_RUN_ROOT_REL}/spec.md", prompt)
        self.assertIn("six-layer spec", prompt)
        self.assertIn("declaration input", prompt)
        self.assertIn("do not modify it", prompt)
        self.assertIn("do not generate a new spec", prompt)

    def test_prompt_declares_headless_no_pause_semantics(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn("headless", prompt.lower())
        self.assertIn("the user is not in the loop", prompt)
        self.assertIn("never pause for confirmation", prompt)
        self.assertIn("agent-decided entries", prompt)
        self.assertIn("documented default", prompt)
        self.assertIn("DD entry with rationale", prompt)

    def test_prompt_requires_dd_entries_with_tier_rules(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn("references/decisions.md", prompt)
        self.assertIn("At least one DD entry is REQUIRED", prompt)
        self.assertIn("R-tier", prompt)
        self.assertIn("C-tier", prompt)
        self.assertIn("E-tier", prompt)
        self.assertIn("`kind: user` + `report-batch`", prompt)
        self.assertIn("adapter-absent rule", prompt)
        self.assertIn("Do NOT reference preview confirm rounds", prompt)

    def test_prompt_pins_flow_map_dd_item_shape(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn("single-line flow maps", prompt)
        self.assertIn("never indented field-style blocks", prompt)
        for section in ("candidates", "comparison.axes", "selection.rejected"):
            self.assertIn(section, prompt)
        # the copy-paste example must itself be a legal flow-map item
        self.assertIn(
            "- {id: A, source: agent, created_at: 2026-08-27T00:00:00Z,",
            prompt,
        )
        self.assertIn("Fold a long item onto following lines only at a comma", prompt)
        self.assertIn("never put ASCII commas or braces inside a value", prompt)

    def test_prompt_pins_report_path_top_block_and_stop(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn(f"{UI_RUN_ROOT_REL}/decision-report.md", prompt)
        for field in (
            "design-baseline",
            "scene",
            "density",
            "template",
            "regions",
            "components",
            "baseline-changes",
            "risks",
        ):
            self.assertIn(field, prompt)
        self.assertIn("waiver/explicit-new path", prompt)
        self.assertIn("Stop immediately after writing the decision report", prompt)

    def test_prompt_restricted_to_ui_picker_only(self) -> None:
        prompt = runner.SCENARIOS[UI_SCENARIO].prompt

        self.assertIn("`ui-picker`", prompt)
        self.assertIn("No Fill", prompt)
        self.assertIn("no preview", prompt)
        self.assertIn("no code scaffolding", prompt)
        self.assertIn("no ui-evaluator", prompt)
        self.assertIn("no craft-guard", prompt)
        self.assertNotIn("`ux-spec`", prompt)


class UiPickerRegistryTests(unittest.TestCase):
    def test_ui_picker_pack_declares_slice_elements(self) -> None:
        pack = runner.SCENARIOS[UI_SCENARIO]

        self.assertEqual(pack.run_root, UI_RUN_ROOT_REL)
        self.assertEqual(pack.spec_artifact, "spec.md")
        self.assertEqual(
            pack.seed_artifacts,
            (
                (
                    "packages/design-playbook/examples/dogfood/run/spec.md",
                    "spec.md",
                ),
            ),
        )
        self.assertEqual(pack.expected_artifacts, ("spec.md", "decision-report.md"))
        self.assertEqual(pack.audit_artifacts, ())
        self.assertEqual(
            pack.forbidden_artifacts,
            ("fill/**", "filled-ui.md", "preview/**", "confirm-round-*.json"),
        )
        self.assertEqual(pack.decision_report_artifact, "decision-report.md")
        self.assertEqual(pack.run_status_required_stages, ("decision",))
        self.assertEqual(pack.timeout_seconds, 600)
        self.assertEqual(
            pack.validator["decision_report"],
            "decision-report.md (G10 engages on DD entries; G5 stays quiet "
            "because no --preview-dir is passed)",
        )
        self.assertNotIn("--decision-report", pack.validator["forbidden_flags"])
        for flag in (
            "--run-root",
            "--shaping-dir",
            "--evidence-dir",
            "--preview-dir",
            "--strict",
        ):
            self.assertIn(flag, pack.validator["forbidden_flags"])
        self.assertEqual(set(pack.isolation), set(runner.SCENARIOS[SCENARIO].isolation))

    def test_ux_spec_pack_unchanged_by_new_fields(self) -> None:
        pack = runner.SCENARIOS[SCENARIO]

        self.assertEqual(pack.seed_artifacts, ())
        self.assertIsNone(pack.decision_report_artifact)
        self.assertEqual(pack.run_status_required_stages, ())
        self.assertNotIn("decision_report", pack.validator)
        self.assertIn("--decision-report", pack.validator["forbidden_flags"])

    def test_pack_stage_keys_must_exist_in_stages_registry(self) -> None:
        # A renamed STAGES key must fail at pack construction, not surface
        # as a live-run run-status mismatch.
        base = {
            field: getattr(runner.SCENARIOS[UI_SCENARIO], field)
            for field in (
                "run_root", "spec_artifact", "prompt", "expected_artifacts",
                "audit_artifacts", "forbidden_artifacts", "validator",
                "timeout_seconds", "isolation",
            )
        }
        with self.assertRaises(ValueError) as ctx:
            runner.ScenarioPack(
                name="bogus-slice", run_status_required_stages=("decisions",),
                **base,
            )
        self.assertIn("unknown stage keys", str(ctx.exception))
        self.assertIn("'decisions'", str(ctx.exception))

    def test_list_prints_both_scenarios(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = runner.main(["list"])

        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn(SCENARIO, output)
        self.assertIn(UI_SCENARIO, output)
        self.assertIn(UI_RUN_ROOT_REL, output)
        self.assertIn("packages/design-playbook/examples/dogfood/run/spec.md", output)
        self.assertIn("decision report:    decision-report.md", output)
        self.assertIn("run-status stages:  decision", output)
        self.assertIn("filled-ui.md", output)


class UiPickerSeedingTests(unittest.TestCase):
    def test_seed_lands_before_claude_runs_and_survives(self) -> None:
        # The fake claude asserts at call time that the seeded spec.md
        # already exists with the packaged dogfood bytes.
        with _run_main(
            _ui_picker_claude_writer(DECISION_REPORT_FIXTURE),
            argv=(UI_SCENARIO,),
        ) as (code, payload, _markdown, _output, _calls):
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "pass", payload.get("error"))
            seed_stage = [
                check
                for check in payload["checks"]
                if check["name"] == "seed declaration inputs"
            ]
            self.assertEqual(seed_stage[-1]["status"], "pass")
            self.assertEqual(seed_stage[-1]["detail"], "spec.md")
            immutability = [
                check
                for check in payload["checks"]
                if check["name"] == "seed immutability"
            ]
            self.assertEqual(immutability[-1]["status"], "pass")

    def test_seed_mutation_fails_scenario(self) -> None:
        behavior = _ui_picker_claude_writer(
            DECISION_REPORT_FIXTURE, mutate_spec="# mutated spec\n"
        )
        with _run_main(behavior, argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("declaration input was modified", payload["error"])
            immutability = [
                check
                for check in payload["checks"]
                if check["name"] == "seed immutability"
            ]
            self.assertEqual(immutability[-1]["status"], "fail")
            self.assertIsNone(
                payload["validator"],
                "a mutated declaration input must fail before any gate runs",
            )

    def test_missing_decision_report_fails(self) -> None:
        with _run_main(_claude_returns(0, stdout="done"), argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("required artifact missing", payload["error"])
            self.assertIn("decision-report.md", payload["error"])


class UiPickerCommandShapeTests(unittest.TestCase):
    def test_ui_picker_claude_command_shape_env_cwd_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            config = runner.HostScenarioConfig(
                scenario=UI_SCENARIO, output_dir=Path(tmp) / "evidence"
            )
            with _host_patch(
                _ui_picker_claude_writer(DECISION_REPORT_FIXTURE)
            ) as calls:
                result = runner.run_scenario(config, temp_root=work)
            self.assertEqual(result["status"], "pass", result.get("error"))
            claude_calls = [call for call in calls if call["cmd"][0] == "claude"]

            self.assertEqual(len(claude_calls), 1)
            call = claude_calls[0]
            self.assertEqual(
                call["cmd"],
                [
                    "claude",
                    "--plugin-dir",
                    str(runner.PKG),
                    "--permission-mode",
                    "acceptEdits",
                    "--allowedTools",
                    f"Read({runner.PKG.as_posix()}/**)",
                    "-p",
                    runner.SCENARIOS[UI_SCENARIO].prompt,
                ],
            )
            isolated = Path(call["env"]["CLAUDE_CONFIG_DIR"])
            self.assertEqual(isolated, work.resolve() / "claude-config")
            self.assertTrue(isolated.is_dir())
            self.assertEqual(Path(call["cwd"]), work.resolve() / "target")
            self.assertEqual(call["timeout"], 600)
            self.assertEqual(call["input_text"], "")

    def test_ui_picker_validator_and_run_status_command_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            config = runner.HostScenarioConfig(
                scenario=UI_SCENARIO, output_dir=Path(tmp) / "evidence"
            )
            with _host_patch(
                _ui_picker_claude_writer(DECISION_REPORT_FIXTURE)
            ) as calls:
                result = runner.run_scenario(config, temp_root=work)
            self.assertEqual(result["status"], "pass", result.get("error"))
            run_root = work.resolve() / "target" / UI_RUN_ROOT_REL
            validator_calls = [
                call
                for call in calls
                if call["cmd"][0] == sys.executable
                and call["cmd"][1] == str(runner.VALIDATOR_SCRIPT)
            ]
            self.assertEqual(len(validator_calls), 1)
            cmd = validator_calls[0]["cmd"]
            self.assertEqual(cmd[0], sys.executable)
            self.assertEqual(cmd[1], str(runner.VALIDATOR_SCRIPT))
            self.assertEqual(cmd[2:4], ["--format", "json"])
            spec_arg = Path(cmd[4])
            pointback_arg = Path(cmd[5])
            self.assertEqual(cmd[6], "--decision-report")
            report_arg = Path(cmd[7])
            self.assertEqual(len(cmd), 8)
            for arg in (spec_arg, pointback_arg, report_arg):
                self.assertTrue(arg.is_absolute())
            self.assertEqual(spec_arg.name, "spec.md")
            self.assertEqual(pointback_arg.name, "point-back-stub.md")
            self.assertEqual(report_arg.name, "decision-report.md")
            self.assertEqual(spec_arg.parent, run_root)
            self.assertEqual(report_arg.parent, run_root)
            for flag in (
                "--run-root",
                "--shaping-dir",
                "--evidence-dir",
                "--preview-dir",
                "--strict",
                "--require-preview",
                "--require-evidence",
                "--require-coverage",
            ):
                self.assertNotIn(flag, cmd)
            self.assertEqual(validator_calls[0]["cwd"], runner.ROOT)

            run_status_calls = [
                call
                for call in calls
                if call["cmd"][0] == sys.executable
                and call["cmd"][1] == str(runner.RUN_STATUS_SCRIPT)
            ]
            self.assertEqual(len(run_status_calls), 1)
            rs_cmd = run_status_calls[0]["cmd"]
            self.assertEqual(rs_cmd[2], "--json")
            self.assertEqual(Path(rs_cmd[3]), run_root)
            self.assertEqual(run_status_calls[0]["cwd"], runner.ROOT)


class RunStatusStageTests(unittest.TestCase):
    """Unit tests for the run-status stage helper against the REAL
    run_status.py subprocess (two fixture run roots)."""

    def test_helper_reports_decision_stage_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            (run_root / "decision-report.md").write_text("# report\n", encoding="utf-8")
            present = runner._require_run_status_stages(run_root, ("decision",))

        self.assertIn("spec", present)
        self.assertIn("decision", present)

    def test_helper_fails_when_required_stage_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            with self.assertRaises(runner.SmokeFailure) as ctx:
                runner._require_run_status_stages(run_root, ("decision",))

        message = str(ctx.exception)
        self.assertIn("missing", message)
        self.assertIn("decision", message)


class UiPickerEndToEndTests(unittest.TestCase):
    """The critical seam: real validate_run.py (G1+G10) and real
    run_status.py judge the fake host's seeded-spec + decision-report run."""

    def test_ui_picker_pass_end_to_end(self) -> None:
        with _run_main(
            _ui_picker_claude_writer(DECISION_REPORT_FIXTURE),
            validator="real",
            argv=(UI_SCENARIO,),
        ) as (code, payload, markdown, output, _calls):
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["validator"]["exit_code"], 0)
            self.assertEqual(payload["validator"]["findings"], [])
            self.assertEqual(payload["validator"]["g1_findings"], [])
            self.assertEqual(payload["point_back"]["l6_count"], 3)
            self.assertFalse(
                [check for check in payload["checks"] if check["status"] != "pass"]
            )
            self.assertIn("**Status:** **PASS**", markdown)
            for name in (
                "result.json",
                "result.md",
                "spec.md",
                "decision-report.md",
                "point-back-stub.md",
            ):
                self.assertTrue(
                    (output / name).is_file(), f"missing evidence copy: {name}"
                )
            self.assertEqual(
                payload["artifacts"]["audit_copied"],
                ["spec.md", "decision-report.md", "point-back-stub.md"],
            )
            self.assertEqual(payload["run_status"]["required_stages"], ["decision"])
            self.assertIn("decision", payload["run_status"]["present_stages"])
            self.assertFalse(payload["temporary_root"]["retained"])
            self.assertFalse(Path(payload["temporary_root"]["path"]).exists())

    def test_ui_picker_broken_report_fails_with_g10_finding(self) -> None:
        with _run_main(
            _ui_picker_claude_writer(BROKEN_DECISION_REPORT),
            validator="real",
            argv=(UI_SCENARIO,),
        ) as (code, payload, _markdown, output, _calls):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["validator"]["exit_code"], 1)
            rule_ids = [item["rule_id"] for item in payload["validator"]["findings"]]
            self.assertIn("G10.invalid_tier", rule_ids)
            self.assertEqual(
                payload["validator"]["g1_findings"],
                [
                    item
                    for item in payload["validator"]["findings"]
                    if item["rule_id"].startswith("G1")
                ],
            )
            self.assertIn("validator findings", payload["error"])
            self.assertIsNone(
                payload["run_status"],
                "the run-status stage must not run when the validator fails",
            )
            for name in ("spec.md", "decision-report.md"):
                self.assertTrue(
                    (output / name).is_file(),
                    f"the failing run must still be captured as evidence: {name}",
                )


class UiPickerForbiddenTests(unittest.TestCase):
    def test_ui_picker_fill_directory_fails(self) -> None:
        behavior = _ui_picker_claude_writer(
            DECISION_REPORT_FIXTURE, extras=(_make_fill,)
        )
        with _run_main(behavior, argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("forbidden artifacts present", payload["error"])
            self.assertIn("fill", payload["error"])

    def test_ui_picker_filled_ui_md_fails(self) -> None:
        behavior = _ui_picker_claude_writer(
            DECISION_REPORT_FIXTURE, extras=(_make_filled_ui,)
        )
        with _run_main(behavior, argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("forbidden artifacts present", payload["error"])
            self.assertIn("filled-ui.md", payload["error"])

    def test_ui_picker_preview_dir_and_confirm_round_fail(self) -> None:
        behavior = _ui_picker_claude_writer(
            DECISION_REPORT_FIXTURE, extras=(_make_preview_round,)
        )
        with _run_main(behavior, argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 1)
            self.assertEqual(payload["status"], "fail")
            self.assertIn("forbidden artifacts present", payload["error"])
            self.assertIn("preview", payload["error"])
            self.assertIn("confirm-round-1.json", payload["error"])


class UiPickerSkipSemanticsTests(unittest.TestCase):
    def test_ui_picker_not_logged_in_skips_without_gates(self) -> None:
        behavior = _claude_returns(1, stdout="Not logged in · Please run /login\n")
        with _run_main(behavior, argv=(UI_SCENARIO,)) as (
            code,
            payload,
            _markdown,
            _output,
            calls,
        ):
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "skip")
            self.assertIn("Not logged in", payload["skip_reason"])
            self.assertEqual(payload["exit_code"], 1)
            self.assertIsNone(payload["validator"])
            self.assertIsNone(payload["run_status"])
            self.assertEqual(
                [call for call in calls if call["cmd"][0] == sys.executable],
                [],
                "no validator or run_status call may happen on a skip",
            )


class KeepTempTests(unittest.TestCase):
    def test_keep_retains_temp_roots(self) -> None:
        with _run_main(_claude_writer(FIXTURE_SPEC), argv=("--keep",)) as (
            code,
            payload,
            _markdown,
            _output,
            _calls,
        ):
            self.assertEqual(code, 0)
            self.assertTrue(payload["temporary_root"]["retained"])
            self.assertTrue(Path(payload["temporary_root"]["path"]).is_dir())


if __name__ == "__main__":
    unittest.main()
