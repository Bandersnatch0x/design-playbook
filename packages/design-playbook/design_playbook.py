"""Namespace alias: absolute ``design_playbook.*`` imports inside this plugin.

The plugin directory is ``design-playbook`` (hyphen), so Python's import
system cannot load it under the identifier ``design_playbook`` — FileFinder
matches directory names literally. This module aliases the package root onto
``design_playbook.__path__`` so that, once the one bootstrap (ADR-0022) puts
the package root on ``sys.path``, absolute imports such as
``design_playbook.mcp.preview.integrity`` and
``design_playbook.scripts.stages`` resolve to the real ``mcp/`` and
``scripts/`` trees below.

The alias also keeps the import seam namespaced: a bare ``mcp.*`` import
would collide with the PyPI ``mcp`` SDK when the host has it installed.
"""
from __future__ import annotations

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent)]
__all__: list[str] = []
