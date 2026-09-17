"""Evidence capture runtime behind one browser-adapter interface.

Captures artifacts via Playwright in production and an injected fake in tests.
Never writes manifest.jsonl; never accepts criterion refs (orchestrator binds).
Returns relative ``artifact`` plus absolute ``written_path`` so RUN_ROOT/cwd
misconfig is visible to the orchestrator.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Protocol

from design_playbook.mcp.evidence import containment
from design_playbook.mcp.evidence.action_params import (
    action_param_errors,
    normalize_action_do,
)
from design_playbook.mcp.evidence.capture_contract import parse_capture_contract
from design_playbook.mcp.evidence.path_syntax import trimmed_relpath
from design_playbook.mcp.evidence.disclosure import (
    LAYOUT_PROBE_JS,
    VIEWPORTS,
    ViewportMetrics,
    metric_payload,
    probe_layout,
)
from design_playbook.mcp.evidence.page_defects import (
    PROBE_SCHEMA,
    probe_defects,
)
from design_playbook.mcp.util import log as _log

CAPTURE_TYPES = frozenset({"screenshot", "a11y tree", "interaction trace"})
ALLOWED_ARGUMENTS = frozenset(
    {
        "schemaVersion",
        "url",
        "type",
        "state",
        "actions",
        "artifact_path",
        "overwrite",
        "viewport",
        "freeze",
        "storage_state",
    }
)
RUN_ROOT_ENV = "DESIGN_PLAYBOOK_RUN_ROOT"


class BrowserAdapter(Protocol):
    """Internal browser seam used by the capture runtime."""

    def capture(
        self,
        *,
        url: str,
        capture_type: str,
        actions: list[dict[str, Any]],
        out_path: Path,
        viewport: dict[str, Any],
        freeze: dict[str, Any],
    ) -> str:
        """Write one artifact and return the observed page state."""


class ProbeBrowserAdapter(Protocol):
    """Optional seam for capturing and probing one browser page."""

    def capture_and_probe(
        self,
        *,
        url: str,
        capture_type: str,
        actions: list[dict[str, Any]],
        out_path: Path,
        viewport: dict[str, Any],
        freeze: dict[str, Any],
    ) -> dict[str, Any]:
        """Capture an artifact and evaluate the layout probe before teardown."""


def _failed(
    artifact: str,
    error: str,
    written_path: str = "",
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture failure payload.

    ``written_path`` is the absolute path under the resolved run root when
    known (empty when path resolution never ran). Callers must not treat a
    non-empty path as proof the file exists — only as where the write was
    attempted. Exposing the absolute path makes cwd / RUN_ROOT misconfig
    visible to the orchestrator without a post-hoc filesystem search.
    """
    payload = {
        "artifact": artifact,
        "observed_state": "unknown",
        "result": "failed",
        "error": error,
        "written_path": written_path,
    }
    if request is not None:
        payload["request"] = request
    return payload


def _captured(
    artifact: str,
    observed_state: str,
    written_path: str,
    request: dict[str, Any],
    *,
    probe_artifact: str = "",
) -> dict[str, Any]:
    """Successful capture payload.

    ``written_path`` is always the absolute path of the written artifact
    (resolved under DESIGN_PLAYBOOK_RUN_ROOT or process cwd). Relative
    ``artifact`` stays the run-root-relative path for manifest binding.
    ``request`` echoes the normalized capture contract for manifest embedding.
    ``probe_artifact`` is the sibling page-probe JSON when a screenshot
    capture produced one (empty otherwise). Facts, not a judgment.
    """
    payload = {
        "artifact": artifact,
        "observed_state": observed_state,
        "result": "captured",
        "error": "",
        "written_path": written_path,
        "request": request,
    }
    if probe_artifact:
        payload["probe_artifact"] = probe_artifact
    return payload


def probe_sidecar_rel(artifact_rel: str) -> str:
    """Sibling ``.probe.json`` path for a screenshot artifact path."""
    if "." in artifact_rel.rsplit("/", 1)[-1]:
        return artifact_rel.rsplit(".", 1)[0] + ".probe.json"
    return artifact_rel + ".probe.json"


_MEASUREMENT_STATUSES = frozenset({"measured", "blocked", "unmeasured"})


def _measurement_meta(
    status: object, error: object, *, missing: str
) -> dict[str, str]:
    """Coerce one measurement face. measured → empty error; other states keep a reason."""
    text_status = str(status) if status else "unmeasured"
    if text_status not in _MEASUREMENT_STATUSES:
        text_status = "unmeasured"
    text_error = str(error or "")
    if text_status == "measured":
        return {"measurement_status": "measured", "measurement_error": ""}
    if not text_error:
        text_error = (
            missing if text_status == "unmeasured" else "probe measurement blocked"
        )
    return {
        "measurement_status": text_status,
        "measurement_error": text_error,
    }


def _console_face(probed: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Map capture_and_probe console_errors to rows + measurement meta.

    Missing key → unmeasured. None → unmeasured. Non-list → blocked.
    A list (including empty) → measured. Never coerce None/bad shape to a
    clean zero-hit.
    """
    missing = "console probe not returned"
    if "console_errors" not in probed:
        return [], _measurement_meta(None, None, missing=missing)
    raw = probed.get("console_errors")
    if raw is None:
        return [], _measurement_meta(
            "unmeasured", "console probe returned no list", missing=missing
        )
    if not isinstance(raw, (list, tuple)):
        return [], _measurement_meta(
            "blocked",
            "console probe output is not a list",
            missing=missing,
        )
    rows = [str(item) for item in raw if item]
    return rows, _measurement_meta("measured", "", missing=missing)


def _write_probe_sidecar(probe_rel: str, probed: dict[str, Any]) -> str:
    """Write page-probe/v1 JSON next to a screenshot.

    Path containment failures raise ValueError so a probing capture cannot
    report success without a sidecar.
    """
    out_path = _resolve_artifact_path(probe_rel)
    metrics = probed.get("metrics")
    defects = probed.get("defects")
    layout: dict[str, Any] = {
        "sw": 0,
        "innerH": 0,
        "hOverflow": 0,
        "inFold": False,
        **_measurement_meta(None, None, missing="layout probe not returned"),
    }
    if metrics is not None:
        layout = {
            "sw": getattr(metrics, "sw", 0),
            "innerH": getattr(metrics, "innerH", 0),
            "hOverflow": getattr(metrics, "hOverflow", 0),
            "inFold": getattr(metrics, "inFold", False),
            **_measurement_meta(
                getattr(metrics, "measurement_status", "unmeasured"),
                getattr(metrics, "measurement_error", ""),
                missing="layout probe not returned",
            ),
        }
    leak_rows = list(getattr(defects, "leaks", ()) or ()) if defects is not None else []
    tap_rows = list(getattr(defects, "tap_fails", ()) or ()) if defects is not None else []
    if defects is None:
        defects_meta = _measurement_meta(
            None, None, missing="defect probe not returned"
        )
    else:
        defects_meta = _measurement_meta(
            getattr(defects, "measurement_status", "unmeasured"),
            getattr(defects, "measurement_error", ""),
            missing="defect probe not returned",
        )
    console_rows, console_meta = _console_face(probed)
    payload = {
        "schema": PROBE_SCHEMA,
        "layout": layout,
        "leaks": leak_rows,
        "tapFails": tap_rows,
        "consoleErrors": console_rows,
        "defects": defects_meta,
        "console": console_meta,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return probe_rel


def _apply_freeze(page: Any, freeze: dict[str, Any]) -> None:
    """Disable motion and optionally wait for fonts / network idle."""
    if freeze.get("enabled", True):
        page.add_style_tag(
            content=(
                "*, *::before, *::after {"
                "animation: none !important;"
                "transition: none !important;"
                "caret-color: transparent !important;"
                "}"
            )
        )
    if freeze.get("waitFonts", True):
        page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
    if freeze.get("networkIdle", False):
        page.wait_for_load_state("networkidle", timeout=30_000)


_RUN_MARKERS = ("plan.md", "point-back.md")
_warned_run_root = False


def _run_root() -> Path:
    configured = os.environ.get(RUN_ROOT_ENV)
    if not configured or configured == ".":
        # cwd-relative default silently mis-roots multi-run workspaces (the
        # root .mcp.json ships DESIGN_PLAYBOOK_RUN_ROOT="."). Warn only when
        # cwd does not look like a run dir (no run marker file) — the shipped
        # default resolving to a real run dir is correct usage, not a
        # misconfig — and only once per process to avoid per-capture spam.
        root = Path.cwd().resolve()
        global _warned_run_root
        if not _warned_run_root and not any(
            (root / marker).is_file() for marker in _RUN_MARKERS
        ):
            _warned_run_root = True
            _log(
                "WARNING: DESIGN_PLAYBOOK_RUN_ROOT is unset or '.' "
                f"(cwd-relative) and {root} has no run marker "
                f"({' / '.join(_RUN_MARKERS)}); artifacts resolve under "
                f"{root}/evidence/. Set DESIGN_PLAYBOOK_RUN_ROOT to the run "
                "root when the host workspace is not the intended run "
                "directory."
            )
        return root
    return Path(configured).resolve()


def _resolve_artifact_path(artifact_path: str) -> Path:
    """Resolve ``artifact_path`` to an absolute path under ``<run_root>/evidence/``.

    Delegates containment to the single Evidence artifact containment module
    (ADR-0026): ``containment.write_target`` owns the canonical resolution and
    every escape rejection (absolute paths, ``..``, resolution failures,
    canonical escapes, observed symlink escapes). This site maps the stable
    reason codes to the Provider's existing ValueError payloads so
    ``execute_capture_plan`` captures them via its existing ``except ValueError``
    path. Callers must not add another preflight check (ADR-0026 TOCTOU limit).

    The caller is responsible for providing a path that already starts with
    ``evidence/``; we do not prepend it (``spec.md`` and ``skills/x`` are
    refused because they land outside the evidence subtree).
    """
    result = containment.write_target(artifact_path, _run_root())
    if result.ok:
        assert result.path is not None  # ok implies path is set
        _refuse_reserved_write(result.path)
        return result.path
    raise ValueError(_reason_message(result.reason))


def _refuse_reserved_write(path: Path) -> None:
    """Provider never writes the manifest SSOT, including via sidecar aliases."""
    if path.name.casefold() == "manifest.jsonl":
        raise ValueError("provider never writes manifest.jsonl")


_JS_MAX_SAFE_INTEGER = 2**53


def _load_storage_state_object(text: str) -> dict[str, Any]:
    """Parse Playwright storage_state JSON without nonstandard constants."""

    def reject_constant(name: str) -> object:
        del name
        raise ValueError("storage_state JSON contains a nonstandard constant")

    def parse_int(raw: str) -> int:
        value = int(raw)
        if abs(value) > _JS_MAX_SAFE_INTEGER:
            raise ValueError("storage_state JSON contains an overflowing integer")
        return value

    def parse_float(raw: str) -> float:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("storage_state JSON contains a non-finite number")
        return value

    try:
        session = json.loads(
            text,
            parse_constant=reject_constant,
            parse_int=parse_int,
            parse_float=parse_float,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("storage_state is not readable JSON") from exc
    if not isinstance(session, dict):
        raise ValueError("storage_state must be a JSON object")
    return session


def _safe_capture_failure(
    exc: BaseException, *, operation: str, session: dict[str, Any] | None
) -> str:
    """Log/return one diagnostic. Session context never echoes exception text.

    When a session was loaded we suppress the raw exception string (it may
    contain ``Call log`` or other operator-sensitive detail). The diagnostic
    keeps the failure type and the operation, plus a neutral recovery cue that
    does NOT assume the failure is a session problem — a navigation
    ``TimeoutError`` after a valid session load is not an auth failure
    (A4-007), so we point at the run log and a supported path rather than
    telling the operator to refresh credentials.
    """
    if session is None:
        return str(exc)
    kind = type(exc).__name__
    return (
        f"{operation} failed ({kind}); operator: check the run log or retry "
        "with a supported path, then recapture"
    )


def _reason_message(reason: str) -> str:
    """Provider message for a containment reason code (ADR-0026).

    Returns the existing ValueError wording for every escape class so the
    capture-failure payload stays compatible. An unmapped code (a future
    reason added to containment.py without a matching entry here) degrades
    to a generic message instead of raising KeyError mid-capture.
    """
    return _REASON_MESSAGES.get(
        reason,
        f"artifact_path was rejected by containment ({reason})",
    )


# Reason-code -> Provider message mapping (ADR-0026). The Provider keeps its
# existing ValueError wording for every escape class so its capture-failure
# payload stays compatible; resolution_failure is the one new surface (the
# old inline resolver propagated OSError uncaught).
_REASON_MESSAGES = {
    containment.REASON_ABSOLUTE_PATH: "artifact_path must be relative to the configured run root",
    containment.REASON_DOTDOT_SEGMENT: "artifact_path must not contain '..' segments",
    containment.REASON_RESOLUTION_FAILURE: "artifact_path could not be resolved under the evidence/ subtree",
    containment.REASON_CANONICAL_ESCAPE: "artifact_path must stay under the evidence/ subtree",
    containment.REASON_SYMLINK_ESCAPE: "artifact_path symlink escapes the evidence/ subtree",
}


def _require_selector(action: dict, index: int, do: str) -> str:
    """Extract and validate a required selector for an action."""
    selector = action.get("selector")
    if not isinstance(selector, str) or not selector:
        raise ValueError(f"actions[{index}].selector required for {do}")
    return selector


def _action_click(page: Any, action: dict, index: int, do: str) -> None:
    selector = _require_selector(action, index, do)
    page.click(selector, timeout=10_000)


def _action_fill(page: Any, action: dict, index: int, do: str) -> None:
    selector = _require_selector(action, index, do)
    value = action.get("value")
    if value is None:
        value = action.get("text", "")
    if not isinstance(value, str):
        raise ValueError(f"actions[{index}].value must be a string")
    page.fill(selector, value, timeout=10_000)


def _action_type(page: Any, action: dict, index: int, do: str) -> None:
    selector = _require_selector(action, index, do)
    value = action.get("value")
    if value is None:
        value = action.get("text", "")
    if not isinstance(value, str):
        raise ValueError(f"actions[{index}].value must be a string")
    page.click(selector, timeout=10_000)
    page.keyboard.type(value)


def _action_press(page: Any, action: dict, index: int, do: str) -> None:
    key = action.get("key") or action.get("value")
    if not isinstance(key, str) or not key:
        raise ValueError(f"actions[{index}].key required for press")
    selector = action.get("selector")
    if isinstance(selector, str) and selector:
        page.press(selector, key, timeout=10_000)
    else:
        page.keyboard.press(key)


def _action_wait_for_selector(page: Any, action: dict, index: int, do: str) -> None:
    selector = _require_selector(action, index, do)
    page.wait_for_selector(selector, timeout=10_000)


def _action_wait_for_state(page: Any, action: dict, index: int, do: str) -> None:
    state = action.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError(f"actions[{index}].state required for wait_for_state")
    selector = action.get("selector")
    target = (
        f'{selector}[data-state="{state}"]'
        if isinstance(selector, str) and selector
        else f'[data-state="{state}"]'
    )
    page.wait_for_selector(target, timeout=10_000)


def _action_wait(page: Any, action: dict, index: int, do: str) -> None:
    ms = action.get("ms")
    if ms is None:
        ms = action.get("timeout_ms", 200)
    page.wait_for_timeout(int(ms))


def _action_select_option(page: Any, action: dict, index: int, do: str) -> None:
    selector = _require_selector(action, index, do)
    value = action.get("value")
    label = action.get("label")
    if value is None and label is None:
        raise ValueError(f"actions[{index}].value or label required for select_option")
    if value is not None:
        page.select_option(selector, value=value, timeout=10_000)
    else:
        page.select_option(selector, label=label, timeout=10_000)


# Action registry: do → handler. Each handler owns its validation + Playwright
# call. Adding an action type means adding a function + one entry here, not an
# elif branch in a 75-line function.
_ACTION_HANDLERS: dict[str, Any] = {
    "click": _action_click,
    "fill": _action_fill,
    "type": _action_type,
    "press": _action_press,
    "wait_for_selector": _action_wait_for_selector,
    "wait_for_state": _action_wait_for_state,
    "wait": _action_wait,
    "sleep": _action_wait,
    "select_option": _action_select_option,
}


def _run_actions(page: Any, actions: list[dict[str, Any]]) -> None:
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{i}] must be an object")
        raw_do = action.get("do")
        do = normalize_action_do(raw_do)
        if not do:
            raise ValueError(f"actions[{i}].do is required")
        handler = _ACTION_HANDLERS.get(do)
        if handler is None:
            raise ValueError(f"actions[{i}]: unsupported do={do!r}")
        checked = dict(action)
        checked["do"] = do
        param_errors = action_param_errors(checked, i)
        if param_errors:
            raise ValueError(param_errors[0])
        handler(page, action, i, do)


def _read_observed_state(page: Any) -> str:
    try:
        value = page.evaluate(
            """() => {
              const body = document.body;
              if (body && body.dataset && body.dataset.state) {
                return body.dataset.state;
              }
              const root = document.documentElement;
              if (root && root.dataset && root.dataset.state) {
                return root.dataset.state;
              }
              const el = document.querySelector("[data-state]");
              if (el && el.getAttribute("data-state")) {
                return el.getAttribute("data-state");
              }
              return null;
            }"""
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as exc:  # noqa: BLE001 ? report an honest unknown
        _log(f"observed_state probe failed: {exc}")
    return "unknown"


def _write_screenshot(page: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def _write_a11y_tree(page: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Playwright removed page.accessibility; aria_snapshot is the v1 tree.
    if hasattr(page, "aria_snapshot"):
        tree = page.aria_snapshot()
        payload: Any = {"format": "aria_snapshot", "tree": tree}
    elif hasattr(page, "accessibility"):
        payload = page.accessibility.snapshot()
    else:
        raise RuntimeError("page has no aria_snapshot/accessibility API")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_interaction_trace(
    context: Any, page: Any, path: Path, actions: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Restart tracing for this capture only.
    try:
        context.tracing.stop()
    except Exception:  # noqa: BLE001 — may not have started
        pass
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        _run_actions(page, actions)
        context.tracing.stop(path=str(path))
    except Exception:
        try:
            context.tracing.stop()
        except Exception:  # noqa: BLE001
            pass
        raise


class PlaywrightBrowserAdapter:
    """Production adapter for one isolated Playwright capture."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._sync_playwright = sync_playwright

    def _capture_page(
        self,
        *,
        url: str,
        capture_type: str,
        actions: list[dict[str, Any]],
        out_path: Path,
        viewport: dict[str, Any],
        freeze: dict[str, Any],
        probe: bool,
        storage_state: str | None = None,
    ) -> dict[str, Any]:
        """Single Playwright capture path shared by the two adapter seams.

        ``probe=False`` stops after the observed state (the plain
        :class:`BrowserAdapter` contract); ``probe=True`` additionally
        evaluates layout and defect probes on the same page before teardown
        so the screenshot and its sidecar share one browser pass.
        """
        with self._sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context_kwargs: dict[str, Any] = {
                    "viewport": {
                        "width": viewport["width"],
                        "height": viewport["height"],
                    },
                    "device_scale_factor": viewport["devicePixelRatio"],
                    "color_scheme": viewport["colorScheme"],
                }
                if storage_state:
                    context_kwargs["storage_state"] = storage_state
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                console_errors: list[str] = []
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text)
                    if msg.type == "error" and msg.text
                    else None,
                )
                page.on(
                    "pageerror",
                    lambda exc: console_errors.append(str(exc)),
                )
                if viewport.get("media"):
                    page.emulate_media(media=viewport["media"])
                wait_until = (
                    "networkidle" if freeze.get("networkIdle") else "domcontentloaded"
                )
                page.goto(url, wait_until=wait_until, timeout=30_000)
                _apply_freeze(page, freeze)

                if capture_type == "interaction trace":
                    _write_interaction_trace(context, page, out_path, actions)
                    _apply_freeze(page, freeze)
                else:
                    _run_actions(page, actions)
                    _apply_freeze(page, freeze)
                    if capture_type == "screenshot":
                        _write_screenshot(page, out_path)
                    elif capture_type == "a11y tree":
                        _write_a11y_tree(page, out_path)

                observed = _read_observed_state(page)
                if not probe:
                    return {"observed_state": observed}
                raw = page.evaluate(LAYOUT_PROBE_JS)
                metrics = probe_layout(lambda _js: raw)
                defects = probe_defects(page.evaluate)
                return {
                    "observed_state": observed,
                    "metrics": metrics,
                    "defects": defects,
                    "console_errors": console_errors,
                }
            finally:
                browser.close()

    def capture(
        self,
        *,
        url: str,
        capture_type: str,
        actions: list[dict[str, Any]],
        out_path: Path,
        viewport: dict[str, Any],
        freeze: dict[str, Any],
        storage_state: str | None = None,
    ) -> str:
        result = self._capture_page(
            url=url,
            capture_type=capture_type,
            actions=actions,
            out_path=out_path,
            viewport=viewport,
            freeze=freeze,
            probe=False,
            storage_state=storage_state,
        )
        return str(result["observed_state"])

    def capture_and_probe(
        self,
        *,
        url: str,
        capture_type: str,
        actions: list[dict[str, Any]],
        out_path: Path,
        viewport: dict[str, Any],
        freeze: dict[str, Any],
        storage_state: str | None = None,
    ) -> dict[str, Any]:
        """Capture and probe the same page before closing its browser."""
        return self._capture_page(
            url=url,
            capture_type=capture_type,
            actions=actions,
            out_path=out_path,
            viewport=viewport,
            freeze=freeze,
            probe=True,
            storage_state=storage_state,
        )


def _validate_runtime_object(
    args: dict[str, Any],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    """Validate Runtime Object fields and return (url, cap_type, state, actions).

    Owns the field-level validation that execute_capture_plan previously
    interleaved with capture logic. Keeps url/type/state/actions validation
    in one locality so the handler reads cleanly.
    """
    url = args.get("url")
    cap_type = args.get("type")
    state = args.get("state")
    actions = args.get("actions")

    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")
    if not isinstance(cap_type, str) or cap_type not in CAPTURE_TYPES:
        raise ValueError(
            f"type must be one of {sorted(CAPTURE_TYPES)}; got {cap_type!r}"
        )
    if not isinstance(state, str) or not state.strip():
        raise ValueError("state is required")
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        raise ValueError("actions must be an array")
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ValueError(f"actions[{i}] must be an object")
    return url, cap_type, state, actions


def execute_capture_plan(
    args: dict[str, Any],
    browser_adapter: BrowserAdapter | None = None,
) -> dict[str, Any]:
    unknown = sorted(set(args) - ALLOWED_ARGUMENTS)
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(
            f"unsupported argument(s): {names}; provider accepts Runtime Object fields only"
        )

    # Capture contract first: fail closed before path resolution so unversioned
    # requests never partially execute (ADR-0018).
    try:
        request = parse_capture_contract(args)
    except ValueError as exc:
        artifact = args.get("artifact_path")
        label = artifact if isinstance(artifact, str) else ""
        return _failed(label, str(exc))

    url, cap_type, state, actions = _validate_runtime_object(args)
    artifact_path = args.get("artifact_path")
    overwrite = args.get("overwrite", False)
    storage_state_rel = args.get("storage_state")

    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ValueError("artifact_path is required")
    if not isinstance(overwrite, bool):
        raise ValueError("overwrite must be a boolean")
    if storage_state_rel is None:
        storage_state_rel = ""
    if storage_state_rel != "" and not isinstance(storage_state_rel, str):
        raise ValueError("storage_state must be a string path when provided")

    rel = artifact_path.strip()
    try:
        out_path = _resolve_artifact_path(rel)
    except ValueError as exc:
        return _failed(rel, str(exc), request=request)
    storage_state_path = ""
    session_obj: dict[str, Any] | None = None
    if storage_state_rel:
        session_rel = trimmed_relpath(storage_state_rel)
        resolved = containment.read_under(_run_root(), session_rel)
        if not resolved.ok or resolved.path is None:
            return _failed(
                rel,
                f"storage_state was rejected ({resolved.reason or 'unreadable'})",
                request=request,
            )
        try:
            raw_session = resolved.path.read_text(encoding="utf-8")
            session_obj = _load_storage_state_object(raw_session)
        except (OSError, UnicodeError):
            return _failed(
                rel,
                "storage_state is not readable JSON",
                request=request,
            )
        except ValueError as exc:
            return _failed(rel, str(exc), request=request)
        storage_state_path = str(resolved.path)
    abs_written = str(out_path)
    # G6 write boundary: refuse to overwrite an existing artifact unless the
    # caller explicitly opts in via overwrite=true. Checked before any
    # Playwright launch so a misconfigured re-run cannot clobber prior evidence.
    will_probe = cap_type == "screenshot" and (
        browser_adapter is None
        or callable(getattr(browser_adapter, "capture_and_probe", None))
    )
    probe_rel = probe_sidecar_rel(rel) if will_probe else ""
    probe_path = None
    if probe_rel:
        try:
            probe_path = _resolve_artifact_path(probe_rel)
        except ValueError as exc:
            return _failed(
                rel,
                f"probe sidecar path rejected: {exc}",
                request=request,
            )
    if out_path.exists() and not overwrite:
        return _failed(
            rel,
            f"artifact already exists: {out_path} (pass overwrite=true to replace)",
            abs_written,
            request=request,
        )
    if probe_path is not None and probe_path.exists() and not overwrite:
        return _failed(
            rel,
            f"artifact already exists: {probe_path} (pass overwrite=true to replace)",
            abs_written,
            request=request,
        )

    viewport = request["viewport"]
    freeze = request["freeze"]
    if browser_adapter is None:
        try:
            browser_adapter = PlaywrightBrowserAdapter()
        except ImportError as exc:
            return _failed(
                rel,
                f"playwright not installed: {exc}",
                abs_written,
                request=request,
            )
    capture_kwargs: dict[str, Any] = {
        "url": url.strip(),
        "capture_type": cap_type,
        "actions": actions,
        "out_path": out_path,
        "viewport": viewport,
        "freeze": freeze,
    }
    if storage_state_path:
        capture_kwargs["storage_state"] = storage_state_path
    probe_payload: dict[str, Any] | None = None
    try:
        probe_fn = getattr(browser_adapter, "capture_and_probe", None)
        if cap_type == "screenshot" and callable(probe_fn):
            probe_payload = probe_fn(**capture_kwargs)
            observed = str(probe_payload.get("observed_state") or "unknown")
        else:
            observed = browser_adapter.capture(**capture_kwargs)
    except Exception as exc:  # noqa: BLE001 — surface as capture failure
        safe = _safe_capture_failure(
            exc, operation="capture", session=session_obj
        )
        _log(safe)
        return _failed(rel, safe, abs_written, request=request)

    if not out_path.is_file():
        return _failed(
            rel,
            f"artifact not written: {out_path}",
            abs_written,
            request=request,
        )

    wrote_probe = ""
    if probe_payload is not None:
        if not probe_rel:
            return _failed(
                rel,
                "probe sidecar path rejected: missing sidecar path",
                abs_written,
                request=request,
            )
        # OSError (disk full / permission / path-is-a-directory) must reach the
        # orchestrator via the same {result:"failed"} channel as the main
        # capture — escaping to MCP isError loses the structured echo (A3-002).
        # ValueError stays for containment/path-shape sidecar rejection and
        # keeps its full message (debug info, not raw exception text). We do
        # NOT write a clean sidecar; the failure carries written_path (the
        # non-secret absolute artifact path).
        try:
            wrote_probe = _write_probe_sidecar(probe_rel, probe_payload)
        except ValueError as exc:
            return _failed(
                rel,
                f"probe sidecar path rejected: {exc}",
                abs_written,
                request=request,
            )
        except OSError as exc:
            return _failed(
                rel,
                f"probe sidecar write failed: {type(exc).__name__}",
                abs_written,
                request=request,
            )
        if not wrote_probe:
            return _failed(
                rel,
                "probe sidecar was not written",
                abs_written,
                request=request,
            )
    return _captured(
        rel, observed, abs_written, request, probe_artifact=wrote_probe
    )


# --------------------------------------------------------------------------- #
# Stage 9 delivery matrix: five-viewport capture + fold/overflow metrics       #
# --------------------------------------------------------------------------- #


def matrix_viewport(name: str) -> dict[str, Any]:
    """Map a standard delivery viewport name to a capture-contract viewport.

    ``sw``/``innerH`` become the contract ``width``/``height``; device pixels
    stay at 1.0 with the Light color scheme so the matrix is reproducible.
    The ``print`` viewport additionally carries ``media: "print"`` so the
    adapter emulates print media (page breaks, print stylesheets) rather than
    just resizing the window. Unknown names raise ValueError so a caller cannot
    silently capture a non-standard viewport into the disclosure matrix.
    """
    ref = VIEWPORTS.get(name)
    if ref is None:
        raise ValueError(
            f"unknown delivery viewport {name!r}; expected one of {sorted(VIEWPORTS)}"
        )
    viewport = {
        "width": ref["sw"],
        "height": ref["innerH"],
        "devicePixelRatio": 1.0,
        "colorScheme": "light",
    }
    if ref.get("kind") == "print":
        viewport["media"] = "print"
    return viewport


def capture_delivery_matrix(
    *,
    url: str,
    out_dir: Path,
    freeze: dict[str, Any] | None = None,
    browser_adapter: BrowserAdapter | None = None,
) -> dict[str, dict[str, Any]]:
    """Drive the five standard delivery viewports and return their metrics.

    For each of ``VIEWPORTS``, captures one full-page screenshot under
    ``out_dir`` (``viewport-<name>.png``) and reads the layout probe. The
    returned dict maps viewport name -> ``{metrics, screenshot}`` so a caller
    can assemble the ``disclosure-review.json`` matrix and the ``/export-zip``
    package from one pass.

    ``out_dir`` is required and carries no default: handoff artifacts live
    under the run tree (``<run_root>/evidence/static-handoff/``, ADR-0034 §5),
    never the process CWD, so the caller must pass the run-tree destination
    explicitly. ``browser_adapter`` uses the same ``BrowserAdapter`` seam as
    ``execute_capture_plan`` (real Playwright by default, injected fake in
    tests). Production adapters should expose ``capture_and_probe`` so the
    snapshot and metrics share one page; adapters without that seam remain
    explicitly ``unmeasured``.
    """
    freeze = freeze or {"enabled": True, "waitFonts": True, "networkIdle": False}
    if browser_adapter is None:
        browser_adapter = PlaywrightBrowserAdapter()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    for name in VIEWPORTS:
        viewport = matrix_viewport(name)
        out_path = out_dir / f"viewport-{name}.png"
        try:
            capture_and_probe = getattr(browser_adapter, "capture_and_probe", None)
            if callable(capture_and_probe):
                captured = capture_and_probe(
                    url=url,
                    capture_type="screenshot",
                    actions=[],
                    out_path=out_path,
                    viewport=viewport,
                    freeze=freeze,
                )
                measured = captured.get("metrics") if isinstance(captured, dict) else None
                if not isinstance(measured, ViewportMetrics):
                    raise TypeError("capture_and_probe returned no ViewportMetrics")
                metrics = metric_payload(measured)
            else:
                browser_adapter.capture(
                    url=url,
                    capture_type="screenshot",
                    actions=[],
                    out_path=out_path,
                    viewport=viewport,
                    freeze=freeze,
                )
                metrics = _unmeasured_metric_payload(name)
            results[name] = {"metrics": metrics, "screenshot": str(out_path)}
        except Exception as exc:  # noqa: BLE001 — preserve blocked evidence
            _log(f"matrix capture/probe failed for {name}: {exc}")
            results[name] = {
                "metrics": metric_payload(
                    ViewportMetrics(
                        sw=VIEWPORTS[name]["sw"],
                        innerH=VIEWPORTS[name]["innerH"],
                        hOverflow=0,
                        inFold=False,
                        measurement_status="blocked",
                        measurement_error=str(exc),
                    )
                ),
                "screenshot": str(out_path),
                "result": "blocked",
                "error": str(exc),
            }
    return results


def _unmeasured_metric_payload(name: str) -> dict[str, Any]:
    """Return reference dimensions without claiming a layout measurement."""
    ref = VIEWPORTS[name]
    return metric_payload(
        ViewportMetrics(
            sw=ref["sw"],
            innerH=ref["innerH"],
            hOverflow=0,
            inFold=False,
            measurement_status="unmeasured",
        )
    )
