<!-- spec-schema: 2 -->

# Learning inbox — automated continuation fixture

Adapted from the September 7, 2026 extra-project dogfood journey. All approval
and review inputs in this fixture are simulated, not external trial evidence.

## L1 Positioning and intent

- 用户可见目标：Complete, clear, and recover tasks in a learning inbox.
- Primary user: a learner with today's tasks.
- Always: show state; ask first: clear all; never: delete silently.
- Non-goals: synchronization, notifications, task editing.

## L2 Information architecture

- Inbox: summary, task list, empty-state CTA, recoverable error.
- Clear all requires an explicit consequence confirmation.

| Page | Duty |
| --- | --- |
| inbox | Complete, clear, and recover today's tasks |

## L3 Core paths

- P1: seeded → complete first → updated summary.
- P2: seeded → clear → cancel or confirm → empty → add task.
- P3: seeded → sync error → retry → usable list.

| Path | Steps |
| --- | --- |
| P1 | seeded → complete first → updated summary |
| P2 | seeded → clear → cancel or confirm → empty → add task |
| P3 | seeded → sync error → retry → usable list |

## L4 Components

- Native buttons with keyboard activation and preserved focus.
- Live summary and alert for confirmation/errors.

## L5 Boundaries

- Initial/success: task list. Empty: explanation + Add next task.
- Failure: visible sync error + Retry. Loading: not applicable (static fixture).
- No permission or network backend is simulated.

| Page | initial | loading | success | failure | empty |
| --- | --- | --- | --- | --- | --- |
| inbox | Seeded tasks | not applicable (no asynchronous work) | Updated task and count | Sync error + Retry | Explanation + Add next task |

## L6 Acceptance criteria

- Given pending tasks When the first task is completed Then its state and summary update (path: P1).
- Given tasks When clear all is requested Then cancel preserves tasks and confirmation leads to an empty state with a working CTA (path: P2).
- Given a sync error When retry is selected Then the error disappears and tasks remain usable (path: P3).
