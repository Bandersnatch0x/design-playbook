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


def _make_fill(run_root: Path) -> None:
    fill = run_root / "fill"
    fill.mkdir(parents=True, exist_ok=True)
    (fill / "draft.md").write_text("fill artifact", encoding="utf-8")


def _make_confirm_round(run_root: Path) -> None:
    (run_root / "confirm-round-1.json").write_text("{}", encoding="utf-8")


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
    """Fake ``_run_host_command`` dispatching on cmd[0].

    claude calls go to the behavior; validate_run.py calls either return a
    canned clean result ("stub") or execute the real validator subprocess
    ("real") so the G1 contract is exercised end to end.
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
        assert cmd[1] == str(runner.VALIDATOR_SCRIPT)
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
                "'['claude', '-p']' timed out after 600 seconds"
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
                    "-p",
                    runner.SCENARIOS[SCENARIO].prompt,
                ],
            )
            isolated = Path(call["env"]["CLAUDE_CONFIG_DIR"])
            self.assertEqual(isolated, work / "claude-config")
            self.assertTrue(isolated.is_dir())
            ambient = os.environ.get("CLAUDE_CONFIG_DIR")
            if ambient:
                self.assertNotEqual(isolated.resolve(), Path(ambient).resolve())
            self.assertEqual(Path(call["cwd"]), work / "target")
            self.assertEqual(call["timeout"], 600)
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
            self.assertEqual(spec_arg.parent, work / "target" / RUN_ROOT_REL)
            for flag in runner.VALIDATOR_FORBIDDEN_FLAGS:
                self.assertNotIn(flag, cmd)
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
