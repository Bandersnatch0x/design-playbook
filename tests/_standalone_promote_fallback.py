"""Standalone-import harness for the promote() governance fallback.

Run by test_design_baseline_promote.py with the package NOT importable, so
``from design_playbook.scripts import promotion_governance`` raises ImportError
and the importlib fallback in ``_load_user_promotions`` is the code under test.
Exits 0 and prints FALLBACK_OK when the fallback loads the module and promote()
reaches the not-ready gate; any ImportError/path failure surfaces as non-zero.
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1])
MODULE = REPO / "packages/design-playbook/skills/design-baseline/scripts/design_baseline.py"

# Ensure the package import fails so the fallback branch executes.
sys.path = [p for p in sys.path if "design-playbook" not in p]
sys.modules.pop("design_playbook", None)

spec = importlib.util.spec_from_file_location("db_standalone", MODULE)
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)

tmp = tempfile.mkdtemp()
project = Path(tmp) / "p"
run = project / ".scratch" / "r"
project.mkdir(parents=True)
(project / "promotion-governance.jsonl").write_text(
    json.dumps({
        "id": "e1", "event": "promotion_decided", "decided_by": "user",
        "confirmed_at": "2026-09-22T00:00:00Z", "kind": "component",
        "target": "src/ui/B.tsx", "decision": "promote", "rationale": "x",
    }) + "\n",
    encoding="utf-8",
)
try:
    db.promote(project, run, "src/ui/B.tsx", "x")
except Exception as exc:  # noqa: BLE001 - harness asserts the failure mode
    # Reaching ANY BaselineError business gate (state missing / not ready)
    # proves _load_user_promotions loaded the governance log via the importlib
    # fallback — an ImportError or a wrong-path failure would not be a
    # BaselineError.
    if type(exc).__name__ == "BaselineError":
        print("FALLBACK_OK")
        sys.exit(0)
    print(f"WRONG_FAILURE: {type(exc).__name__}: {exc}")
    sys.exit(1)
print("UNEXPECTED_SUCCESS")
sys.exit(1)
