"""Locale selection shared by the generated UI surfaces."""
from __future__ import annotations

import os

ZH = "zh-CN"
EN = "en"


def resolve_ui_locale(locale: str | None = None) -> str:
    """Explicit locale wins; keep the adapter's documented CJK-first env policy.

    A blank explicit locale means "unspecified" (forms and MCP callers
    encode absence as an empty string) and falls back like ``None``;
    anything else still fails closed with ``ValueError``.
    """
    if locale is not None and not locale.strip():
        locale = None
    raw = locale if locale is not None else (
        os.environ.get("DPB_PREVIEW_LANG") or os.environ.get("LANG") or ZH
    )
    language = raw.replace("_", "-").lower().split(".", 1)[0].split("-", 1)[0]
    if language == "en":
        return EN
    if locale is not None and language != "zh":
        raise ValueError(f"Unsupported UI locale: {locale!r}; use zh-CN or en")
    return ZH
