# Gate 5 install smoke — v0.9.2

**Date:** 2026-08-04
**Host:** Windows 11 · Claude Code 2.1.220 · isolated `CLAUDE_CONFIG_DIR`
**Release source:** public `main` at `04f30eb`
**Public npm artifact:** `design-playbook@0.9.2`

## Procedure

1. Created an empty Claude config directory under the system temp directory.
2. Added the public GitHub marketplace over explicit HTTPS; no `--plugin-dir` dev load.
3. Installed `design-playbook@design-playbook` at user scope inside the isolated config.
4. Checked installed inventory, ran `claude plugin validate --strict`, and called `initialize` + `tools/list` on both installed MCP servers through their shipped process-boundary tests.
5. Installed public npm package `design-playbook@0.9.2` into a clean consumer directory and checked its shipped inventory.

## Results

| Check | Result |
| --- | --- |
| isolated config starts with no marketplaces | PASS |
| public HTTPS marketplace add | PASS |
| public marketplace HEAD matches `origin/main` | PASS — `04f30eb` |
| plugin install | PASS |
| installed version / enabled | **0.9.2 / true** |
| on-disk model skills | **8** |
| on-disk slash commands | **3** |
| registered MCP servers | **2** — preview + evidence |
| installed plugin strict validation | PASS |
| Preview MCP initialize + `tools/list` | PASS — `preview_prototype` |
| Evidence MCP initialize + `tools/list` | PASS — `execute_capture_plan` |
| public npm install | PASS — **0.9.2**, 8 skills, 3 commands, 2 MCP servers |
| npm registry shasum | `c4150e9d2e97db774f8a52445c444048b77e7a2e` |

Claude Code 2.1.220 reports the eight model skills and three slash commands together as 11 skill-like entries under `plugin details`; on-disk counts preserve the product's 8 + 3 distinction.

## Portability finding

`claude plugin marketplace add Bandersnatch0x/design-playbook` selected `git@ssh.github.com` on this host and failed without an SSH key. No Git URL rewrite was configured, GitHub CLI was set to HTTPS, and direct HTTPS Git access succeeded. The equivalent public command below passed:

```text
claude plugin marketplace add https://github.com/Bandersnatch0x/design-playbook.git
```

This does not invalidate the installed artifact or public-main smoke, but the documented `owner/repo` shorthand is not credential-independent under Claude Code 2.1.220. v0.10 release prep must change the public install path to explicit HTTPS.

## Honest limits

- Interactive `/help` inspection is not automatable from this isolated CLI run. `plugin details`, exact on-disk counts, strict validation, and live MCP handshakes cover the component inventory.
- The initial shorthand attempt failed before installation; all reported installed-state checks use the successful public HTTPS marketplace source.

## Verdict

**v0.9.2 public release-artifact install smoke PASS.** Public `main` and npm both resolve version 0.9.2 with the expected installable surface. Install-command portability finding remains a required v0.10 documentation fix.
