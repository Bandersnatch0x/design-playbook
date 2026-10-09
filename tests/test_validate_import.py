"""Import and repeat-call contracts for the static validator entry point."""
import contextlib
import importlib.util
import io
import sys
from pathlib import Path
from unittest.mock import patch


VALIDATE = Path(__file__).resolve().parents[1] / "scripts" / "validate.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validator_under_test", VALIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_does_not_validate_or_reconfigure_streams():
    output = io.StringIO()
    path_before = sys.path[:]
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            with patch("pathlib.Path.read_text", side_effect=AssertionError("validation read on import")):
                with patch("subprocess.run", side_effect=AssertionError("process on import")):
                    module = load_validator()
        assert output.getvalue() == ""
        assert module.failures == []
        assert callable(module.main)
        assert module.native_order("Native desktop order: `one` then `two`.") == ("one", "two")
    finally:
        sys.path[:] = path_before


def test_main_returns_status_and_clears_previous_failures():
    path_before = sys.path[:]
    try:
        module = load_validator()
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            for name in vars(module):
                if name.startswith("validate_"):
                    stack.enter_context(patch.object(module, name))
            module.validate_json_manifests.return_value = ({}, {})
            module.validate_runtime_surface.side_effect = lambda: module.check(False, "pinned failure")
            assert module.main() == 1
            assert "VALIDATION FAILED: 1 issue(s)" in output.getvalue()
            module.validate_runtime_surface.side_effect = None
            output.seek(0)
            output.truncate()
            assert module.main() == 0
            assert module.failures == []
            assert output.getvalue() == "\nVALIDATION PASSED\n"
    finally:
        sys.path[:] = path_before

def test_every_named_check_is_registered_and_runs():
    """main() must be a runner over CHECKS, not a hand-ordered procedure.

    A ``validate_*`` function that exists but is missing from ``CHECKS`` never
    runs, and nothing would say so; this pins the two sets to each other so
    adding a check without registering it fails here instead of silently
    passing the gate.
    """
    module = load_validator()
    defined = {
        name for name in vars(module)
        if name.startswith("validate_") and callable(getattr(module, name))
    }
    registered = {name for name, _inputs, _targets in module.CHECKS}
    assert defined == registered
    for name, inputs, targets in module.CHECKS:
        assert isinstance(targets, tuple)
        assert set(inputs) <= {t for _n, _i, ts in module.CHECKS for t in ts}


class _RecordingStream(io.StringIO):
    """A StringIO that remembers any reconfigure() the validator asks for."""

    def __init__(self):
        super().__init__()
        self.reconfigures = []

    def reconfigure(self, **kwargs):
        self.reconfigures.append(kwargs)


def test_main_leaves_the_callers_path_and_streams_alone():
    """An in-process main() must not edit the importer's state.

    The module-level path inserts that make this file importable are measured
    after loading; only main()'s own effect is under test here.
    """
    module = load_validator()
    path_before = sys.path[:]
    stream = _RecordingStream()
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(stream))
        stack.enter_context(contextlib.redirect_stderr(stream))
        for name in vars(module):
            if name.startswith("validate_"):
                stack.enter_context(patch.object(module, name))
        module.validate_json_manifests.return_value = ({}, {})
        module.validate_runtime_surface.side_effect = lambda: module.check(False, "pinned failure")
        assert module.main() == 1
    assert stream.reconfigures == []
    assert sys.path == path_before
