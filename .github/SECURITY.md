# Security Policy

## Supported versions

Only the latest release line published to npm (`design-playbook` / `dsh-design-playbook`, dist-tag `latest`) receives security fixes. `main` is the stable channel; tagged `v*` releases are the installable record.

## Reporting a vulnerability

Report privately via [GitHub Security Advisories](https://github.com/Bandersnatch0x/design-playbook/security/advisories/new). Include the affected surface (plugin skills, preview MCP, evidence MCP, run console, adapter generator), a reproduction, and the version.

Please avoid public issues for undisclosed vulnerabilities. You should receive an initial response within 7 days.

## Scope notes

The preview and evidence MCP runtimes execute locally and write only under their run root; reports about escaping that boundary (path traversal, forged confirm records, cross-run reads) are especially welcome.
