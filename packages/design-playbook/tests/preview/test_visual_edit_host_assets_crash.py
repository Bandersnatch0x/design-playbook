"""Declared local assets and controlled fixture aborts, not OS crash guarantees."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from .test_visual_edit_host_e2e import FIXTURE, host_cli
from .test_visual_edit_host_multifile import apply_in_process, host_case as host_case, read_source

from host import source_hash  # noqa: E402


@pytest.mark.parametrize("host_case", [True], indirect=True)
def test_declared_asset_set_is_bound_and_unchanged_apply_succeeds(host_case):
    case = host_case
    reviewed = host_cli("review", case.root, case.handoff, case.candidate, case.route)
    print("DECLARED REVIEW", reviewed.returncode, reviewed.stdout, reviewed.stderr)
    assert reviewed.returncode == 0
    proposal = json.loads(reviewed.stdout)
    assert set(proposal["assetHashes"]) == set(case.before)
    assert proposal["assetHashes"]["palette.json"] == hashlib.sha256(case.before["palette.json"]).hexdigest()
    applied = host_cli("apply", case.root, case.handoff, case.candidate, case.route,
                       proposal["confirmation"] + "\n")
    print("DECLARED APPLY", applied.returncode, applied.stdout, applied.stderr)
    assert applied.returncode == 0
    assert read_source(case) == {**case.before, **case.contents}
    assert json.loads(applied.stdout.splitlines()[-1])["pluginWritesSource"] is False


@pytest.mark.parametrize("host_case", [True], indirect=True)
@pytest.mark.parametrize("change", ["changed", "removed", "undeclared", "added-to-manifest", "manifest-removed"])
@pytest.mark.parametrize("during_confirmation", [False, True], ids=["after-review", "while-typing"])
def test_declared_asset_drift_refuses_without_writing(host_case, change, during_confirmation):
    case = host_case
    reviewed = host_cli("review", case.root, case.handoff, case.candidate, case.route)
    assert reviewed.returncode == 0
    proposal = json.loads(reviewed.stdout)
    manifest = case.root / "assets.json"

    def change_asset():
        if change == "changed":
            (case.root / "palette.json").write_bytes(b'{"ink": "#000000"}\n')
        elif change == "removed":
            (case.root / "palette.json").unlink()
        elif change == "undeclared":
            manifest.write_text(json.dumps({"assets": ["index.html", "styles.css"]}))
        elif change == "added-to-manifest":
            (case.root / "new.json").write_text("{}")
            manifest.write_text(json.dumps({"assets": ["index.html", "styles.css", "palette.json", "new.json"]}))
        else:
            manifest.unlink()
        expected.update(read_source(case))
        return proposal["confirmation"] + "\n"

    expected = {}
    if during_confirmation:
        code, diagnostic = apply_in_process(case, change_asset)
    else:
        phrase = change_asset()
        refused = host_cli("apply", case.root, case.handoff, case.candidate, case.route, phrase)
        print("ASSET DRIFT", change, refused.returncode, refused.stdout, refused.stderr)
        code = refused.returncode
        assert code == 2
        diagnostic = json.loads(refused.stderr.removeprefix("REFUSED: "))
    assert code == 2
    assert any(word in diagnostic["error"] for word in ("stale", "asset", "review changed"))
    assert diagnostic["pluginWritesSource"] is False
    assert read_source(case) == expected
    assert not (case.root.parent / ("." + case.root.name + ".applier.lock")).exists()
    print("NO HOST WRITE", change, "while-typing=" + str(during_confirmation))


@pytest.mark.parametrize("host_case", [True], indirect=True)
@pytest.mark.parametrize("point", ["after-staging", "after-first-commit"])
def test_fixture_abort_restores_all_bytes_and_restart_acquires_lock(host_case, point):
    case = host_case
    reviewed = host_cli("review", case.root, case.handoff, case.candidate, case.route)
    assert reviewed.returncode == 0
    phrase = json.loads(reviewed.stdout)["confirmation"] + "\n"
    command = [sys.executable, "-X", "utf8", str(FIXTURE / "applier.py"), "apply",
               "--root", str(case.root), "--handoff", str(case.handoff),
               "--candidate", str(case.candidate), "--route-url", case.route,
               "--interrupt-at", point]
    interrupted = subprocess.run(command, input=phrase, text=True, encoding="utf-8",
                                 capture_output=True, timeout=20)
    print("FIXTURE ABORT", point, interrupted.returncode, interrupted.stdout, interrupted.stderr)
    assert interrupted.returncode == 2
    assert interrupted.stderr.startswith("REFUSED: ")
    diagnostic = json.loads(interrupted.stderr.removeprefix("REFUSED: "))
    assert diagnostic["outcome"] == "failed"
    assert diagnostic["phase"] == "interruption"
    assert diagnostic["faultPoint"] == point
    assert diagnostic["reason"] == "fixture-abort:" + point
    assert diagnostic["recoveryScope"] == "controlled-fixture-abort-only"
    committed = ["index.html"] if point == "after-first-commit" else []
    assert diagnostic["committedFiles"] == committed
    assert diagnostic["writeApplied"] is bool(committed)
    assert diagnostic["rollbackAttempted"] is bool(committed)
    assert diagnostic["rolledBack"] is True
    assert diagnostic["rollbackErrors"] == {}
    assert diagnostic["lockDisposition"] == "owned-lock-released"
    assert diagnostic["pluginWritesSource"] is False
    assert not any(line.startswith("{") for line in interrupted.stdout.splitlines())
    assert read_source(case) == case.before  # Includes manifest, unselected asset and no staged leftovers.
    lock = case.root.parent / ("." + case.root.name + ".applier.lock")
    assert not lock.exists()
    print("NO PARTIAL STATE", point, json.dumps({name: hashlib.sha256(data).hexdigest()
          for name, data in read_source(case).items()}, sort_keys=True))
    restarted = host_cli("apply", case.root, case.handoff, case.candidate, case.route, phrase)
    print("RESTART", point, restarted.returncode, restarted.stdout, restarted.stderr)
    assert restarted.returncode == 0
    assert read_source(case) == {**case.before, **case.contents}
    assert not lock.exists()


@pytest.mark.parametrize("extra", ["../outside.json", "/outside.json", "https://example.test/a.json",
                                  "folder/../palette.json", "palette.json", "ASSETS.JSON"])
def test_asset_manifest_rejects_escaping_duplicate_or_metadata_paths(tmp_path, extra):
    for name in ("index.html", "styles.css", "palette.json"):
        shutil.copyfile(FIXTURE / name, tmp_path / name)
    (tmp_path / "assets.json").write_text(json.dumps({"assets": ["index.html", "styles.css", "palette.json", extra]}))
    with pytest.raises(ValueError, match="host asset"):
        source_hash(tmp_path)
    print("MANIFEST REFUSED", extra)


def test_unlisted_asset_is_not_discovered(tmp_path):
    for name in ("index.html", "styles.css", "palette.json", "assets.json"):
        shutil.copyfile(FIXTURE / name, tmp_path / name)
    before = source_hash(tmp_path)
    (tmp_path / "unlisted.json").write_text("{}")
    assert source_hash(tmp_path) == before
    (tmp_path / "unlisted.json").write_text('{"changed": true}')
    assert source_hash(tmp_path) == before
    print("NO DISCOVERY: unlisted asset additions/changes do not enter the binding")
