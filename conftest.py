"""One shared ``tests`` package, so every suite can run in a single process.

The repository owns three test roots: ``tests/``, the plugin's
``packages/design-playbook/tests`` and the workbench's
``packages/design-playbook-workbench/tests``. Both package-owned suites
import their own helpers as ``tests.*`` — ``tests.run_console``,
``tests.preview_e2e_helpers``, ``tests.harness`` — but a process binds the
name ``tests`` to one directory, so collecting all of them at once from the
repository root raised 40 collection errors while the per-directory CI jobs
stayed green. The "full matrix" was in fact disjoint subsets.

Binding ``tests`` to both package-owned roots at once lets every existing
``tests.*`` import reach the file it names, in any invocation shape. The
repository's own ``tests/`` is left out on purpose: it has no
``__init__.py``, so pytest collects its modules under bare module names and
never addresses them as ``tests.*``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent

TESTS_ROOTS = (
    REPO_ROOT / "packages" / "design-playbook" / "tests",
    REPO_ROOT / "packages" / "design-playbook-workbench" / "tests",
)

if "tests" not in sys.modules:
    _tests = ModuleType("tests")
    _tests.__path__ = [str(root) for root in TESTS_ROOTS]
    sys.modules["tests"] = _tests
