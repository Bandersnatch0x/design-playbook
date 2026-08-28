#!/usr/bin/env node
'use strict'
/**
 * design-playbook CLI shim (ADR-0042).
 *
 * Locates python3/python and delegates to
 * packages/design-playbook/scripts/generate_adapter.py with passthrough args.
 *
 *   npx design-playbook --list
 *   npx design-playbook init <agent>
 *   npx design-playbook <agent> --dry-run
 */
const { execFileSync } = require('node:child_process')
const path = require('node:path')

const SCRIPT = path.join(__dirname, '..', 'scripts', 'generate_adapter.py')

function findPython() {
  for (const bin of ['python3', 'python']) {
    try {
      const out = execFileSync(bin, ['--version'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
      if (/python\s+3\./i.test(out)) return bin
    } catch {}
  }
  return null
}

const python = findPython()
if (!python) {
  process.stderr.write(
    'error: design-playbook requires Python 3 (python3 or python).\n' +
    'Install Python 3 from https://python.org and re-run.\n'
  )
  process.exit(1)
}

// Strip leading "init" if invoked as `design-playbook init <agent>` so both
// forms are equivalent:  `design-playbook init codex` == `design-playbook codex`
const rawArgs = process.argv.slice(2)
const args = rawArgs[0] === 'init' ? rawArgs.slice(1) : rawArgs

try {
  execFileSync(python, [SCRIPT, ...args], { stdio: 'inherit' })
} catch (err) {
  process.exit(err.status ?? 1)
}
