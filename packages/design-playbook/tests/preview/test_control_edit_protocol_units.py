"""The preview request lifecycle, executed from the shipped file.

``control.edits.js`` owns what the bridge is doing right now: the request id
counter, the request in flight, the requests no receipt has answered, what has
been dispatched, what the bridge has accepted, the accepted sequence per target,
the values an interrupt took with it, and the 1500 ms deadline. Slice S3 moved
that out of ``control.react.js``, and until this table the only thing that could
evaluate any of it was the browser matrix - a lost guard or a wrong comparison
there showed up as a whole area of red rather than as a failing rule. The store
reaches for nothing by itself: the transport, the timer, the two value
normalizers, the publish flag and the panel callback all arrive in ``deps``, so
this loads the shipped module in node, drives it with an injected clock over a
case table, and asserts the send log, the settled promises and the status. It
needs node, which the repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[2]
PREVIEW = PKG_ROOT / "mcp" / "preview"
EDITS = PREVIEW / "control.edits.js"
SHELL = PREVIEW / "control.react.js"

_HARNESS = r"""
var failures = [];
function eq(got, want, label) {
  var g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) failures.push(label + ": got " + g + ", want " + w);
}
function ok(value, label) { if (!value) failures.push(label + ": falsy"); }
var P = window.DPBEdit.protocol;

// The clock is injected, so a deadline is a `tick`, not a sleep. The harness
// still uses the real microtask queue for promise observation (`flush`), which
// is independent of this table.
function makeEnv() {
  var env = { sends: [], emits: [], results: [], disconnects: [], published: true,
    now: 0, handle: 0, timers: {}, hasWork: false };
  env.deps = {
    send: function (message) { env.sends.push(message); },
    post: function (message) { env.sends.push(message); },
    now: function () { return env.now; },
    // The component's `disconnected()`: a round holding ledger work goes stale,
    // one without keeps whatever staleness it had. `hasWork` stands in for
    // `current.current.entries.length`, so a case can decide which it is.
    disconnect: function () {
      env.disconnects.push(env.sends.length);
      var fields = { ready: false, connecting: false };
      if (env.hasWork) fields.stale = true;
      env.store.patch(fields);
    },
    setTimer: function (fn, ms) { var id = ++env.handle; env.timers[id] = { fn: fn, at: env.now + ms }; return id; },
    clearTimer: function (id) { delete env.timers[id]; },
    // A plain property set: the shimmed shorthand and the padding/mirror rules
    // belong to the panel, not the store, and the ledger table owns them.
    syncDraft: function (values, property, value) {
      var next = Object.assign({}, values); next[property] = value; return next;
    },
    // Distinct from the dispatched value so a test can tell which of the two a
    // record was built from.
    canonicalValue: function (property, value) { return "c:" + value; },
    unpublish: function () { env.published = false; },
    emit: function (outcome) { env.emits.push(outcome.status || null); },
  };
  env.tick = function (ms) {
    env.now += ms;
    var due = Object.keys(env.timers).filter(function (id) { return env.timers[id].at <= env.now; });
    due.forEach(function (id) { var timer = env.timers[id]; delete env.timers[id]; timer.fn(); });
  };
  // A round the bridge has answered once: the state the panel is in when a
  // reviewer types.
  env.store = P.create(env.deps);
  env.store.patch({ ready: true, connecting: false, diagnostic: "" });
  env.begin = function (over) {
    var promise = env.store.begin(Object.assign({ property: "color", value: "red",
      action: "edit", origin: "shell", entry: null, locator: "#a", oldValue: "",
      draft: "red", viewport: "any" }, over || {}));
    promise.then(function (res) { env.results.push(res); });
    return promise;
  };
  return env;
}
function flush() { return new Promise(function (r) { setTimeout(r, 0); }); }

async function table() {
  // ---- ack -----------------------------------------------------------------
  var a = makeEnv();
  a.begin({ draft: "rr" });
  eq(a.sends.length, 1, "ack: one send");
  eq(a.sends[0], { type: "set-style", requestId: 1, selector: "#a", property: "color",
    value: "red", changes: null, replay: false }, "ack: the wire shape is unchanged");
  eq(a.published, false, "ack: a dispatch unpublishes the batch");
  eq(a.store.status().busy, true, "ack: busy while the request is in flight");
  eq(a.store.hasUnacked(), true, "ack: the request is owed a receipt");
  eq(a.store.requestId(), 1, "ack: the request id is the allocated sequence");
  var ack = a.store.reduce({ type: "change", requestId: 1, selector: "#a", selected: "#a" });
  eq(ack.changes, [{ property: "color", oldValue: "", newValue: "c:red" }],
    "ack: the edit is rebuilt from our dispatch, not from what the frame reports");
  eq(ack.source, "shell", "ack: provenance stays the reviewer");
  eq(ack.opSeq, 1, "ack: the receipt carries the request sequence");
  eq(a.store.acceptedValue("color"), "c:red", "ack: accepted moves to the confirmed value");
  eq(ack.drafts({ color: "rr" }), { color: "red" }, "ack: the draft lands on what was sent");
  eq(ack.drafts({ color: "typed-later" }), { color: "typed-later" },
    "ack: a keystroke newer than the request is not overwritten");
  eq(ack.status.busy, false, "ack: receipt clears busy");
  eq(ack.status.diagnostic, "", "ack: receipt clears the diagnostic");
  a.store.acknowledge(ack.operation, true);
  await flush();
  eq(a.results, [{ accepted: true, pending: true }], "ack: the promise the inspector awaits");
  eq([a.store.hasRequest(), a.store.hasUnacked(), a.store.pendingRequest() === null],
    [false, false, true], "ack: the round is settled");
  eq(a.emits.length, 1, "ack: only busy on is emitted; the receipt carries its own status");

  // ---- refusal -------------------------------------------------------------
  var r = makeEnv();
  r.store.acceptSelection({ color: "old" });
  eq(r.store.dispatchedValues(), { color: "old" },
    "a new selection re-bases dispatched too, so the fresh snapshot reads as already sent");
  r.begin({ value: "red", draft: "red" });
  var stray = r.store.reduce({ type: "rejected", requestId: 9, code: "visual_other" });
  eq(Object.keys(stray).length, 0, "refusal: an id this store is not waiting on answers nothing");
  eq(r.emits.length, 1, "refusal: a stray refusal does not move the status");
  var refusal = r.store.reduce({ type: "rejected", requestId: 1, code: "visual_bridge_error" });
  eq(refusal.consumed, true, "refusal: our own id is terminal, so the panel stops looking");
  eq(refusal.drafts({}), { color: "old" }, "refusal: the draft rolls back to what was accepted");
  eq(r.store.dispatchedValues().color, "old", "refusal: dispatched re-bases on the accepted value");
  eq(refusal.status.busy, false, "refusal: busy clears");
  eq(refusal.status.diagnostic, "visual_bridge_error", "refusal: the code reaches the panel");
  eq(r.store.hasUnacked(), false, "refusal: an id the bridge will never confirm is dropped");
  await flush();
  eq(r.results, [{ accepted: false, error: "visual_bridge_error" }], "refusal: the drain fails closed");

  // A missing target is the one refusal that also ages the round out.
  var m = makeEnv();
  m.begin();
  var missing = m.store.reduce({ type: "rejected", requestId: 1, code: "visual_target_missing" });
  eq(missing.status.stale, true, "target missing: the round goes stale");
  eq(missing.status.diagnostic, "visual_target_missing", "target missing: and says why");
  eq(m.store.status().stale, true, "target missing: the store keeps it");

  // ---- timeout -------------------------------------------------------------
  var t = makeEnv();
  t.begin();
  t.tick(P.REQUEST_TIMEOUT_MS - 1);
  eq([t.store.hasRequest(), t.emits.length], [true, 1],
    "timeout: one millisecond short of the deadline is not a failure");
  t.tick(1);
  eq(t.store.status().busy, false, "timeout: the panel stops sitting busy");
  eq(t.store.status().diagnostic, "visual_drain_failed", "timeout: and says the drain failed");
  eq(t.store.dispatchedValues().color === undefined, true,
    "timeout: the value the request carried reads as unsent again");
  eq(t.store.hasRequest(), false, "timeout: the round is no longer waiting");
  eq(t.store.hasUnacked(), true,
    "timeout: the request is not forgotten - the round still owes the reviewer its edit");
  await flush();
  eq(t.results, [{ accepted: false, error: "timeout" }], "timeout: the awaited promise fails");
  t.tick(P.REQUEST_TIMEOUT_MS);
  eq(t.emits.length, 2, "timeout: the deadline fires once, it is not a repeating timer");

  // ---- late ack after a timeout --------------------------------------------
  // The bridge answered after the round gave up. The receipt is still true
  // information, so it updates what the panel holds, but it must not re-settle
  // anything, clear the failure, or move the status back.
  var before = t.emits.length;
  var late = t.store.reduce({ type: "change", requestId: 1, selector: "#a", selected: "#a" });
  eq(late.changes, [{ property: "color", oldValue: "", newValue: "c:red" }],
    "late ack: the receipt is still recorded");
  eq(late.status === undefined, true, "late ack: it does not touch the failed round");
  eq(t.store.status().diagnostic, "visual_drain_failed", "late ack: the failure stands");
  t.store.acknowledge(late.operation, true);
  await flush();
  eq(t.results, [{ accepted: false, error: "timeout" }],
    "late ack: the promise the round already gave up on is not re-answered");
  eq(t.emits.length, before, "late ack: no extra transition reaches the panel");
  eq(t.store.hasUnacked(), false, "late ack: the receipt is spent");

  // ---- two concurrent begins ----------------------------------------------
  var c = makeEnv();
  c.begin();
  await c.begin({ property: "width", value: "10px" });
  eq(c.sends.length, 1, "concurrent: a second request while one is in flight is not sent");
  eq(c.emits[c.emits.length - 1].diagnostic, "visual_unavailable",
    "concurrent: and the panel is told why");
  var cAck = c.store.reduce({ type: "change", requestId: 1, selector: "#a", selected: "#a" });
  c.store.acknowledge(cAck.operation, true);
  c.begin({ property: "width", value: "10px" });
  eq(c.store.requestId(), 2,
    "concurrent: a refused begin burns no sequence number, so requests stay dense");
  eq(c.sends.length, 2, "concurrent: the next begin goes out once the round is free");

  // ---- interrupt, then a gesture receipt -----------------------------------
  // A disconnect remembers the pre-edit value of an unfinished request, because
  // the receipt that never came would otherwise be the only record of what the
  // element looked like. A gesture the frame did on its own arrives with no
  // record of ours, so that remembered value is what makes its edit undoable.
  var i = makeEnv();
  i.begin({ oldValue: "orig" });
  var dropped = i.store.interrupt();
  i.store.fail("visual_disconnected");
  eq(dropped.length, 1, "interrupt: the unanswered request goes with the round");
  eq(i.store.dispatchedValues().color === undefined, true,
    "interrupt: its dispatched mark goes with it, so the draft reads unsent again");
  await flush();
  eq(i.results, [{ accepted: false, error: "visual_disconnected" }],
    "interrupt: fail settles what interrupt left waiting");
  var gesture = i.store.reduce({ type: "change", requestId: "gesture-7", selector: "#a",
    selected: "#a", changes: [{ property: "color", oldValue: "red", newValue: "blue" }] });
  eq(gesture.source, "frame", "gesture: not our request, so not the reviewer's edit");
  eq(gesture.changes, [{ property: "color", oldValue: "orig", newValue: "blue" }],
    "gesture: the value the interrupt remembered is what the edit reports");
  eq(gesture.opSeq, 2, "gesture: a receipt with no id of ours takes the next sequence");
  eq(gesture.drafts({}), { color: "blue" }, "gesture: with no dispatch of ours the frame wins");

  // ---- I7: a no-op transition hands back nothing --------------------------
  // `applyOutcome` only opens the setters when the outcome carries a status, so
  // the store must not invent one for an event that moved nothing. The pin is
  // the reference: the same status object in, the same one out.
  var n = makeEnv();
  var held = n.store.status();
  eq(n.store.patch({ ready: true }), undefined, "idempotence: a patch that changes nothing answers nothing");
  eq(n.store.status() === held, true, "idempotence: and the status is the same reference");
  var busyHeld = held.busy;
  eq(n.store.patch({ busy: busyHeld }), undefined, "idempotence: field by field, not by object identity");
  n.begin();
  var emits = n.emits.length;
  n.begin({ property: "width", value: "10px" });
  eq(n.emits.length, emits + 1, "idempotence: the first refusal of a kind moves the diagnostic");
  n.begin({ property: "width", value: "10px" });
  eq(n.emits.length, emits + 1, "idempotence: the same refusal again moves nothing, so it emits nothing");

  // ---- heartbeat ------------------------------------------------------------
  var h = makeEnv();
  var heldHeartbeat = h.store.status();
  var idle = h.store.ping({ compact: true, labels: { ok: "yes" } });
  eq(h.sends, [{ type: "ping", nonce: 1, compact: true, labels: { ok: "yes" } }],
    "heartbeat: the wire shape is unchanged");
  eq(idle, undefined, "heartbeat: a ping that changes nothing answers nothing");
  eq(h.store.status() === heldHeartbeat, true,
    "heartbeat: a no-op tick returns the same status reference");
  h.now += 30000;
  var late = h.store.ping({ compact: false, labels: {} });
  eq([late, h.store.status().stale, h.disconnects], [undefined, false, []],
    "heartbeat: one throttled late tick is not a disconnect");

  var d = makeEnv();
  d.hasWork = true;
  d.store.status().ready = true;
  d.store.status().diagnostic = "";
  d.store.ping({ compact: false, labels: {} });
  d.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  d.store.ping({ compact: false, labels: {} });
  d.store.ping({ compact: false, labels: {} });
  d.store.ping({ compact: false, labels: {} });
  d.store.ping({ compact: false, labels: {} });
  d.store.ping({ compact: false, labels: {} });
  eq(d.store.status().stale, true, "heartbeat: the third unanswered ping goes stale");

  var f = makeEnv();
  f.store.status().ready = false;
  f.store.status().connecting = true;
  f.store.status().diagnostic = "";
  f.store.ping({ compact: false, labels: {} });
  f.now += 2501;
  var first = f.store.ping({ compact: false, labels: {} });
  eq(first.connecting, false, "heartbeat: the first-connect fallback clears connecting");
  eq(first.stale, false, "heartbeat: and does not mark the round stale");

  var r = makeEnv();
  r.store.ping({ compact: false, labels: {} });
  r.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  r.store.ready({ nonce: 9, routeUrl: "route" }, "route");
  eq(r.store.status().ready, true, "heartbeat: a stale nonce changes nothing");
  r.store.ping({ compact: false, labels: {} });
  var route = r.store.ready({ nonce: 2, routeUrl: "elsewhere" }, "route");
  eq([route.stale, route.ready, route.diagnostic], [true, false, "visual_stale"],
    "heartbeat: a route mismatch marks the round stale and fails it");

  var ack = makeEnv();
  ack.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  ack.store.ping({ compact: false, labels: {} });
  ack.store.ping({ compact: false, labels: {} });
  ack.store.ready({ nonce: 2, routeUrl: "route" }, "route");
  ack.store.ping({ compact: false, labels: {} });
  ack.store.ping({ compact: false, labels: {} });
  eq([ack.store.status().stale, ack.disconnects], [false, []],
    "heartbeat: an ack restarts the unanswered count");

  // ---- heartbeat disconnect: the staleness the component already decided -----
  // Three unanswered pings call the component's `disconnected()`, which writes
  // the status itself - a round with work pending goes stale, one without keeps
  // whatever staleness it had. The store must not write a second, inverted copy
  // over that, so each of the three directions is pinned.
  var pending = makeEnv();
  pending.hasWork = true;
  pending.store.ping({ compact: false, labels: {} });
  pending.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  pending.store.ping({ compact: false, labels: {} });
  pending.store.ping({ compact: false, labels: {} });
  pending.store.ping({ compact: false, labels: {} });
  eq([pending.store.status().stale, pending.store.status().ready, pending.disconnects.length],
    [true, false, 1], "heartbeat: a disconnect with work pending leaves the round stale");

  var quiet = makeEnv();
  quiet.store.ping({ compact: false, labels: {} });
  quiet.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  quiet.store.ping({ compact: false, labels: {} });
  quiet.store.ping({ compact: false, labels: {} });
  quiet.store.ping({ compact: false, labels: {} });
  eq([quiet.store.status().stale, quiet.disconnects.length], [false, 1],
    "heartbeat: a disconnect with no work pending leaves the round not stale");

  var aged = makeEnv();
  aged.store.status().stale = true;
  aged.store.ping({ compact: false, labels: {} });
  aged.store.ready({ nonce: 1, routeUrl: "route" }, "route");
  aged.store.ping({ compact: false, labels: {} });
  aged.store.ping({ compact: false, labels: {} });
  aged.store.ping({ compact: false, labels: {} });
  eq([aged.store.status().stale, aged.disconnects.length], [true, 1],
    "heartbeat: a disconnect with no work pending keeps the round stale");

  // ---- route mismatch with a request in flight ------------------------------
  // The route moved under the round: the round ages out and the request in
  // flight is refused, so the panel is not left busy and the inspector's await
  // settles with the route reason instead of a later timeout.
  var moved = makeEnv();
  moved.begin();
  moved.store.ping({ compact: false, labels: {} });
  var mismatch = moved.store.ready({ nonce: 1, routeUrl: "elsewhere" }, "route");
  eq([mismatch.ready, mismatch.connecting, mismatch.stale, mismatch.busy,
    mismatch.diagnostic], [false, false, true, false, "visual_stale"],
    "route mismatch: the round ages out and stops sitting busy");
  eq(moved.store.hasRequest(), false, "route mismatch: no request is left in flight");
  await flush();
  eq(moved.results, [{ accepted: false, error: "visual_stale" }],
    "route mismatch: the in-flight request is refused with the route reason");

  console.log(JSON.stringify(failures));
}
table().then(function () {}, function (error) {
  console.log(JSON.stringify(["harness threw: " + String(error && error.stack)]));
});
"""


def _run_node(tmp_path: Path, script_text: str, name: str) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - the repository requires node
        pytest.skip("node is not installed")
    # node -e mangles multi-line payloads on some installs; run from a file.
    script_path = tmp_path / name
    script_path.write_text(script_text, encoding="utf-8")
    return subprocess.run(
        [node, str(script_path)], capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )


def test_the_protocol_keeps_its_answers(tmp_path) -> None:
    script = ("globalThis.window = {};\n" + EDITS.read_text(encoding="utf-8") + _HARNESS)
    result = _run_node(tmp_path, script, "control_edit_protocol_units.js")
    assert result.returncode == 0, result.stderr
    failures = json.loads(result.stdout)
    assert failures == [], "\n".join(failures)


# The refs S3 replaced. A leftover of any of them is a crash at render time that
# only the browser matrix would catch, so the absence is pinned here instead.
MOVED_REFS = ("sequence.current", "unackedRequests.current", "request.current",
              "requestPromiseRef.current", "dispatchedDrafts.current",
              "interruptedValues.current", "lastAcceptedSeq.current", "accepted.current")


def test_the_shell_keeps_no_lifecycle_ref_of_its_own() -> None:
    shell = SHELL.read_text(encoding="utf-8")
    for ref in MOVED_REFS:
        assert ref not in shell, ref
    # The old status writers were the other half: every one of them now goes
    # through the single `applyOutcome` sink.
    assert shell.count("setReady(") == 1
    assert shell.count("setConnecting(") == 1
    assert shell.count("setStale(") == 1
    assert shell.count("setBusy(") == 1
    assert shell.count("setDiagnostic(") == 1
    assert "function fail(" not in shell


def test_the_store_is_built_once_per_editor_instance() -> None:
    # A store created in the render body is a new lifecycle on every keystroke,
    # and the bridge effects capture the first one: the request in flight, the
    # accepted values and the live deadline would silently disagree. The store is
    # therefore a ref, created once, with the records reached through it.
    shell = SHELL.read_text(encoding="utf-8")
    assert "var protocolRef = React.useRef(null);" in shell
    assert "if (!protocolRef.current) {" in shell
    assert "var protocol = protocolRef.current;" in shell


def test_the_deadline_lives_only_in_the_module() -> None:
    edits = EDITS.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    assert edits.count("var REQUEST_TIMEOUT_MS = 1500;") == 1
    assert "REQUEST_TIMEOUT_MS" not in shell
