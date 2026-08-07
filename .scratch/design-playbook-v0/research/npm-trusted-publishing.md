# npm Trusted Publishing / GitHub Actions release research

**Date:** 2026-08-07  
**Scope:** `design-playbook` 从 GitHub Actions 使用 npm Trusted Publishing (OIDC) 自动发布，并在 npm 成功后创建 GitHub Release。  
**Evidence rule:** 规范事实只引用 npm / GitHub 第一方文档；`D:/code_space/pi-switch` 只作为本地实现参考，不作为规范来源。

## Executive conclusion

`design-playbook` 可以移除 npm 长期写 token，使用单独的 `.github/workflows/release.yml` 在 `v*` tag push 后发布。发布 job 应运行在 GitHub-hosted runner，显式提供 `id-token: write`，使用 Node >= 22.14.0 与 npm >= 11.5.1，并在 npmjs.com 将 `Bandersnatch0x/design-playbook`、`release.yml`、GitHub environment `npm` 绑定为该包唯一的 trusted publisher。

推荐顺序是：tag/版本/门禁校验 -> `npm publish` -> 验证 registry -> 创建 GitHub Release。GitHub Release 不应先于 npm 公开；否则 npm 失败时会留下宣称已发布但 registry 不可安装的公开 Release。

## First-party sources

- npm: [Trusted publishing for npm packages](https://docs.npmjs.com/trusted-publishers/)
- npm: [Generating provenance statements](https://docs.npmjs.com/generating-provenance-statements/)
- npm CLI: [`npm publish`](https://docs.npmjs.com/cli/v11/commands/npm-publish)
- GitHub: [OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- GitHub: [Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- GitHub: [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- GitHub: [Managing environments for deployment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- GitHub: [Creating branch or tag rulesets](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules)
- GitHub: [Managing releases in a repository](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

## Official requirements and behavior

### Runtime and runner

1. npm Trusted Publishing requires **npm CLI 11.5.1 or later** and **Node.js 22.14.0 or later**. Selecting only a Node major is not proof that the bundled npm meets the npm minimum; the workflow should install or verify an eligible npm version. [npm trusted publishers](https://docs.npmjs.com/trusted-publishers/)
2. GitHub support is limited to **GitHub-hosted runners**. Self-hosted runners are not currently supported. [npm trusted publishers: supported CI/CD providers](https://docs.npmjs.com/trusted-publishers/#supported-cicd-providers)
3. The publish job needs `id-token: write`; without it, GitHub cannot mint the OIDC JWT. This permission only enables requesting the token and does not grant other resource writes. `contents: read` is needed when checking out the repository. [GitHub OIDC permissions](https://docs.github.com/en/actions/reference/security/oidc#workflow-permissions-for-the-requesting-the-oidc-token)

### npmjs.com trusted publisher configuration

For GitHub Actions, npm requires these fields: [npm trusted publishers: GitHub Actions](https://docs.npmjs.com/trusted-publishers/#for-github-actions)

| Field | Official rule | Proposed project value |
| --- | --- | --- |
| Organization or user | Required | `Bandersnatch0x` |
| Repository | Required | `design-playbook` |
| Workflow filename | Required; filename only, include `.yml`/`.yaml`, file must be under `.github/workflows/` | `release.yml` |
| Environment name | Optional; binds deployment protection when used | `npm` |
| Allowed actions | Required; select `npm publish`, `npm stage publish`, or both | `npm publish` |

- npm treats configuration fields as exact/case-sensitive and does not validate the connection when it is saved; mistakes surface only on publish. The package's `repository.url` must exactly match the GitHub repository. [npm trusted publishers: troubleshooting](https://docs.npmjs.com/trusted-publishers/#troubleshooting)
- Each package can have only one trusted publisher connection at a time. [npm trusted publishers: managing configurations](https://docs.npmjs.com/trusted-publishers/#managing-trusted-publisher-configurations)
- If `Environment name` is configured on npm, the publish job must use the same environment identity. A GitHub job referencing an environment must pass that environment's protection rules before it runs or can access environment secrets. [GitHub environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
- `npm stage publish` is a valid higher-security alternative, but it requires later interactive approval with 2FA. It changes the requested fully automatic release behavior, so direct `npm publish` is the current project choice. [npm trusted publishers: limitations / maximum security](https://docs.npmjs.com/trusted-publishers/#limitations-and-future-improvements)

### Authentication and provenance

- `npm publish` needs **no `NPM_TOKEN` or `NODE_AUTH_TOKEN`** when Trusted Publishing is configured. npm CLI detects the OIDC environment and uses it before falling back to traditional credentials. [npm trusted publishers: how it works](https://docs.npmjs.com/trusted-publishers/#how-trusted-publishing-works)
- Trusted Publishing applies only to `npm publish` / `npm stage publish`; commands such as `npm install`, `npm view`, `npm access`, and `npm whoami` do not gain OIDC authentication. Private dependency installation still needs a read-only token. This package has no private dependency requirement, so the release workflow needs no npm token. [npm trusted publishers: limitations](https://docs.npmjs.com/trusted-publishers/#limitations-and-future-improvements)
- For a public package from a public GitHub repository, npm automatically emits provenance when publishing through Trusted Publishing. `--provenance` is unnecessary. [npm trusted publishers: automatic provenance](https://docs.npmjs.com/trusted-publishers/#automatic-provenance-generation)
- npm recommends first proving Trusted Publishing works, then restricting token publishing and revoking obsolete automation tokens. [npm trusted publishers: migration tip](https://docs.npmjs.com/trusted-publishers/#migration-tip)

### Trigger and immutable version behavior

- GitHub supports tag filters on the `push` event; npm's official example uses `on.push.tags: ['v*']`. [GitHub workflow syntax: tag filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushbranchestagsbranches-ignoretags-ignore), [npm GitHub Actions example](https://docs.npmjs.com/trusted-publishers/#github-actions-configuration)
- GitHub also supports `release: types: [published]`, where the ref is the release tag. This is available but is not the recommended project trigger because the public GitHub Release would exist before npm publication succeeds. [GitHub release event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#release)
- npm rejects a publish when the package name/version already exists. Once published, the same name/version cannot be reused, even after unpublish. [npm publish](https://docs.npmjs.com/cli/v11/commands/npm-publish)

## Project recommendations (not npm/GitHub requirements)

### Workflow boundary

Use a dedicated `.github/workflows/release.yml`, not the existing broad CI workflow. This narrows the exact workflow trusted by npm and keeps `id-token: write` away from pull-request CI. Keep permissions at job scope:

```yaml
permissions:
  contents: read
  id-token: write
```

Only the later GitHub Release creation job/step should receive `contents: write`; all unspecified `GITHUB_TOKEN` permissions should remain `none` or read-only. GitHub supports job-level permission narrowing. [GitHub workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)

For the first version, let `release.yml` execute `npm publish` directly rather than hiding it behind a reusable workflow. npm binds an exact workflow filename; avoiding indirection keeps the identity and troubleshooting surface explicit.

### Release invariant and gates

Before the irreversible step, enforce all of these in one job:

1. Ref is a tag matching strict stable semver `vX.Y.Z` (the GitHub `v*` glob is only a trigger, not validation).
2. Tag version equals `packages/design-playbook/package.json` version.
3. Tag/checkout commit is the release commit; the existing five-site version consistency and release note checks pass.
4. Run the existing release gate and affected tests, then `npm pack --dry-run` from `packages/design-playbook`.
5. Verify Node and npm versions explicitly before publish; use a GitHub-hosted `ubuntu-latest` runner and disable package-manager caching for the release job, matching npm's official example.
6. Use release concurrency keyed by the tag and **do not cancel an in-progress release**, because cancellation can occur after npm has accepted the immutable version.

Protect `refs/tags/v*` with a GitHub ruleset and restrict the `npm` environment to release tags. Add a required reviewer / prevent self-review if the repository plan and desired automation level allow it. GitHub documents rulesets for controlling tag interactions and environment approval/branch-tag restrictions. [GitHub tag rulesets](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/configuring-tag-protection-rules), [GitHub environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)

### Publish, Release, and recovery order

Recommended state transition:

```text
tag + gates valid
  -> npm version absent
  -> npm publish (irreversible)
  -> registry version/provenance visible
  -> GitHub Release created from docs/releases/vX.Y.Z.md
```

- Do not create the public GitHub Release before `npm publish` succeeds.
- A normal rerun must not blindly call `npm publish` for an existing version. Check `npm view design-playbook@X.Y.Z version` before publishing.
- Treat an already-existing version on a first attempt as a collision and fail visibly; do not silently report success.
- Provide an explicit manual recovery path for the partial state "npm exists, GitHub Release missing". It should revalidate tag/version/repository, skip npm publication, and only create the missing Release.
- If npm publication fails before acceptance, fix the cause and rerun the same tag. If npm accepted the version but later verification/Release creation failed, recover forward; never move the tag or try to reuse the version.

## `pi-switch` implementation comparison

Local reference inspected read-only at `D:/code_space/pi-switch`.

### Reusable patterns

- Tag push plus an explicit manual recovery entry point: `.github/workflows/ci.yml:3-14`.
- Test job must pass before publish: `.github/workflows/ci.yml:53-58` (`needs: test`).
- Job-scoped `contents: read` / `id-token: write`: `.github/workflows/ci.yml:59-62`.
- Tag version must equal `package.json` version; manual dispatch additionally verifies the matching tag points at `HEAD`: `.github/workflows/ci.yml:86-114`.
- Preflight detection of an existing registry version: `.github/workflows/ci.yml:116-128`.
- Release gate checks clean tree, semver/package metadata, tests, pack contents, and tag identity: `scripts/release.mjs:54-172`.
- Package metadata has an exact GitHub `repository.url` and public access declaration: `package.json:8-10`, `package.json:66-68`.
- Release-tag ruleset blocks deletion and retargeting for `refs/tags/v*`: `.github/ruleset-tags.json:12-26`; the documented release flow is `.github/branch-protection.md:37-55`.

### Do not copy as-is

- It uses `actions/setup-node` with `node-version: "22"` but does not install or verify npm >= 11.5.1: `.github/workflows/ci.yml:74-78`. Node >= 22.14.0 and npm >= 11.5.1 are separate official requirements.
- It still passes `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` to `npm publish`: `.github/workflows/ci.yml:130-134`, and its README tells maintainers to create an npm Automation token: `README.md:515-520`. Because npm CLI falls back to token auth, this does not prove Trusted Publishing is configured and preserves the long-lived credential risk OIDC is intended to remove.
- `--provenance` at `.github/workflows/ci.yml:132` is unnecessary under Trusted Publishing. Automatic provenance is already the official behavior for a public GitHub repository/public package.
- Publish lives in the general `ci.yml`. Configuring npm to trust that large workflow creates a broader change surface than a dedicated `release.yml`: `.github/workflows/ci.yml:1-153`.
- Its release concurrency has `cancel-in-progress: true`: `.github/workflows/ci.yml:19-21`. That is appropriate for ordinary CI but unsafe around an irreversible publish boundary.
- Its existing-version check silently skips publish: `.github/workflows/ci.yml:116-132`; the summary can only say "published (or attempted)": `.github/workflows/ci.yml:136-153`. `design-playbook` should distinguish an expected recovery from an unexpected collision and verify final registry state.
- Its README describes "push tag -> Actions publishes" but no GitHub Release ordering or partial-failure recovery: `README.md:507-540`.

## External configuration still required

These settings cannot be completed by a repository commit alone:

1. On npmjs.com, open `design-playbook` -> Settings -> Trusted publishing and configure the proposed GitHub fields above.
2. Create GitHub environment `npm`; restrict deployment to release tags and decide whether a required reviewer / prevent self-review is desired.
3. Create/verify a ruleset protecting `refs/tags/v*` from deletion and retargeting.
4. After the first successful OIDC publish, set npm Publishing access to disallow traditional token publishing where appropriate, then revoke obsolete npm automation tokens/secrets.

The repository workflow should be merged before configuring npm's `Workflow filename`, because npm requires that file to exist under `.github/workflows/` and does not validate a bad binding until publication is attempted.
