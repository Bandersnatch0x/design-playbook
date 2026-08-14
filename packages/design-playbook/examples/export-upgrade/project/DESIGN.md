---
name: ops-console
colors:
  surface: neutral-50
  accent: blue-600
---

# Ops console baseline (v2, post-refactor)

Atmosphere: dense operator console, no marketing chrome.

## Layout

Regions per page: toolbar (actions), table (primary data), status (global
task feed — in-flight and recent tasks persist across view switches), toast
(page-level notices). Pages enable the subset their duty needs; the status
region convention is a persistent feed, never an ephemeral popup.

## Density

console-tight: 32px rows, inline batch actions, no card walls.

## Motion

Progress is continuous and calm; no attention-grabbing animation.

## Component conventions

Primary action = Button (icon + label). Notices = toast with role=alert.

## Source Evidence & Confidence

- source: baseline-v2-refactor.md
  observed: layout conventions restated after source restructure
  confidence: high
