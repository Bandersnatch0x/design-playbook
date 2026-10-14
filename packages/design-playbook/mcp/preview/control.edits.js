/* The preview edit ledger: the coalesce rule and the list operations the editor
   performs on its entries. Slice S1 moved the rules out of control.react.js
   unchanged; slice S2 collapses the three lists to two: `entries` is the undo
   stack - grouped entries in `seqOf` order, newest replayed last - and also
   holds the edits that have not been published away, so the old flat `pending`
   list is no longer stored. The flat view the batch, the counts and the
   modified dots need is `flatten(entries)`: one projection, computed where it is
   read. A coalesce still mutates the edit object that the last entry holds, and
   that shared identity is what reaches the published batch. These functions only
   answer "what are the next lists". */
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
  };
})();
