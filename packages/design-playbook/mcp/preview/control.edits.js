/* The preview edit ledger: the coalesce rule and the list operations the editor
   performs on its entries. Slice S1 moved the rules out of control.react.js
   unchanged; slice S2 collapses the three lists to two: `entries` is the undo
   stack - grouped entries in `seqOf` order, newest replayed last - and also
   holds the edits that have not been published away, so the old flat `pending`
   list is no longer stored. The flat view the batch, the counts and the
   modified dots need is `flatten(entries)`: one projection, computed where it is
   read. A coalesce still mutates the edit object that the last entry holds, and
   that shared identity is what reaches the published batch. These functions only
   answer "what are the next lists".

   `protocol` is the other half of the module: what the bridge is doing right now.
   Slice S3 moved the request lifecycle in - the request id counter, the request in
   flight, the table of requests no receipt has answered, what has been dispatched,
   what the bridge has accepted, the accepted sequence per target and property, the
   values an interrupted request took with it, and the 1500 ms deadline. Slice S5
   moved two more decisions in: the drain's decision, as one query the panel's walk
   switches on, and the two flags that had one reader and several writers - whether
   the batch the panel holds is still the one it published, and whether a drain is
   walking. Unlike the ledger it is a store: it keeps those records for one Editor
   instance. Every capability it must not reach for itself arrives in `deps` - the
   transport, the timer, the two DOM-bound value normalizers, and `emit`, which is
   how a transition nobody called it for (the deadline) still reaches the panel.
   That is also what makes the whole lifecycle executable in node. */
(function () {
  "use strict";
  // The wire contract's provenance constants. The generated block ships ahead
  // of this module, so these reads are direct.
  var VC = window.DPBUI.visualContract;
  var SHELL_SOURCE = VC.SHELL_SOURCE;
  var FRAME_SOURCE = VC.FRAME_SOURCE;
  var MERGE_WINDOW_MS = 500;
  function mergeEdit(prev, next, now, windowMs) {
    if (!prev || !next || prev.locator !== next.locator || prev.property !== next.property) return false;
    if (prev.viewport !== next.viewport || !prev._t || now - prev._t > windowMs) return false;
    prev.newValue = next.newValue;
    prev._t = now;
    return true;
  }
  function getEntryId(item) {
    if (!item) return null;
    if (item._entryId !== undefined) return item._entryId;
    if (Array.isArray(item) && item.length > 0) {
      if (item._entryId !== undefined) return item._entryId;
      if (item[0]._entryId !== undefined) return item[0]._entryId;
      if (item[0]._seq !== undefined) return item[0]._seq;
    }
    if (item._seq !== undefined) return item._seq;
    return null;
  }
  // One reading of a sequence number: a flat edit answers with its `_seq` /
  // `_entryId`, a grouped entry array with its first edit's. Both fields carry
  // the same operation sequence, so this replaces the five sort spellings and
  // the receipt guard read the component used to write out by hand.
  function seqOf(item) {
    var seq = getEntryId(item);
    return seq === null ? 0 : seq;
  }
  function bySeq(a, b) { return seqOf(a) - seqOf(b); }
  function lastIndexOfId(list, id) {
    for (var i = list.length - 1; i >= 0; i--) {
      if (getEntryId(list[i]) === id) return i;
    }
    return -1;
  }
  // The flat projection of the ledger: every edit in every entry, in the order
  // the reviewer made them. Its length is the pending count, NOT entries.length
  // - one resize receipt is one entry holding two edits.
  function flatten(entryLists) {
    var flat = [];
    (entryLists || []).forEach(function (entry) {
      flat = flat.concat(entry);
    });
    return flat.sort(bySeq);
  }
  // Undo moves the entry out of history into future and drops its edits from
  // the entries list. Returns null when the entry is no longer there.
  function undoEntry(state, entry) {
    var targetId = getEntryId(entry);
    var hist = state.entries || [];
    var targetIdx = lastIndexOfId(hist, targetId);
    if (targetIdx < 0) return null;
    var nextHist = hist.slice(0, targetIdx).concat(hist.slice(targetIdx + 1));
    var fut = state.future || [];
    var alreadyInFut = fut.some(function (f) { return getEntryId(f) === targetId; });
    var nextFut = alreadyInFut ? fut : fut.concat([entry]);
    return { entries: nextHist, future: nextFut };
  }
  // Redo is undo's mirror: the entry returns to the entries list, re-ordered by
  // sequence because a receipt can land out of order.
  function redoEntry(state, entry) {
    var targetId = getEntryId(entry);
    var fut = state.future || [];
    var targetIdx = lastIndexOfId(fut, targetId);
    if (targetIdx < 0) return null;
    var nextFut = fut.slice(0, targetIdx).concat(fut.slice(targetIdx + 1));
    var hist = state.entries || [];
    var alreadyInHist = hist.some(function (h) { return getEntryId(h) === targetId; });
    var nextHist = alreadyInHist ? hist : hist.concat([entry]);
    nextHist.sort(bySeq);
    return { entries: nextHist, future: nextFut };
  }
  // A new entry joins the entries list in sequence order. A receipt older than
  // something already in `future` must not throw the redo stack away, so
  // `future` comes back null when it stands.
  function appendEdits(state, edits, opSeq) {
    var nextHist = (state.entries || []).concat([edits]);
    nextHist.sort(bySeq);
    var fut = state.future || [];
    var isOlderReceipt = fut.some(function (f) { return opSeq < seqOf(f); });
    return { entries: nextHist, future: isOlderReceipt ? null : [] };
  }

  // ---- the request lifecycle (slice S3) ----
  // The deadline for one dispatched edit. A bridge that answers later than this is
  // treated as failed even if its receipt arrives, so the panel never sits `busy`
  // on a request the round has already given up on.
  var REQUEST_TIMEOUT_MS = 1500;
  var HEARTBEAT_FIRST_CONNECT_MS = 2500;
  function hasOwn(map, key) {
    return Object.prototype.hasOwnProperty.call(map, key);
  }
  // Whether the batch the panel holds is still the one it published. Slice S5
  // moved the flag in from the component, where the pending rule was its one
  // reader and three writers kept it; `begin` is a writer inside the store now,
  // so the panel is no longer called back out to for it.
  function setPublished(store, value) {
    store.published = value;
  }
  // Whether a drain is walking its steps. The render guard reads it on every
  // render, so it is a fact of the round like the records above, not a ref.
  function setDraining(store, value) {
    store.draining = value;
  }
  // Write the status only where a field actually moved, and hand out the whole
  // value, never a patch. A transition that changes nothing leaves the store's
  // status object identical, which is what lets the panel skip its setters on a
  // no-op: one reference check answers "did anything move".
  function markStatus(store, outcome, fields) {
    var moved = Object.keys(fields).some(function (key) {
      return store.status[key] !== fields[key];
    });
    if (!moved) return outcome;
    store.status = Object.assign({}, store.status, fields);
    outcome.status = store.status;
    return outcome;
  }
  // A transition the panel did not start has no return value to carry its status,
  // so it goes out through `deps.emit` like every other outcome.
  function emitStatus(store, fields) {
    var outcome = markStatus(store, {}, fields);
    if (outcome.status) store.deps.emit(outcome);
    return outcome.status;
  }
  function clearRequestTimer(store) {
    if (store.request && store.request.timer) store.deps.clearTimer(store.request.timer);
  }
  // The deadline is only terminal for the request that armed it: a timer left over
  // from a request that has since been answered or refused must not fail the round
  // a second time.
  function deadlineFired(store, id) {
    var req = store.request;
    if (!req || req.id !== id) return null;
    if (req.property && store.dispatched) delete store.dispatched[req.property];
    store.request = null;
    store.requestPromise = null;
    var outcome = {};
    markStatus(store, outcome, { busy: false, diagnostic: "visual_drain_failed" });
    if (outcome.status) store.deps.emit(outcome);
    var resFn = req.resolve;
    req.resolve = null;
    if (typeof resFn === "function") {
      resFn({ accepted: false, error: "timeout" });
    }
    return outcome;
  }
  function beginRequest(store, request) {
    if (!store.status.ready || store.status.stale || request.locator == null || store.request) {
      emitStatus(store, { diagnostic: "visual_unavailable" });
      return Promise.resolve({ accepted: false, error: "visual_unavailable" });
    }
    var id = ++store.sequence;
    var entry = request.entry || null;
    if (entry) entry._replayId = id;
    // Record what this dispatch sends. Typing already set this in commit(), but the
    // replay paths (undo/redo) did not, so drafts and dispatched values stayed
    // permanently unequal and the editor reported a pending edit forever - which the
    // readiness mirror now reads as "submittable".
    store.dispatched[request.property] = request.value;
    setPublished(store, false);
    emitStatus(store, { busy: true });
    var operation = { oldValue: request.oldValue, id: id, action: request.action || "edit",
      entry: entry, origin: request.origin || SHELL_SOURCE,
      value: request.value, draft: request.draft, property: request.property,
      viewport: request.viewport, locator: request.locator };
    store.unacked[id] = operation;
    var promise = new Promise(function (resolve) {
      // The in-flight record is a copy that also carries the resolve and the timer;
      // the unacked entry carries neither, so a receipt that lands after the
      // deadline is still recorded but can never re-settle anything.
      store.request = Object.assign({ resolve: resolve,
        timer: store.deps.setTimer(function () { deadlineFired(store, id); }, REQUEST_TIMEOUT_MS) },
        operation);
      store.deps.send({ type: "set-style", requestId: id, selector: request.locator,
        property: request.property, value: request.value, changes: entry && entry.map(function (item) {
          return { property: item.property, value: operation.action === "undo" ? item.oldValue : item.newValue };
        }), replay: !!entry });
    });
    store.requestPromise = promise;
    promise.finally(function () {
      if (store.requestPromise === promise) store.requestPromise = null;
    });
    return promise;
  }
  function reduceRejected(store, event) {
    var outcome = {};
    // A rejection is terminal for that request id: the bridge will never confirm
    // it, so a retained entry made every later drain answer unresolved_edits and
    // left only Abort usable.
    delete store.unacked[event.requestId];
    if (!store.request || event.requestId !== store.request.id) return outcome;
    if (event.code === "visual_target_missing") markStatus(store, outcome, { stale: true });
    var rolledBack = store.request.property;
    if (rolledBack && hasOwn(store.accepted, rolledBack)) {
      store.dispatched[rolledBack] = store.accepted[rolledBack];
      var value = store.accepted[rolledBack];
      outcome.drafts = function (old) { return store.deps.syncDraft(old, rolledBack, value); };
    }
    clearRequestTimer(store);
    store.request.resolve({ accepted: false, error: event.code });
    store.request = null;
    store.requestPromise = null;
    markStatus(store, outcome, { diagnostic: event.code, busy: false });
    outcome.consumed = true;
    return outcome;
  }
  // The receipt for a request this store dispatched, or a gesture the prototype did
  // on its own. Everything the round needs to know about the request lives here;
  // the ledger transitions the receipt drives stay with the ledger's owner.
  function reduceChange(store, event) {
    if (!store.status.ready || store.status.stale) return null;
    var unacked = store.unacked[event.requestId];
    var operation = (store.request && event.requestId === store.request.id ? store.request : null) || unacked;
    // Whether the id names a gesture is the parser's reading, not the store's:
    // the event carries the answer, so no wire spelling is re-derived down here.
    if (!operation && !event.gesture) return null;
    if (unacked) delete store.unacked[event.requestId];
    if (operation && operation.entry && operation.entry._replayId !== operation.id) return null;
    // Provenance decides whether an edit can stand in for review notes. The
    // prototype shares the bridge window, so a change it reports for a request the
    // parent dispatched can carry values the parent never asked for: for those the
    // parent rebuilds the record from its own dispatch. A gesture the parent did not
    // dispatch has no such record, so its reported values are kept with "frame"
    // provenance, and a WebMCP tool call is the agent editing, not the reviewer.
    // The default provenance is the wire contract's reviewer source; a
    // prototype-reported change without a parent dispatch keeps "frame".
    var source = operation ? (operation.origin || SHELL_SOURCE) : FRAME_SOURCE;
    var reported = source === "frame" ? (event.changes || [event]) : (
      operation.entry ? operation.entry.map(function (item) {
        var target = operation.action === "undo" ? item.oldValue : item.newValue;
        var prior = operation.action === "undo" ? item.newValue : item.oldValue;
        return { property: item.property, oldValue: prior, newValue: target };
      }) : [{
        property: operation.property, oldValue: operation.oldValue,
        newValue: store.deps.canonicalValue(operation.property, operation.value)
      }]
    );
    var changes = reported.map(function (c) {
      var key = event.selector + ":" + c.property;
      if (!hasOwn(store.interruptedValues, key)) return c;
      var recovered = Object.assign({}, c, { oldValue: store.interruptedValues[key] });
      delete store.interruptedValues[key];
      return recovered;
    });
    var outcome = { operation: operation, changes: changes, source: source };
    if (operation && operation.timer) store.deps.clearTimer(operation.timer);
    if (operation && store.request && store.request.id === event.requestId) {
      store.request = null;
      store.requestPromise = null;
      markStatus(store, outcome, { busy: false, diagnostic: "" });
    }
    // A receipt the store never allocated an id for (a gesture) still needs one, so
    // it takes the next sequence number. `begin` remains the only writer of the
    // counter for requests.
    outcome.opSeq = operation ? (operation.id || ++store.sequence) : ++store.sequence;
    if (event.selected === event.selector) {
      var opSeq = outcome.opSeq;
      changes.forEach(function (c) {
        var key = event.selector + ":" + c.property;
        if (opSeq < (store.lastAcceptedSeq[key] || 0)) return;
        store.lastAcceptedSeq[key] = opSeq;
        store.accepted = store.deps.syncDraft(store.accepted, c.property, c.newValue);
      });
      // Keep newer inspector keystrokes while acknowledging older requests. The
      // transform runs against the drafts the panel holds when it is applied, and
      // reads the sequence map as the loop above just left it.
      var settled = operation;
      var acceptedChanges = changes;
      outcome.drafts = function (values) {
        acceptedChanges.forEach(function (c) {
          var key = event.selector + ":" + c.property;
          if (opSeq < (store.lastAcceptedSeq[key] || 0)) return;
          if (!settled || settled.entry || values[c.property] === settled.draft) {
            values = store.deps.syncDraft(values, c.property,
              settled && !settled.entry ? settled.value : c.newValue);
          }
        });
        return values;
      };
    }
    return outcome;
  }
  // What a disconnect takes with it: the requests still waiting for a receipt.
  // Their values are remembered, because the receipt that never comes would
  // otherwise be the only record of what the element used to look like, and their
  // dispatched marks are dropped so the drafts read as unsent again.
  function interruptRequests(store) {
    var interrupted = Object.values(store.unacked);
    store.unacked = {};
    store.lastAcceptedSeq = {};
    interrupted.forEach(function (operation) {
      var key = operation.locator + ":" + operation.property;
      if (!operation.entry && !hasOwn(store.interruptedValues, key)) {
        store.interruptedValues[key] = operation.oldValue;
      }
      delete store.dispatched[operation.property];
    });
    return interrupted;
  }

  // The drain's next move, decided here rather than by the panel's walk: a request
  // in flight has to settle first, then the first draft the bridge has not been
  // sent, then the receipts no answer has cleared, then the round is done. The
  // walk keeps every effect - the `finished` guard, the 2 s timer, the dispatch,
  // the batch - and switches on `kind`. `drafts` is render state the store does
  // not hold, so it arrives in `view` the way `begin` takes `viewport`.
  function planDrain(store, view) {
    if (store.requestPromise) return { kind: "await" };
    var drafts = view.drafts, dispatched = store.dispatched;
    var uncommitted = Object.keys(drafts).filter(function (p) {
      return drafts[p] !== undefined && dispatched[p] !== drafts[p];
    });
    if (uncommitted.length > 0) {
      return { kind: "send", property: uncommitted[0], value: drafts[uncommitted[0]] };
    }
    if (Object.keys(store.unacked).length > 0) return { kind: "unacked" };
    return { kind: "done" };
  }

  function failRound(store, code) {
    if (store.request) {
      clearRequestTimer(store);
      store.request.resolve({ accepted: false, error: code });
      store.request = null;
    }
    store.requestPromise = null;
    return markStatus(store, {}, { diagnostic: code, busy: false }).status;
  }

  function heartbeatPing(store, request) {
    var heartbeat = store.heartbeat;
    var now = store.deps.now();
    if (heartbeat.started === null) heartbeat.started = now;
    // Count unanswered pings, not wall clock: a throttled late tick is not a
    // disconnect, while three unanswered pings are. The disconnect writes the
    // status itself - a round with work pending goes stale, one without keeps
    // whatever staleness it had - so there is nothing to hand back here.
    var status;
    if (heartbeat.lastAck) {
      if (heartbeat.unanswered >= 2) store.deps.disconnect();
      heartbeat.unanswered += 1;
    }
    if (!heartbeat.lastAck && now - heartbeat.started > HEARTBEAT_FIRST_CONNECT_MS) {
      status = markStatus(store, {}, { connecting: false }).status;
    }
    heartbeat.nonce += 1;
    store.deps.post({ type: "ping", nonce: heartbeat.nonce,
      compact: request.compact, labels: request.labels });
    return status;
  }

  function heartbeatLoad(store, request) {
    var heartbeat = store.heartbeat;
    heartbeat.lastAck = 0;
    heartbeat.unanswered = 0;
    heartbeat.started = store.deps.now();
    store.deps.disconnect();
    var status = markStatus(store, {}, { connecting: true }).status;
    heartbeatPing(store, request);
    return status;
  }

  function heartbeatReady(store, response, routeUrl) {
    var heartbeat = store.heartbeat;
    if (response.nonce !== heartbeat.nonce) return null;
    if (response.routeUrl !== routeUrl) {
      // The route moved under the round: age it out, then end the request in
      // flight so the panel is not left busy on a bridge it can no longer
      // reach and the await settles with the route reason, not a later timeout.
      markStatus(store, {}, { stale: true, ready: false });
      return failRound(store, "visual_stale") || store.status;
    }
    heartbeat.lastAck = true;
    heartbeat.unanswered = 0;
    var status = markStatus(store, {}, { ready: true, connecting: false }).status;
    if (!store.status.stale && store.status.diagnostic === "visual_disconnected") {
      status = markStatus(store, {}, { diagnostic: "" }).status || status;
    }
    return status;
  }

  // ---- the wire boundary (slice S6) ----
  // The four shapes pin_bridge.js posts, each message carrying exactly one of
  // them, become the four events the panel and the store take. This is the only
  // place the `dpbVisualEdit*` names appear: a rename on the wire stops here
  // instead of reaching the panel's arms and the store's guards. It is pure - it
  // reads no store state, so `hasAck` stays where the state is.
  function isGestureId(id) {
    return typeof id === "string" && id.indexOf("gesture-") === 0;
  }
  function parseEvent(data) {
    if (!data) return null;
    // One shape per message, so the first match is the message. The order is the
    // panel's: ready, then selection, then rejected, then change. A falsy shape
    // is no message at all, the way the component's own `if (!change) return`
    // read it.
    var response = data.dpbVisualEditReady;
    if (response) return { type: "ready", response: response };
    var selection = data.dpbVisualEditSelection;
    if (selection) {
      return { type: "selection", selection: selection,
        gesture: isGestureId(selection.requestId) };
    }
    var rejected = data.dpbVisualEditRejected;
    if (rejected) return { type: "rejected", requestId: rejected.requestId, code: rejected.code };
    var change = data.dpbVisualEditChange;
    if (change) {
      return { type: "change", requestId: change.requestId, selector: change.selector,
        changes: change.changes, gesture: isGestureId(change.requestId) };
    }
    return null;
  }
  window.DPBEdit = {
    ledger: {
      MERGE_WINDOW_MS: MERGE_WINDOW_MS,
      mergeEdit: mergeEdit,
      getEntryId: getEntryId,
      seqOf: seqOf,
      bySeq: bySeq,
      flatten: flatten,
      undoEntry: undoEntry,
      redoEntry: redoEntry,
      appendEdits: appendEdits,
    },
    protocol: {
      REQUEST_TIMEOUT_MS: REQUEST_TIMEOUT_MS,
      // The wire boundary: one message in, one event or null out. The node table
      // reaches it here, on the namespace; the panel reaches the copy on each
      // instance, because `create`'s answer is the only protocol it holds.
      parse: parseEvent,
      // deps: { send, post, now, disconnect, setTimer, clearTimer, syncDraft,
      // canonicalValue, emit }. The initial status below is the store's own, so
      // the panel's first render has one definition of what the bridge looks
      // like before it answers.
      create: function (deps) {
        var store = {
          deps: deps,
          status: { ready: false, connecting: true, stale: false, busy: false,
            diagnostic: "visual_disconnected" },
          sequence: 0,
          request: null,
          requestPromise: null,
          unacked: {},
          dispatched: {},
          accepted: {},
          lastAcceptedSeq: {},
          interruptedValues: {},
          heartbeat: { nonce: 0, lastAck: 0, started: null, unanswered: 0 },
          published: true,
          draining: false,
        };
        return {
          // The wire boundary is the same function on both objects the shell can
          // hold. `parse` reads no store state, but the panel's only reference is
          // the instance `create` answers, so a namespace-only copy is a call the
          // panel cannot reach.
          parse: parseEvent,
          begin: function (request) { return beginRequest(store, request); },
          reduce: function (event) {
            if (!event) return null;
            if (event.type === "rejected") return reduceRejected(store, event);
            if (event.type === "change") return reduceChange(store, event);
            return null;
          },
          status: function () { return store.status; },
          // The status writes that are not request transitions: the heartbeat and
          // the round's own lifecycle still decide `ready`, `connecting` and
          // `stale`. Answers the new status, or null when nothing moved.
          patch: function (fields) { return markStatus(store, {}, fields).status; },
          // Terminal for the round: refuse the request in flight and say why.
          fail: function (code) {
            return failRound(store, code);
          },
          ping: function (request) { return heartbeatPing(store, request); },
          load: function (request) { return heartbeatLoad(store, request); },
          ready: function (response, routeUrl) { return heartbeatReady(store, response, routeUrl); },
          hasAck: function () { return !!store.heartbeat.lastAck; },
          interrupt: function () { return interruptRequests(store); },
          // The receipt is in hand and the ledger has been told: settle the promise
          // with what the round ended up holding.
          acknowledge: function (operation, pending) {
            if (operation && typeof operation.resolve === "function") {
              var resFn = operation.resolve;
              operation.resolve = null;
              resFn({ accepted: true, pending: !!pending });
            }
          },
          // Unmount: the deadline must not outlive the panel. Nothing is resolved -
          // the round is gone.
          dispose: function () { clearRequestTimer(store); },
          hasRequest: function () { return !!store.request; },
          requestId: function () { return store.request ? store.request.id : null; },
          pendingRequest: function () { return store.requestPromise; },
          markDispatched: function (property, value) { store.dispatched[property] = value; },
          acceptedValue: function (property) { return store.accepted[property]; },
          // A new selection re-bases both records: the accepted values are the
          // snapshot the panel now shows, and nothing has been sent against it.
          acceptSelection: function (values) {
            store.accepted = values;
            store.dispatched = Object.assign({}, values);
            return store.accepted;
          },
          // The drain's decision (S5). One query in place of the three the panel
          // used to ask for separately, in the order it had to ask them.
          planDrain: function (view) { return planDrain(store, view); },
          // The seven fields the pending rule reads, in the order it reads them.
          // `selected`, `draftTimers` and `drafts` are render/DOM inputs the store
          // does not hold, so they arrive in `view`; the rest are its own records.
          pendingSnapshot: function (view) {
            return {
              selected: view.selected,
              published: store.published,
              request: store.requestPromise,
              unacked: store.unacked,
              draftTimers: view.draftTimers,
              drafts: view.drafts,
              dispatched: store.dispatched,
            };
          },
          // The two single-writer flags (S5), each behind one setter.
          setPublished: function (value) { setPublished(store, value); },
          isDraining: function () { return store.draining; },
          setDraining: function (value) { setDraining(store, value); },
        };
      },
    },
  };
})();
