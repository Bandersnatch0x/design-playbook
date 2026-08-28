# template (page skeleton declaration)

## Dashboard / scheduler (default example)

- **Scene**: task scheduling, run monitoring, queue, batch-processing progress.
- **Skeleton**:
  - top: overview metrics
  - main: task list or task flow
  - side: trend, queue pressure, failure reasons
  - actions: refresh, batch retry, pause, etc.
- **Density**: console density; overview carries only key metrics; charts do not compete with the main list.
- **Prohibited uses**: marketing landing pages, pure chart big screens, sample/playground as production.

## List page

- Filter + table + row actions + empty/loading/error; batch zone visible at same level as main table.

## Detail page

- Title + meta + main content + secondary tabs/sidebar; dangerous operations require confirmation.

## Settings page

- Grouped form + save feedback; do not stuff settings into arbitrary modals.
