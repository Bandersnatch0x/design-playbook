# dsh-design-playbook

Thin DSH (DeepSeek Harness) bundle that bridges **design-playbook**'s `preview` and `evidence` MCP servers into a DSH profile.

## What this is

A separate, thin npm package (`dsh-design-playbook`) that declares a DSH bundle patch. When installed into a profile via `dsh plugin add`, it appends two `@deepseek-ai/dsh-mcp-client` rows to the profile's patch layers, each launching one of design-playbook's Python stdio MCP servers:

- `mcp__design-playbook-preview__preview_prototype`
- `mcp__design-playbook-evidence__execute_capture_plan`

The skills provider (P1) lives in the main [`design-playbook`](../design-playbook) package and is unaffected.

## How resolution works

The Cordis `!!js` evaluation scope provides no global `require`, but:

- DSH runs on Node ≥ 22.19, where `process.getBuiltinModule('node:module')` is available.
- The DSH Loader exposes the profile directory as `baseUrl`.

So each MCP row resolves the server path via:

```js
process.getBuiltinModule('node:module')
  .createRequire(baseUrl)
  .resolve('design-playbook/mcp/preview/server.py')
```

`baseUrl` points at the profile root; `createRequire(baseUrl)` resolves from the profile's `node_modules`, where `design-playbook` is installed as a dependency of this bundle. No hardcoded paths, no cwd dependence, no profile-name dependence.

## Install

```sh
dsh plugin --profile <name> add dsh-design-playbook
```

This installs both `dsh-design-playbook` and its dependency `design-playbook` into the profile. Reconcile activates the bundle layer automatically.

## Verify

```sh
dsh --profile <name> --dump-config   # see the two mcp rows
```

Both MCP tools should appear in the tool catalog:

```
mcp__design-playbook-preview__preview_prototype
mcp__design-playbook-evidence__execute_capture_plan
```

## Layout

```
packages/dsh-design-playbook/
├── package.json          # npm name: dsh-design-playbook; depends on design-playbook
├── cordis.patch.yml      # two dsh-mcp-client stdio rows
└── README.md             # this file
```

## Related

- [design-playbook](../design-playbook) — main package (skills + MCP server implementations)
- [Issue #19](https://github.com/Bandersnatch0x/design-playbook/issues/19) — P2 MCP bridge ticket
