#!/usr/bin/env python3
"""Static validation for the design-playbook plugin. No dependencies.
Mirrors the static portion of docs/agents/release-checklist.md.
Exit non-zero on any failure.

See docs/agents/release-checklist.md 'Validation surfaces' for the split
between this script (static structure gate), release.py (publish gate),
and doctor.py (read-only diagnostic aggregator).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"  FAIL  {msg}")
    else:
        print(f"  ok    {msg}")


print("== JSON manifests ==")
plugin_json = PKG / ".claude-plugin" / "plugin.json"
market_json = ROOT / ".claude-plugin" / "marketplace.json"
pj = json.loads(plugin_json.read_text(encoding="utf-8")) if plugin_json.exists() else {}
mj = json.loads(market_json.read_text(encoding="utf-8")) if market_json.exists() else {}
check(bool(pj), f"plugin.json present: {plugin_json}")
check(bool(mj), f"marketplace.json present at repo root: {market_json}")
check(bool(pj.get("version")), "plugin.json has explicit semver version")
check(bool(pj.get("name")), "plugin.json has name")
check(bool(pj.get("description")), "plugin.json has description")

print("== Plugin-root layout (ADR-0006) ==")
check((PKG / "skills").is_dir(), "skills/ at plugin root")
check((PKG / "commands").is_dir(), "commands/ at plugin root")
check(not (PKG / ".claude-plugin" / "skills").exists(), "no skills/ inside .claude-plugin/")
check(not (PKG / ".claude-plugin" / "commands").exists(), "no commands/ inside .claude-plugin/")
check(not (PKG / ".claude-plugin" / "marketplace.json").exists(),
      "no in-package marketplace.json (catalog lives at repo root)")

print("== Bundled MCP adapters (marketplace install path) ==")
mcp_json = PKG / ".mcp.json"
check(mcp_json.is_file(), "plugin .mcp.json present")
if mcp_json.is_file():
    try:
        mcp = json.loads(mcp_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        mcp = {}
        check(False, f"plugin .mcp.json is valid JSON: {exc}")
    else:
        servers = mcp.get("mcpServers", {}) if isinstance(mcp, dict) else {}
        check(isinstance(servers, dict) and "design-playbook-preview" in servers,
              "plugin .mcp.json registers design-playbook-preview")
        check(isinstance(servers, dict) and "design-playbook-evidence" in servers,
              "plugin .mcp.json registers design-playbook-evidence")
        raw = mcp_json.read_text(encoding="utf-8")
        check("${CLAUDE_PLUGIN_ROOT}" in raw,
              "plugin .mcp.json uses ${CLAUDE_PLUGIN_ROOT}")
check((PKG / "mcp" / "preview" / "server.py").is_file(),
      "bundled preview runtime at mcp/preview/server.py")
check((PKG / "mcp" / "evidence" / "server.py").is_file(),
      "bundled evidence runtime at mcp/evidence/server.py")

print("== Marketplace catalog ==")
if mj:
    plugins = mj.get("plugins", [])
    check(bool(plugins), "marketplace lists >=1 plugin")
    if plugins:
        src = plugins[0].get("source", "")
        check(src.endswith("packages/design-playbook"),
              f"marketplace plugin source points at package (got {src!r})")

print("== Skill frontmatter ==")
for skill_dir in sorted((PKG / "skills").iterdir()):
    sm = skill_dir / "SKILL.md"
    check(sm.is_file(), f"{skill_dir.name}/SKILL.md exists")
    if sm.is_file():
        txt = sm.read_text(encoding="utf-8")
        fm = txt.split("---", 2)
        head = fm[1] if len(fm) >= 3 else ""
        check(bool(re.search(r"^name:\s*\S", head, re.M)), f"{skill_dir.name} has name frontmatter")
        check(bool(re.search(r"^description:\s*\S", head, re.M)), f"{skill_dir.name} has description frontmatter")

print("== Command frontmatter ==")
for cmd in sorted((PKG / "commands").glob("*.md")):
    txt = cmd.read_text(encoding="utf-8")
    fm = txt.split("---", 2)
    head = fm[1] if len(fm) >= 3 else ""
    check(bool(re.search(r"^description:\s*\S", head, re.M)), f"{cmd.name} has description frontmatter")

print("== Clean runtime surface (no upstream/vendor residue) ==")
# Attribution files (README, NOTICE) legitimately credit sources; scan runtime only.
banned = re.compile(r"cloudai|阿里云|alibaba-cloud-design|\bACD\b|\bECS\b|演示附件|manuscript|#636AF1", re.I)
attribution = {"readme.md", "notice", "license"}
hits = []
for f in PKG.rglob("*"):
    if not f.is_file() or f.suffix not in {".md", ".json", ".mjs", ".py"}:
        continue
    if f.name.lower() in attribution:
        continue  # required attribution, not residue
    try:
        if banned.search(f.read_text(encoding="utf-8")):
            hits.append(str(f.relative_to(ROOT)))
    except Exception:
        pass
check(not hits, f"no vendor residue in runtime surface (found in: {hits})" if hits else "no vendor residue in runtime surface")

print("== Native-desktop routing ==")
orchestrator = (PKG / "skills" / "design-playbook" / "SKILL.md").read_text(encoding="utf-8")
codex = (PKG / "codex" / "AGENTS.md").read_text(encoding="utf-8")
expected_order = (
    "ux-spec",
    "native-craft",
    "ui-picker",
    "fill",
    "craft-guard",
    "ui-evaluator",
)


def native_order(text: str) -> tuple[str, ...] | None:
    lines = [line for line in text.splitlines() if line.startswith("Native desktop order:")]
    if len(lines) != 1:
        return None
    seq = lines[0].split(".", 1)[0]
    return tuple(re.findall(r"`([^`]+)`", seq))


orchestrator_order = native_order(orchestrator)
codex_order = native_order(codex)
check(orchestrator_order == expected_order, "orchestrator owns conditional native route")
check(codex_order == expected_order, "Codex adapter preserves conditional native route")
check(orchestrator_order is not None and orchestrator_order == codex_order,
      "orchestrator and Codex native routes match")
web_skip = "Web and mobile Web skip `native-craft`"
check(web_skip in orchestrator and web_skip in codex,
      "orchestrator and Codex skip native-craft for Web targets")

print("== Dogfood 004 regression guards ==")


def section_between(text: str, start: str, end: str) -> str:
    """Slice body between two heading labels, robust to step renumbering.

    ``"### 5. Accept"`` matches ``"### 9. Accept"`` — the numeric step is
    optional. Returns "" if either anchor is absent or appears more than once.
    """
    def _anchor(label: str) -> str:
        m = re.match(r"^(#+\s*)", label)
        if m:
            prefix = re.escape(m.group(1))
            body = re.sub(r"^\d+\.\s*", "", label[len(m.group(1)):])
            return prefix + r"(?:\d+\.\s*)?" + re.escape(body)
        return re.escape(label)

    start_re = re.compile(_anchor(start))
    end_re = re.compile(_anchor(end))
    if len(start_re.findall(text)) != 1 or len(end_re.findall(text)) != 1:
        return ""
    _, tail = start_re.split(text, 1)
    parts = end_re.split(tail, 1)
    return parts[0] if len(parts) > 1 else ""


evaluator = (PKG / "skills" / "ui-evaluator" / "SKILL.md").read_text(encoding="utf-8")
verdict = section_between(evaluator, "### 4. Verdict", "## Recirculate map")
check(
    bool(verdict) and all(phrase in verdict for phrase in (
        "only after an explicit user decision",
        "user's statement or decision record",
        "remain in recirculate",
        "requests a decision",
    )),
    "ui-evaluator blocks unattended acceptance",
)

playbook = (PKG / "skills" / "design-playbook" / "SKILL.md").read_text(encoding="utf-8")
accept = section_between(playbook, "### 5. Accept", "## Recirculate")
check(
    bool(accept)
    and "authoritative verdict completion criterion in `ui-evaluator`" in accept
    and "explicitly accepted" not in accept,
    "orchestrator points to the authoritative evaluator verdict",
)

fill = section_between(playbook, "### 3. Fill", "### 4. Craft")
check(
    bool(fill) and all(phrase in fill for phrase in (
        "reused host component",
        "conflicts with spec L5",
        "recirculate to `spec`",
        "authoritative map in `ui-evaluator`",
    )),
    "fill routes reused-component L5 conflicts back to spec",
)

spec_template = (
    PKG / "skills" / "ux-spec" / "references" / "spec-template.md"
).read_text(encoding="utf-8")
l4 = section_between(spec_template, "## L4", "## L5")
check(
    bool(l4) and all(phrase in l4 for phrase in (
        "L4 declares control behavior only",
        "reuse / no-internal-change constraints must name exceptions",
        "conflict with L5",
    )),
    "L4 implementation constraints name L5 exceptions",
)

print("== Outcome-first run contract ==")
run_contract = section_between(playbook, "## Run contract", "## Steps")
check(
    bool(run_contract) and all(f"**{control}**" in run_contract for control in (
        "Goal", "Success", "Evidence", "Stop", "Confirm",
    )),
    "orchestrator names all five run-contract controls",
)
check(
    bool(run_contract) and all(phrase in run_contract for phrase in (
        "external, destructive, costly, or scope-expanding",
        "same blocking finding survives two repair -> re-evaluate cycles",
        "smallest next decision",
    )),
    "orchestrator defines confirmation and stop boundaries",
)

ux_spec = (PKG / "skills" / "ux-spec" / "SKILL.md").read_text(encoding="utf-8")
l6 = section_between(spec_template, "## L6", "---")
check(
    bool(l6)
    and "必备证据" in l6
    and "every L6 item" in ux_spec
    and "says what evidence will prove it" in ux_spec,
    "ux-spec binds each success criterion to required evidence",
)

run_checks = section_between(evaluator, "### 2. Run checks", "### 3. Emit point-back findings")
check(
    bool(run_checks) and all(phrase in run_checks for phrase in (
        "Record an evidence ledger",
        "result:    pass|fail|blocked|N/A",
        "unavailable required proof is `blocked`",
    )),
    "ui-evaluator requires an evidence ledger and blocks missing proof",
)
check(
    bool(verdict) and "every required evidence row passes" in verdict,
    "ui-evaluator pass requires all evidence rows",
)

print()
if failures:
    print(f"VALIDATION FAILED: {len(failures)} issue(s)")
    sys.exit(1)
print("VALIDATION PASSED")
