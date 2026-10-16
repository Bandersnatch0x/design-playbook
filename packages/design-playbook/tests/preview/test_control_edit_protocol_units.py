"""The preview request lifecycle, executed from the shipped file.

``control.edits.js`` owns what the bridge is doing right now: the request id
counter, the request in flight, the requests no receipt has answered, what has
been dispatched, what the bridge has accepted, the accepted sequence per target,
the values an interrupt took with it, the 1500 ms deadline, and - since slice S5
- the drain's decision plus the two flags that say whether the panel's batch is
still the published one and whether a drain is walking. Slice S6 added the wire
boundary: ``parse`` turns the four shapes ``pin_bridge.js`` posts into the events
the panel and the store take, so no ``dpbVisualEdit*`` name is read outside it.
Slice S3 moved that out
of ``control.react.js``, and until this table the only thing that could
evaluate any of it was the browser matrix - a lost guard or a wrong comparison
there showed up as a whole area of red rather than as a failing rule. The store
reaches for nothing by itself: the transport, the timer, the two value
normalizers and the panel callback all arrive in ``deps``, so
this loads the shipped module in node, drives it with an injected clock over a
case table, and asserts the send log, the settled promises and the status. It
needs node, which the repository already requires for its JavaScript checks.
"""
from __future__ import annotations

import json
import re
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
  var env = { sends: [], emits: [], results: [], disconnects: [],
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
// The publish flag's one reader is the pending rule's snapshot, so that is how a
// case reads it now that the store holds it instead of the panel's ref.
function publishedOf(env) {
  return env.store.pendingSnapshot({ selected: null, draftTimers: {}, drafts: {} }).published;
}
// The two record tables are read the way the pending rule reads them: out of the
// one snapshot, so a probe cannot reach around the store's own answer.
function recordsOf(env) {
  return env.store.pendingSnapshot({ selected: null, draftTimers: {}, drafts: {} });
}

async function table() {
  // ---- parse: the wire boundary ---------------------------------------------
  // First, before any store exists: `parse` is the boundary, and it needs no
  // round to answer. The four fixtures mirror the four `parent.postMessage` sites
  // in `pin_bridge.js`, each message carrying exactly one shape, so a rename on
  // the wire shows up here instead of as a whole area of red in the browser
  // matrix.
  var wireReady = { dpbVisualEditReady: { bridgeVersion: 1, nonce: 4, routeUrl: "about:srcdoc" } };
  var wireSelection = { dpbVisualEditSelection: { selector: "#a", tag: "h2", textEditable: true,
    style: { color: "rgb(255, 0, 0)" }, inlineStyle: "color: red;", replay: false, requestId: 3 } };
  var wireRejected = { dpbVisualEditRejected: { requestId: 3, code: "visual_rejected" } };
  var wireChange = { dpbVisualEditChange: { requestId: 3, selector: "#a",
    changes: [{ property: "color", oldValue: "", newValue: "red" }], replay: false } };

  eq(typeof P.parse, "function", "parse: the parser sits on the protocol, not on a store");
  eq(P.parse(wireReady), { type: "ready", response: wireReady.dpbVisualEditReady },
    "parse: ready carries the response the frame sent");
  eq(P.parse(wireSelection), { type: "selection", selection: wireSelection.dpbVisualEditSelection,
    gesture: false }, "parse: selection carries the snapshot the frame sent");
  eq(P.parse(wireRejected), { type: "rejected", requestId: 3, code: "visual_rejected" },
    "parse: rejected carries the id and the code");
  eq(P.parse(wireChange), { type: "change", requestId: 3, selector: "#a",
    changes: wireChange.dpbVisualEditChange.changes, gesture: false },
    "parse: change carries the receipt the frame sent");

  // A gesture id is minted by the frame when nobody asked for the edit, and it is
  // the one thing the two receipt shapes share. Every case compares the whole
  // event, so a parser that answers nothing reads as a labelled failure instead
  // of throwing on a missing field.
  eq(P.parse({ dpbVisualEditChange: { requestId: "gesture-7", selector: "#a", changes: [] } }),
    { type: "change", requestId: "gesture-7", selector: "#a", changes: [], gesture: true },
    "parse: a gesture- change id is a gesture");
  eq(P.parse({ dpbVisualEditSelection: { selector: "#a", requestId: "gesture-7" } }),
    { type: "selection", selection: { selector: "#a", requestId: "gesture-7" }, gesture: true },
    "parse: a gesture- selection id is a gesture");
  eq(P.parse(wireChange), { type: "change", requestId: 3, selector: "#a",
    changes: wireChange.dpbVisualEditChange.changes, gesture: false },
    "parse: a real request id is not a gesture");
  eq(P.parse({ dpbVisualEditChange: { requestId: "req-3", selector: "#a", changes: [] } }),
    { type: "change", requestId: "req-3", selector: "#a", changes: [], gesture: false },
    "parse: a string id that is not a gesture- id is not a gesture");
  eq(P.parse({ dpbVisualEditChange: { selector: "#a", changes: [] } }),
    { type: "change", selector: "#a", changes: [], gesture: false },
    "parse: a missing id is not a gesture");

  // Nothing else is a message. A falsy shape is no message at all, the way the
  // component's own `if (!change) return` read it.
  eq(P.parse({}), null, "parse: an empty message is not an event");
  eq(P.parse(null), null, "parse: null is not an event");
  eq(P.parse(undefined), null, "parse: undefined is not an event");
  eq(P.parse("dpbVisualEditChange"), null, "parse: a non-object is not an event");
  eq(P.parse({ dpbVisualEditChange: null }), null, "parse: a falsy shape is not an event");

  // One shape per message, so a two-shape object is unreachable on the real wire.
  // The order is pinned anyway: a reordered parser would pass every case above and
  // only the browser matrix would notice.
  eq(P.parse({ dpbVisualEditReady: wireReady.dpbVisualEditReady,
    dpbVisualEditSelection: wireSelection.dpbVisualEditSelection,
    dpbVisualEditRejected: wireRejected.dpbVisualEditRejected,
    dpbVisualEditChange: wireChange.dpbVisualEditChange }),
    { type: "ready", response: wireReady.dpbVisualEditReady },
    "parse: ready outranks the other three");
  eq(P.parse({ dpbVisualEditSelection: wireSelection.dpbVisualEditSelection,
    dpbVisualEditRejected: wireRejected.dpbVisualEditRejected,
    dpbVisualEditChange: wireChange.dpbVisualEditChange }),
    { type: "selection", selection: wireSelection.dpbVisualEditSelection, gesture: false },
    "parse: selection outranks rejected and change");
  eq(P.parse({ dpbVisualEditRejected: wireRejected.dpbVisualEditRejected,
    dpbVisualEditChange: wireChange.dpbVisualEditChange }),
    { type: "rejected", requestId: 3, code: "visual_rejected" },
    "parse: rejected outranks change");

  // The panel never holds the namespace: `control.react.js` calls
  // `window.DPBEdit.protocol.create(deps)` once and keeps the answer. A parser
  // reachable only on the namespace is a `TypeError` at the first bridge message,
  // which kills `onMessage` outright - no selection, no receipt, no inspector. So
  // the binding is checked the way the panel makes it, not the way this table does.
  var bound = makeEnv();
  eq(typeof bound.store.parse, "function",
    "parse: the instance the panel holds answers too, not just the namespace");
  eq(bound.store.parse(wireChange), P.parse(wireChange),
    "parse: both bindings are the same function");

  // ---- ack -----------------------------------------------------------------
  var a = makeEnv();
  a.begin({ draft: "rr" });
  eq(a.sends.length, 1, "ack: one send");
  eq(a.sends[0], { type: "set-style", requestId: 1, selector: "#a", property: "color",
    value: "red", changes: null, replay: false }, "ack: the wire shape is unchanged");
  eq(publishedOf(a), false, "ack: a dispatch unpublishes the batch");
  eq(a.store.status().busy, true, "ack: busy while the request is in flight");
  eq(Object.keys(recordsOf(a).unacked), ["1"], "ack: the request is owed a receipt");
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
  eq([a.store.hasRequest(), Object.keys(recordsOf(a).unacked), a.store.pendingRequest() === null],
    [false, [], true], "ack: the round is settled");
  eq(a.emits.length, 1, "ack: only busy on is emitted; the receipt carries its own status");

  // ---- refusal -------------------------------------------------------------
  var r = makeEnv();
  r.store.acceptSelection({ color: "old" });
  eq(recordsOf(r).dispatched, { color: "old" },
    "a new selection re-bases dispatched too, so the fresh snapshot reads as already sent");
  r.begin({ value: "red", draft: "red" });
  var stray = r.store.reduce({ type: "rejected", requestId: 9, code: "visual_other" });
  eq(Object.keys(stray).length, 0, "refusal: an id this store is not waiting on answers nothing");
  eq(r.emits.length, 1, "refusal: a stray refusal does not move the status");
  var refusal = r.store.reduce({ type: "rejected", requestId: 1, code: "visual_bridge_error" });
  eq(refusal.consumed, true, "refusal: our own id is terminal, so the panel stops looking");
  eq(refusal.drafts({}), { color: "old" }, "refusal: the draft rolls back to what was accepted");
  eq(recordsOf(r).dispatched.color, "old", "refusal: dispatched re-bases on the accepted value");
  eq(refusal.status.busy, false, "refusal: busy clears");
  eq(refusal.status.diagnostic, "visual_bridge_error", "refusal: the code reaches the panel");
  eq(Object.keys(recordsOf(r).unacked), [], "refusal: an id the bridge will never confirm is dropped");
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
  eq(recordsOf(t).dispatched.color, undefined,
    "timeout: the value the request carried reads as unsent again");
  eq(t.store.hasRequest(), false, "timeout: the round is no longer waiting");
  eq(Object.keys(recordsOf(t).unacked), ["1"],
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
  eq(Object.keys(recordsOf(t).unacked), [], "late ack: the receipt is spent");

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
  eq(recordsOf(i).dispatched.color, undefined,
    "interrupt: its dispatched mark goes with it, so the draft reads unsent again");
  await flush();
  eq(i.results, [{ accepted: false, error: "visual_disconnected" }],
    "interrupt: fail settles what interrupt left waiting");
  // The receipt reaches the store as a domain event, the way every case in this
  // table hands one over. Whether the id names a gesture is the parser's answer
  // (pinned above), so the store no longer re-reads the prefix itself.
  var gesture = i.store.reduce({ type: "change", requestId: "gesture-7", selector: "#a",
    selected: "#a", gesture: true,
    changes: [{ property: "color", oldValue: "red", newValue: "blue" }] });
  eq(gesture.source, "frame", "gesture: not our request, so not the reviewer's edit");
  eq(gesture.changes, [{ property: "color", oldValue: "orig", newValue: "blue" }],
    "gesture: the value the interrupt remembered is what the edit reports");
  eq(gesture.opSeq, 2, "gesture: a receipt with no id of ours takes the next sequence");
  eq(gesture.drafts({}), { color: "blue" }, "gesture: with no dispatch of ours the frame wins");
  // An event that does not say it is a gesture is not one, whatever its id looks
  // like: the store takes the parser's word, and `parse` is the only place left
  // that knows the prefix.
  eq(i.store.reduce({ type: "change", requestId: "gesture-8", selector: "#a", selected: "#a" }), null,
    "gesture: the store reads the event's answer, not the id's spelling");

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

  // ---- planDrain: the decision the drain walks on ---------------------------
  // One query answers, in the order the walk must take it, what the panel used to
  // ask for separately: the request in flight, the first draft the bridge has not
  // been sent, the receipts no answer has cleared, or done.
  var p = makeEnv();
  eq(p.store.planDrain({ drafts: {} }), { kind: "done" },
    "planDrain: nothing in flight, nothing uncommitted, nothing unacked is done");
  p.begin({ draft: "red" });
  eq(p.store.planDrain({ drafts: { color: "blue" } }), { kind: "await" },
    "planDrain: a request in flight is awaited before any draft is sent");
  var pAck = p.store.reduce({ type: "change", requestId: 1, selector: "#a", selected: "#a" });
  p.store.acknowledge(pAck.operation, true);
  await flush();
  eq(p.store.planDrain({ drafts: { color: "blue", width: "10px" } }),
    { kind: "send", property: "color", value: "blue" },
    "planDrain: the first uncommitted draft is the one to send");
  p.store.markDispatched("color", "blue");
  eq(p.store.planDrain({ drafts: { color: "blue", width: "10px" } }),
    { kind: "send", property: "width", value: "10px" },
    "planDrain: once that draft is dispatched the next one is next");
  p.store.markDispatched("width", "10px");
  eq(p.store.planDrain({ drafts: { color: "blue", width: "10px" } }), { kind: "done" },
    "planDrain: every draft dispatched and nothing unacked is done");

  // A request the deadline gave up on is still owed: no receipt ever came, so the
  // round must fail the drain rather than publish over it. It is only reached
  // once there is nothing left to send - a draft the deadline un-marked is
  // re-sent first.
  var u = makeEnv();
  u.begin({ draft: "red" });
  u.tick(P.REQUEST_TIMEOUT_MS);
  eq(Object.keys(recordsOf(u).unacked), ["1"], "planDrain: the deadline leaves the receipt owed");
  eq(u.store.planDrain({ drafts: {} }), { kind: "unacked" },
    "planDrain: nothing left to send but a receipt still owed is the unacked residue");
  eq(u.store.planDrain({ drafts: { color: "red" } }),
    { kind: "send", property: "color", value: "red" },
    "planDrain: a draft outranks the residue, so the walk tries it first");

  // ---- a replay records what it sent ----------------------------------------
  // The comment on `begin`'s dispatch record describes a real defect: the undo and
  // redo paths did not mark the value they re-sent, so `drafts[property]` and
  // `dispatched[property]` stayed permanently unequal and the editor reported a
  // pending edit forever. `begin` records it for the replay paths too, so a replay
  // leaves the property committed.
  var rp = makeEnv();
  rp.store.acceptSelection({ color: "blue" });
  var redoEntry = [{ kind: "style", viewport: "any", locator: "#a", property: "color",
    oldValue: "red", newValue: "blue", _seq: 1, _entryId: 1 }];
  rp.begin({ action: "undo", entry: redoEntry, value: "red", draft: "blue", oldValue: "blue" });
  eq(recordsOf(rp).dispatched.color, "red",
    "replay: an undo records the value it re-sent, so the property is not left uncommitted");
  var rpAck = rp.store.reduce({ type: "change", requestId: 1, selector: "#a", selected: "#a" });
  rp.store.acknowledge(rpAck.operation, true);
  await flush();
  eq(rp.store.planDrain({ drafts: { color: "red" } }), { kind: "done" },
    "replay: after the receipt the drain sees nothing uncommitted");

  // ---- pendingSnapshot: the seven fields the rule reads ---------------------
  var s = makeEnv();
  s.store.acceptSelection({ color: "blue" });
  s.begin({ draft: "blue" });
  var view = { selected: { selector: "#a" }, draftTimers: { width: 7 }, drafts: { color: "blue" } };
  var snap = s.store.pendingSnapshot(view);
  eq(Object.keys(snap),
    ["selected", "published", "request", "unacked", "draftTimers", "drafts", "dispatched"],
    "pendingSnapshot: the seven field names are the rule's, byte-identical");
  eq(snap.selected, view.selected, "pendingSnapshot: selected comes from the caller's view");
  eq(snap.draftTimers, view.draftTimers, "pendingSnapshot: draftTimers comes from the caller's view");
  eq(snap.drafts, view.drafts, "pendingSnapshot: drafts comes from the caller's view");
  eq(snap.published, false,
    "pendingSnapshot: published is the store's, and a dispatch unpublishes it");
  eq(snap.request === s.store.pendingRequest(), true,
    "pendingSnapshot: request is the promise in flight");
  eq(Object.keys(snap.unacked), ["1"],
    "pendingSnapshot: unacked is the store's table of the receipts still owed");
  eq(snap.dispatched, { color: "red" },
    "pendingSnapshot: dispatched is the store's record of what was sent, not the draft");

  // ---- the two flags: one writer each ---------------------------------------
  var fl = makeEnv();
  eq(publishedOf(fl), true, "flags: a fresh store is published");
  fl.store.setPublished(false);
  eq(publishedOf(fl), false, "flags: the published setter is what the pending rule reads");
  fl.store.setPublished(true);
  eq(publishedOf(fl), true, "flags: and it sets both ways");
  eq(fl.store.isDraining(), false, "flags: a fresh store is not draining");
  fl.store.setDraining(true);
  eq(fl.store.isDraining(), true, "flags: the draining setter is what the render guard reads");
  fl.store.setDraining(false);
  eq(fl.store.isDraining(), false, "flags: and it clears again");
  // A dispatch unpublishes through the same setter, in the store: the panel is no
  // longer called back out to for it, so `deps` carries no publish flag.
  fl.begin({ draft: "red" });
  eq(publishedOf(fl), false, "flags: begin unpublishes the batch inside the store");

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


# The refs S3 and S5 replaced. A leftover of any of them is a crash at render time
# that only the browser matrix would catch, so the absence is pinned here instead.
MOVED_REFS = ("sequence.current", "unackedRequests.current", "request.current",
              "requestPromiseRef.current", "dispatchedDrafts.current",
              "interruptedValues.current", "lastAcceptedSeq.current", "accepted.current",
              "isPublishedRef.current", "isDrainingRef.current")


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


def test_the_two_flags_have_one_writer_each() -> None:
    # `published` and `isDraining` were component refs with one reader and several
    # writers. The records moved into the store; the writers that are the panel's
    # go through the one setter each, and the render reads the store's answer.
    shell = SHELL.read_text(encoding="utf-8")
    assert shell.count("protocol.setPublished(") == 2, "publishBatch and the input handler"
    assert shell.count("protocol.setDraining(") == 3, "the drain's start, deadline and finish"
    assert shell.count("protocol.isDraining()") == 2, "the render guard and the input guard"


def test_the_store_no_longer_reaches_out_for_the_publish_flag() -> None:
    # The deps entry disappearing is the point of the slice, not a tidy-up: a
    # `deps` key left behind would be a callback the store no longer calls.
    shell = SHELL.read_text(encoding="utf-8")
    edits = EDITS.read_text(encoding="utf-8")
    # "unpublished" is the pending rule's own adjective; the deps key is "unpublish".
    assert shell.replace("unpublished", "").count("unpublish") == 0
    assert "unpublish" not in edits


def test_the_shell_never_spells_a_wire_field() -> None:
    # The design's red-flag screen for this slice: after S6 the component names no
    # inbound `dpbVisualEdit*` field, because `parse` is the only reader of the
    # wire. One reappearing here means the boundary moved back into the panel. The
    # outbound `{ dpbVisualEdit: message }` in `post` is the other direction.
    shell = SHELL.read_text(encoding="utf-8")
    for field in ("dpbVisualEditReady", "dpbVisualEditSelection",
                  "dpbVisualEditRejected", "dpbVisualEditChange"):
        assert field not in shell, field
    assert "protocol.parse(event.data || {})" in shell


def test_the_parser_is_the_only_reader_of_the_wire_names() -> None:
    # The store does not start reading the wire: each name appears once, in the
    # parser, so a second reader would be the boundary leaking back down.
    edits = EDITS.read_text(encoding="utf-8")
    for field in ("dpbVisualEditReady", "dpbVisualEditSelection",
                  "dpbVisualEditRejected", "dpbVisualEditChange"):
        assert edits.count(field) == 1, field


def test_the_gesture_prefix_has_one_reading_left() -> None:
    # The prefix test used to sit at two sites - the store's change guard and the
    # panel's selection guard - so the two could drift apart. S6 computes it once
    # in `parse`, and both sites read the field it answers.
    edits = EDITS.read_text(encoding="utf-8")
    shell = SHELL.read_text(encoding="utf-8")
    assert edits.count('indexOf("gesture-")') == 1, "`parse` is the only reader left"
    assert shell.count("gesture-") == 0
    assert "!event.gesture" in edits
    assert "parsed.gesture" in shell


def test_every_protocol_call_the_shell_makes_is_on_the_instance() -> None:
    # The trap this pins: `protocol` in the shell is what `create(deps)` answered,
    # not the `DPBEdit.protocol` namespace, and the two are separate objects. A
    # method added to the namespace alone reads fine in a text assertion and still
    # throws at the first call - S6 shipped `parse` that way and the panel went
    # blank on every bridge message. So every `protocol.<name>` the shell spells
    # must appear as a key of `create`'s return block.
    shell = SHELL.read_text(encoding="utf-8")
    edits = EDITS.read_text(encoding="utf-8")
    called = set(re.findall(r"\bprotocol\.([A-Za-z_$][\w$]*)", shell))
    assert "create" in called, "the shell builds its protocol through `create`"
    called.discard("create")

    # The keys are the members of `create`'s return object: it opens at the
    # function's own indent and closes with the same. Anchoring on `var store`'s
    # `};` instead would cut the block off before the return object starts.
    start = edits.index("create: function (deps) {")
    block = edits[edits.index("        return {", start):edits.index("\n        };",
                                                                    edits.index("        return {", start))]
    defined = set(re.findall(r"^ {10}([A-Za-z_$][\w$]*):", block, re.M))
    missing = sorted(called - defined)
    assert missing == [], f"called in the shell but not on the instance: {missing}"
