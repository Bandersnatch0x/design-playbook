/* The preview edit ledger: the coalesce rule and the list operations the editor
   performs on pending / history / future. Slice S1 moves these out of
   control.react.js unchanged: `pending` stays a flat list of edits, `history`
   and `future` stay lists of grouped entries, and one entry object can still be
   visible in two lists at once - that identity is how a coalesce reaches the
   batch the rail reads. The component keeps its React state writes; these
   functions only answer "what are the next lists". */
(function () {
  "use strict";
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
  // Undo moves the entry out of history into future and drops its edits from
  // the flat pending list. Returns null when the entry is no longer there.
  function undoEntry(state, entry) {
    var targetId = getEntryId(entry);
    var hist = state.history || [];
    var targetIdx = lastIndexOfId(hist, targetId);
    if (targetIdx < 0) return null;
    var nextHist = hist.slice(0, targetIdx).concat(hist.slice(targetIdx + 1));
    var fut = state.future || [];
    var alreadyInFut = fut.some(function (f) { return getEntryId(f) === targetId; });
    var nextFut = alreadyInFut ? fut : fut.concat([entry]);
    var nextPending = (state.pending || []).filter(function (e) {
      return getEntryId(e) !== targetId;
    });
    return { pending: nextPending, history: nextHist, future: nextFut };
  }
  // Redo is undo's mirror: the entry returns to history, its edits return to
  // pending, and both lists are re-ordered by sequence because a receipt can
  // land out of order.
  function redoEntry(state, entry) {
    var targetId = getEntryId(entry);
    var fut = state.future || [];
    var targetIdx = lastIndexOfId(fut, targetId);
    if (targetIdx < 0) return null;
    var nextFut = fut.slice(0, targetIdx).concat(fut.slice(targetIdx + 1));
    var hist = state.history || [];
    var alreadyInHist = hist.some(function (h) { return getEntryId(h) === targetId; });
    var nextHist = alreadyInHist ? hist : hist.concat([entry]);
    nextHist.sort(bySeq);
    var curPending = state.pending || [];
    var alreadyInPending = curPending.some(function (e) { return getEntryId(e) === targetId; });
    var nextPending = alreadyInPending ? curPending : curPending.concat(entry);
    nextPending.sort(bySeq);
    return { pending: nextPending, history: nextHist, future: nextFut };
  }
  // A new edit joins pending (flat) and history (grouped), both in sequence
  // order. A receipt older than something already in `future` must not throw
  // the redo stack away, so `future` comes back null when it stands.
  function appendEdits(state, edits, opSeq) {
    var nextPending = (state.pending || []).concat(edits);
    nextPending.sort(bySeq);
    var nextHist = (state.history || []).concat([edits]);
    nextHist.sort(bySeq);
    var fut = state.future || [];
    var isOlderReceipt = fut.some(function (f) { return opSeq < seqOf(f); });
    return { pending: nextPending, history: nextHist, future: isOlderReceipt ? null : [] };
  }
  window.DPBEdit = {
    ledger: {
      MERGE_WINDOW_MS: MERGE_WINDOW_MS,
      mergeEdit: mergeEdit,
      getEntryId: getEntryId,
      seqOf: seqOf,
      bySeq: bySeq,
      undoEntry: undoEntry,
      redoEntry: redoEntry,
      appendEdits: appendEdits,
    },
  };
})();
