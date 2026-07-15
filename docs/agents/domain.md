# Domain Docs

## Before exploring, read

- `CONTEXT.md`
- `docs/adr/` relevant to the task

Missing files → proceed silently; create via grill/domain-modeling when needed.

## Layout

```
/
├── CONTEXT.md
├── docs/adr/
├── docs/agents/
├── .scratch/
└── packages/design-playbook/    ← product (plugin root)
    ├── .claude-plugin/plugin.json
    ├── skills/
    ├── commands/
    ├── codex/AGENTS.md
    ├── examples/
    ├── LICENSE · NOTICE
    └── README.md
```

## Vocabulary

Use `CONTEXT.md` terms. Flag ADR conflicts explicitly.
