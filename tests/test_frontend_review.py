"""User-visible, read-only frontend review through the existing status CLI."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "design-playbook"
STATUS = PACKAGE / "scripts" / "run_status.py"

SPEC = """# Checkout
## L1 Intent
Goal: Recover a failed checkout.
## L2 Pages
| Page | Duty |
| --- | --- |
| checkout | Submit order |
| receipt | Show receipt |
## L3 Paths
| Path | Steps |
| --- | --- |
| P1 | checkout |
| P2 | receipt |
## L4 Controls
Submit button.
## L5 States
## L6 Acceptance
- Given checkout fails When retry is offered Then recovery is visible (path: P1)
  Required evidence: screenshot; state=error; viewport=390x844
- Given order exists When receipt opens Then its number is visible (path: P2)
  Required evidence: screenshot; state=default; viewport=1280x800
"""


def make_run(tmp_path: Path) -> Path:
    run = tmp_path / "project with spaces" / ".scratch" / "run"
    run.mkdir(parents=True)
    (run / "spec.md").write_text(SPEC, encoding="utf-8")
    return run


def status(run: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(STATUS), str(run), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_declared_scope_links_to_criterion_without_inventing_impact(tmp_path):
    run = make_run(tmp_path)
    original = (run / "spec.md").read_bytes()
    result = status(run, "--scope", "path:P1", "--scope", "component:Retry", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    mapped, unknown = report["impact"]
    assert mapped["scope"] == "path:P1"
    assert mapped["availability"] == "known"
    assert mapped["links"] == [{
        "criterion": "L6.1", "declaration": "spec.md#L3.P1",
        "reason": "declared-path-reference",
        "source_hash": "sha256:" + hashlib.sha256(original).hexdigest(),
    }]
    assert unknown["availability"] == "unknown"
    assert unknown["links"] == []
    assert unknown["reason"] == "no-declared-association"
    assert report["unaffected"] == []
    assert (run / "spec.md").read_bytes() == original


@pytest.mark.parametrize("scope", [
    "file:../secret", "file:C:/secret", "file:/secret", "file:dir/../../secret",
    "page:checkout?token=SECRET", "component:SECRET\ncommand",
])
def test_scope_rejection_does_not_echo_private_input(tmp_path, scope):
    result = status(make_run(tmp_path), "--scope", scope, "--json")
    assert result.returncode == 2
    assert "invalid-scope" in result.stderr
    assert "SECRET" not in result.stdout + result.stderr


@pytest.mark.parametrize("steps,availability", [
    ("checkout (assumed)", "assumed"),
    ("", "inconsistent"),
])
def test_uncertain_declarations_are_not_promoted(tmp_path, steps, availability):
    run = make_run(tmp_path)
    (run / "spec.md").write_text(SPEC.replace("| P1 | checkout |", f"| P1 | {steps} |"),
                               encoding="utf-8")
    result = status(run, "--scope", "path:P1", "--json")
    item = json.loads(result.stdout)["impact"][0]
    assert item["availability"] == availability
    assert item["confirmation"] == "review-source-declaration"


def test_page_association_requires_a_declared_page(tmp_path):
    run = make_run(tmp_path)
    (run / "spec.md").write_text(SPEC.replace("| checkout | Submit order |\n", ""),
                               encoding="utf-8")
    item = json.loads(status(run, "--scope", "page:checkout", "--json").stdout)["impact"][0]
    assert item["availability"] == "unknown"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True, timeout=15).stdout.strip()


@pytest.mark.parametrize("filename", ["button file.tsx", "app/(account)/[id]/page+client.tsx"])
def test_git_clues_use_explicit_revisions_and_include_uncommitted_files(tmp_path, filename):
    run = make_run(tmp_path)
    root = run.parents[1]
    git(root, "init", "-q")
    changed_file = root / filename
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("before", encoding="utf-8")
    git(root, "add", filename)
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "initial")
    base = git(root, "rev-parse", "HEAD")
    changed_file.write_text("after", encoding="utf-8")
    git(root, "add", filename)
    git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "update")
    head = git(root, "rev-parse", "HEAD")
    changed_file.write_text("uncommitted", encoding="utf-8")
    before = git(root, "status", "--porcelain")
    result = status(run, "--scope", "path:P1", "--git-root", str(root),
                    "--base-revision", base, "--head-revision", head, "--json")
    assert result.returncode == 0, result.stderr
    clues = json.loads(result.stdout)["change_clues"]
    assert clues == {"availability": "known", "base": base, "head": head,
                     "worktree": False, "files": [filename]}
    result = status(run, "--scope", "path:P1", "--git-root", str(root),
                    "--base-revision", head, "--worktree", "--json")
    assert json.loads(result.stdout)["change_clues"]["files"] == [
        ".scratch/run/spec.md", filename,
    ]
    assert git(root, "status", "--porcelain") == before


def test_git_clues_never_guess_base_or_discover_a_parent_repository(tmp_path):
    run = make_run(tmp_path)
    result = status(run, "--scope", "path:P1", "--git-root", str(run),
                    "--worktree", "--json")
    assert result.returncode == 2
    result = status(run, "--scope", "path:P1", "--git-root", str(run),
                    "--base-revision", "HEAD", "--worktree", "--json")
    assert result.returncode == 2
    assert "git-input-unavailable" in result.stderr


def test_missing_declared_proof_blocks_without_inventing_extra_states(tmp_path):
    report = json.loads(status(make_run(tmp_path), "--scope", "path:P1", "--json").stdout)
    first, second = report["evidence_gaps"]
    assert first["criterion"] == "L6.1"
    assert first["required"] == {
        "proof": "screenshot", "state": "error", "viewport": {"width": 390, "height": 844},
    }
    assert first["binding"] == "missing"
    assert first["status"] == "blocked"
    assert first["evaluator"] == "unaudited"
    assert first["availability"] == "known"
    assert first["reasons"] == ["required-proof-missing"]
    assert second["required"]["state"] == "default"
    assert report["sampling"] == []


def write_evidence(run: Path, *, artifact_name: str = "L6.1-error.png",
                   capture_artifact_name: str | None = None,
                   proof: str = "screenshot", **request_changes) -> None:
    evidence = run / "evidence"
    evidence.mkdir(exist_ok=True)
    artifact = evidence / artifact_name
    capture_artifact = evidence / (capture_artifact_name or artifact_name)
    artifact.write_bytes(b"test-rendered-artifact")
    capture_artifact.write_bytes(b"test-rendered-artifact")
    request = {
        "schemaVersion": 1,
        "viewport": {"width": 390, "height": 844, "devicePixelRatio": 1, "colorScheme": "light"},
        "freeze": {"enabled": True, "waitFonts": True, "networkIdle": True},
        **request_changes,
    }
    capture = {
        "url": "https://private.invalid/?token=SECRET",
        "type": proof,
        "state": "error",
        "artifact_path": f"evidence/{capture_artifact.name}",
    }
    entry = {"criterion": "L6.1", "artifact": artifact.name,
             "ts": "2026-09-24T10:00:00Z",
             "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
             "request": request, "capture": capture}
    (evidence / "manifest.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    (run / "point-back.md").write_text("""## Findings
```
issue: recovery needs a follow-up
source: spec L6
fix: check retry
severity: S2
disposition: blocking
```
## Coverage statement
exhaustive: completed
unreviewed: none
## Invalidated evidence
invalidated:
  - criterion: L6.2
    artifacts: []
    reason: receipt needs review
## Verdict
**Recirculate.**
## Evidence ledger
```
criterion: L6.1
required: screenshot
observed: evidence/{artifact_name}
result: pass

criterion: L6.2
required: receipt
observed: not applicable: SECRET personal rationale
result: n/a
```
""".format(artifact_name=artifact_name), encoding="utf-8")


def test_binding_integrity_is_separate_from_verdict_and_private_prose(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    first, second = report["evidence_gaps"]
    assert first["binding"] == "complete"
    assert first["status"] == "available"
    assert first["evaluator"] == "pass"
    assert second["status"] == "notApplicable"
    assert second["not_applicable_reason"]["source"] == "point-back.md#L6.2"
    assert report["evaluation"]["value"] == "Recirculate"
    assert "SECRET" not in result.stdout
    assert "private.invalid" not in result.stdout


def test_normalized_capture_snapshot_without_capture_metadata_stays_unavailable(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    manifest = run / "evidence/manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8"))
    entry["request"] = {
        key: entry["request"][key]
        for key in ("schemaVersion", "viewport", "freeze")
    }
    entry.pop("capture", None)
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert gap["binding"] != "complete"
    assert gap["status"] == "blocked"
    assert "capture-metadata-unavailable" in gap["reasons"]
    assert not any(reason.startswith("capture.") for reason in gap["reasons"])


def test_capture_metadata_takes_precedence_over_legacy_request_aliases(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    manifest = run / "evidence/manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8"))
    entry["request"].update({"type": "screenshot", "state": "error"})
    entry["capture"].update({"type": "a11y tree", "state": "default"})
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert {"proof-type-mismatch", "state-mismatch"} <= set(gap["reasons"])
    assert gap["binding"] == "invalid"
    assert gap["status"] == "blocked"


@pytest.mark.parametrize("proof,capture_type,artifact_name", [
    ("screenshot", "screenshot", "L6.1-error.png"),
    ("a11y_tree", "a11y tree", "L6.1-error.json"),
    ("interaction_trace", "interaction trace", "L6.1-error.trace.zip"),
])
def test_declared_proof_type_matches_provider_capture_vocabulary(
        tmp_path, proof, capture_type, artifact_name):
    run = make_run(tmp_path)
    (run / "spec.md").write_text(SPEC.replace(
        "Required evidence: screenshot; state=error; viewport=390x844",
        f"Required evidence: {proof}; state=error; viewport=390x844",
    ), encoding="utf-8")
    write_evidence(run, artifact_name=artifact_name, proof=capture_type)

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert gap["binding"] == "complete"
    assert gap["status"] == "available"
    assert "proof-type-mismatch" not in gap["reasons"]


@pytest.mark.parametrize("declare_probe", [False, True])
def test_probe_primary_artifact_binds_to_originating_capture(tmp_path, declare_probe):
    run = make_run(tmp_path)
    write_evidence(
        run,
        artifact_name="L6.1-error.probe.json",
        capture_artifact_name="L6.1-error.png",
    )
    if declare_probe:
        manifest = run / "evidence/manifest.jsonl"
        entry = json.loads(manifest.read_text(encoding="utf-8"))
        entry["probe_artifact"] = "evidence/L6.1-error.probe.json"
        manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert gap["binding"] == "complete"
    assert gap["status"] == "available"
    assert "capture-artifact-mismatch" not in gap["reasons"]


def test_probe_sidecar_only_binds_to_a_screenshot_capture(tmp_path):
    run = make_run(tmp_path)
    (run / "spec.md").write_text(SPEC.replace(
        "Required evidence: screenshot; state=error; viewport=390x844",
        "Required evidence: a11y_tree; state=error; viewport=390x844",
    ), encoding="utf-8")
    write_evidence(
        run,
        artifact_name="L6.1-error.probe.json",
        capture_artifact_name="L6.1-error.json",
        proof="a11y tree",
    )

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert "capture-artifact-mismatch" in gap["reasons"]
    assert gap["binding"] == "invalid"
    assert gap["status"] == "blocked"


def test_unrelated_explicit_probe_artifact_does_not_bind(tmp_path):
    run = make_run(tmp_path)
    write_evidence(
        run,
        artifact_name="L6.1-other.probe.json",
        capture_artifact_name="L6.1-error.png",
    )
    manifest = run / "evidence/manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8"))
    entry["probe_artifact"] = "evidence/L6.1-other.probe.json"
    manifest.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert "capture-artifact-mismatch" in gap["reasons"]
    assert gap["binding"] == "invalid"
    assert gap["status"] == "blocked"


def test_unrelated_primary_artifact_does_not_bind_to_capture(tmp_path):
    run = make_run(tmp_path)
    write_evidence(
        run,
        artifact_name="L6.1-other.png",
        capture_artifact_name="L6.1-error.png",
    )

    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert "capture-artifact-mismatch" in gap["reasons"]
    assert gap["binding"] == "invalid"
    assert gap["status"] == "blocked"


@pytest.mark.parametrize("change,reason,availability", [
    ("viewport", "viewport-mismatch", "known"),
    ("state", "state-mismatch", "known"),
    ("criterion", "G6.unknown_criterion", "known"),
    ("artifact", "G6.artifact_missing", "known"),
    ("hash", "artifact-hash-mismatch", "stale"),
    ("partial", "manifest-malformed", "inconsistent"),
    ("conflict", "conflicting-bindings", "inconsistent"),
    ("capture", "G6.capture_freeze", "known"),
])
def test_evidence_gaps_fail_closed(tmp_path, change, reason, availability):
    run = make_run(tmp_path)
    write_evidence(run)
    manifest = run / "evidence/manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8"))
    if change == "viewport":
        entry["request"]["viewport"]["width"] = 1280
    elif change == "state":
        entry["capture"]["state"] = "default"
    elif change == "criterion":
        entry["criterion"] = "L6.99"
    elif change == "artifact":
        (run / "evidence/L6.1-error.png").unlink()
    elif change == "hash":
        (run / "evidence/L6.1-error.png").write_bytes(b"changed-after-binding")
    elif change == "capture":
        entry["request"].pop("freeze")
    content = json.dumps(entry) + "\n"
    if change == "partial":
        content += '{"partial":'
    elif change == "conflict":
        content += json.dumps({**entry, "sha256": "0" * 64}) + "\n"
    manifest.write_text(content, encoding="utf-8")
    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 0, result.stderr
    gap = json.loads(result.stdout)["evidence_gaps"][0]
    assert gap["status"] == "blocked"
    assert gap["availability"] == availability
    assert reason in gap["reasons"]
    assert gap["binding"] != "complete"


def test_skipped_evaluator_never_turns_na_into_accepted_proof(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    pointback = run / "point-back.md"
    pointback.write_text("audited: false\n" + pointback.read_text(encoding="utf-8"),
                        encoding="utf-8")
    report = json.loads(status(run, "--scope", "path:P1", "--json").stdout)
    assert report["evaluation"]["value"] == "unaudited"
    assert report["evidence_gaps"][0]["evaluator"] == "unaudited"
    assert report["evidence_gaps"][1]["status"] == "blocked"


def test_sampling_only_enumerates_declared_cells_and_preserves_unreviewed_reason(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    spec = SPEC.replace("## L5 States", """## L5 States
| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| checkout | Ready | | | Retry | |
""")
    (run / "spec.md").write_text(spec, encoding="utf-8")
    pointback = run / "point-back.md"
    pointback.write_text(pointback.read_text(encoding="utf-8").replace(
        "unreviewed: none", "unreviewed: checkout/failure\nsampling-matrix:\n"
        "- checkout/initial: evidence/L6.1-error.png\n"
        "- checkout/failure: unreviewed (SECRET login prerequisite)"), encoding="utf-8")
    result = status(run, "--scope", "page:checkout", "--json")
    sampling = json.loads(result.stdout)["sampling"]
    assert [(row["page"], row["state"]) for row in sampling] == [
        ("checkout", "initial"), ("checkout", "failure"),
    ]
    assert sampling[1]["status"] == "unreviewed"
    assert sampling[1]["reason_source"] == "point-back.md#coverage"
    assert "SECRET" not in result.stdout


def test_proposal_includes_owner_invalidations_and_does_not_narrow_unknown_scope(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    report = json.loads(status(run, "--scope", "path:P1", "--json").stdout)
    proposal = report["reverification"]
    assert [item["criterion"] for item in proposal["included"]] == ["L6.1", "L6.2"]
    assert proposal["invalidated_evidence"]["value"] == ["L6.2"]
    assert "owner-invalidated" in proposal["included"][1]["reasons"]
    assert proposal["resume_stage"]["value"] == "ui-evaluator"
    assert proposal["next_command"]["value"].startswith("/design-playbook:design-io repair ")
    assert proposal["recapture_requirement"]["value"]
    assert proposal["unaffected"] == []
    unknown = json.loads(status(run, "--scope", "component:Retry", "--json").stdout)
    assert unknown["reverification"]["can_narrow"] is False
    assert [row["criterion"] for row in unknown["reverification"]["included"]] == ["L6.1", "L6.2"]
    assert "scope-unresolved" in unknown["reverification"]["reasons"]


def test_previous_proposal_hash_is_revalidated_before_copy(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    before = json.loads(status(run, "--scope", "path:P1", "--json").stdout)
    unchanged = status(run, "--scope", "path:P1", "--expected-source-hash",
                       before["source_hash"], "--json")
    assert unchanged.returncode == 0, unchanged.stderr
    assert json.loads(unchanged.stdout)["freshness"] == "current"
    (run / "contract-bind.json").write_text('{"partial":', encoding="utf-8")
    after = json.loads(status(run, "--scope", "path:P1", "--expected-source-hash",
                              before["source_hash"], "--json").stdout)
    assert after["freshness"] == "stale"
    assert after["source_hash"] != before["source_hash"]
    assert after["reverification"]["next_command"]["value"] is None
    assert after["reverification"]["availability"] == "stale"


def test_read_time_source_change_cannot_return_a_current_proposal(tmp_path, monkeypatch):
    sys.path.insert(0, str(PACKAGE))
    from design_playbook.scripts.frontend_review import build_frontend_review
    run = make_run(tmp_path)
    write_evidence(run)
    original = Path.read_bytes
    changed = False

    def read(path):
        nonlocal changed
        value = original(path)
        if path.name == "L6.1-error.png" and not changed:
            changed = True
            (run / "spec.md").write_text(SPEC.replace("390x844", "400x800"), encoding="utf-8")
        return value

    monkeypatch.setattr(Path, "read_bytes", read)
    report = build_frontend_review(run, ("path:P1",))
    assert changed
    assert report["freshness"] == "stale"
    assert report["reverification"]["next_command"]["value"] is None


def test_partial_contract_does_not_offer_a_copyable_repair(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    (run / "contract-bind.json").write_text('{"partial":', encoding="utf-8")
    report = json.loads(status(run, "--scope", "path:P1", "--json").stdout)
    assert report["reverification"]["availability"] == "inconsistent"
    assert report["reverification"]["next_command"]["value"] is None
    assert report["reverification"]["invalidated_evidence"]["value"] == ["L6.2"]


def test_proposal_provenance_uses_the_selected_legacy_spec(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    (run / "spec.md").rename(run / "01-spec.md")
    report = json.loads(status(run, "--scope", "path:P1", "--json").stdout)
    first = report["reverification"]["included"][0]
    assert first["sources"] == ["01-spec.md#L3.P1"]
    second = report["reverification"]["included"][1]
    assert "point-back.md#invalidated-evidence" in second["sources"]


def test_read_time_manifest_deletion_requires_refresh(tmp_path, monkeypatch):
    sys.path.insert(0, str(PACKAGE))
    from design_playbook.scripts.frontend_review import build_frontend_review
    run = make_run(tmp_path)
    write_evidence(run)
    original = Path.read_bytes
    deleted = False

    def read(path):
        nonlocal deleted
        value = original(path)
        if path.name == "L6.1-error.png" and not deleted:
            deleted = True
            (run / "evidence/manifest.jsonl").unlink()
        return value

    monkeypatch.setattr(Path, "read_bytes", read)
    report = build_frontend_review(run, ("path:P1",))
    assert deleted
    assert report["freshness"] == "stale"
    assert report["reverification"]["next_command"]["value"] is None


def test_repeated_unverified_owner_reads_cannot_be_promoted_to_current(tmp_path, monkeypatch):
    sys.path.insert(0, str(PACKAGE))
    from design_playbook.scripts.frontend_review import build_frontend_review
    run = make_run(tmp_path)
    write_evidence(run)
    original = Path.read_bytes
    artifact_reads = 0

    def read(path):
        nonlocal artifact_reads
        if path.name == "L6.1-error.png":
            artifact_reads += 1
            if artifact_reads % 3 == 2:
                raise OSError("temporary filesystem read failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    report = build_frontend_review(run, ("path:P1",))
    assert artifact_reads >= 6
    assert report["freshness"] == "stale"
    assert report["reverification"]["next_command"]["value"] is None


def test_text_report_retains_declaration_and_na_reason_references(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    result = status(run, "--scope", "path:P1", "--scope", "component:Retry")
    assert result.returncode == 0, result.stderr
    assert "spec.md#L3.P1" in result.stdout
    assert "review-source-declaration" in result.stdout
    assert "point-back.md#L6.2" in result.stdout
    assert "SECRET" not in result.stdout


def test_text_report_retains_bound_evidence_and_the_overall_evaluator_result(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    result = status(run, "--scope", "path:P1")
    assert result.returncode == 0, result.stderr
    assert "evidence/manifest.jsonl#L6.1" in result.stdout
    assert "Evaluation (known): Recirculate" in result.stdout


@pytest.mark.parametrize("seed,availability", [
    ("", "unknown"),
    ("  Required evidence: screenshot of error on a narrow screen\n", "unknown"),
    ("  Required evidence: screenshot\n  Required evidence: a11y_tree\n", "inconsistent"),
])
def test_unavailable_requirements_do_not_invent_proof(tmp_path, seed, availability):
    run = make_run(tmp_path)
    (run / "spec.md").write_text(SPEC.replace(
        "  Required evidence: screenshot; state=error; viewport=390x844\n", seed),
        encoding="utf-8")
    gap = json.loads(status(run, "--scope", "path:P1", "--json").stdout)["evidence_gaps"][0]
    assert gap["availability"] == availability
    assert gap["status"] == "unknown"
    assert gap["required"] == {"proof": None, "state": None, "viewport": None}


@pytest.mark.parametrize("source", ["spec.md", "evidence"])
def test_escaped_sources_are_rejected_without_reading_them(tmp_path, source):
    run = make_run(tmp_path)
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "spec.md").write_text("SECRET", encoding="utf-8")
    target = run / source
    if target.exists():
        target.unlink()
    try:
        target.symlink_to(outside / "spec.md" if source == "spec.md" else outside,
                          target_is_directory=source == "evidence")
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = status(run, "--scope", "path:P1", "--json")
    assert result.returncode == 2
    assert "source-outside-selected-run" in result.stderr
    assert "SECRET" not in result.stdout + result.stderr


def test_report_is_read_only_deterministic_and_keeps_pass_as_source_verdict(tmp_path):
    run = make_run(tmp_path)
    write_evidence(run)
    pointback = run / "point-back.md"
    pointback.write_text(pointback.read_text(encoding="utf-8").replace(
        "**Recirculate.**", "**Pass.**").replace("result: n/a", "result: pass").replace(
        "severity: S2", "severity: S0").replace("disposition: blocking", "disposition: info"),
        encoding="utf-8")
    before = {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()}
    first = status(run, "--scope", "path:P1", "--json")
    second = status(run, "--scope", "path:P1", "--json")
    assert first.stdout == second.stdout
    report = json.loads(first.stdout)
    assert report["evaluation"]["value"] == "Pass"
    assert report["evidence_gaps"][1]["status"] == "blocked"
    assert report["reverification"]["next_command"]["value"] is None
    assert before == {path.relative_to(run): path.read_bytes() for path in run.rglob("*") if path.is_file()}


def test_conflicting_manifest_heads_are_unbound_in_the_existing_snapshot(tmp_path):
    sys.path.insert(0, str(PACKAGE))
    from design_playbook.mcp.run_console.snapshot_builder import build_snapshot
    run = make_run(tmp_path)
    write_evidence(run)
    manifest = run / "evidence/manifest.jsonl"
    entry = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps(entry) + "\n" + json.dumps(
        {**entry, "sha256": "0" * 64}) + "\n", encoding="utf-8")
    snapshot = build_snapshot(selected_root=run, package_root=PACKAGE,
                              session_secret=b"test-only", now="2026-09-24T00:00:00Z").document
    first = snapshot["evaluation"]["criteria"][0]["result"]
    assert first["criterionId"] == "L6.1"
    assert first["evidenceBindings"] == []
