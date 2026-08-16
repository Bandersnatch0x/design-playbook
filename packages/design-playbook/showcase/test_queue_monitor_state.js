"use strict";

const assert = require("node:assert/strict");
const state = require("./queue-monitor-state.js");

{
  const runs = [
    { id: "a", state: "failed", attempts: 1 },
    { id: "b", state: "failed", attempts: 2 },
    { id: "c", state: "queued", attempts: 0 },
  ];
  const result = state.completeRetry(runs, { a: true, b: true }, "fail-once");
  assert.deepEqual(result.runs.map((run) => run.state), ["queued", "failed", "queued"]);
  assert.deepEqual(result.selected, {});
  assert.equal(result.count, 1);
}

{
  let current = state.openDialog(state.createDialogState());
  const session = current.session;
  current = state.beginExecution(current);
  assert.equal(state.canCancel(current), false);
  assert.equal(state.isCurrentSession(current, session), true);
  current = state.closeDialog(current);
  assert.equal(state.canCancel(current), true);
  assert.equal(state.isCurrentSession(current, session), false);
}

console.log("queue-monitor-state tests passed");
