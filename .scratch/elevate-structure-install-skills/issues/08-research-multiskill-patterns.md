# 08 — Multi-skill plugin workflow patterns

**Type:** research  
**Status:** resolved  
**Blocked by:** None

## Question

What do high-quality **multi-skill UI/agent plugins** do for workflow structure that we should learn from (not copy content)?

## Answer

Patterns: (1) flagship skill + specialized leaves; (2) model-invoked descriptions for auto-trigger, user-only when context cost must drop; (3) progressive disclosure of bulk refs/data; (4) commands as explicit pipeline entry, skills as reusable contracts; (5) completion criteria beat essay skills. Anti: wrong layout, monorepo maintainer noise in public pack, unnamespaced docs. design-playbook’s 5-skill Design I/O fits the orchestrator+leaves shape without becoming a style DB. Full notes: [research/08-multiskill-patterns.md](../research/08-multiskill-patterns.md).
