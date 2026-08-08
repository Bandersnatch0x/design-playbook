#!/usr/bin/env python3
"""Static validation for the design-playbook plugin. No dependencies.
Mirrors the static portion of docs/agents/release-checklist.md.
Exit non-zero on any failure.

See docs/agents/release-checklist.md 'Validation surfaces' for the split
between this script (static structure gate), release.py (publish gate),
and doctor.py (read-only diagnostic aggregator).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# scripts/ must resolve even when validate.py is imported in-process rather
# than run as `python scripts/validate.py` (mirrors doctor.py's guard).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _checks

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"  FAIL  {msg}")
    else:
        print(f"  ok    {msg}")


def _read_json(path: Path) -> dict:
    """Read a JSON manifest, returning {} on absent or malformed JSON.

    Malformed JSON records a clean FAIL line via ``check`` instead of
    crashing validate.py with a stack trace — same defensive contract as
    doctor.read_json and the inline guard at the .mcp.json block (lines
    ~50-55). Callers downstream already defend against non-dict payloads
    via isinstance checks.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        check(False, f"{path.relative_to(ROOT)} malformed JSON: {exc}")
        return {}


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
check((PKG / "mcp" / "preview" / "integrity.py").is_file(),
      "bundled preview integrity module at mcp/preview/integrity.py")
for resource_name in ("control.html", "control.css", "control.js"):
    check((PKG / "mcp" / "preview" / resource_name).is_file(),
          f"bundled preview frontend resource at mcp/preview/{resource_name}")
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

print("== Codex manifest (ADR-0009 dual-publish) ==")
# The Codex marketplace install path ships its own plugin.json + mcp.json
# under packages/design-playbook/.codex-plugin/, plus a separate catalog at
# .agents/plugins/marketplace.json. None of these are read by the Claude
# plugin loader, so a static gate is the only thing catching drift between
# the two publish surfaces. See issue 07 (secure-ship-0.4.4).
codex_plugin_json = PKG / ".codex-plugin" / "plugin.json"
codex_mcp_json = PKG / ".codex-plugin" / "mcp.json"
agents_market_json = ROOT / ".agents" / "plugins" / "marketplace.json"
cpj = _read_json(codex_plugin_json)
cmcp = _read_json(codex_mcp_json)
amj = _read_json(agents_market_json)
check(bool(cpj), f".codex-plugin/plugin.json present: {codex_plugin_json.relative_to(ROOT)}")
check(bool(cmcp), f".codex-plugin/mcp.json present: {codex_mcp_json.relative_to(ROOT)}")
check(bool(amj), f".agents marketplace.json present: {agents_market_json.relative_to(ROOT)}")

# 1) Codex plugin.json version must equal the Claude plugin.json version.
#    A bump that touches only the Claude side leaves the Codex marketplace
#    shipping a stale version — fail-fast here so the gate catches it.
codex_version = cpj.get("version") if isinstance(cpj, dict) else None
claude_version = pj.get("version") if isinstance(pj, dict) else None
check(bool(codex_version), ".codex-plugin/plugin.json has explicit semver version")
check(
    bool(codex_version) and codex_version == claude_version,
    f".codex-plugin/plugin.json version matches Claude plugin.json "
    f"(codex={codex_version!r}, claude={claude_version!r})",
)

# 2) Codex mcp.json preview/evidence target files exist on disk. The Codex
#    adapter resolves these relative to its install cwd, so a missing file
#    would surface only at runtime in a foreign agent.
if isinstance(cmcp, dict):
    codex_servers = cmcp.get("mcpServers", {})
    codex_servers = codex_servers if isinstance(codex_servers, dict) else {}
    for codex_server_name in ("design-playbook-preview", "design-playbook-evidence"):
        entry = codex_servers.get(codex_server_name)
        if not isinstance(entry, dict):
            check(False, f".codex-plugin/mcp.json registers {codex_server_name}")
            continue
        check(True, f".codex-plugin/mcp.json registers {codex_server_name}")
        raw_args = entry.get("args", [])
        args_list = raw_args if isinstance(raw_args, list) else []
        target_arg = args_list[0] if args_list and isinstance(args_list[0], str) else ""
        if not target_arg:
            check(False, f".codex-plugin/mcp.json {codex_server_name} has args[0] path")
            continue
        target_path = PKG / target_arg
        check(target_path.is_file(),
              f".codex-plugin/mcp.json {codex_server_name} target exists on disk: {target_arg}")

# 3) .agents marketplace plugins[0].source.path must resolve to a real dir.
#    Unlike the Claude marketplace, the .agents catalog intentionally has no
#    version field (issue 07); only the source path is verified here.
if isinstance(amj, dict):
    agents_plugins = amj.get("plugins", [])
    agents_plugins = agents_plugins if isinstance(agents_plugins, list) else []
    check(bool(agents_plugins), ".agents marketplace lists >=1 plugin")
    if agents_plugins and isinstance(agents_plugins[0], dict):
        agents_src = agents_plugins[0].get("source", "")
        agents_path = ""
        if isinstance(agents_src, dict):
            raw_path = agents_src.get("path", "")
            agents_path = raw_path if isinstance(raw_path, str) else ""
        elif isinstance(agents_src, str):
            agents_path = agents_src
        check(bool(agents_path), ".agents marketplace plugins[0].source.path present")
        if agents_path:
            check((ROOT / agents_path).is_dir(),
                  f".agents marketplace plugins[0].source.path exists: {agents_path}")

print("== npm / pi publish manifest ==")
# packages/design-playbook/package.json is the third publish surface: pi has
# no marketplace, and the pi.dev gallery indexes npm for the `pi-package`
# keyword. Drop the keyword and the package silently vanishes from the
# gallery while `pi install` keeps working — no runtime symptom to catch it.
npm_json = PKG / "package.json"
npmj = _read_json(npm_json)
check(bool(npmj), f"package.json present: {npm_json.relative_to(ROOT)}")
if isinstance(npmj, dict) and npmj:
    npm_version = npmj.get("version")
    check(
        bool(npm_version) and npm_version == claude_version,
        f"package.json version matches Claude plugin.json "
        f"(npm={npm_version!r}, claude={claude_version!r})",
    )
    keywords = npmj.get("keywords", [])
    keywords = keywords if isinstance(keywords, list) else []
    check("pi-package" in keywords,
          "package.json keywords include 'pi-package' (pi.dev gallery indexing)")

    # pi resolves these relative to the package root; a stale path means the
    # installed package loads zero skills with no error at install time.
    pi_manifest = npmj.get("pi", {})
    pi_manifest = pi_manifest if isinstance(pi_manifest, dict) else {}
    check(bool(pi_manifest), "package.json has a 'pi' manifest")
    for pi_key, expected_dir in (("skills", "skills"), ("prompts", "commands")):
        entries = pi_manifest.get(pi_key, [])
        entries = entries if isinstance(entries, list) else []
        check(bool(entries), f"package.json pi.{pi_key} declared")
        for entry in entries:
            if not isinstance(entry, str):
                check(False, f"package.json pi.{pi_key} entry is a string")
                continue
            check((PKG / entry).is_dir(),
                  f"package.json pi.{pi_key} target exists on disk: {entry}")
        check(any(isinstance(e, str) and e.rstrip("/").endswith(expected_dir)
                  for e in entries),
              f"package.json pi.{pi_key} points at {expected_dir}/")

    # The npm tarball is the only surface pi users ever see. Keep its public
    # instructions and the inventory that backs them in lockstep.
    files_field = npmj.get("files", [])
    files_field = files_field if isinstance(files_field, list) else []
    for shipped in ("skills", "commands", "mcp", "scripts", "examples"):
        check(shipped in files_field, f"package.json files[] ships {shipped}/")

    for reference in _checks.discover_package_references(PKG):
        target = PKG / reference.target
        label = f"{reference.surface} -> {reference.target}"
        exists = target.exists()
        check(exists, f"public package reference target exists: {label}")
        if exists:
            check(
                _checks.package_file_is_published(reference.target, files_field),
                f"public package reference included by package.json files[]: {label}",
            )

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

print("== Release identity (ADR-0015): version vs command inventory ==")
# Stable-main invariant enforced from the shared policy module
# (scripts/_checks.py): the plugin version must admit exactly the shipped
# command set. main is the public install surface, so unreleased capability
# must never ship under a released version (OPP-01).
version_text = pj.get("version", "")
shipped_commands = frozenset(p.stem for p in (PKG / "commands").glob("*.md"))
expected = _checks.expected_commands(version_text)
if expected is not None:
    check(
        shipped_commands == expected,
        f"version {version_text} expects commands {sorted(expected)}, "
        f"shipped {sorted(shipped_commands)} (ADR-0015 stable main)",
    )
else:
    check(
        False,
        f"version {version_text} has no declared command inventory "
        f"(ADR-0015); add an entry to COMMAND_INVENTORY in scripts/_checks.py",
    )

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

print("== Reference intake (ADR-0011) ==")
ref_skill = PKG / "skills" / "reference-intake" / "SKILL.md"
ref_template = PKG / "skills" / "reference-intake" / "references" / "contract-template.md"
check(ref_skill.is_file(), "reference-intake skill present")
check(ref_template.is_file(), "reference-intake contract template present")
ref_body = ref_skill.read_text(encoding="utf-8") if ref_skill.is_file() else ""
check(
    "Keep" in ref_body and "Do not copy" in ref_body and "manifest.json" in ref_body,
    "reference-intake names Keep/Do not copy and manifest.json",
)
playbook_for_ref = (PKG / "skills" / "design-playbook" / "SKILL.md").read_text(encoding="utf-8")
check(
    "reference-intake?" in playbook_for_ref and "ADR-0011" in playbook_for_ref,
    "orchestrator data flow includes reference-intake? (ADR-0011)",
)
check(
    (PKG / "examples" / "reference-intake" / "screenshot" / "contract.md").is_file()
    and (PKG / "examples" / "reference-intake" / "url" / "manifest.json").is_file()
    and (PKG / "examples" / "reference-intake" / "product-analogy" / "contract.md").is_file(),
    "reference-intake examples cover screenshot/url/product-analogy",
)
ux_for_ref = (PKG / "skills" / "ux-spec" / "SKILL.md").read_text(encoding="utf-8")
picker_for_ref = (PKG / "skills" / "ui-picker" / "SKILL.md").read_text(encoding="utf-8")
eval_for_ref = (PKG / "skills" / "ui-evaluator" / "SKILL.md").read_text(encoding="utf-8")
check(
    "reference/contract.md" in ux_for_ref and "always/ask/never" in ux_for_ref,
    "ux-spec consumes reference/contract.md before L1",
)
check(
    "reference/contract.md" in picker_for_ref and "Visual cues" in picker_for_ref,
    "ui-picker consumes reference visual cues",
)
check(
    "reference/contract.md" in eval_for_ref
    and "never" in eval_for_ref.lower()
    and "L6 proof" in eval_for_ref,
    "ui-evaluator may cite reference but not as L6 proof",
)
check(
    "reference/assets" in playbook_for_ref and "reference/example.html" in playbook_for_ref,
    "orchestrator Fill hard-boundary bans reference assets/example.html",
)
check(
    "always / ask / never hints:" in ref_template.read_text(encoding="utf-8")
    if ref_template.is_file()
    else False,
    "reference contract template includes always/ask/never hints",
)

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

print("== Craft detector protocol ==")
detector_catalog = PKG / "skills" / "craft-guard" / "references" / "detectors.md"
detector_fixture = PKG / "examples" / "craft-detectors" / "saas-dashboard.md"
detector_text = detector_catalog.read_text(encoding="utf-8") if detector_catalog.exists() else ""
fixture_text = detector_fixture.read_text(encoding="utf-8") if detector_fixture.exists() else ""
detector_ids = tuple(f"CRAFT-{index:02d}" for index in range(1, 9))
detector_fields = (
    "**Purpose:**",
    "**Rendered signals:**",
    "**Source signals:**",
    "**Legitimate exceptions:**",
    "**Owner hint:**",
    "**Positive fix:**",
)
for index, detector_id in enumerate(detector_ids):
    next_id = detector_ids[index + 1] if index + 1 < len(detector_ids) else None
    headings = re.findall(rf"^## {re.escape(detector_id)}\b", detector_text, re.M)
    start = re.search(rf"^## {re.escape(detector_id)}\b", detector_text, re.M)
    end = re.search(rf"^## {re.escape(next_id)}\b", detector_text, re.M) if next_id else None
    section = detector_text[start.start():end.start()] if start and end else (
        detector_text[start.start():] if start else ""
    )
    check(
        len(headings) == 1
        and bool(section)
        and all(section.count(field) == 1 for field in detector_fields),
        f"{detector_id} detector contract",
    )

fixture_rows = re.findall(
    r"^\| (CRAFT-\d{2}) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
    fixture_text,
    re.M,
)
check(
    len(fixture_rows) == len(detector_ids)
    and tuple(row[0] for row in fixture_rows) == detector_ids,
    "SaaS detector ledger has all eight IDs exactly once",
)
check(
    all(row[1].strip() in {"clear", "hit", "blocked"} for row in fixture_rows),
    "SaaS detector ledger uses allowed statuses",
)
check(
    all(all(cell.strip() for cell in row[2:]) for row in fixture_rows),
    "SaaS detector ledger has complete evidence fields",
)
check(
    {row[1].strip() for row in fixture_rows} >= {"clear", "hit", "blocked"},
    "SaaS detector ledger demonstrates hit clear and blocked",
)

composition_fixture = PKG / "examples" / "craft-detectors" / "composition-contrast.md"
composition_text = (
    composition_fixture.read_text(encoding="utf-8")
    if composition_fixture.exists() else ""
)
composition_rows = re.findall(
    r"^\| ([^|]+) \| (CRAFT-\d{2}) \| (hit|clear) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
    composition_text,
    re.M,
)
for detector_id in detector_ids[:5]:
    rows = [row for row in composition_rows if row[1] == detector_id]
    check(
        len(rows) == 2 and {row[2] for row in rows} == {"hit", "clear"},
        f"{detector_id} contrast has hit and clear",
    )
    hit_rows = [row for row in rows if row[2] == "hit"]
    check(
        len(hit_rows) == 1
        and all(cell.strip() and cell.strip() != "-" for cell in hit_rows[0][3:]),
        f"{detector_id} hit has evidence exception owner and fix",
    )

landing_fixture = PKG / "examples" / "craft-detectors" / "landing-product-contrast.md"
landing_text = landing_fixture.read_text(encoding="utf-8") if landing_fixture.exists() else ""
landing_rows = re.findall(
    r"^\| ([^|]+) \| (CRAFT-\d{2}) \| (hit|clear) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
    landing_text,
    re.M,
)
for detector_id in detector_ids[5:]:
    rows = [row for row in landing_rows if row[1] == detector_id]
    check(
        len(rows) == 2 and {row[2] for row in rows} == {"hit", "clear"},
        f"{detector_id} contrast has hit and clear",
    )
    hit_rows = [row for row in rows if row[2] == "hit"]
    check(
        len(hit_rows) == 1
        and all(cell.strip() and cell.strip() != "-" for cell in hit_rows[0][3:]),
        f"{detector_id} hit has evidence exception owner and fix",
    )

brand_fixture = PKG / "examples" / "craft-detectors" / "existing-brand-contrast.md"
brand_text = brand_fixture.read_text(encoding="utf-8") if brand_fixture.exists() else ""
check(
    all(phrase in brand_text for phrase in (
        "binding status is `ready`",
        "Baseline disposition: clear",
        "verified project choice wins generic detector taste",
    )),
    "verified baseline wins generic detector taste",
)
check(
    all(phrase in brand_text for phrase in (
        "Override disposition: hit",
        "safety, usability, and explicit dangerous-action declarations override baseline consistency",
        "Positive fix:",
    )),
    "safety usability and declarations override baseline",
)

print("== Dogfood 004 regression guards ==")


PROSE_PHRASES: dict[str, list[str]] = {
    "ui-evaluator blocks unattended acceptance": [
        "only after an explicit user decision",
        "user's statement or decision record",
        "remain in recirculate",
        "requests a decision",
    ],
    "orchestrator points to the authoritative evaluator verdict": [
        "authoritative verdict completion criterion in `ui-evaluator`",
    ],
    "fill routes reused-component L5 conflicts back to spec": [
        "reused host component",
        "conflicts with spec L5",
        "recirculate to `spec`",
        "authoritative map in `ui-evaluator`",
    ],
    "L4 implementation constraints name L5 exceptions": [
        "L4 declares control behavior only",
        "reuse / no-internal-change constraints must name exceptions",
        "conflict with L5",
    ],
    "orchestrator names all five run-contract controls": [
        "**Goal**", "**Success**", "**Evidence**", "**Stop**", "**Confirm**",
    ],
    "orchestrator defines confirmation and stop boundaries": [
        "external, destructive, costly, or scope-expanding",
        "same blocking finding survives two repair -> re-evaluate cycles",
        "smallest next decision",
    ],
    "ux-spec binds each success criterion to required evidence": [
        "必备证据",
        "every L6 item",
        "says what evidence will prove it",
    ],
    "ui-evaluator requires an evidence ledger and blocks missing proof": [
        "Record an evidence ledger",
        "result:    pass|fail|blocked|N/A",
        "unavailable required proof is `blocked`",
    ],
    "ui-evaluator pass requires all evidence rows": [
        "every required evidence row passes",
    ],
    "ui-evaluator consumes craft detector ledger": [
        "`.scratch/<run>/craft-guard.md`",
        "all eight `CRAFT-01` through `CRAFT-08` rows",
        "A detector never decides source, severity, or verdict",
        "Carry every `blocked` row into evaluation as a craft proof gap",
        "Keep craft detector rows out of the G6 manifest and L6 evidence ledger",
    ],
}


def check_skill_prose(text: str, gate: str, *, extra: bool = True,
                     anchor: str = "") -> None:
    """Report one phrase-table gate through the standard validation surface.

    The failure message names the gate, the missing phrases, and the heading
    anchor the section was sliced from — so prose drift is diagnosed in one
    pass instead of leaving the author to grep PROSE_PHRASES for the cause.
    """
    missing = [p for p in PROSE_PHRASES[gate] if not text or p not in text]
    if missing:
        where = f" (in {anchor!r})" if anchor else ""
        check(False, f"{gate}: missing {missing}{where}")
    else:
        check(extra, gate)


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
check_skill_prose(verdict, "ui-evaluator blocks unattended acceptance", anchor="### 4. Verdict")

playbook = (PKG / "skills" / "design-playbook" / "SKILL.md").read_text(encoding="utf-8")
accept = section_between(playbook, "### 5. Accept", "## Recirculate")
check_skill_prose(
    accept,
    "orchestrator points to the authoritative evaluator verdict",
    extra="explicitly accepted" not in accept,
    anchor="### 5. Accept",
)

fill = section_between(playbook, "### 3. Fill", "### 4. Craft")
check_skill_prose(fill, "fill routes reused-component L5 conflicts back to spec", anchor="### 3. Fill")

spec_template = (
    PKG / "skills" / "ux-spec" / "references" / "spec-template.md"
).read_text(encoding="utf-8")
l4 = section_between(spec_template, "## L4", "## L5")
check_skill_prose(l4, "L4 implementation constraints name L5 exceptions", anchor="## L4")

print("== Outcome-first run contract ==")
run_contract = section_between(playbook, "## Run contract", "## Steps")
check_skill_prose(run_contract, "orchestrator names all five run-contract controls", anchor="## Run contract")
check_skill_prose(run_contract, "orchestrator defines confirmation and stop boundaries", anchor="## Run contract")

ux_spec = (PKG / "skills" / "ux-spec" / "SKILL.md").read_text(encoding="utf-8")
l6 = section_between(spec_template, "## L6", "---")
check_skill_prose(
    f"{l6}\n{ux_spec}",
    "ux-spec binds each success criterion to required evidence",
    extra=bool(l6),
    anchor="## L6",
)

run_checks = section_between(evaluator, "### 2. Run checks", "### 3. Emit point-back findings")
check_skill_prose(
    run_checks,
    "ui-evaluator requires an evidence ledger and blocks missing proof",
    anchor="### 2. Run checks",
)
check_skill_prose(run_checks, "ui-evaluator consumes craft detector ledger", anchor="### 2. Run checks")
check_skill_prose(verdict, "ui-evaluator pass requires all evidence rows", anchor="### 4. Verdict")

print("== Run aggregate (v0.9) ==")
# Smoke only runs where a dogfood corpus exists. Fixture copies (e.g.
# tests/test_validate.py: scripts + package + catalogs, no .scratch) are
# legitimate static-gate inputs, so an absent corpus is a skip, not a FAIL.
if not any((ROOT / ".scratch").glob("**/dogfood/*/point-back.md")):
    print("  info  no dogfood runs under .scratch - aggregate smoke skipped")
else:
    try:
        agg_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        agg = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "aggregate_runs.py"), "--top", "5"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=ROOT, env=agg_env, timeout=180,
        )
        agg_data = json.loads(agg.stdout) if agg.returncode == 0 else None
        if agg_data is None:
            check(False, f"aggregate_runs exited {agg.returncode}: "
                         f"{(agg.stdout + agg.stderr).strip()[-200:]}")
        else:
            total = agg_data.get("runs_total", 0)
            repeat = len(agg_data.get("repeat_blockers", []))
            check(total >= 1, f"aggregate_runs discovers >=1 dogfood run ({total})")
            print(f"  info  runs={total} repeat_blockers={repeat} "
                  f"rollup={agg_data.get('rollup', {}).get('by_result', {})}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        check(False, f"aggregate_runs smoke failed: {exc}")

print()
if failures:
    print(f"VALIDATION FAILED: {len(failures)} issue(s)")
    sys.exit(1)
print("VALIDATION PASSED")
