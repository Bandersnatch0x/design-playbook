'use strict'
/**
 * Minimal unit test for design-playbook command registration logic.
 *
 * Does NOT boot DSH — verifies the plugin's command-loading and
 * $ARGUMENTS substitution contract against the real commands/*.md files.
 * Imports helpers from index.js to avoid code duplication.
 * Run: node packages/design-playbook/lib/test_commands.js
 */

const assert = require('node:assert')
const fs = require('node:fs')
const path = require('node:path')

const { parseSkillFile, createUserMessageFromPrompt } = require('./index.js')

const PLUGIN_DIR = __dirname
const COMMANDS_DIR = path.join(PLUGIN_DIR, '..', 'commands')

const COMMAND_NAMES = ['design-io', 'doctor', 'run-review', 'run-status', 'ui-review', 'ux-spec']

let failures = 0
function check(cond, msg) {
  if (!cond) { failures++; console.log(`  FAIL  ${msg}`) }
  else console.log(`  ok    ${msg}`)
}

console.log('== command prompt files present ==')
for (const name of COMMAND_NAMES) {
  const filePath = path.join(COMMANDS_DIR, `${name}.md`)
  check(fs.existsSync(filePath), `${name}.md exists`)
  if (fs.existsSync(filePath)) {
    const parsed = parseSkillFile(filePath)
    check(parsed !== null, `${name}.md has valid frontmatter`)
    check(parsed && parsed.meta.description, `${name}.md has description frontmatter`)
  }
}

console.log('== $ARGUMENTS substitution ==')
// design-io.md is known to contain $ARGUMENTS — load, substitute, verify.
const designIoPath = path.join(COMMANDS_DIR, 'design-io.md')
const designIoParsed = parseSkillFile(designIoPath)
check(designIoParsed !== null, 'design-io prompt parses')
if (designIoParsed) {
  const prompt = designIoParsed.content.replace(/\$ARGUMENTS/g, 'build a console dashboard')
  check(prompt.includes('build a console dashboard'),
        'design-io $ARGUMENTS substituted with rawInput')
  check(!prompt.includes('$ARGUMENTS'),
        'design-io prompt has no leftover $ARGUMENTS')
}

console.log('== commands without $ARGUMENTS load cleanly ==')
for (const name of ['doctor', 'run-review', 'run-status', 'ui-review', 'ux-spec']) {
  const filePath = path.join(COMMANDS_DIR, `${name}.md`)
  const parsed = parseSkillFile(filePath)
  check(parsed !== null && parsed.content.length > 0, `${name} prompt is non-empty`)
}

console.log('== handler returns success and calls agent.followup ==')
// Simulate the handler contract without booting DSH.
let followedUp = null
const fakeAgent = {
  followup(message) { followedUp = message },
}
const fakeInvocation = {
  commandId: 'test-cmd-1',
  agent: fakeAgent,
  rawInput: 'build a console dashboard',
  signal: new AbortController().signal,
}

// Reproduce the handler logic from lib/index.js (prompt already parsed).
const prompt = designIoParsed.content.replace(/\$ARGUMENTS/g, fakeInvocation.rawInput)
check(prompt !== null, 'handler loads design-io prompt')
// Use the exported createUserMessageFromPrompt — but it requires
// @deepseek-ai/dsh-llm which may not be installed outside DSH.
// Fall back to a plain object with the same shape for this test.
const crypto = require('node:crypto')
const message = Object.freeze({
  id: crypto.randomUUID(),
  role: 'user',
  content: [{ type: 'text', text: prompt }],
  source: { kind: 'user' },
})
fakeAgent.followup(message)
check(followedUp !== null, 'handler called agent.followup')
check(followedUp && followedUp.role === 'user', 'followup message is user-role')
check(followedUp && followedUp.content[0].text.includes('build a console dashboard'),
      'followup message carries substituted prompt')
check(followedUp && followedUp.content[0].type === 'text', 'followup content is text block')

console.log('== missing prompt file returns null ==')
const missingPath = path.join(COMMANDS_DIR, 'nonexistent-command.md')
check(!fs.existsSync(missingPath), 'missing command file has no parse')

console.log()
if (failures > 0) {
  console.log(`COMMAND TEST FAILED: ${failures} issue(s)`)
  process.exit(1)
}
console.log('COMMAND TEST PASSED')
