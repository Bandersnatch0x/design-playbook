"""Deterministic extra-project replay, not a human approval or external trial.

Real CLI, Console process/browser, capture Provider, validators and handoff.
Only the project, repair, review and confirmation inputs are test fixtures.
Missing Chromium is an error, not a successful skip.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
FIXTURE = Path(__file__).parent / "fixtures" / "operator-project"
sys.path.insert(0, str(PKG))

from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from mcp.run_console.test_http_server import _make_root, _tree_digest  # noqa: E402

COMMAND_TIMEOUT = 90  # Handoff includes five real browser captures.
STAMP = "2026-09-07T00:00:00Z"
CAPTURE_CODE = (
    "import json,sys; "
    "from design_playbook.mcp.evidence.capture_runtime import execute_capture_plan; "
    "print(json.dumps(execute_capture_plan(json.load(sys.stdin))))"
)


def _command(project: Path, *args: str, data: dict | None = None) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", *map(str, args)],
        cwd=project, capture_output=True, text=True, encoding="utf-8",
        input=json.dumps(data) if data is not None else None,
        env={**os.environ, "PYTHONPATH": str(PKG), "PYTHONDONTWRITEBYTECODE": "1",
             "DESIGN_PLAYBOOK_RUN_ROOT": str(project / ".scratch" / "operator-run")},
        timeout=COMMAND_TIMEOUT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _cli(project: Path, name: str, run: Path) -> dict:
    return json.loads(_command(project, PKG / "scripts" / name, run, "--json"))


def _review(run: Path, *, repaired: bool) -> None:
    """Fixture review inputs are written only after browser assertions succeed."""
    ledger = "\n\n".join(
        f"criterion: L6.{n}\nrequired: inbox path P{n}\n"
        f"observed: evidence/L6.{n}.png\n"
        f"result: {'blocked' if n == 2 and not repaired else 'pass'}"
        for n in (1, 2, 3)
    )
    finding = (
        "issue: clear all has no confirmation\nsource: L6.2\n"
        "fix: add consequence confirmation and preserve tasks on cancel\n"
        "severity: S3\ndisposition: blocking"
    )
    closure = (
        "## Recirculate closure trail\n\n"
        "- closes: clear all has no confirmation -> reopen `spec L6.2` -> "
        "fix: explicit confirmation -> re-eval: cancel preserves tasks, "
        "confirm clears -> **0 blocking**\n"
        if repaired else
        "invalidated:\n  - criterion: L6.2\n    artifacts: [evidence/L6.2.png]\n"
        "    reason: destructive action needs repair and re-capture\n"
    )
    (run / "point-back.md").write_text(
        "# Automated review fixture\n\naudited: true\n\n"
        "Not human approval, model judgment, or external trial evidence.\n\n"
        f"## Evidence ledger\n\n```text\n{ledger}\n```\n\n"
        f"## Findings\n\n```text\n{finding}\n```\n\n{closure}\n"
        "## Coverage statement\n\n必审: inbox paths 3/3\n未审: visual taste\n\n"
        "## Limitations\n\nSynthetic review/confirmation inputs; browser behavior only.\n\n"
        f"## Verdict\n\n**{'Pass' if repaired else 'Recirculate'}.**\n",
        encoding="utf-8",
    )


def _confirm_fixture(run: Path, html: bytes) -> None:
    (run / "decision-report.md").write_text(
        "# Simulated approval input\nAutomated test fixture, not real approval.\n",
        encoding="utf-8",
    )
    (run / "preview" / "round-1.html").write_bytes(html)
    record = {
        "round": 1, "report_ref": "decision-report.md", "confirmed": True,
        "floor_pass": True, "selected_options": ["确认通过"],
        "feedback": "Simulated test input; not a human confirmation.",
        "timestamp": STAMP, "prototype_path": "preview/round-1.html",
        "prototype_html_hash": prototype_html_digest(html),
        "decision_id": "automated-fixture-1",
    }
    (run / "preview" / "confirm-round-1.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8",
    )


def _capture_paths(project: Path, run: Path, *, repaired: bool) -> None:
    paths = [
        [{"do": "press", "selector": "[data-complete]", "key": "Enter"}],
        [{"do": "click", "selector": "#clear"}],
        [{"do": "click", "selector": "#fail"}, {"do": "click", "selector": "#retry"}],
    ]
    # A unique selector exercises the keyboard path on the actual Fill.
    paths[0][0]["selector"] = "#tasks li:first-child [data-complete]"
    if repaired:
        paths[1].append({"do": "click", "selector": "#confirm"})
    entries = []
    for n, actions in enumerate(paths, 1):
        result = json.loads(_command(project, "-c", CAPTURE_CODE, data={
            "schemaVersion": 1, "url": (project / "index.html").as_uri(),
            "type": "screenshot", "state": "empty" if n == 2 else "ok",
            "artifact_path": f"evidence/L6.{n}.png", "overwrite": repaired,
            "viewport": {"width": 1280, "height": 800,
                         "devicePixelRatio": 1, "colorScheme": "light"},
            "actions": actions,
        }))
        assert result["result"] == "captured", result
        assert Path(result["written_path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        entries.append({"criterion": f"L6.{n}", "artifact": f"L6.{n}.png",
                        "ts": STAMP, "request": result["request"]})
    # Manifest binding is a harness/owner action, never performed by the Provider.
    (run / "evidence" / "manifest.jsonl").write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8",
    )


@contextmanager
def _console(argv: list[str], project: Path):
    """Execute exactly the explicit argv emitted by run-status; no shell parsing."""
    process = subprocess.Popen(
        argv, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    lines = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        line = lines.get(timeout=15)
        match = re.fullmatch(r"Run console: (http://127\.0\.0\.1:\d+) token: ([\w-]+)\s*", line)
        assert match, "Console failed to emit its launch receipt"
        yield match.group(1), match.group(2)
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stdout.close()


def _exercise_inbox(page) -> None:
    page.locator("[data-complete]").first.press("Enter")
    expect(page.locator("#summary")).to_have_text("1 pending, 1 done")
    expect(page.locator("[data-complete]").nth(1)).to_be_focused()
    page.locator("#clear").click()
    expect(page.locator("#confirmation")).to_be_visible()
    expect(page.locator("#tasks li")).to_have_count(2)
    page.locator("#cancel").click()
    expect(page.locator("#tasks li")).to_have_count(2)
    expect(page.locator("#clear")).to_be_focused()
    page.locator("#clear").click()
    page.locator("#confirm").click()
    expect(page.locator("#empty")).to_be_visible()
    expect(page.locator("#clear")).to_be_hidden()
    expect(page.locator("#add")).to_be_focused()
    page.locator("#add").click()
    expect(page.locator("#tasks li")).to_have_count(1)
    page.locator("#fail").click()
    expect(page.locator("#error")).to_be_visible()
    page.locator("#retry").click()
    expect(page.locator("#error")).to_be_hidden()
    page.locator("[data-complete]").press("Space")
    expect(page.locator("#summary")).to_have_text("0 pending, 1 done")


def test_extra_project_blocker_to_repaired_handoff(tmp_path: Path) -> None:
    project = tmp_path / "external project with spaces"
    shutil.copytree(FIXTURE, project)
    run = _make_root(project / ".scratch", "operator-run")
    shutil.copyfile(project / "spec.md", run / "spec.md")
    (run / "plan.md").write_text(
        "<!-- run-profile: v1 -->\n\n```yaml\ntier: P2\n"
        f"confirmed_by: user (simulated fixture, not real approval) + {STAMP}\nskipped: []\nupgrades: []\n```\n\n"
        "## Scope\nInbox paths P1–P3 only.\n\n"
        "## Intent mapping\nComplete/clear/retry → L6.1/L6.2/L6.3.\n\n"
        "## Presentation input\nSingle page, native controls, no external assets.\n\n"
        "fill: ../../index.html\n", encoding="utf-8",
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        try:
            app = context.new_page()
            app.goto((project / "index.html").as_uri())
            app.locator("#clear").click()
            expect(app.locator("#tasks li")).to_have_count(0)
            expect(app.locator("#confirmation")).to_be_hidden()
            _capture_paths(project, run, repaired=False)
            _review(run, repaired=False)
            pending = _cli(project, "run_handoff.py", run)
            assert pending["verdict"] == "Pending"
            assert Path(pending["index_html"]).is_file()
            _confirm_fixture(run, (project / "index.html").read_bytes())
            blocked = _cli(project, "run_handoff.py", run)
            assert blocked["verdict"] == "Recirculate"

            before = _tree_digest(project)
            status = _cli(project, "run_status.py", run)
            assert status["verdict"] == "Recirculate"
            assert status["invalidated_evidence"] is True
            continuation = status["continuation"]
            assert continuation["next_action"]["owner"]["actor"] == "agent"
            assert continuation["open_console"]["eligible"] is True
            assert Path(continuation["open_console"]["argv"][2]) == run
            assert _tree_digest(project) == before
            with _console(continuation["open_console"]["argv"], project) as (origin, token):
                context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
                console = context.new_page()
                console.goto(f"{origin}/#token={token}")
                expect(console.locator("#view-ready")).to_be_visible()
                assert console.url == f"{origin}/"
                packet = console.locator("#section-repair-packet")
                expect(packet).to_contain_text("clear all has no confirmation")
                expect(packet).to_contain_text("L6.2")
                # The owner exposes the flag, but no detailed set/resume target.
                # The derived packet must report those gaps, not mine source prose.
                expect(packet).to_contain_text("The snapshot does not project an invalidated-evidence set.")
                expect(packet).to_contain_text("The snapshot does not project an explicit resume stage;")
                packet.get_by_role("button", name=re.compile("Copy.*command", re.I)).click()
                assert console.evaluate("navigator.clipboard.readText()") == \
                    continuation["next_action"]["copyable_agent_command"]
                assert _tree_digest(project) == before

                # Deterministic test repair, not Console execution or agent generation.
                fill = project / "index.html"
                fill.write_text(fill.read_text(encoding="utf-8").replace(
                    "const requireConfirmation = false;", "const requireConfirmation = true;",
                ), encoding="utf-8")
                app.reload()
                _exercise_inbox(app)
                _capture_paths(project, run, repaired=True)
                _review(run, repaired=True)
                read_boundary = _tree_digest(project)
                console.locator("#refresh-button").click()
                expect(console.locator("#fact-grid .fact").nth(1)).to_contain_text("Pass")
                expect(console.locator("#fact-grid .fact").nth(3)).to_contain_text("run-operator")
                assert _tree_digest(project) == read_boundary
                console.screenshot(path=str(project / "console-complete.png"), full_page=True)

            strict = _command(
                project, PKG / "scripts" / "validate_run.py",
                run / "spec.md", run / "point-back.md", "--run-root", run,
                "--preview-dir", run / "preview", "--evidence-dir", run / "evidence",
                "--decision-report", run / "decision-report.md",
                "--require-preview", "--require-evidence", "--strict",
            )
            assert "RUN OK" in strict
            status = _cli(project, "run_status.py", run)
            assert status["verdict"] == "Pass"
            assert status["continuation"]["blocker"] is None
            point_back = (run / "point-back.md").read_bytes()
            handoff = _cli(project, "run_handoff.py", run)
            assert handoff["verdict"] == "Pass"
            assert (run / "point-back.md").read_bytes() == point_back
            assert Path(handoff["deliverable_html"]).read_bytes() == fill.read_bytes()
            with zipfile.ZipFile(handoff["zip_path"]) as archive:
                assert any(archive.read(name) == fill.read_bytes() for name in archive.namelist())
            captures = list((Path(handoff["out_dir"]) / "snapshots").glob("*.png"))
            assert len(captures) == 5
            assert all(p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for p in captures)
            app.goto(Path(handoff["deliverable_html"]).as_uri())
            _exercise_inbox(app)
            (project / "replay-result.json").write_text(json.dumps({
                "recordType": "automated-regression", "externalTrial": False,
                "confirmation": "simulated fixture, not human approval",
                "states": [pending["verdict"], blocked["verdict"], handoff["verdict"]],
                "authority": handoff["authority"],
                "confirmationSource": handoff["confirmationSource"],
                "fillSha256": hashlib.sha256(fill.read_bytes()).hexdigest(),
                "captureCount": len(captures),
            }, indent=2), encoding="utf-8")
        finally:
            context.close()
            browser.close()
