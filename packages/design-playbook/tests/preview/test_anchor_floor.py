"""F3: an anchor the parser cannot use must fail the round, not disappear.

The floor rule is "every supplied anchor carries a selector and a comment".
`_parse_anchors` used to drop an item with an empty selector, so the floor never
saw the incomplete anchor and a round with valid feedback or an effective visual
edit confirmed anyway.

Two layers are pinned here. The parser must raise on an item it cannot trust,
and the served `/decide` endpoint must refuse the round without spending the
one-time token, so a malformed submission cannot burn a reviewer's session.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlrequest

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.integrity import (  # noqa: E402
    evaluate_feedback_floor,
    prototype_html_digest,
)
from design_playbook.mcp.preview.transaction import run_preview_transaction  # noqa: E402

PROTOTYPE = '<!doctype html><html><body><h2 id="panel-title">Anchor floor</h2></body></html>'
UNUSABLE = (
    '[{"selector":"","comment":"incomplete anchor"}]',
    '[{"selector":"   ","comment":"whitespace selector"}]',
    '[{"comment":"no selector key"}]',
    '["not-an-object"]',
    '{"selector":"h2"}',
    'not json at all',
)


def test_parser_raises_on_an_anchor_it_cannot_trust() -> None:
    for raw in UNUSABLE:
        with pytest.raises(review_session.AnchorParseError):
            review_session._parse_anchors(raw, 1)


def test_parser_keeps_a_supplied_but_incomplete_anchor_for_the_floor() -> None:
    anchors = review_session._parse_anchors('[{"selector":"h2","comment":""}]', 1)
    assert len(anchors) == 1, "an incomplete anchor must reach the floor, not vanish"
    floor = evaluate_feedback_floor("", anchors)
    assert floor.passed is False
    assert "anchor missing non-empty selector and comment" in floor.reason


class _PrintOnlyAdapter:
    def __init__(self) -> None:
        self.url: str | None = None
        self.ready = threading.Event()

    def open(self, url: str):
        self.url = url
        self.ready.set()
        return {"url": url}

    def close(self, handle) -> None:
        pass


def _post(url: str, form: dict) -> bytes:
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}))
    return opener.open(
        urlrequest.Request(
            url + "decide", data=urlparse.urlencode(form).encode(), method="POST"
        ),
        timeout=30,
    ).read()


def test_served_round_refuses_an_unusable_anchor_without_spending_the_token() -> None:
    work = Path(tempfile.mkdtemp(prefix="dpb-anchor-floor-"))
    prototype = work / "round-1.html"
    prototype.write_text(PROTOTYPE, encoding="utf-8")
    adapter = _PrintOnlyAdapter()
    outcome: dict = {}

    def collect(prototype_path, summary, options, round_n, *, criteria):
        return review_session.collect_review(
            prototype_path, summary, options, round_n,
            browser_adapter=adapter, criteria=criteria,
        )

    thread = threading.Thread(
        target=lambda: outcome.update(result=run_preview_transaction(
            path_arg=str(prototype), html=None, summary="anchor floor", round_n=1,
            report_ref="report.md", options=["确认通过", "需要修改"], collect=collect,
        )),
        name="anchor-floor-txn",
        daemon=True,
    )
    thread.start()
    assert adapter.ready.wait(30), "the preview session never came up"
    url = adapter.url or ""
    page = urlrequest.build_opener(urlrequest.ProxyHandler({})).open(url, timeout=20).read().decode("utf-8")
    token = re.search(r'name="dpb_token"[^>]*value="([^"]+)"', page)
    assert token, "the served page must carry the one-time token"

    batch = {
        "schemaVersion": 1,
        "status": "pending",
        "sourceHash": prototype_html_digest(PROTOTYPE.encode("utf-8")),
        "routeUrl": "",
        "edits": [{
            "kind": "style", "viewport": "desktop", "locator": "#panel-title",
            "property": "background-color", "oldValue": "", "newValue": "rgb(18, 52, 86)",
        }],
    }
    malformed = {
        "choice": "确认通过",
        "feedback": "",
        "anchors_json": '[{"selector":"","comment":"incomplete anchor"}]',
        "criteria_json": "[]",
        "visual_edits_json": json.dumps(batch),
        "dpb_round": "1",
        "dpb_token": token.group(1),
    }

    body = _post(url, malformed)
    thread.join(6)
    assert b"refusing to drop it" in body, "the refusal must state why"
    assert "result" not in outcome, "an unusable anchor list must not settle the round"

    valid = dict(malformed)
    valid["anchors_json"] = "[]"
    valid["feedback"] = "reviewed after the malformed attempt"
    _post(url, valid)
    thread.join(40)

    result = outcome.get("result") or {}
    assert result.get("confirmed") is True, (
        "the token must survive a malformed submission so the reviewer can retry"
    )
