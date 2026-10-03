from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from design_playbook.mcp.preview.live_route import observe_visual_source
from design_playbook.mcp.preview.visual_batch import (
    VisualBatchError,
    normalize_visual_batch,
    validate_batch_current,
)


@pytest.fixture
def dynamic_host(tmp_path):
    (tmp_path / "index.html").write_text("<html>Host entry</html>", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/App.tsx").write_text("export const title = 'before';", encoding="utf-8")
    (tmp_path / "assets.json").write_text(
        json.dumps({"assets": ["src/App.tsx"]}), encoding="utf-8")
    state = {"renders": 0, "status": 200, "content_type": "text/html"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            state["renders"] += 1
            body = f"<html>dynamic render {state['renders']}</html>".encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", state["content_type"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # Suppress the test server's access log, not observation failures.

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield tmp_path, f"http://127.0.0.1:{server.server_port}/", state
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def test_declared_source_observation_stable_across_dynamic_html(dynamic_host):
    root, route, state = dynamic_host
    first = observe_visual_source(root / "index.html", route)
    second = observe_visual_source(root / "index.html", route)
    assert state["renders"] == 2  # Both HTTP responses were really fetched and differ.
    assert first == second


def test_declared_source_change_invalidates_batch(dynamic_host):
    root, route, _ = dynamic_host
    source_hash = observe_visual_source(root / "index.html", route)
    batch = normalize_visual_batch({"edits": [{
        "locator": "#title", "property": "color", "oldValue": "red", "newValue": "blue",
    }]}, source_hash=source_hash, route_url=route)
    validate_batch_current(batch, observe_visual_source(root / "index.html", route), current_route_url=route)
    (root / "src/App.tsx").write_text("export const title = 'after';", encoding="utf-8")
    current = observe_visual_source(root / "index.html", route)
    assert current != source_hash
    with pytest.raises(VisualBatchError, match="stale"):
        validate_batch_current(batch, current, current_route_url=route)
    assert batch["sourceHash"] == source_hash


@pytest.mark.parametrize("status,content_type,error", [
    (503, "text/html", "observation failed"),
    (200, "application/json", "must return text/html"),
])
def test_declared_source_still_requires_reachable_html(dynamic_host, status, content_type, error):
    root, route, state = dynamic_host
    state.update(status=status, content_type=content_type)
    with pytest.raises(VisualBatchError, match=error):
        observe_visual_source(root / "index.html", route)
    assert state["renders"] == 1


def test_declared_asset_map_changes_are_bound(dynamic_host):
    root, route, _ = dynamic_host
    first = observe_visual_source(root / "index.html", route)
    (root / "src/theme.css").write_text("body { color: red; }", encoding="utf-8")
    assert observe_visual_source(root / "index.html", route) == first  # No asset discovery.
    (root / "assets.json").write_text(
        json.dumps({"assets": ["src/App.tsx", "src/theme.css"]}), encoding="utf-8")
    second = observe_visual_source(root / "index.html", route)
    assert second != first
    (root / "src/theme.css").write_text("body { color: blue; }", encoding="utf-8")
    assert observe_visual_source(root / "index.html", route) != second


def test_single_html_without_asset_map_keeps_response_binding(dynamic_host):
    root, route, _ = dynamic_host
    (root / "assets.json").unlink()
    assert observe_visual_source(root / "index.html", route) != observe_visual_source(root / "index.html", route)


@pytest.mark.parametrize("names", [["../outside"], ["/absolute"], ["C:/outside"],
                                   ["src\\App.tsx"], ["src/App.tsx", "src/App.tsx"],
                                   ["missing.tsx"], []])
def test_declared_asset_map_refuses_unsafe_or_missing_files(dynamic_host, names):
    root, route, _ = dynamic_host
    (root / "assets.json").write_text(json.dumps({"assets": names}), encoding="utf-8")
    with pytest.raises(VisualBatchError, match="declared source"):
        observe_visual_source(root / "index.html", route)


def test_detached_preview_and_explicit_host_map_share_source_binding(dynamic_host, tmp_path):
    root, route, _ = dynamic_host
    preview = tmp_path / "preview"
    preview.mkdir()
    prototype = preview / "index.html"
    prototype.write_bytes((root / "index.html").read_bytes())
    nested = root / "declarations"
    nested.mkdir()
    manifest = nested / "assets.json"
    (root / "assets.json").rename(manifest)
    (preview / "visual-source.json").write_text(json.dumps({
        "sourceRoot": str(root.resolve()), "assetMap": "declarations/assets.json",
    }), encoding="utf-8")
    observed = observe_visual_source(prototype, route)
    assert observed == observe_visual_source(root / "index.html", route,
                                            source_root=root, asset_map=manifest)
    (root / "src/App.tsx").write_text("changed", encoding="utf-8")
    assert observe_visual_source(prototype, route) != observed
    assert observe_visual_source(prototype, route) == observe_visual_source(
        root / "index.html", route, source_root=root, asset_map=manifest)


def test_explicit_asset_map_missing_or_outside_source_root_refuses(dynamic_host, tmp_path):
    root, route, _ = dynamic_host
    for manifest in (root / "missing.json", root.parent / "outside.json"):
        with pytest.raises(VisualBatchError, match="declared source"):
            observe_visual_source(root / "index.html", route, source_root=root, asset_map=manifest)
    with pytest.raises(VisualBatchError, match="declared together"):
        observe_visual_source(root / "index.html", route, source_root=root)


def test_malformed_sidecar_does_not_fall_back_to_response(dynamic_host):
    root, route, _ = dynamic_host
    (root / "visual-source.json").write_text('{"sourceRoot":42}', encoding="utf-8")
    with pytest.raises(VisualBatchError, match="declared source"):
        observe_visual_source(root / "index.html", route)
