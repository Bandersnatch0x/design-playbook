/* Queue-monitor dialog and retry state module.
 *
 * Pure state transitions stay independent from DOM/timers. The showcase page
 * supplies those as adapters; Node tests can exercise this module directly.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.QueueMonitorState = factory();
  }
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";

  function createDialogState() {
    return { session: 0, executing: false };
  }

  function openDialog(state) {
    return { session: state.session + 1, executing: false };
  }

  function closeDialog(state) {
    return { session: state.session + 1, executing: false };
  }

  function beginExecution(state) {
    return { session: state.session, executing: true };
  }

  function resetExecution(state) {
    return { session: state.session, executing: false };
  }

  function canCancel(state) {
    return !state.executing;
  }

  function isCurrentSession(state, session) {
    return state.session === session;
  }

  function selectedFailed(runs, selected) {
    return runs.filter(function (run) {
      return selected[run.id] && run.state === "failed";
    });
  }

  function inScope(runs, scope) {
    return scope === "fail-once"
      ? runs.filter(function (run) { return run.attempts === 1; })
      : runs;
  }

  function completeRetry(runs, selected, scope) {
    var targets = inScope(selectedFailed(runs, selected), scope);
    var targetIds = new Set(targets.map(function (run) { return run.id; }));
    return {
      runs: runs.map(function (run) {
        return targetIds.has(run.id)
          ? Object.assign({}, run, { state: "queued" })
          : run;
      }),
      selected: {},
      count: targets.length,
    };
  }

  return {
    createDialogState: createDialogState,
    openDialog: openDialog,
    closeDialog: closeDialog,
    beginExecution: beginExecution,
    resetExecution: resetExecution,
    canCancel: canCancel,
    isCurrentSession: isCurrentSession,
    selectedFailed: selectedFailed,
    inScope: inScope,
    completeRetry: completeRetry,
  };
});
