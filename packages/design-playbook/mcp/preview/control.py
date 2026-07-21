"""Confirm control-bar template + builder + feedback formatting.

Sibling module split from server.py; behavior unchanged. Holds the large
injected HTML/CSS/JS template (``control_tpl``), the locale-aware builder
``_build_control`` (shared by the runtime HTTP page and the playwright
frontend floor test), and ``_format_feedback``.
"""
from __future__ import annotations

import html as html_lib
import json
from typing import Any

from i18n import CONFIRM_LABELS, REVISE_LABELS, t


control_tpl = r"""
<style>
  #dpb-preview-bar {{
--dpb-bg: #1e2330;
--dpb-surface: #252b38;
--dpb-elev: #2a3140;
--dpb-line: #2c3444;
--dpb-line-strong: #3d475a;
--dpb-ink: #f3f4f6;
--dpb-muted: #9aa3b2;
--dpb-soft: #c5cbd6;
--dpb-accent: #14b8a6;
--dpb-accent-ink: #ffffff;
--dpb-accent-deep: #0f766e;
--dpb-danger: #f87171;
--dpb-radius: 10px;
--dpb-control-h: 40px;
font: 13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
color: var(--dpb-ink);
  }}
  /* ---- floating pill (default state) ---- */
  #dpb-preview-bar {{
position: fixed;
right: 24px;
bottom: 24px;
left: auto;
top: auto;
z-index: 1000;
background: transparent;
border: 0;
padding: 0;
border-radius: 0;
border-top: 0;
  }}
  #dpb-preview-bar .dpb-pill {{
display: inline-flex;
align-items: center;
gap: 8px;
padding: 8px 8px 8px 16px;
background: var(--dpb-bg);
border: 1px solid var(--dpb-line);
border-radius: 999px;
box-shadow: 0 8px 28px rgba(0,0,0,.15), 0 2px 6px rgba(0,0,0,.1);
  }}
  #dpb-preview-bar .dpb-pill .dpb-pill-info {{
display: inline-flex; align-items: center; gap: 8px; max-width: 260px;
  }}
  #dpb-preview-bar .dpb-round {{
flex: 0 0 auto; display: inline-flex; align-items: center; height: 22px;
padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 700;
font-variant-numeric: tabular-nums; color: #99f6e4;
background: rgba(20,184,166,.14); border: 1px solid rgba(20,184,166,.35);
  }}
  #dpb-preview-bar .dpb-pill .dpb-summary {{
margin: 0; min-width: 0; color: var(--dpb-soft);
font-size: 12.5px; font-weight: 500; overflow: hidden;
text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-pill .dpb-pill-actions {{
display: inline-flex; align-items: center; gap: 6px;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost {{
appearance: none; cursor: pointer; height: 32px; padding: 0 12px;
border-radius: 999px; border: 1px solid var(--dpb-line-strong);
background: var(--dpb-surface); color: var(--dpb-soft);
font: 650 12.5px/1 system-ui, sans-serif;
display: inline-flex; align-items: center; gap: 6px;
transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost:hover {{
background: var(--dpb-elev); border-color: #5b6578; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-ghost:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  #dpb-preview-bar .dpb-pill .dpb-badge-dot {{
display: none; min-width: 18px; height: 18px; padding: 0 5px;
align-items: center; justify-content: center; border-radius: 999px;
font-size: 11px; font-weight: 700; color: #042f2e;
background: var(--dpb-accent);
  }}
  #dpb-preview-bar .dpb-pill .dpb-badge-dot.is-on {{ display: inline-flex; }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary {{
appearance: none; cursor: pointer; height: 32px; padding: 0 16px;
border-radius: 999px; border: 1px solid var(--dpb-accent-deep);
background: var(--dpb-accent); color: var(--dpb-accent-ink);
font: 650 12.5px/1 system-ui, sans-serif;
box-shadow: inset 0 1px 0 rgba(255,255,255,.18);
transition: background 140ms ease, transform 100ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:hover {{ background: #2dd4bf; color: #042f2e; }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:active {{ transform: translateY(1px); }}
  #dpb-preview-bar .dpb-pill .dpb-btn-primary:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  /* Direct confirm state on pill primary when readiness allows immediate action */
  #dpb-preview-bar .dpb-pill .dpb-btn-primary.is-direct-confirm {{
    box-shadow: 0 0 0 3px rgba(20,184,166,0.25);
    font-weight: 700;
  }}
  /* secondary action surfaced on the pill (e.g. the revise label) */
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary {{
appearance: none; cursor: pointer; height: 32px; padding: 0 14px;
border-radius: 999px; border: 1px solid var(--dpb-line-strong);
background: var(--dpb-elev); color: var(--dpb-soft);
font: 650 12.5px/1 system-ui, sans-serif;
display: inline-flex; align-items: center;
transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary:hover {{
background: #3a4150; border-color: #6b7588; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  @media (max-width: 720px) {{
#dpb-preview-bar .dpb-pill .dpb-btn-pill-secondary {{ display: inline-flex; font-size: 11px; padding: 0 8px; }}
/* Per debate: do not hide revise on mobile; allow stacking if needed */
  }}

  /* ---- drawer (expanded state) ---- */
  #dpb-preview-bar dialog.dpb-drawer {{
position: fixed;
right: 24px;
bottom: 24px;
margin: 0;
width: 380px;
max-width: calc(100vw - 48px);
max-height: calc(100vh - 48px);
flex-direction: column;
background: var(--dpb-bg);
border: 1px solid var(--dpb-line);
border-radius: 16px;
box-shadow: 0 16px 48px rgba(0,0,0,.22), 0 4px 12px rgba(0,0,0,.12);
overflow: hidden;
color: var(--dpb-ink);
padding: 0;
  }}
  /* non-modal <dialog>.show() is not in the top layer, so we keep the hand-rolled
     scrim (stronger than before per UX V4) so the drawer reads as a focused layer. */
  #dpb-preview-bar dialog.dpb-drawer[open] {{ display: flex; }}
  /* show() failure / no-dialog fallback: is-open alone must reveal the drawer */
  #dpb-preview-bar.is-open dialog.dpb-drawer {{ display: flex; }}
  #dpb-preview-bar.is-open::before {{
content: "";
position: fixed; inset: 0; z-index: -1;
background: rgba(15,23,42,.5);
pointer-events: auto;  /* P1.5: intercept clicks outside drawer (close on scrim) */
  }}
  body.dpb-pin-mode #dpb-preview-bar.is-open::before {{
pointer-events: none;  /* P1.5: let pin-mode clicks reach prototype elements */
  }}
  #dpb-preview-bar.is-open .dpb-pill {{ display: none; }}

  #dpb-preview-bar .dpb-drawer-head {{
display: flex; align-items: center; justify-content: space-between;
gap: 10px; padding: 12px 14px;
border-bottom: 1px solid var(--dpb-line);
background: linear-gradient(180deg, #131722, var(--dpb-bg));
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-head-left {{
display: inline-flex; align-items: center; gap: 8px; min-width: 0;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-title {{
margin: 0; font-size: 13px; font-weight: 650; color: var(--dpb-ink);
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn {{
appearance: none; cursor: pointer; width: 28px; height: 28px;
border-radius: 8px; border: 1px solid transparent;
background: transparent; color: var(--dpb-muted);
font: 650 16px/1 system-ui, sans-serif;
display: inline-grid; place-items: center;
transition: background 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn:hover {{
background: var(--dpb-elev); color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-drawer-head .dpb-icon-btn:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 1px;
  }}

  #dpb-preview-bar .dpb-drawer-body {{
display: flex; flex-direction: column; min-height: 0;
overflow: auto; padding: 10px 14px 14px; gap: 14px;
  }}
  #dpb-preview-bar .dpb-drawer-body .dpb-subhead {{
margin: 0; font-size: 11px; font-weight: 700; letter-spacing: 0.05em;
color: var(--dpb-muted); text-transform: uppercase;
  }}

  /* pin toggle in drawer */
  #dpb-preview-bar .dpb-pin-toggle {{
appearance: none; cursor: pointer; height: 34px; padding: 0 12px;
border-radius: 8px; border: 1px solid var(--dpb-line-strong);
background: var(--dpb-surface); color: var(--dpb-soft);
font: 650 12.5px/1 system-ui, sans-serif;
display: inline-flex; align-items: center; gap: 7px;
transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
  }}
  #dpb-preview-bar .dpb-pin-toggle:hover {{
background: var(--dpb-elev); border-color: #5b6578; color: var(--dpb-ink);
  }}
  #dpb-preview-bar .dpb-pin-toggle.is-on {{
color: #042f2e; background: var(--dpb-accent); border-color: var(--dpb-accent-deep);
  }}
  #dpb-preview-bar .dpb-pin-toggle:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 2px;
  }}
  #dpb-preview-bar .dpb-pin-row {{
display: flex; align-items: center; justify-content: space-between; gap: 10px;
  }}
  #dpb-preview-bar .dpb-pin-count {{
font-size: 11.5px; color: var(--dpb-muted); font-variant-numeric: tabular-nums;
  }}

  /* anchor list */
  #dpb-preview-bar .dpb-anchors {{
display: none; flex-direction: column; gap: 6px;
max-height: 180px; overflow: auto; padding: 8px;
border-radius: 8px; background: var(--dpb-surface);
border: 1px solid var(--dpb-line);
  }}
  #dpb-preview-bar .dpb-anchors.has-items {{ display: flex; }}
  #dpb-preview-bar .dpb-empty {{
display: none; padding: 10px 4px; font-size: 12px; color: var(--dpb-muted);
text-align: center;
  }}
  #dpb-preview-bar .dpb-anchors:not(.has-items) + .dpb-empty {{ display: block; }}
  #dpb-preview-bar .dpb-anchor {{
display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 8px;
align-items: start; padding: 6px 8px; border-radius: 8px;
background: var(--dpb-elev); border: 1px solid var(--dpb-line);
  }}
  #dpb-preview-bar .dpb-anchor .n {{
font-size: 11px; font-weight: 700; color: var(--dpb-accent); padding-top: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .meta {{
min-width: 0; display: grid; gap: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .label {{
font-size: 12px; font-weight: 650; color: var(--dpb-ink);
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
appearance: none; border: 0; background: transparent; padding: 0;
text-align: left; cursor: pointer; width: 100%;
display: block; min-width: 0;
  }}
  #dpb-preview-bar .dpb-anchor .label:hover {{ color: var(--dpb-accent); }}
  #dpb-preview-bar .dpb-anchor .label:focus-visible {{
outline: 2px solid var(--dpb-accent); outline-offset: 1px; border-radius: 4px;
  }}
  #dpb-preview-bar .dpb-anchor .sel {{
font-size: 11px; color: var(--dpb-muted);
overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-anchor input {{
width: 100%; box-sizing: border-box; height: 28px; margin: 0; padding: 0 8px;
border-radius: 6px; border: 1px solid var(--dpb-line-strong);
background: var(--dpb-surface); color: var(--dpb-ink); font: inherit; outline: none;
  }}
  #dpb-preview-bar .dpb-anchor input:focus {{
border-color: var(--dpb-accent); box-shadow: 0 0 0 2px rgba(20,184,166,.2);
  }}
  #dpb-preview-bar .dpb-anchor .rm {{
appearance: none; cursor: pointer; height: 28px; padding: 0 8px;
border: 0; border-radius: 6px; background: transparent; color: var(--dpb-muted);
font: 650 12px/1 system-ui, sans-serif;
  }}
  #dpb-preview-bar .dpb-anchor .rm:hover {{ color: var(--dpb-danger); background: rgba(248,113,113,.08); }}

  /* overall comment */
  #dpb-preview-bar .dpb-field {{ display: grid; gap: 6px; min-width: 0; }}
  #dpb-preview-bar .dpb-label-row {{
display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  }}
  #dpb-preview-bar .dpb-label {{ font-size: 12px; font-weight: 650; color: var(--dpb-muted); }}
  /* I4: neutral hint up-front; .is-on only adds emphasis (was red-danger-only). */
  #dpb-preview-bar .dpb-hint {{ margin: 0; font-size: 12px; color: var(--dpb-muted); display: block; }}
  #dpb-preview-bar .dpb-hint.is-on {{ color: var(--dpb-danger); font-weight: 600; }}
  /* I4: pill readiness indicator (live status on the resting pill). */
  #dpb-preview-bar .dpb-pill .dpb-pill-ready {{
font-size: 11px; color: var(--dpb-muted); white-space: nowrap;
  }}
  #dpb-preview-bar .dpb-pill .dpb-pill-ready.is-ready {{
color: #5eead4; font-weight: 600;
  }}
  #dpb-preview-bar textarea[name="feedback"] {{
width: 100%; box-sizing: border-box; min-height: 56px; max-height: 120px;
resize: vertical; margin: 0; padding: 8px 12px; color: var(--dpb-ink);
background: var(--dpb-surface); border: 1px solid var(--dpb-line-strong);
border-radius: var(--dpb-radius); font: inherit; line-height: 1.45; outline: none;
transition: border-color 140ms ease, box-shadow 140ms ease, background 140ms ease;
  }}
  #dpb-preview-bar textarea[name="feedback"]::placeholder {{ color: #7d8698; }}
  #dpb-preview-bar textarea[name="feedback"]:hover {{ border-color: #525c70; background: var(--dpb-elev); }}
  #dpb-preview-bar textarea[name="feedback"]:focus {{
border-color: var(--dpb-accent); box-shadow: 0 0 0 3px rgba(20,184,166,.22); background: #12161e;
  }}
  #dpb-preview-bar textarea[name="feedback"][aria-invalid="true"] {{
border-color: #f87171; box-shadow: 0 0 0 3px rgba(248,113,113,.18);
  }}

  /* footer actions */
  #dpb-preview-bar .dpb-drawer-foot {{
display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between;
align-items: center; padding: 12px 14px;
border-top: 1px solid var(--dpb-line);
background: linear-gradient(180deg, var(--dpb-bg), #131722);
  }}
  #dpb-preview-bar .dpb-btns {{
display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; align-items: center;
  }}
  #dpb-preview-bar .dpb-btn {{
appearance: none; cursor: pointer; box-sizing: border-box; height: var(--dpb-control-h);
min-width: 96px; padding: 0 16px; border-radius: var(--dpb-radius);
font: 650 13px/1 system-ui, -apple-system, "Segoe UI", sans-serif;
border: 1px solid transparent;
transition: background 140ms ease, border-color 140ms ease, color 140ms ease, transform 100ms ease;
  }}
  #dpb-preview-bar .dpb-btn:active {{ transform: translateY(1px); }}
  #dpb-preview-bar .dpb-btn:focus-visible {{ outline: 2px solid var(--dpb-accent); outline-offset: 2px; }}
  #dpb-preview-bar .dpb-btn-primary {{
background: var(--dpb-accent); color: var(--dpb-accent-ink); border-color: var(--dpb-accent-deep);
box-shadow: inset 0 1px 0 rgba(255,255,255,.18);
  }}
  #dpb-preview-bar .dpb-btn-primary:hover {{ background: #2dd4bf; color: #042f2e; }}
  #dpb-preview-bar .dpb-btn-secondary {{
background: var(--dpb-elev); color: var(--dpb-ink); border-color: var(--dpb-line-strong);
  }}
  #dpb-preview-bar .dpb-btn-secondary:hover {{ background: #252b39; border-color: #5b6578; }}
  #dpb-preview-bar .dpb-btn-quiet {{
min-width: 72px; background: transparent; color: var(--dpb-muted); border-color: transparent;
  }}
  #dpb-preview-bar .dpb-btn-quiet:hover {{ color: var(--dpb-ink); background: rgba(255,255,255,.04); }}
  #dpb-preview-bar .dpb-btn-danger {{
min-width: 72px; background: transparent; color: var(--dpb-danger); border-color: transparent;
  }}
  #dpb-preview-bar .dpb-btn-danger:hover {{ color: #fff; background: var(--dpb-danger); border-color: var(--dpb-danger); }}
  #dpb-preview-bar .dpb-btn-danger.is-armed {{ color: #fff; background: var(--dpb-danger); border-color: var(--dpb-danger); font-weight: 700; animation: dpb-abort-pulse 1s ease-in-out infinite; }}
  /* ring pulse (not opacity) so the armed label stays at full contrast */
  @keyframes dpb-abort-pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(248,113,113,.55); }} 50% {{ box-shadow: 0 0 0 7px rgba(248,113,113,.12); }} }}
  /* visually hidden live region (screen-reader announcements, e.g. abort arming) */
  #dpb-preview-bar .dpb-sr-only {{
position: absolute; width: 1px; height: 1px; overflow: hidden;
clip-path: inset(50%); white-space: nowrap;
  }}

  /* floating annotation bubbles pinned to targeted elements.
     z-index 999 < #dpb-preview-bar (1000): float-note sits above the prototype
     page content but BELOW the bar/drawer, so pin bubbles never cover the
     confirm controls (was 1001 -> covered drawer, d46682d follow-up). */
  .dpb-float-note {{
position: absolute;
z-index: 999;
max-width: 240px;
min-width: 120px;
padding: 6px 10px 6px 8px;
border-radius: 10px;
background: #1f2430;
color: #f3f4f6;
border: 1px solid #2c3444;
box-shadow: 0 8px 24px rgba(0,0,0,.32), 0 2px 6px rgba(0,0,0,.18);
font: 12px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
pointer-events: none;
transform: translateY(4px);
opacity: 0;
transition: opacity 160ms ease, transform 160ms ease;
  }}
  .dpb-float-note.is-visible {{ opacity: 1; transform: translateY(0); }}
  .dpb-float-note .dpb-float-n {{
position: absolute; top: -7px; left: -7px;
width: 18px; height: 18px; border-radius: 999px;
background: var(--dpb-accent); color: #042f2e;
font-size: 11px; font-weight: 700;
display: inline-grid; place-items: center;
box-shadow: 0 1px 3px rgba(0,0,0,.3);
  }}
  .dpb-float-note .dpb-float-label {{
display: block; font-weight: 650; color: #99f6e4;
font-size: 11px; margin-bottom: 2px; word-break: break-word;
  }}
  .dpb-float-note .dpb-float-comment {{
color: var(--dpb-soft); word-break: break-word; white-space: pre-wrap;
  }}

  .dpb-pin-target {{
outline: 1.5px solid rgba(20,184,166,.9) !important;
outline-offset: 1px !important;
background-color: rgba(20,184,166,.06) !important;
cursor: crosshair !important;
  }}
  .dpb-pin-hover {{
outline: 1px dashed rgba(20,184,166,.45) !important;
outline-offset: 1px !important;
  }}
  /* brief flash when an anchor is located from the list */
  .dpb-pin-flash {{
animation: dpb-flash 900ms ease-out 1;
  }}
  @keyframes dpb-flash {{
0% {{ box-shadow: 0 0 0 0 rgba(20,184,166,.55); outline-color: rgba(20,184,166,.9) !important; }}
50% {{ box-shadow: 0 0 0 6px rgba(20,184,166,.25); }}
100% {{ box-shadow: 0 0 0 0 rgba(20,184,166,0); }}
  }}
  body.dpb-pin-mode, body.dpb-pin-mode * {{ cursor: crosshair !important; }}
  body.dpb-pin-mode #dpb-preview-bar, body.dpb-pin-mode #dpb-preview-bar * {{
cursor: default !important;
  }}

  @media (max-width: 720px) {{
#dpb-preview-bar {{ right: 12px; bottom: 12px; }}
#dpb-preview-bar .dpb-drawer {{ width: calc(100vw - 24px); }}
#dpb-preview-bar .dpb-pill .dpb-pill-info {{ display: none; }}
#dpb-preview-bar .dpb-drawer-body {{ padding: 10px 10px 14px; }}
#dpb-preview-bar .dpb-drawer-foot {{ justify-content: flex-start; flex-wrap: wrap; }}
#dpb-preview-bar .dpb-btn.dpb-btn-danger {{ flex: 0 0 auto; }}
#dpb-preview-bar .dpb-btns {{ flex: 1 1 auto; }}
#dpb-preview-bar .dpb-btns .dpb-btn {{ flex: 1 1 auto; min-width: 0; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
#dpb-preview-bar .dpb-btn,
#dpb-preview-bar textarea[name="feedback"],
.dpb-float-note {{ transition: none; }}
#dpb-preview-bar .dpb-btn:active {{ transform: none; }}
.dpb-pin-flash {{ animation: none; }}
/* armed state still reads via solid danger fill + bold label, no pulse */
#dpb-preview-bar .dpb-btn-danger.is-armed {{ animation: none; }}
  }}
</style>
<div id="dpb-preview-bar" role="region" aria-label="{t_region}">
  <form method="POST" action="/decide" id="dpb-decide-form">
<input type="hidden" name="anchors_json" id="dpb-anchors-json" value="[]" />

<!-- floating pill (default) -->
<div class="dpb-pill">
  <span class="dpb-pill-info">
    <span class="dpb-round">{t_round}</span>
    <p class="dpb-summary" title="{summary_safe}">{summary_safe}</p>
  </span>
  <span class="dpb-pill-ready" id="dpb-pill-ready" role="status">{t_not_ready}</span>
  <span class="dpb-pill-actions">
    {pill_secondary_html}
    <button type="button" class="dpb-btn-ghost" id="dpb-open-drawer" aria-haspopup="dialog">
      <span aria-hidden="true">💬</span>{t_annotate}<span class="dpb-badge-dot" id="dpb-pill-count">0</span>
    </button>
    <button type="button" class="dpb-btn-primary" id="dpb-open-primary" aria-haspopup="dialog">{t_pill_open}</button>
  </span>
</div>

<!-- drawer (expanded) -->
<dialog class="dpb-drawer" id="dpb-drawer" aria-label="{t_drawer_aria}">
  <div class="dpb-drawer-head">
    <span class="dpb-head-left">
      <span class="dpb-round">{t_round}</span>
      <h2 class="dpb-title">{summary_safe}</h2>
    </span>
    <button type="button" class="dpb-icon-btn" id="dpb-close-drawer" aria-label="{t_collapse}">−</button>
  </div>
  <div class="dpb-drawer-body">
    <div class="dpb-pin-row">
      <button type="button" class="dpb-pin-toggle" id="dpb-pin-toggle" aria-pressed="false">
        <span aria-hidden="true">🎯</span><span class="dpb-pin-label">{t_pin_toggle}</span>
      </button>
      <span class="dpb-pin-count" id="dpb-pin-count">{t_pin_count}</span>
    </div>

    <div>
      <p class="dpb-subhead">{t_anchors_head}</p>
      <div class="dpb-anchors" id="dpb-anchors" aria-live="polite"></div>
      <p class="dpb-empty">{t_anchors_empty}</p>
    </div>

    <div class="dpb-field">
      <span class="dpb-label-row">
        <span class="dpb-label">{t_field_label}</span>
        <span class="dpb-hint" id="dpb-feedback-hint" role="alert">{t_field_hint}</span>
      </span>
      <textarea name="feedback" rows="2"
        placeholder="{t_field_placeholder}"
        autocomplete="off"></textarea>
    </div>
  </div>
  <div class="dpb-drawer-foot">
    <button type="submit" name="choice" value="__abort__" class="dpb-btn dpb-btn-danger" id="dpb-abort">{t_terminate}</button>
    <span class="dpb-sr-only" id="dpb-abort-status" role="alert"></span>
    <div class="dpb-btns">
      <button type="button" class="dpb-btn dpb-btn-quiet" id="dpb-draft">{t_draft}</button>
      {secondary_html}
      <button type="submit" name="choice" value="{primary_val}" class="dpb-btn dpb-btn-primary">{primary_label}</button>
    </div>
  </div>
</dialog>
  </form>
</div>
<div id="dpb-preview-spacer" aria-hidden="true"></div>
<script>window.DPB_I18N = {i18n_json};</script>
<script>
(function () {{
  var bar = document.getElementById("dpb-preview-bar");
  var form = document.getElementById("dpb-decide-form");
  if (!form) return;
  var I18N = window.DPB_I18N || {{}};
  var field = form.querySelector('textarea[name="feedback"]');
  var hint = document.getElementById("dpb-feedback-hint");
  var pinBtn = document.getElementById("dpb-pin-toggle");
  var pinLabel = pinBtn ? pinBtn.querySelector(".dpb-pin-label") : null;
  var listEl = document.getElementById("dpb-anchors");
  var hidden = document.getElementById("dpb-anchors-json");
  var openBtn = document.getElementById("dpb-open-drawer");
  var closeBtn = document.getElementById("dpb-close-drawer");
  var pinCountEl = document.getElementById("dpb-pin-count");
  var pillCountEl = document.getElementById("dpb-pill-count");
  var drawerEl = document.getElementById("dpb-drawer");
  var pillReadyEl = document.getElementById("dpb-pill-ready");
  var anchors = [];
  var pinOn = false;
  var hoverEl = null;
  var floatRoot = null;
  var floatMap = {{}};  // selector -> bubble element

  function ensureFloatRoot() {{
if (floatRoot) return floatRoot;
floatRoot = document.createElement("div");
floatRoot.id = "dpb-float-root";
document.body.appendChild(floatRoot);
return floatRoot;
  }}

  function esc(s) {{
return String(s || "").replace(/[&<>"']/g, function (c) {{
  return ({{"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}})[c];
}});
  }}

  function cssPath(el) {{
if (!el || el.nodeType !== 1) return "";
if (el.id) return "#" + CSS.escape(el.id);
var parts = [];
var cur = el;
var depth = 0;
while (cur && cur.nodeType === 1 && cur !== document.documentElement && depth < 8) {{
  if (cur.id === "dpb-preview-bar" || cur.id === "dpb-preview-spacer" || cur.id === "dpb-float-root") break;
  var part = cur.tagName.toLowerCase();
  if (cur.classList && cur.classList.length) {{
    var cls = Array.prototype.slice.call(cur.classList, 0, 2)
      .filter(function (c) {{ return c && c.indexOf("dpb-") !== 0; }})
      .map(function (c) {{ return "." + CSS.escape(c); }})
      .join("");
    part += cls;
  }}
  var parent = cur.parentElement;
  if (parent) {{
    var kids = parent.children;
    var n = 0, idx = 0, i;
    for (i = 0; i < kids.length; i++) {{
      if (kids[i].tagName === cur.tagName) {{
        n++;
        if (kids[i] === cur) idx = n;
      }}
    }}
    if (n > 1) part += ":nth-of-type(" + idx + ")";
  }}
  parts.unshift(part);
  if (cur.tagName === "BODY") break;
  cur = parent;
  depth++;
}}
return parts.join(" > ");
  }}

  function labelFor(el) {{
var t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
if (t.length > 40) t = t.slice(0, 40) + "…";
if (t) return el.tagName.toLowerCase() + ' "' + t + '"';
if (el.getAttribute("aria-label")) return el.tagName.toLowerCase() + " " + el.getAttribute("aria-label");
if (el.id) return "#" + el.id;
if (el.className && typeof el.className === "string") return el.tagName.toLowerCase() + "." + el.className.trim().split(/\s+/)[0];
return el.tagName.toLowerCase();
  }}

  function syncHidden() {{
hidden.value = JSON.stringify(anchors.map(function (a) {{
  return {{ selector: a.selector, label: a.label, comment: a.comment, tag: a.tag }};
}}));
  }}

  function positionFloat(a, idx) {{
// ponytail: orphan guard — if target element left the DOM, drop the bubble
if (!a.el || !a.el.isConnected) {{ removeBubble(a.selector); return; }}
var bubble = floatMap[a.selector];
if (!bubble) return;
var rect = a.el.getBoundingClientRect();
var root = ensureFloatRoot();
var nEl = bubble.querySelector(".dpb-float-n");
if (nEl) nEl.textContent = String(idx + 1);
bubble.style.left = (window.scrollX + rect.right + 8) + "px";
var top = window.scrollY + rect.top;
// keep on screen
var maxTop = window.scrollY + window.innerHeight - 60;
bubble.style.top = Math.min(top, maxTop) + "px";
// flip to left if overflows right
if (rect.right + 260 > window.innerWidth) {{
  bubble.style.left = (window.scrollX + rect.left - bubble.offsetWidth - 8) + "px";
}}
  }}

  function ensureBubble(a, idx) {{
if (!a.el || !a.el.isConnected) {{ removeBubble(a.selector); return; }}
if (!floatMap[a.selector]) {{
  var bubble = document.createElement("div");
  bubble.className = "dpb-float-note";
  bubble.setAttribute("role", "status");
  bubble.innerHTML =
    '<span class="dpb-float-n" aria-hidden="true">' + (idx + 1) + "</span>" +
    '<span class="dpb-float-label">' + esc(a.label) + "</span>" +
    '<span class="dpb-float-comment"></span>';
  ensureFloatRoot().appendChild(bubble);
  floatMap[a.selector] = bubble;
}}
var bubble = floatMap[a.selector];
var commentEl = bubble.querySelector(".dpb-float-comment");
commentEl.textContent = a.comment || "";
bubble.style.display = a.comment ? "block" : "none";
if (a.comment) {{
  // position after layout
  requestAnimationFrame(function () {{
    positionFloat(a, idx);
    bubble.classList.add("is-visible");
  }});
}} else {{
  bubble.classList.remove("is-visible");
}}
  }}

  function removeBubble(selector) {{
var bubble = floatMap[selector];
if (bubble) {{
  bubble.remove();
  delete floatMap[selector];
}}
  }}

  function render() {{
listEl.innerHTML = "";
if (!anchors.length) {{
  listEl.classList.remove("has-items");
  syncHidden();
  updateCounts();
  return;
}}
listEl.classList.add("has-items");
anchors.forEach(function (a, idx) {{
  var row = document.createElement("div");
  row.className = "dpb-anchor";
  row.innerHTML =
    '<span class="n">' + (idx + 1) + "</span>" +
    '<div class="meta">' +
      '<button type="button" class="label" data-locate="' + idx + '" title="' + esc(I18N.locate) + '" aria-label="' + esc(I18N.locate_anchor) + ' ' + (idx + 1) + '">' + esc(a.label) + "</button>" +
      '<div class="sel" title="' + esc(a.selector) + '">' + esc(a.selector) + "</div>" +
      '<input type="text" data-i="' + idx + '" aria-label="' + esc(I18N.anchor_num_pre) + (idx + 1) + esc(I18N.anchor_num_post) + '" placeholder="' + esc(I18N.anchor_placeholder) + '" value="' + esc(a.comment) + '" />' +
    "</div>" +
    '<button type="button" class="rm" data-rm="' + idx + '" aria-label="' + esc(I18N.remove_num_pre) + (idx + 1) + '">' + esc(I18N.remove) + '</button>';
  listEl.appendChild(row);
  ensureBubble(a, idx);
}});
syncHidden();
updateCounts();
  }}

  function updateCounts() {{
var n = anchors.length;
if (pinCountEl) pinCountEl.textContent = (I18N.pin_count_pre || "") + n + (I18N.pin_count_post || "");
if (pillCountEl) {{
  pillCountEl.textContent = String(n);
  pillCountEl.classList.toggle("is-on", n > 0);
}}
setReadiness();
  }}

  // I4: ADR-0008 substantive predicate (mirror of adapter floor) + live readiness.
  // Structural only, no minimum length (ADR-0008: semantic junk is G6's job).
  function isSubstantive() {{
var value = (field && field.value || "").trim();
var anchorsComplete = !anchors.length || anchors.every(function (a) {{
  return (a && (a.selector || "").trim() && (a.comment || "").trim());
}});
return (value.length > 0 || anchors.length) && anchorsComplete;
  }}
  var lastReady = null;
  var pillOpenLabel = null;  // I13: original pill-primary label, restored on ready->not-ready flip
  function setReadiness() {{
if (!pillReadyEl) return;
var ready = isSubstantive();
pillReadyEl.classList.toggle("is-ready", ready);
if (ready === lastReady) return;  // P1.6: cache to avoid screen-reader jitter on every input
lastReady = ready;
if (ready) {{
  pillReadyEl.textContent = I18N.ready || "";
  if (openPrimary) {{
    if (pillOpenLabel === null) pillOpenLabel = openPrimary.textContent;  // I13: capture once
    openPrimary.classList.add('is-direct-confirm');
    openPrimary.removeAttribute('aria-haspopup');  // P1.1: direct confirm, no longer a dialog trigger
    // Mirror the confirm button label so user sees the action will confirm directly
    var drawerPrimary = document.querySelector('.dpb-drawer .dpb-btn-primary');
    if (drawerPrimary && drawerPrimary.textContent && openPrimary.textContent !== drawerPrimary.textContent) {{
      openPrimary.textContent = drawerPrimary.textContent;
    }}
  }}
}} else {{
  pillReadyEl.textContent = I18N.not_ready || "";
  if (openPrimary) {{
    openPrimary.classList.remove('is-direct-confirm');
    openPrimary.setAttribute('aria-haspopup', 'dialog');  // P1.1: restore dialog trigger
    // I13: restore original label so the pill no longer advertises direct confirm
    if (pillOpenLabel !== null && openPrimary.textContent !== pillOpenLabel) {{
      openPrimary.textContent = pillOpenLabel;
    }}
  }}
}}
  }}

  function clearHover() {{
if (hoverEl) {{
  hoverEl.classList.remove("dpb-pin-hover");
  hoverEl = null;
}}
  }}

  function setPin(on) {{
pinOn = !!on;
document.body.classList.toggle("dpb-pin-mode", pinOn);
if (pinBtn) {{
  pinBtn.classList.toggle("is-on", pinOn);
  pinBtn.setAttribute("aria-pressed", pinOn ? "true" : "false");
}}
if (pinLabel) pinLabel.textContent = pinOn ? (I18N.pin_on || "") : (I18N.pin_off || "");
if (!pinOn) clearHover();
  }}

  var lastFocus = null;
  function openDrawer() {{
lastFocus = document.activeElement;
// Use non-modal <dialog>.show() (NOT showModal): the drawer must NOT make the
// page inert, because pin-to-annotate requires clicking prototype elements
// behind the drawer. ::backdrop (modal only) is replaced by the .is-open::before
// scrim below. ESC + focus-restore handled manually.
// is-open is the reliable open signal (scrim/pill + CSS display fallback when
// dialog.show is missing or throws — drawer must not depend on dialog[open]).
if (drawerEl && typeof drawerEl.show === "function") {{
  try {{ if (!drawerEl.open) drawerEl.show(); }} catch (e) {{ /* fall through to is-open */ }}
}}
bar.classList.add("is-open");
setTimeout(function () {{ if (closeBtn) closeBtn.focus(); }}, 0);
  }}
  function closeDrawer() {{
bar.classList.remove("is-open");
resetAbortArmed();  // I18: clear abort arming when drawer closes (no stale armed state on reopen)
if (pinOn) setPin(false);
if (drawerEl && drawerEl.open && typeof drawerEl.close === "function") drawerEl.close();
if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
  }}

  // I2: 批注 (annotate) and the not-ready pill primary used to both just open
  // the drawer. Annotate now drops straight into element picking, so the two
  // buttons carry distinct intents (annotate elements vs. review/confirm).
  if (openBtn) openBtn.addEventListener("click", function () {{
openDrawer();
setPin(true);
  }});
  var openPrimary = document.getElementById("dpb-open-primary");
  // Shared: submit the confirm (drawer primary). Used by pill-primary direct
  // confirm (handlePillPrimary) and Ctrl+Enter (I8) to avoid divergent targets.
  function submitPrimary() {{
var targetBtn = document.querySelector(".dpb-drawer .dpb-btn-primary");
if (targetBtn) form.requestSubmit(targetBtn); else form.requestSubmit();
  }}
  function handlePillPrimary(e) {{
    if (isSubstantive()) {{
      // When ready, the pill primary directly submits the confirm (no need to open drawer)
      e.preventDefault();
      submitPrimary();
    }} else {{
      openDrawer();
    }}
  }}
  if (openPrimary) openPrimary.addEventListener("click", handlePillPrimary);
  var pillReviseBtns = bar.querySelectorAll('[data-pill-revise]');
  for (var ri = 0; ri < pillReviseBtns.length; ri++) {{
    pillReviseBtns[ri].addEventListener("click", function () {{
      openDrawer();
      setTimeout(function () {{ if (field) field.focus(); }}, 0);
    }});
  }}
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  if (pinBtn) pinBtn.addEventListener("click", function () {{ setPin(!pinOn); }});
  // P1.5: click on scrim (outside drawer) closes the drawer. Fires only when pin
  // is OFF (CSS sets scrim pointer-events:none while body.dpb-pin-mode is on, so
  // pin-on clicks reach the page for element selection, not the scrim).
  bar.addEventListener("click", function (e) {{
if (bar.classList.contains("is-open") && !pinOn && e.target === bar) closeDrawer();
  }});

  // Draft: keep current feedback/anchors in the form and close without a
  // confirm/revise decision (per debate); nothing is submitted or persisted.
  var draftBtn = document.getElementById("dpb-draft");
  if (draftBtn) draftBtn.addEventListener("click", function () {{ closeDrawer(); }});

  // I8: Ctrl/Cmd+Enter in the feedback textarea submits the confirm (primary) action
  if (field) {{
field.addEventListener("keydown", function (e) {{
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {{
    e.preventDefault();
    submitPrimary();
  }}
}});
  }}

  // I18: abort requires a second click within the confirm window (prevents accidental
  // session kill). First click arms the button for ABORT_ARM_MS; second click submits __abort__.
  // Armed state is announced to screen readers via the #dpb-abort-status alert
  // region (the visible textContent swap alone is not reliably announced).
  // 4000ms: at 2000ms a hesitant user's second click landed AFTER expiry and
  // just re-armed, so the button felt dead no matter how often it was clicked.
  var ABORT_ARM_MS = 4000;
  var abortBtn = document.getElementById("dpb-abort");
  var abortStatus = document.getElementById("dpb-abort-status");
  var abortArmed = false;
  var abortTimer = null;
  var abortLabel = "";
  // announceCancel: when true (4s timeout), write "cancelled" to the sr-only
  // status so screen readers hear the arm expire; other paths clear silently.
  function resetAbortArmed(announceCancel) {{
if (abortTimer) {{ clearTimeout(abortTimer); abortTimer = null; }}
var wasArmed = abortArmed;
if (abortBtn && abortArmed) {{
  abortArmed = false;
  abortBtn.textContent = abortLabel;
  abortBtn.classList.remove("is-armed");
}}
if (abortStatus) {{
  abortStatus.textContent = (announceCancel && wasArmed)
    ? (I18N.abort_cancelled || "")
    : "";
}}
  }}
  if (abortBtn) {{
abortLabel = abortBtn.textContent;
abortBtn.addEventListener("click", function (e) {{
  if (!abortArmed) {{
    e.preventDefault();
    abortArmed = true;
    abortBtn.textContent = I18N.terminate_confirm || "";
    abortBtn.classList.add("is-armed");
    if (abortStatus) abortStatus.textContent = I18N.terminate_confirm || "";
    abortTimer = setTimeout(function () {{ resetAbortArmed(true); }}, ABORT_ARM_MS);
  }}  // else: let the submit proceed (choice=__abort__)
}});
  }}
  // MEDIUM: clicking elsewhere in the drawer cancels abort arming (not just
  // ESC / 4s timeout); the abort button's own click is excluded via closest.
  if (drawerEl) drawerEl.addEventListener("click", function (e) {{
if (abortArmed && abortBtn && !e.target.closest("#dpb-abort")) {{
  resetAbortArmed();
}}
  }});

  // Initial readiness (may enable direct confirm on pill primary)
  setReadiness();

  // non-modal <dialog>.show() has no native focus trap / ESC. Mirror close +
  // trap Tab inside the drawer when pin is OFF; when pin is ON, Tab must reach
  // the prototype so keyboard users can move focus onto page elements.
  if (drawerEl) drawerEl.addEventListener("close", function () {{
bar.classList.remove("is-open");
resetAbortArmed();  // I18: defense-in-depth - clear arming if a future path closes the dialog directly
if (pinOn) setPin(false);
  }});
  function drawerFocusables() {{
if (!drawerEl) return [];
var sel = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
var nodes = drawerEl.querySelectorAll(sel);
return Array.prototype.filter.call(nodes, function (el) {{
  return !el.hasAttribute("disabled") && el.tabIndex !== -1 &&
    (el.offsetWidth > 0 || el.offsetHeight > 0 || el === document.activeElement);
}});
  }}
  document.addEventListener("keydown", function (e) {{
if (e.key === "Escape") {{
  if (pinOn) {{ setPin(false); return; }}
  if (bar.classList.contains("is-open")) {{ e.preventDefault(); closeDrawer(); }}
  return;
}}
if (e.key !== "Tab") return;
if (!bar.classList.contains("is-open") || pinOn) return;  // pinOn: let Tab escape to prototype
var list = drawerFocusables();
if (!list.length) return;
var first = list[0];
var last = list[list.length - 1];
var active = document.activeElement;
var outside = !drawerEl.contains(active);
if (e.shiftKey) {{
  if (outside || active === first) {{ e.preventDefault(); last.focus(); }}
}} else {{
  if (outside || active === last) {{ e.preventDefault(); first.focus(); }}
}}
  }});

  document.addEventListener("mousemove", function (e) {{
if (!pinOn) return;
var el = e.target;
if (!el || el.closest("#dpb-preview-bar") || el.closest("#dpb-preview-spacer") || el.closest("#dpb-float-root")) {{
  clearHover();
  return;
}}
if (el === document.body || el === document.documentElement) {{
  clearHover();
  return;
}}
if (hoverEl !== el) {{
  clearHover();
  hoverEl = el;
  hoverEl.classList.add("dpb-pin-hover");
}}
  }}, true);

  document.addEventListener("click", function (e) {{
if (!pinOn) return;
var raw = e.target;
if (!raw || raw.closest("#dpb-preview-bar") || raw.closest("#dpb-preview-spacer") || raw.closest("#dpb-float-root")) return;
if (raw === document.body || raw === document.documentElement) return;
e.preventDefault();
e.stopPropagation();
// anchor to the hovered element, not the inner node that received the click
var el = (hoverEl && hoverEl.contains(raw)) ? hoverEl : raw;
var selector = cssPath(el);
if (!selector) return;
// de-dupe by selector; clear stale highlight on any previous element ref
for (var i = 0; i < anchors.length; i++) {{
  if (anchors[i].selector === selector) {{
    if (anchors[i].el && anchors[i].el !== el) anchors[i].el.classList.remove("dpb-pin-target");
    anchors[i].el = el;
    el.classList.add("dpb-pin-target");
    render();
    return;
  }}
}}
el.classList.add("dpb-pin-target");
anchors.push({{
  selector: selector,
  label: labelFor(el),
  comment: "",
  tag: el.tagName.toLowerCase(),
  el: el
}});
render();
// focus newest comment input
setTimeout(function () {{
  var inputs = listEl.querySelectorAll("input[data-i]");
  if (inputs.length) inputs[inputs.length - 1].focus();
}}, 0);
  }}, true);

  listEl.addEventListener("input", function (e) {{
var t = e.target;
if (!t || !t.getAttribute) return;
if (t.getAttribute("data-i") == null) return;
var i = Number(t.getAttribute("data-i"));
anchors[i].comment = t.value;
syncHidden();
ensureBubble(anchors[i], i);
setReadiness();
  }});

  listEl.addEventListener("click", function (e) {{
var t = e.target;
if (!t || !t.getAttribute) return;
var loc = t.getAttribute("data-locate");
if (loc != null) {{
  e.preventDefault();
  var a = anchors[Number(loc)];
  if (a && a.el && a.el.isConnected) {{
    a.el.scrollIntoView({{ behavior: "smooth", block: "center" }});
    a.el.classList.remove("dpb-pin-flash");
    // force reflow so the animation can restart
    void a.el.offsetWidth;
    a.el.classList.add("dpb-pin-flash");
  }}
  return;
}}
var rm = t.getAttribute("data-rm");
if (rm == null) return;
var i = Number(rm);
var a = anchors[i];
if (a) {{
  if (a.el) a.el.classList.remove("dpb-pin-target");
  removeBubble(a.selector);
}}
anchors.splice(i, 1);
render();
setReadiness();
  }});

  // reposition floats on scroll/resize
  function repositionAll() {{
anchors.forEach(function (a, idx) {{ positionFloat(a, idx); }});
  }}
  window.addEventListener("scroll", repositionAll, true);
  window.addEventListener("resize", repositionAll);

  // ADR-0008: confirm requires substantive feedback too -
  // (non-empty feedback OR >=1 anchor) AND all anchors complete.
  // Frontend mirrors adapter _check_feedback_floor via isSubstantive().
  var reviseLabels = {{{t_revise_labels}}};
  form.addEventListener("submit", function (e) {{
syncHidden();
var submitter = e.submitter;
var choice = submitter && submitter.name === "choice" ? submitter.value : "";
if (!choice || choice === "__abort__") return;
var isRevise = !!reviseLabels[choice] || /修改|revise|change/i.test(choice);
// For revise actions (e.g. "需要修改"), allow even without substantive feedback (the point is to request changes).
// Only enforce floor for actual confirm actions.
if (isRevise || isSubstantive()) {{
  if (field) field.removeAttribute("aria-invalid");
  if (hint) hint.classList.remove("is-on");
  return;
}}
e.preventDefault();
if (field) {{ field.setAttribute("aria-invalid", "true"); field.focus(); }}
if (hint) hint.classList.add("is-on");
if (!bar.classList.contains("is-open")) openDrawer();
// I1: do NOT force pin mode on - that was an intent guess; the user may want
// overall feedback, not element selection.
  }});
  if (field) {{
field.addEventListener("input", function () {{
  if (isSubstantive()) {{
    field.removeAttribute("aria-invalid");
    if (hint) hint.classList.remove("is-on");
  }}
  setReadiness();
}});
  }}
}})();
</script>
"""



def _build_control(round_n: int, summary: str, options: list[str]) -> str:
    """Build the injected confirm control-bar HTML (ADR-0008 floor-aware).

    Shared by _collect_via_browser (runtime) and test_floor_frontend
    (playwright) so the option/button markup is not duplicated across them.
    """
    confirm_cf = {c.casefold() for c in CONFIRM_LABELS}
    revise_cf = {r.casefold() for r in REVISE_LABELS}

    def display_label(opt: str) -> str:
        """Render known confirm/revise labels in the ACTIVE locale.

        The submitted value stays the raw option (CONFIRM/REVISE union sets
        still classify it); only the visible label is localized, so options
        a caller copied from another locale's docs cannot mix languages into
        an otherwise locale-consistent control bar.
        """
        if opt in CONFIRM_LABELS or opt.casefold() in confirm_cf:
            return t("confirm")
        if opt in REVISE_LABELS or opt.casefold() in revise_cf:
            return t("revise")
        return opt

    # JS object literal of revise labels across all locales (frontend classifies
    # a revise regardless of UI language). Keys are JSON-quoted/escaped.
    revise_js = ", ".join(
        f"{json.dumps(lbl, ensure_ascii=False)}: 1" for lbl in sorted(REVISE_LABELS))
    primary_bits: list[str] = []
    secondary_bits: list[str] = []
    for opt in options:
        safe_val = html_lib.escape(opt, quote=True)
        safe_label = html_lib.escape(display_label(opt))
        primary = opt in CONFIRM_LABELS or opt.casefold() in confirm_cf
        cls = "dpb-btn dpb-btn-primary" if primary else "dpb-btn dpb-btn-secondary"
        bit = (
            f'<button type="submit" name="choice" value="{safe_val}" class="{cls}">'
            f"{safe_label}</button>"
        )
        (primary_bits if primary else secondary_bits).append(bit)
    secondary_html = "\n".join(secondary_bits)
    # secondary actions surfaced on the floating pill (so revise is not hidden in the drawer)
    # Second replace rewrites the full class attr; a third partial replace would be dead.
    pill_secondary_html = "\n".join(
        b.replace('type="submit" name="choice"', 'type="button" data-pill-revise')
         .replace('class="dpb-btn dpb-btn-secondary"', 'class="dpb-btn-pill-secondary"')
        for b in secondary_bits
    )
    summary_safe = html_lib.escape(summary)
    primary_opt = next(
        (o for o in options if o in CONFIRM_LABELS or o.casefold() in confirm_cf),
        options[0] if options else t("confirm"),
    )
    primary_val = html_lib.escape(primary_opt, quote=True)
    primary_label = html_lib.escape(display_label(primary_opt))
    # JS-side strings: inject via JSON script (not .format into JS literals).
    # Translations with quotes, braces, or "/{" must not break JS or raise KeyError.
    # HTML {t_xxx} placeholders stay on .format (html.escape-safe static chrome).
    JS_KEYS = (
        "locate",
        "locate_anchor",
        "anchor_num_pre",
        "anchor_num_post",
        "anchor_placeholder",
        "remove_num_pre",
        "remove",
        "pin_count_pre",
        "pin_count_post",
        "ready",
        "not_ready",
        "pin_on",
        "pin_off",
        "terminate_confirm",
        "abort_cancelled",  # 4s-timeout a11y broadcast (window.DPB_I18N.abort_cancelled)
    )
    # json.dumps is JS-safe for quotes/backslashes; also neutralize </script>
    # and U+2028/2029 (pre-ES2019 JS string breaks) in case translations ever
    # carry them — defense, not a current risk.
    i18n_json = (
        json.dumps({k: t(k) for k in JS_KEYS}, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return control_tpl.format(
        t_revise_labels=revise_js,
        i18n_json=i18n_json,
        summary_safe=summary_safe,
        secondary_html=secondary_html,
        pill_secondary_html=pill_secondary_html,
        primary_val=primary_val,
        primary_label=primary_label,
        t_region=html_lib.escape(t("region_label"), quote=True),
        t_round=html_lib.escape(t("round_n", n=round_n)),
        t_annotate=html_lib.escape(t("annotate")),
        t_pill_open=html_lib.escape(t("pill_open")),
        t_not_ready=html_lib.escape(t("not_ready")),
        t_drawer_aria=html_lib.escape(t("drawer_aria"), quote=True),
        t_collapse=html_lib.escape(t("collapse"), quote=True),
        t_pin_toggle=html_lib.escape(t("pin_toggle")),
        t_pin_count=html_lib.escape(t("pin_count", n=0)),
        t_anchors_head=html_lib.escape(t("anchors_head")),
        t_anchors_empty=html_lib.escape(t("anchors_empty")),
        t_field_label=html_lib.escape(t("field_label")),
        t_field_hint=html_lib.escape(t("field_hint")),
        t_field_placeholder=html_lib.escape(t("field_placeholder"), quote=True),
        t_terminate=html_lib.escape(t("terminate")),
        t_draft=html_lib.escape(t("draft")),
    )



def _format_feedback(feedback: str, anchors: list[dict[str, Any]]) -> str:
    feedback = (feedback or "").strip()
    if not anchors:
        return feedback
    lines = []
    if feedback:
        lines.append(feedback)
        lines.append("")
    lines.append(t("anchor_note_label", n=len(anchors)))
    for i, a in enumerate(anchors, 1):
        label = a.get("label") or a.get("tag") or "?"
        note = a.get("comment") or t("no_text")
        sel = a.get("selector") or ""
        lines.append(f"{i}. [{label}] {note} — {sel}")
    return "\n".join(lines)

