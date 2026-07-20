// Screenshot the design-playbook showcase into PNGs using SwarSight's playwright-core + cached chromium.
// Run: node scripts/screenshot-showcase.mjs
import { createRequire } from "node:module";
const require = createRequire("D:/code_space/SwarSight/frontend/package.json");
const { chromium } = require("playwright-core");
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const EXE =
  "C:/Users/amsterdam/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe";
const OUT = path.resolve("packages/design-playbook/showcase/screenshots");
mkdirSync(OUT, { recursive: true });
const VERSION = JSON.parse(
  readFileSync("packages/design-playbook/.claude-plugin/plugin.json", "utf8")
).version;

const BASE = `
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',-apple-system,sans-serif;background:#080A0D;color:#E6EDF3;padding:40px 48px;min-height:100vh}
.wrap{max-width:1040px;margin:0 auto}
.eyebrow{font-family:'JetBrains Mono',ui-monospace,monospace;color:#2DD4BF;font-size:13px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}
h1{font-size:30px;font-weight:700;margin-bottom:6px;line-height:1.2}
.sub{color:#8B949E;font-size:15px;margin-bottom:26px}
.tag{display:inline-block;font-family:ui-monospace,monospace;font-size:12px;color:#2DD4BF;border:1px solid #2DD4BF33;border-radius:6px;padding:3px 9px;margin:0 6px 6px 0;background:#2DD4BF0d}
pre{background:#0D1117;border:1px solid #26313D;border-radius:10px;padding:18px 20px;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:13.5px;line-height:1.7;color:#E6EDF3;overflow:auto;white-space:pre-wrap}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #26313D}
th{color:#8B949E;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
td{color:#E6EDF3}
code{font-family:ui-monospace,monospace;color:#2DD4BF;font-size:13px}
.card{background:#0D1117;border:1px solid #26313D;border-radius:12px;padding:20px 24px;margin-bottom:16px}
.card h3{font-size:15px;color:#E6EDF3;margin-bottom:8px}
.card p,.card li{color:#8B949E;font-size:13.5px;line-height:1.65}
ul{padding-left:18px}
.ok{color:#2DD4BF}
.amber{color:#F2C94C}
.sev-h{color:#F2C94C;font-family:ui-monospace,monospace;font-size:11px}
.sev-m{color:#8B949E;font-family:ui-monospace,monospace;font-size:11px}
.foot{margin-top:24px;color:#4a5663;font-size:12px;font-family:ui-monospace,monospace}
`;

const pages = [
  {
    name: "00-install",
    html: `<div class=wrap><div class=eyebrow>Step 0 · Install</div>
<h1>Install design-playbook</h1><div class=sub>One marketplace add, one install. No clone, no build.</div>
<pre>/plugin marketplace add &lt;owner&gt;/&lt;repo&gt;
/plugin install design-playbook@design-playbook</pre>
<div style="margin-top:18px">
<span class=tag>6 skills</span><span class=tag>3 commands</span><span class=tag>MIT</span><span class=tag>Claude Code</span><span class=tag>Codex</span>
</div>
<div class=card style="margin-top:20px"><h3>Then invoke namespaced</h3>
<p><code>/design-playbook:design-io &lt;your UI ask&gt;</code></p></div>
<div class=foot>design-playbook · Design I/O for coding agents</div></div>`,
  },
  {
    name: "01-spec",
    html: `<div class=wrap><div class=eyebrow>Step 1 · ux-spec</div>
<h1>Six-layer spec.md</h1><div class=sub>Produced before any UI — SwarSight simulation run queue.</div>
<div class=card><h3>L1 · Intent</h3><p>View all simulation runs: live state, failed retry, resource usage. Users: ops analyst. Non-goal: no scenario editing here.</p></div>
<div class=card><h3>L3 · Core flow</h3><p><code>queued→running→completed</code> · <code>running→paused→running</code> · <code>running→failed→retry→queued</code> · <code>running→failed→aborted</code></p></div>
<div class=card><h3>L5 · Edge states <span class=ok>(must not be blank)</span></h3>
<ul><li>Empty: no runs → CTA create scenario, not white screen</li>
<li>Loading: table-structure skeleton (Abyss Canvas bg)</li>
<li>Error: sim service down → cause + retry</li>
<li>Permission: viewer → retry/abort disabled + reason</li></ul></div>
<div class=card><h3>L6 · Acceptance</h3><p>Given a failed run → see cause + resource peak + can retry. Given no runs → non-blank empty state. Given viewer → cannot retry, reason shown.</p></div>
<div class=foot>spec.md · substantive L5/L6 before pretty UI ✓</div></div>`,
  },
  {
    name: "02-decision-report",
    html: `<div class=wrap><div class=eyebrow>Step 2 · ui-picker</div>
<h1>Decision report — before code</h1><div class=sub>Shell + component semantics, grounded in SwarSight DESIGN.md tokens.</div>
<pre>scene:      ops list / dashboard (simulation run queue)
density:    cockpit-dense (8/10)
template:   summary + run list + side trends + batch bar
components:
  run state     → Badge (queued/running/paused/failed/completed/aborted/timeout)
  failed/timeout→ Amber Evidence color, not red neon
  resource      → read-only mini sparkline (Tag chip)
  retry         → Button (recovery action, not a Tag)
  run detail    → Drawer (dense read-only, not Dialog)
  batch retry   → Button + confirm Dialog (interrupt)
tokens:
  bg var(--abyss-canvas) · panel var(--graphite-surface)
  accent var(--signal-cyan) (single accent)
  warning var(--amber-evidence)
  no emojis · no glow · no purple-blue gradients</pre>
<div class=foot>decision report exists before coding ✓ — risks flagged for domain/craft</div></div>`,
  },
  {
    name: "03-point-back",
    html: `<div class=wrap><div class=eyebrow>Step 3 · ui-evaluator</div>
<h1>Point-back findings + recirculate closure</h1><div class=sub>Every issue names its declaration; blocking findings close the loop.</div>
<table>
<tr><th>Issue</th><th>Source</th><th>Severity</th></tr>
<tr><td>Batch retry has no confirm step</td><td><code>domain</code></td><td><span class=sev-h>BLOCKING</span></td></tr>
<tr><td>Abort run without confirm</td><td><code>domain</code></td><td><span class=sev-h>BLOCKING</span></td></tr>
<tr><td>Resource sparkline animates width</td><td><code>craft</code></td><td><span class=sev-h>BLOCKING</span></td></tr>
<tr><td>Failed state uses red neon</td><td><code>craft</code></td><td><span class=sev-m>med</span></td></tr>
<tr><td>Viewer can click retry</td><td><code>spec L5</code></td><td><span class=sev-m>med</span></td></tr>
</table>
<div class=card style="margin-top:16px"><h3>Recirculate closure <span class=ok>→ 0 blocking</span></h3>
<p><code>domain</code>: add confirm Dialog + consequence → re-eval: confirm gates execute → <span class=ok>0 blocking</span></p>
<p><code>craft</code>: animate opacity/transform only → re-eval: no width animation → <span class=ok>0 blocking</span></p></div>
<div class=foot>verdict: PASS — 3 blocking recirculated → fixed → re-checked → 0</div></div>`,
  },
  {
    name: "04-gates",
    html: `<div class=wrap><div class=eyebrow>Result · Six gates</div>
<h1>All six gates green</h1><div class=sub>One predictable Design I/O pass on a real third-party codebase.</div>
<table>
<tr><th>Gate</th><th>Pass</th></tr>
<tr><td>L5/L6 present before pretty UI</td><td class=ok>✓</td></tr>
<tr><td>Decision report before code</td><td class=ok>✓</td></tr>
<tr><td>Point-back evaluator findings</td><td class=ok>✓</td></tr>
<tr><td>No skip of Done when</td><td class=ok>✓</td></tr>
<tr><td>Generalizes (SwarSight domain)</td><td class=ok>✓</td></tr>
<tr><td>Recirculate closure (blocking → fix → re-eval → 0)</td><td class=ok>✓</td></tr>
</table>
<div class=card style="margin-top:18px"><h3>What ran</h3><p><code>/design-playbook:design-io 在 SwarSight 加一个模拟运行队列监控页</code></p>
<p style="margin-top:8px">Skills invoked: <code>ux-spec</code> → <code>ui-picker</code> → fill → <code>craft-guard</code> → <code>ui-evaluator</code></p></div>
<div class=foot>design-playbook v${VERSION} · Design I/O on SwarSight</div></div>`,
  },
];

const browser = await chromium.launch({ executablePath: EXE });
for (const p of pages) {
  const page = await browser.newPage({ viewport: { width: 1120, height: 1 } });
  await page.setContent(`<!doctype html><html><head><meta charset=utf8><style>${BASE}</style></head><body>${p.html}</body></html>`);
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
  const h = await page.evaluate(() => document.body.scrollHeight);
  await page.setViewportSize({ width: 1120, height: h });
  await page.screenshot({ path: path.join(OUT, `${p.name}.png`), fullPage: true });
  await page.close();
  console.log("shot:", p.name);
}
await browser.close();
console.log("done ->", OUT);
