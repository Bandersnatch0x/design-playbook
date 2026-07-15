// Render the design-playbook hero banner PNG.
// Run: node scripts/screenshot-hero.mjs
import { createRequire } from "node:module";
const require = createRequire("D:/code_space/SwarSight/frontend/package.json");
const { chromium } = require("playwright-core");
import path from "node:path";

const EXE = "C:/Users/amsterdam/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe";
const OUT = path.resolve("packages/design-playbook/showcase/screenshots/hero.png");

const CSS = `
*{margin:0;padding:0;box-sizing:border-box}
body{width:1280px;height:480px;background:
  radial-gradient(900px 380px at 78% -10%, #2DD4BF22, transparent 60%),
  linear-gradient(180deg,#0B0E12 0%,#080A0D 100%);
  color:#E6EDF3;font-family:'Segoe UI',-apple-system,sans-serif;
  display:flex;flex-direction:column;justify-content:center;padding:0 72px;
  border-top:3px solid #2DD4BF;position:relative;overflow:hidden}
.eyebrow{font-family:'JetBrains Mono',ui-monospace,monospace;color:#2DD4BF;
  font-size:14px;letter-spacing:.22em;text-transform:uppercase;margin-bottom:14px}
h1{font-size:64px;font-weight:800;letter-spacing:-.02em;line-height:1}
h1 .accent{color:#2DD4BF}
.tag{color:#8B949E;font-size:19px;margin-top:14px;max-width:760px;line-height:1.45}
.flow{display:flex;align-items:center;gap:10px;margin-top:30px;flex-wrap:wrap}
.step{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:14px;
  color:#E6EDF3;background:#0D1117;border:1px solid #26313D;border-radius:8px;padding:8px 14px}
.step.last{color:#2DD4BF;border-color:#2DD4BF55;background:#2DD4BF11}
.arrow{color:#2DD4BF66;font-size:16px}
.chips{position:absolute;right:72px;bottom:40px;display:flex;gap:8px;flex-wrap:wrap;
  justify-content:flex-end;max-width:440px}
.chip{font-family:ui-monospace,monospace;font-size:12px;color:#8B949E;
  border:1px solid #26313D;border-radius:999px;padding:4px 12px;background:#0D1117}
.brand{position:absolute;left:72px;bottom:40px;font-family:'JetBrains Mono',monospace;
  color:#4a5663;font-size:13px;letter-spacing:.04em}
`;

const HTML = `<!doctype html><html><head><meta charset=utf8><style>${CSS}</style></head><body>
<div class=eyebrow>Claude Code · Codex Plugin</div>
<h1>design-<span class=accent>playbook</span></h1>
<div class=tag>Design I/O for coding agents — declarations + contracts that make UI generation constrained, reviewable, and recirculatable.</div>
<div class=flow>
<span class=step>plan</span><span class=arrow>→</span>
<span class=step>shell</span><span class=arrow>→</span>
<span class=step>fill</span><span class=arrow>→</span>
<span class=step>craft</span><span class=arrow>→</span>
<span class=step last>accept</span>
</div>
<div class=chips>
<span class=chip>ux-spec</span><span class=chip>ui-picker</span><span class=chip>craft-guard</span>
<span class=chip>native-craft</span><span class=chip>ui-evaluator</span>
</div>
<div class=brand>v0.1.0 · MIT · 6 skills / 3 commands</div>
</body></html>`;

const browser = await chromium.launch({ executablePath: EXE });
const page = await browser.newPage({ viewport: { width: 1280, height: 480 }, deviceScaleFactor: 2 });
await page.setContent(HTML);
await page.evaluate(() => new Promise(r => requestAnimationFrame(() => r())));
await page.screenshot({ path: OUT, clip: { x: 0, y: 0, width: 1280, height: 480 } });
await browser.close();
console.log("hero ->", OUT);
