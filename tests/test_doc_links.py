"""Repository documentation portability through the existing CI link gate."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_doc_links.py"
spec = importlib.util.spec_from_file_location("doc_links", SCRIPT)
assert spec and spec.loader
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


def write(root: Path, name: str, content: str = "# Example\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run_gate(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )


def symlink(root: Path, name: str, target: str, *, directory: bool = False) -> None:
    """Symlink or skip: Windows needs developer mode for either kind."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable")


@pytest.mark.parametrize("directory", [
    "docs/specs", "docs/plan", "docs/research", "docs/issues", "docs/tickets",
    "specs", "plans", "research", "issues", "tickets", ".agents/specs",
    ".claude/commands",
])
def test_planning_is_private_even_when_forced_into_git(tmp_path, directory):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, "README.md")
    write(tmp_path, f"{directory}/private.md")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."], check=True, timeout=10)
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert f"{directory}/private.md: private artifact tracked" in result.stdout


@pytest.mark.parametrize("surface", [
    "AGENTS.md", "CLAUDE.md", "CONTEXT.md", "docs/AGENTS.md", "docs/roadmap.md",
    ".github/CONTRIBUTING.md", ".github/CONTRIBUTING.zh-CN.md",
    "docs/README.md", "docs/architecture.zh.md", "docs/subsystems/runtime.zh.md",
    "docs/user/example.md", "docs/development.md", "docs/testing.md",
])
def test_new_maintained_surfaces_reject_broken_links(tmp_path, surface):
    page = write(tmp_path, surface, "[missing](missing.md)\n")
    assert page in links.collect_files(tmp_path)
    assert "broken link" in links.check_file(page, tmp_path)[0]


@pytest.mark.parametrize("target", [
    ".agents/specs/private.md", ".agents/plans/private.md",
    ".agents/research/private.md", ".agents/tickets/private.md",
    ".agents/dev-workflow.md", ".scratch/old/phase.md",
    "docs/../.agents/specs/private.md", ".agents/%73pecs/private.md",
    ".agents/plugins/personal.md",
    ".claude/commands/dev-next.md", ".claude/settings.local.json",
    "docs/specs/private.md", "docs/plans/private.md", "docs/research/private.md",
    "docs/issues/private.md", "docs/tickets/private.md", "specs/private.md",
])
@pytest.mark.parametrize("exists", [False, True])
def test_private_links_fail_even_on_author_machine(tmp_path, target, exists):
    if exists:
        write(tmp_path, links.unquote(target))
    page = write(tmp_path, "README.md", f"[required]({target})\n")
    errors = links.check_file(page, tmp_path)
    assert len(errors) == 1
    assert "private artifact" in errors[0]


def test_image_and_angle_target_cannot_bypass_private_check(tmp_path):
    page = write(tmp_path, "README.md", "![proof](<.scratch/shot.png>)\n")
    assert "private artifact image" in links.check_file(page, tmp_path)[0]


@pytest.mark.parametrize("content", [
    "[private](/.agents/specs/private.md)\n",
    "[private][plan]\n\n[plan]: .agents/specs/private.md\n",
    "![proof][plan]\n\n[plan]: /.agents/specs/private.md\n",
])
def test_other_markdown_link_forms_cannot_bypass_privacy(tmp_path, content):
    write(tmp_path, ".agents/specs/private.md")
    write(tmp_path, "README.md", content)
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "private artifact" in result.stdout


def test_local_check_can_explicitly_resolve_private_links(tmp_path):
    write(tmp_path, ".agents/specs/private.md")
    page = write(tmp_path, "README.md", "[local](.agents/specs/private.md)\n")
    assert links.check_file(page, tmp_path, public=False) == []


def test_public_catalog_literals_and_promoted_policy_are_allowed(tmp_path):
    write(tmp_path, ".agents/plugins/marketplace.json", "{}\n")
    write(tmp_path, ".claude-plugin/marketplace.json", "{}\n")
    write(tmp_path, "packages/design-playbook/.claude-plugin/plugin.json", "{}\n")
    write(tmp_path, "docs/agents/document-governance.md")
    page = write(tmp_path, "README.md", (
        "[policy](docs/agents/document-governance.md#example)\n"
        "[catalog](.agents/plugins/marketplace.json)\n"
        "[marketplace](.claude-plugin/marketplace.json)\n"
        "[plugin](packages/design-playbook/.claude-plugin/plugin.json)\n"
        "Local path: `.agents/plans/example.md`.\n"
        "```text\n[example](.scratch/example.md)\n```\n"
        "[external](https://example.org/.agents/research/)\n"
    ))
    assert links.check_file(page, tmp_path) == []


def test_historical_release_links_are_not_reinterpreted(tmp_path):
    write(tmp_path, "README.md")
    historical = write(tmp_path, "docs/releases/v0.1.md", "[old](missing.md)\n")
    assert historical not in links.collect_files(tmp_path)


@pytest.mark.parametrize(("heading", "expected"), [
    ("\U0001f310 Install on other agents", "-install-on-other-agents"),
    ("\u4e2d\u6587", "\u4e2d\u6587"),
    ("run-status / run_id", "run-status--run_id"),
])
def test_heading_slug_preserves_identifiers_but_drops_symbols(heading, expected):
    assert links.github_slug(heading) == expected


def test_git_index_rejects_forced_private_additions(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    for name in [".scratch/log.md", ".agents/personal.md", ".claude/settings.json",
                 ".agents/plugins/extra.md", ".agents/plugins/marketplace.json",
                 ".claude-plugin/marketplace.json",
                 "packages/design-playbook/.claude-plugin/plugin.json"]:
        write(tmp_path, name)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."],
                   check=True, timeout=10)
    errors = links.check_tracked_assets(tmp_path)
    assert len(errors) == 4
    assert all("private artifact tracked" in error for error in errors)
    assert not any("marketplace.json" in error for error in errors)
    assert not any("plugin.json" in error for error in errors)


def test_git_index_failure_is_visible(tmp_path):
    (tmp_path / ".git").write_text("invalid git file", encoding="utf-8")
    assert "Git index unreadable" in links.check_tracked_assets(tmp_path)[0]


def test_tracked_product_fixtures_are_not_private_planning(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".gitignore", "**/evidence/\n")
    write(tmp_path, "packages/plugin/tests/fixtures/evidence/shot.png", "fixture")
    write(tmp_path, "README.md", (
        "![fixture](packages/plugin/tests/fixtures/evidence/shot.png)\n"
    ))
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "."],
                   check=True, timeout=10)
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_fails_on_private_authority_and_does_not_write(tmp_path):
    page = write(tmp_path, "README.md", "[policy](.agents/dev-workflow.md)\n")
    before = page.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "private artifact" in result.stdout
    assert page.read_bytes() == before
    assert list(tmp_path.rglob("*")) == [page]


def test_cli_rejects_public_link_to_locally_excluded_document(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".git/info/exclude", "/docs/agents/private.md\n")
    write(tmp_path, "docs/agents/private.md")
    write(tmp_path, "README.md", "[policy](docs/agents/private.md)\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "ignored artifact link" in result.stdout


def test_cli_rejects_public_link_to_ignored_symlink_name(tmp_path):
    """The link's own name decides: resolve() hides an ignored symlink entry."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".gitignore", "ignored-link.md\n")
    write(tmp_path, "docs/inside.md")
    symlink(tmp_path, "ignored-link.md", "docs/inside.md")
    write(tmp_path, "README.md", "[inside](ignored-link.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ignored artifact link -> ignored-link.md" in result.stdout


def test_cli_rejects_public_link_below_an_ignored_symlink(tmp_path):
    """Git cannot name a path beyond the link, but it still ignores the link."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".gitignore", "linkdir\n")
    write(tmp_path, "docs/inside.md")
    symlink(tmp_path, "linkdir", "docs", directory=True)
    write(tmp_path, "README.md", "[inside](linkdir/inside.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ignored artifact link -> linkdir/inside.md" in result.stdout


def test_cli_rejects_public_link_through_symlink_to_ignored_directory(tmp_path):
    """The resolved target keeps its ignore verdict when reached through a link."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".gitignore", "realdir/\n")
    write(tmp_path, "realdir/inside.md")
    symlink(tmp_path, "alias", "realdir", directory=True)
    write(tmp_path, "README.md", "[inside](alias/inside.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "ignored artifact link -> alias/inside.md" in result.stdout


def test_cli_allows_symlinked_navigation_a_clean_checkout_still_reaches(tmp_path):
    """`linkdir/` matches directories only, so the symlink entry stays public."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".gitignore", "linkdir/\n")
    write(tmp_path, "docs/inside.md")
    symlink(tmp_path, "linkdir", "docs", directory=True)
    write(tmp_path, "README.md", "[inside](linkdir/inside.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_rejects_forced_add_of_locally_excluded_document(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".git/info/exclude", "/docs/agents/private.md\n")
    write(tmp_path, "docs/agents/private.md")
    write(tmp_path, "README.md")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-f", "docs/agents/private.md"],
                   check=True, timeout=10)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "docs/agents/private.md: private artifact tracked" in result.stdout


def test_cli_does_not_require_or_validate_personal_planning(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    write(tmp_path, ".git/info/exclude", "/.agents/\n/docs/agents/private.md\n")
    write(tmp_path, "README.md")
    write(tmp_path, "docs/agents/private.md", "[local](missing.md)\n")
    private = write(tmp_path, ".agents/specs/local.md", "No metadata; [local](missing.md)\n")
    local_command = write(tmp_path, ".claude/commands/dev-next.md", "[local](missing.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert private.exists()
    assert local_command.exists()


def test_cli_rejects_planning_in_docs_without_touching_it(tmp_path):
    write(tmp_path, "README.md")
    page = write(tmp_path, "docs/specs/private.md")
    before = page.read_bytes()
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "personal planning belongs outside docs/" in result.stdout
    assert page.read_bytes() == before


def test_cli_reports_unreadable_git_rules(tmp_path):
    write(tmp_path, ".git", "invalid git file")
    write(tmp_path, "README.md")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert "cannot classify document visibility" in result.stderr


def test_fresh_clone_policy_chain_without_local_history(tmp_path):
    surfaces = [
        "AGENTS.md",
        ".github/CONTRIBUTING.md", ".github/CONTRIBUTING.zh-CN.md",
    ]
    # Resolve the actual public entrypoint closure, not a hand-written fixture.
    pending = list(surfaces)
    copied = set()
    ignored = links.ignored_paths(ROOT, links.navigation_paths(links.collect_files(ROOT), ROOT))
    while pending:
        name = pending.pop()
        if name in copied:
            continue
        source = ROOT / name
        assert source not in ignored, f"Public dependency is ignored: {name}"
        assert source.exists(), f"Missing public dependency: {name}"
        if source.is_dir():
            (tmp_path / name).mkdir(parents=True, exist_ok=True)
            continue
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        copied.add(name)
        if source.suffix != ".md":
            continue
        text = source.read_text(encoding="utf-8")
        for pattern in (links.MD_LINK, links.MD_IMAGE, links.MD_REFERENCE):
            for match in pattern.finditer(links.strip_code(text)):
                parsed = links.urlparse(match.group(1).strip().removeprefix("<").removesuffix(">"))
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = links.resolve_navigation(source, ROOT, parsed.path)
                assert target.is_relative_to(ROOT)
                assert not links.is_local_artifact(target, ROOT)
                pending.append(target.relative_to(ROOT).as_posix())
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".scratch").exists()
    for name in copied:
        if Path(name).suffix == ".md":
            assert links.check_file(tmp_path / name, tmp_path) == []
