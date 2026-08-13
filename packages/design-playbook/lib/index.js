'use strict'
/**
 * design-playbook dsh plugin
 *
 * Registers two contributions on the DSH context:
 *
 * 1. A skill provider (ctx.skills) whose candidates are this package's
 *    `skills/` directory. The plugin locates the directory via `__dirname`,
 *    so no `!!js` expression and no cwd-dependent resolution is involved.
 *
 * 2. Six slash commands (ctx.commands) — `design-io`, `doctor`,
 *    `run-review`, `run-status`, `ui-review`, `ux-spec` — that load the
 *    matching `commands/<name>.md` prompt, substitute `$ARGUMENTS` with the
 *    raw trailing input, and inject it as a user-role follow-up turn via
 *    `agent.followup()`.
 *
 * The Cordis `!!js` evaluation scope provides no `require` (only Node globals
 * plus ctx-provided values like dshHomePath/loader), so pointing a
 * skill-filesystem customSkillDirs row at package resources via
 * `require.resolve` does not work. The plugin route is the supported way for
 * a package to contribute its own skills and commands.
 *
 * Requires `ctx.skills` (the skill registry from @deepseek-ai/dsh-skill),
 * `ctx.commands` (from @deepseek-ai/dsh-commands), and `@deepseek-ai/dsh-llm`
 * (a core DSH dependency, always present in a booted profile).
 */

const fs = require('node:fs')
const path = require('node:path')

const SKILLS_DIR = path.join(__dirname, '..', 'skills')
const COMMANDS_DIR = path.join(__dirname, '..', 'commands')

/** Parse a minimal frontmatter block: `---\nkey: value\n...\n---\nbody`. */
function parseSkillFile(filePath) {
  const text = fs.readFileSync(filePath, 'utf8')
  const m = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/.exec(text)
  if (!m) return null
  const front = {}
  for (const line of m[1].split(/\r?\n/)) {
    const kv = /^([a-zA-Z0-9-]+):\s*(.*)$/.exec(line)
    if (kv) front[kv[1]] = kv[2]
  }
  return { meta: front, content: m[2].trim() }
}

/**
 * Build a user-role message carrying one text block.
 *
 * @deepseek-ai/dsh-llm is a core DSH dependency, but it lives in the DSH
 * installation's node_modules, not in this package's node_modules.
 * require.resolve from this package may fail depending on hoisting; the
 * fallback plain object has the same shape DSH's inbox reads
 * ({ id, role, content, source }) and is safe in all runtimes.
 * @param {string} text - the prepared prompt body.
 * @returns {object} a user-role message.
 */
function createUserMessageFromPrompt(text) {
  try {
    const { createUserMessage } = require('@deepseek-ai/dsh-llm')
    return createUserMessage({
      content: [{ type: 'text', text }],
      source: { kind: 'user' },
    })
  } catch {
    const crypto = require('node:crypto')
    return Object.freeze({
      id: crypto.randomUUID(),
      role: 'user',
      content: [{ type: 'text', text }],
      source: { kind: 'user' },
    })
  }
}

exports.name = 'design-playbook'
exports.inject = ['skills', 'commands']

// Exported for test_commands.js to avoid duplicating the helpers.
exports.parseSkillFile = parseSkillFile
exports.createUserMessageFromPrompt = createUserMessageFromPrompt

/**
 * The six slash commands this plugin registers. Each maps to a
 * `commands/<name>.md` prompt file; the file's frontmatter `description`
 * becomes the command's discovery metadata, and the body (with `$ARGUMENTS`
 * substituted) is injected as a user follow-up turn.
 */
const COMMAND_NAMES = [
  'design-io',
  'doctor',
  'run-review',
  'run-status',
  'ui-review',
  'ux-spec',
]

exports.apply = function (ctx) {
  // ---- skills provider (P1) ----
  if (fs.existsSync(SKILLS_DIR)) {
    ctx.skills.registerProvider(() => {
      const candidates = fs
        .readdirSync(SKILLS_DIR, { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => {
          const skillPath = path.join(SKILLS_DIR, e.name, 'SKILL.md')
          if (!fs.existsSync(skillPath)) return null
          const parsed = parseSkillFile(skillPath)
          if (!parsed) return null
          const meta = parsed.meta
          const name = meta.name
          const description = meta.description
          if (!name || !description) return null
          return {
            name,
            description,
            ...(meta.whenToUse ? { whenToUse: meta.whenToUse } : {}),
            rank: 600, // bundled rank (matches skill-filesystem's bundled rank)
            invocation: { modelInvocable: true, userInvocable: true },
            source: 'bundled',
            provider: 'design-playbook',
            resourceBase: { kind: 'directory', path: path.join(SKILLS_DIR, e.name) },
            locator: skillPath,
            path: skillPath,
          }
        })
        .filter(Boolean)

      return {
        name: 'design-playbook',
        list: async () => candidates,
        get: async (candidate) => {
          const parsed = parseSkillFile(candidate.locator)
          if (!parsed) return undefined
          return { ...candidate, content: parsed.content }
        },
      }
    })
  }

  // ---- commands (P2) ----
  // Each command loads its prompt from commands/<name>.md, substitutes
  // $ARGUMENTS, and injects the result as a user-role follow-up turn. The
  // handler returns a CommandResult immediately — the actual model work
  // happens in the turn opened by agent.followup().
  if (ctx.commands && fs.existsSync(COMMANDS_DIR)) {
    for (const name of COMMAND_NAMES) {
      const filePath = path.join(COMMANDS_DIR, `${name}.md`)
      if (!fs.existsSync(filePath)) continue
      const parsed = parseSkillFile(filePath)
      if (!parsed || !parsed.meta.description) continue

      // Capture the parsed body once — the handler substitutes $ARGUMENTS
      // on the already-parsed content instead of re-reading the file.
      const promptBody = parsed.content
      ctx.commands.register({
        name,
        description: parsed.meta.description,
        handler: (invocation) => {
          const prompt = promptBody.replace(/\$ARGUMENTS/g, invocation.rawInput)
          const message = createUserMessageFromPrompt(prompt)
          // followup() queues an ordinary turn and wakes the driver — a
          // slash command is an explicit user action, so followup is the
          // right boundary (not inject(), which seeds context without
          // waking).
          invocation.agent.followup(message)
          return { kind: 'success' }
        },
      })
    }
  }
}
