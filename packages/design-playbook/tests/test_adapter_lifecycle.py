"""Adapter lifecycle check — T-023/T-024 detector semantics (spec 2026-09-19).

Drift means: re-running ``npx design-playbook init <agent>`` with the
installed package would change the file. Only marker-bearing files are
judged; the check is read-only and report-only.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.adapter_matrix import MATRIX  # noqa: E402
from design_playbook.scripts.doctor import (  # noqa: E402
    _adapter_lifecycle_check,
    _lifecycle_findings,
    _normalize_generation,
    run_checks,
)
from design_playbook.scripts.generate_adapter import render, render_entries  # noqa: E402

NON_NATIVE = [row.agent for row in MATRIX if not row.native]

_MARKER_SUB = re.compile(r"generated-by design-playbook v\d[^\s\"']*")


def _init(tmp_path: Path, agent: str) -> None:
    render(agent, out_dir=tmp_path, dry_run=False)


def _check(tmp_path: Path) -> dict:
    return _adapter_lifecycle_check(tmp_path, "9.9.9")


def _strip_marker_lines(root: Path, rel: str) -> None:
    path = root / rel
    kept = [
        line + "\n"
        for line in path.read_text(encoding="utf-8").splitlines()
        if "generated-by design-playbook" not in line
    ]
    path.write_text("".join(kept), encoding="utf-8", newline="\n")


def _retag_version(root: Path, version: str) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "generated-by design-playbook" in text:
            path.write_text(
                _MARKER_SUB.sub(f"generated-by design-playbook v{version}", text),
                encoding="utf-8",
                newline="\n",
            )


class TestRenderEntriesSeam:
    def test_matches_render_manifest(self, tmp_path: Path) -> None:
        manifest = render("windsurf", out_dir=tmp_path, dry_run=True)
        _version, _out, entries = render_entries("windsurf", tmp_path)
        assert manifest["version"] == _version
        assert [(f["path"], f["sha256"]) for f in manifest["files"]] == [
            (rel, hashlib.sha256(c.encode("utf-8")).hexdigest())
            for rel, c in entries
        ]

    def test_unknown_agent_valueerror(self) -> None:
        with pytest.raises(ValueError, match="unknown agent"):
            render_entries("no-such-agent")

    def test_native_agent_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="native"):
            render_entries("claude-code")


class TestDetectorSemantics:
    def test_fresh_init_is_clean(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["level"] == "ok"
        detail = check["detail"]
        assert detail["status"] == "scanned"
        assert detail["counts"]["drifted"] == 0
        assert detail["counts"]["orphaned"] == 0
        assert detail["counts"]["clean"] > 0

    def test_tampered_body_is_drifted(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        victim = tmp_path / ".windsurf" / "rules" / "design-playbook.md"
        victim.write_text(
            victim.read_text(encoding="utf-8") + "\ntampered line\n",
            encoding="utf-8",
            newline="\n",
        )
        check = _check(tmp_path)
        assert check["ok"] is False
        assert check["level"] == "degraded"
        finding = next(
            f for f in check["detail"]["files"] if f["path"].endswith("design-playbook.md")
        )
        assert finding["cls"] == "drifted"
        assert finding["agent"] == "windsurf"
        assert finding["repair"] == "npx design-playbook init windsurf"
        assert "npx design-playbook init windsurf" in check["repair"]

    def test_version_only_staleness_is_clean(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        _retag_version(tmp_path, "0.0.1")
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["counts"]["drifted"] == 0
        marker_versions = {
            f["marker_version"] for f in check["detail"]["files"]
        }
        # No findings are recorded for clean files; staleness is not drift.
        assert marker_versions == set()

    def test_version_staleness_visible_in_clean_count(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        before = _check(tmp_path)["detail"]["counts"]["clean"]
        _retag_version(tmp_path, "0.0.1")
        after = _lifecycle_findings(tmp_path, "9.9.9")
        assert after["counts"]["clean"] == before
        assert after["status"] == "scanned"

    def test_missing_file_is_absent_not_drift(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        (tmp_path / ".windsurf" / "rules" / "craft-guard.md").unlink()
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["counts"]["absent"] >= 1
        assert check["detail"]["counts"]["drifted"] == 0

    def test_marker_less_file_is_unattributed(self, tmp_path: Path) -> None:
        _init(tmp_path, "cursor")
        _strip_marker_lines(tmp_path, ".cursor/rules/ux-spec.mdc")
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["counts"]["unattributed"] >= 1
        assert check["detail"]["counts"]["drifted"] == 0

    def test_repo_without_init_skips(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["status"] == "not-initialized"

    def test_nonexistent_repo_root_reports_not_initialized(self, tmp_path: Path) -> None:
        checks = run_checks(repo_root=str(tmp_path / "does-not-exist"))
        check = next(c for c in checks if c["name"] == "adapter_lifecycle")
        assert check["ok"] is True
        assert check["detail"]["status"] == "not-initialized"

    def test_handwritten_agents_md_alone_is_not_ours(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "# my project\n\nhandwritten guidance\n", encoding="utf-8"
        )
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["status"] == "not-initialized"
        assert check["detail"]["counts"]["drifted"] == 0

    def test_orphaned_file_detected(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        orphan = tmp_path / ".windsurf" / "rules" / "zz-legacy.md"
        orphan.write_text(
            "<!-- generated-by design-playbook v0.1.0 -->\nold artifact\n",
            encoding="utf-8",
            newline="\n",
        )
        check = _check(tmp_path)
        assert check["ok"] is False
        finding = next(
            f for f in check["detail"]["files"] if f["cls"] == "orphaned"
        )
        assert finding["path"] == ".windsurf/rules/zz-legacy.md"
        assert finding["marker_version"] == "0.1.0"
        assert finding["repair"] == (
            "delete .windsurf/rules/zz-legacy.md then npx design-playbook init windsurf"
        )

    def test_crlf_renormalization_no_false_drift(self, tmp_path: Path) -> None:
        _init(tmp_path, "windsurf")
        for path in (tmp_path / ".windsurf" / "rules").glob("*.md"):
            path.write_text(
                path.read_text(encoding="utf-8").replace("\n", "\r\n"),
                encoding="utf-8",
                newline="",
            )
        check = _check(tmp_path)
        assert check["detail"]["counts"]["drifted"] == 0

    def test_shared_target_opencode_init_is_clean(self, tmp_path: Path) -> None:
        _init(tmp_path, "opencode")
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["counts"]["drifted"] == 0
        assert check["detail"]["counts"]["clean"] >= 1

    def test_shared_target_content_outside_block_preserved(self, tmp_path: Path) -> None:
        # Marker-block files preserve user content outside the block by
        # design; re-init only replaces the block region, so an edit after
        # the closing marker is not drift.
        _init(tmp_path, "opencode")
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            agents_md.read_text(encoding="utf-8") + "\nhand edit\n",
            encoding="utf-8",
            newline="\n",
        )
        check = _check(tmp_path)
        assert check["ok"] is True
        assert check["detail"]["counts"]["drifted"] == 0

    def test_shared_target_drift_reports_group_repair(self, tmp_path: Path) -> None:
        _init(tmp_path, "opencode")
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            agents_md.read_text(encoding="utf-8").replace(
                "<!-- design-playbook:end -->",
                "hand edit inside block\n<!-- design-playbook:end -->",
            ),
            encoding="utf-8",
            newline="\n",
        )
        check = _check(tmp_path)
        finding = next(f for f in check["detail"]["files"] if f["path"] == "AGENTS.md")
        assert finding["cls"] == "drifted"
        assert finding["agent"] is None
        assert "<your-agent>" in finding["repair"]
        assert "opencode" in finding["repair"]


class TestReadOnlyBoundary:
    def test_check_never_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init(tmp_path, "windsurf")

        def _boom(*args: object, **kwargs: object) -> None:
            raise AssertionError("lifecycle check must not write")

        monkeypatch.setattr(Path, "write_text", _boom)
        monkeypatch.setattr(Path, "mkdir", _boom)
        report = _lifecycle_findings(tmp_path, "9.9.9")
        assert report["status"] == "scanned"
        assert report["counts"]["drifted"] == 0


class TestFailOpenRenders:
    def test_malformed_json_merge_target_degrades_not_crashes(self, tmp_path: Path) -> None:
        _init(tmp_path, "cursor")
        (tmp_path / ".cursor" / "mcp.json").write_text("{not json", encoding="utf-8")
        check = _check(tmp_path)
        assert check["ok"] is False
        assert check["detail"]["counts"]["render_error"] == 1
        finding = next(
            f for f in check["detail"]["files"] if f["cls"] == "render_error"
        )
        assert finding["agent"] == "cursor"
        assert finding["reason"]
        assert "npx design-playbook init cursor" in finding["repair"]

    def test_invalid_utf8_marker_file_degrades_not_crashes(self, tmp_path: Path) -> None:
        _init(tmp_path, "opencode")
        (tmp_path / "AGENTS.md").write_bytes(
            b"<!-- generated-by design-playbook v0.1.0 -->\n\xff\xfe\xff"
        )
        check = _check(tmp_path)
        finding = next(
            f for f in check["detail"]["files"] if f["cls"] == "render_error"
        )
        assert finding["agent"] == "opencode"

    def test_failed_render_skips_orphan_scan_for_that_agent(self, tmp_path: Path) -> None:
        # Without a rendered path set, flagging the agent's marker'd files
        # orphaned would be a false positive — the scan must skip it.
        _init(tmp_path, "cursor")
        (tmp_path / ".cursor" / "mcp.json").write_text("[]", encoding="utf-8")
        check = _check(tmp_path)
        classes = {f["cls"] for f in check["detail"]["files"]}
        assert classes == {"render_error"}


class TestMatrixZeroFalsePositive:
    @pytest.mark.parametrize("agent", NON_NATIVE)
    def test_fresh_init_zero_false_positive(self, tmp_path: Path, agent: str) -> None:
        _init(tmp_path, agent)
        check = _check(tmp_path)
        assert check["detail"]["status"] == "scanned", agent
        assert check["ok"] is True, (agent, check["detail"]["files"])
        assert check["detail"]["counts"]["drifted"] == 0, agent
        assert check["detail"]["counts"]["orphaned"] == 0, agent
        assert check["detail"]["counts"]["clean"] > 0, agent


class TestNormalization:
    def test_normalize_generation_folds_version_and_crlf(self) -> None:
        a = "<!-- generated-by design-playbook v0.21.1 -->\nbody\r\n"
        b = "<!-- generated-by design-playbook v9.9.9 -->\nbody\n"
        assert _normalize_generation(a) == _normalize_generation(b)
