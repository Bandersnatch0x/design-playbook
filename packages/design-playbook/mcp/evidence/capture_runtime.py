"""Evidence capture runtime behind one browser-adapter interface.

Captures artifacts via Playwright in production and an injected fake in tests.
Never writes manifest.jsonl; never accepts criterion refs (orchestrator binds).
Returns relative ``artifact`` plus absolute ``written_path`` so RUN_ROOT/cwd
misconfig is visible to the orchestrator.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Protocol

from design_playbook.mcp.evidence import containment
from design_playbook.mcp.evidence.capture_contract import parse_capture_contract

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
    }
)
RUN_ROOT_ENV = "DESIGN_PLAYBOOK_RUN_ROOT"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


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
) -> dict[str, Any]:
    """Successful capture payload.

    ``written_path`` is always the absolute path of the written artifact
    (resolved under DESIGN_PLAYBOOK_RUN_ROOT or process cwd). Relative
    ``artifact`` stays the run-root-relative path for manifest binding.
    ``request`` echoes the normalized capture contract for manifest embedding.
    """
    return {
        "artifact": artifact,
        "observed_state": observed_state,
        "result": "captured",
        "error": "",
        "written_path": written_path,
        "request": request,
    }


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
        return result.path  # type: ignore[return-value]
    raise ValueError(_reason_message(result.reason))


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
    containment.REASON_ABSOLUTE_PATH:
        "artifact_path must be relative to the configured run root",
    containment.REASON_DOTDOT_SEGMENT:
        "artifact_path must not contain '..' segments",
    containment.REASON_RESOLUTION_FAILURE:
        "artifact_path could not be resolved under the evidence/ subtree",
    containment.REASON_CANONICAL_ESCAPE:
        "artifact_path must stay under the evidence/ subtree",
    containment.REASON_SYMLINK_ESCAPE:
        "artifact_path symlink escapes the evidence/ subtree",
}


def _run_actions(page: Any, actions: list[dict[str, Any]]) -> None:
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{i}] must be an object")
        do = action.get("do")
        if not isinstance(do, str) or not do.strip():
            raise ValueError(f"actions[{i}].do is required")
        do = do.strip().lower()
        selector = action.get("selector")
        if do == "click":
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"actions[{i}].selector required for click")
            page.click(selector, timeout=10_000)
        elif do in ("fill", "type"):
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"actions[{i}].selector required for {do}")
            value = action.get("value")
            if value is None:
                value = action.get("text", "")
            if not isinstance(value, str):
                raise ValueError(f"actions[{i}].value must be a string")
            if do == "fill":
                page.fill(selector, value, timeout=10_000)
            else:
                page.click(selector, timeout=10_000)
                page.keyboard.type(value)
        elif do == "press":
            key = action.get("key") or action.get("value")
            if not isinstance(key, str) or not key:
                raise ValueError(f"actions[{i}].key required for press")
            if isinstance(selector, str) and selector:
                page.press(selector, key, timeout=10_000)
            else:
                page.keyboard.press(key)
        elif do == "wait_for_selector":
            if not isinstance(selector, str) or not selector:
                raise ValueError(
                    f"actions[{i}].selector required for wait_for_selector"
                )
            page.wait_for_selector(selector, timeout=10_000)
        elif do == "wait_for_state":
            state = action.get("state")
            if not isinstance(state, str) or not state:
                raise ValueError(f"actions[{i}].state required for wait_for_state")
            # Prefer explicit selector; else body[data-state].
            if isinstance(selector, str) and selector:
                page.wait_for_selector(selector, timeout=10_000)
            else:
                page.wait_for_selector(
                    f'[data-state="{state}"]',
                    timeout=10_000,
                )
        elif do in ("wait", "sleep"):
            ms = action.get("ms")
            if ms is None:
                ms = action.get("timeout_ms", 200)
            page.wait_for_timeout(int(ms))
        elif do == "select_option":
            # Native <select> — page.fill raises "Fill did not work on <select>";
            # select_option drives <option> by value (or visible label) and
            # fires change.
            if not isinstance(selector, str) or not selector:
                raise ValueError(
                    f"actions[{i}].selector required for select_option")
            value = action.get("value")
            label = action.get("label")
            if value is None and label is None:
                raise ValueError(
                    f"actions[{i}].value or label required for select_option")
            if value is not None:
                page.select_option(selector, value=value, timeout=10_000)
            else:
                page.select_option(selector, label=label, timeout=10_000)
        else:
            raise ValueError(f"actions[{i}]: unsupported do={do!r}")


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
        with self._sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    viewport={
                        "width": viewport["width"],
                        "height": viewport["height"],
                    },
                    device_scale_factor=viewport["devicePixelRatio"],
                    color_scheme=viewport["colorScheme"],
                )
                page = context.new_page()
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

                return _read_observed_state(page)
            finally:
                browser.close()


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

    url = args.get("url")
    cap_type = args.get("type")
    state = args.get("state")
    actions = args.get("actions")
    artifact_path = args.get("artifact_path")
    overwrite = args.get("overwrite", False)

    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")
    if not isinstance(cap_type, str) or cap_type not in CAPTURE_TYPES:
        raise ValueError(
            f'type must be one of {sorted(CAPTURE_TYPES)}; got {cap_type!r}'
        )
    if not isinstance(state, str) or not state.strip():
        raise ValueError("state is required")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ValueError("artifact_path is required")
    if not isinstance(overwrite, bool):
        raise ValueError("overwrite must be a boolean")
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        raise ValueError("actions must be an array")
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ValueError(f"actions[{i}] must be an object")

    rel = artifact_path.strip()
    try:
        out_path = _resolve_artifact_path(rel)
    except ValueError as exc:
        return _failed(rel, str(exc), request=request)
    abs_written = str(out_path)
    # Refuse every case variant of the manifest execution-record SSOT.
    if out_path.name.casefold() == "manifest.jsonl":
        return _failed(
            rel, "provider never writes manifest.jsonl", abs_written, request=request
        )
    # G6 write boundary: refuse to overwrite an existing artifact unless the
    # caller explicitly opts in via overwrite=true. Checked before any
    # Playwright launch so a misconfigured re-run cannot clobber prior evidence.
    if out_path.exists() and not overwrite:
        return _failed(
            rel,
            f"artifact already exists: {out_path} "
            "(pass overwrite=true to replace)",
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
    try:
        observed = browser_adapter.capture(
            url=url.strip(),
            capture_type=cap_type,
            actions=actions,
            out_path=out_path,
            viewport=viewport,
            freeze=freeze,
        )
    except Exception as exc:  # noqa: BLE001 — surface as capture failure
        _log(f"capture failed: {exc}")
        return _failed(rel, str(exc), abs_written, request=request)

    if not out_path.is_file():
        return _failed(
            rel,
            f"artifact not written: {out_path}",
            abs_written,
            request=request,
        )

    return _captured(rel, observed, abs_written, request)
