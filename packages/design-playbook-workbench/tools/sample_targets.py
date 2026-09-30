#!/usr/bin/env python3
"""Sample project targets for the two-target Agent journey (A11 support).

This is an operator/acceptance tool, not part of the shipped package.

R11/R15 require the real Agent handoff journey to run against two local
targets: a static HTML/CSS/JS project and a React/TypeScript project. This
tool writes both as plain source trees so a maintainer can register them in
the workbench and hand a real request to a real host.

Honesty note: this only writes source scaffolding. It installs nothing, runs
no build, and proves no journey. A11 stays ``blocked`` until a real Agent host
claims a request against one of these targets and returns a proposal, and
A12 stays ``blocked`` until a real owner produces evidence for that run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STATIC_FILES: dict[str, str] = {
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Static target</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main class="shell">
      <h1 class="title">Static target</h1>
      <p class="lede" id="lede">Handoff target for the static stack.</p>
      <button class="action" id="action" type="button">Count</button>
      <output class="count" id="count">0</output>
    </main>
    <script type="module" src="app.js"></script>
  </body>
</html>
""",
    "styles.css": """:root {
  color-scheme: light dark;
  --ink: #14181f;
  --surface: #f6f7f9;
  --accent: #1f4fd8;
}

.shell {
  display: grid;
  gap: 0.75rem;
  min-height: 100vh;
  place-content: center;
  background: var(--surface);
  color: var(--ink);
  font-family: system-ui, sans-serif;
}

.title {
  margin: 0;
  font-size: 1.6rem;
}

.action {
  padding: 0.5rem 1rem;
  border: 1px solid var(--accent);
  border-radius: 0.5rem;
  background: var(--accent);
  color: #fff;
  font: inherit;
}
""",
    "app.js": """const button = document.getElementById("action");
const output = document.getElementById("count");
let count = 0;

button?.addEventListener("click", () => {
  count += 1;
  if (output) output.textContent = String(count);
});
""",
    "README.md": """# Static target

A small static HTML/CSS/JS project used as the A11 handoff target.

No build step. Serve the folder with any static server the host already has.
""",
}

REACT_FILES: dict[str, str] = {
    "package.json": """{
  "name": "react-target",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "node --test"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "typescript": "^5.6.3",
    "vite": "^5.4.11"
  }
}
""",
    "tsconfig.json": """{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
""",
    "vite.config.ts": """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist" },
});
""",
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>React target</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    "src/main.tsx": """import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const host = document.getElementById("root");
if (host) {
  createRoot(host).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
""",
    "src/App.tsx": """import { useState } from "react";

export function App() {
  const [count, setCount] = useState(0);
  return (
    <main className="shell">
      <h1>React target</h1>
      <p>Handoff target for the React/TypeScript stack.</p>
      <button type="button" onClick={() => setCount((value) => value + 1)}>
        Count
      </button>
      <output>{count}</output>
    </main>
  );
}
""",
    "src/App.test.tsx": """// The "test" entry resolves via `node --test`; keep a runnable placeholder
// free of assertions so the wired entry never claims a passing suite.
export const testEntryWired = true;
""",
    "README.md": """# React target

A minimal React/TypeScript project used as the A11 handoff target.

Entries: `npm run dev`, `npm run build`, `npm run preview`, `npm test`.
Dependencies are **not** installed by the generator; installing and executing
them requires explicit authorization (R11).
""",
}


def write_tree(root: Path, files: dict[str, str]) -> list[str]:
    """Write ``files`` under ``root``; return the relative paths written."""
    written: list[str] = []
    for relative, content in sorted(files.items()):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(relative)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sample_targets.py",
        description="Write the two A11 handoff targets (static and React).",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Absolute parent folder for the two targets (R02 refuses relative).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Standalone package (dependencies = []): carry the piped-UTF-8 rule inline
    # rather than importing the plugin seam (T-105).
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    dest = Path(args.dest).expanduser()
    if not dest.is_absolute():
        print("--dest must be an absolute path (project targets never relative)", file=sys.stderr)
        return 2
    dest = dest.resolve()

    targets = {
        "static-target": STATIC_FILES,
        "react-target": REACT_FILES,
    }
    existing = [
        str(path)
        for name, files in targets.items()
        for path in (dest / name / relative for relative in files)
        if path.exists()
    ]
    if existing and not args.force:
        print(
            "refusing to overwrite existing files (use --force): "
            + ", ".join(sorted(existing)[:5]),
            file=sys.stderr,
        )
        return 3

    manifest: dict[str, object] = {
        "kind": "workbench-a11-sample-targets",
        "dest": str(dest),
        "targets": {},
        "note": (
            "Source scaffolding only. No install, no build, no journey. "
            "A11/A12 remain blocked until a real Agent host and a real owner "
            "run the handoff against these targets."
        ),
    }
    for name, files in targets.items():
        written = write_tree(dest / name, files)
        manifest["targets"][name] = {
            "path": str(dest / name),
            "files": written,
            "stack": "static HTML/CSS/JS" if name.startswith("static") else "React/TypeScript",
        }

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry
    raise SystemExit(main())
