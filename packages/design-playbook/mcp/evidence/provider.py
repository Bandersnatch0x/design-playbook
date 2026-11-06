"""Registered capture-provider interface (T-145).

The bundled adapter is the only capture provider shipped, but the seam a
third party implements is written down here: a ``tool_name``, ``describe()``
returning the tool declaration (including ``outputSchema``), and
``capture(arguments)`` returning the payload shape in
``capture_contract.capture_result_schema``.

Registration is process-local and must happen before the adapter starts. The
bundled provider is the default, so an unregistered process behaves exactly
as before.
"""
from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

# The tool name the bundled adapter advertises; ``probe_*`` reports it.
CAPTURE_TOOL_NAME = "execute_capture_plan"


@runtime_checkable
class CaptureProvider(Protocol):
    """What a capture provider must expose over stdio."""

    tool_name: str

    def describe(self) -> dict[str, Any]:
        """Return this provider's MCP tool declaration."""

    def capture(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run one capture and return the capture result payload."""


class ProviderRegistrationError(ValueError):
    """A provider cannot serve the capture tool."""


_REGISTRY: dict[str, CaptureProvider] = {}


def register_capture_provider(
    provider: CaptureProvider, *, replace: bool = False
) -> None:
    """Register ``provider`` under its ``tool_name`` for this process."""
    name = getattr(provider, "tool_name", None)
    if not isinstance(name, str) or not name:
        raise ProviderRegistrationError(
            "capture provider must declare a non-empty tool_name"
        )
    for method in ("describe", "capture"):
        if not callable(getattr(provider, method, None)):
            raise ProviderRegistrationError(
                f"capture provider {name!r} must implement {method}()"
            )
    if name in _REGISTRY and not replace:
        raise ProviderRegistrationError(
            f"capture provider {name!r} is already registered"
        )
    _REGISTRY[name] = provider


def registered_capture_providers() -> dict[str, CaptureProvider]:
    """Snapshot of the registered providers, keyed by tool name."""
    return dict(_REGISTRY)


def resolve_capture_provider(
    default: CaptureProvider | None = None,
) -> CaptureProvider:
    """Return the registered provider, or ``default`` when none is registered.

    More than one registration is ambiguous and fails closed; pass a name to
    ``registered_capture_providers`` when a process hosts several.
    """
    if not _REGISTRY:
        if default is None:
            raise ProviderRegistrationError("no capture provider is registered")
        return default
    if len(_REGISTRY) > 1:
        raise ProviderRegistrationError(
            "multiple capture providers are registered: "
            + ", ".join(sorted(_REGISTRY))
        )
    return next(iter(_REGISTRY.values()))


def probe_capture_provider(tool_names: Iterable[str]) -> str | None:
    """Return the advertised capture tool name, or None when it is absent."""
    return CAPTURE_TOOL_NAME if CAPTURE_TOOL_NAME in tool_names else None
