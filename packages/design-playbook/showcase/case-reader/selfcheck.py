#!/usr/bin/env python3
"""Fill self-check: embedded text must equal source bytes; L6.1 structural claims."""
from pathlib import Path
import hashlib, json, re, sys

root = Path(__file__).resolve().parents[2]
case_dir = root / 'showcase/case-reader'
html = (case_dir / 'index.html').read_text(encoding='utf-8')
gen = (case_dir / '_gen_docs.js').read_text(encoding='utf-8')
docs = json.loads(re.search(r'const DOCS = (\[.*\]);', gen, re.S).group(1))

failures = []
for d in docs:
    src = root / d['src']
    raw = src.read_bytes()
    text = raw.decode('utf-8')
    if text != d['text']:
        failures.append(f"{d['src']}: embedded text differs from decoded source bytes")
    if hashlib.sha256(raw).hexdigest() != d['sha']:
        failures.append(f"{d['src']}: sha mismatch")

# L6.3 error path + L6.2 search elements + noscript + no external fetch
for needle, why in [
    ('id="error-view"', 'error state missing'),
    ('id="search"', 'search input missing'),
    ('aria-current', 'aria-current missing'),
    ('<noscript>', 'noscript notice missing'),
    ('getElementById', 'doc switch logic missing'),
]:
    if needle not in html:
        failures.append(why)
if re.search(r'(fetch\(|XMLHttpRequest|new EventSource|WebSocket)', html + gen):
    failures.append('external network request API present')
if '<script src=' in html:
    failures.append('docs must be inlined (delivery copy is a single self-contained file)')
m = re.search(r'const DOCS = (\[.*?\]);\n', html, re.S)
if not m:
    failures.append('DOCS literal not inlined in index.html')
elif json.loads(m.group(1)) != docs:
    failures.append('inlined DOCS differs from _gen_docs.js')

# command docs reference real files (run from case-reader or showcase)
for name in ('run-status.md', 'run-handoff.md'):
    if not (root / 'commands' / name).exists() and not (case_dir.parent.parent / 'commands' / name).exists():
        failures.append(f'commands/{name} missing')

if failures:
    print('FAIL:'); [print(' -', f) for f in failures]; sys.exit(1)
print(f'OK: {len(docs)} embedded docs byte-identical, sha verified, structure checks pass')
