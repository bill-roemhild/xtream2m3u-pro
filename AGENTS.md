# AGENTS.md

This file defines how coding agents must work in this repository.

## Scope

- Applies to the entire repository.
- If another `AGENTS.md` exists in a subdirectory, the closer file takes precedence for files under that path.

## Branching Rules

- Do not make direct code changes on `main`.
- Base all work on `development`.
- Create feature branches from `development`.

Standard flow:

```bash
git checkout development
git pull origin development
git checkout -b <type>/<short-description>
```

Examples:
- `feat/add-channel-filter-toggle`
- `fix/xmltv-empty-output`
- `docs/update-release-steps`

## Change Workflow

1. Understand request and identify impacted files.
2. Make minimal, focused code changes.
3. Update docs when behavior or operations change.
4. Run tests locally before commit.
5. Commit with clear message.
6. Push branch and open PR to `development`.

## Local Validation

Install test dependencies:

```bash
pip install -r requirements-test.txt
```

Run tests:

```bash
pytest -q
```

Optional syntax check:

```bash
python -m compileall app
```

## Commit Standards

Use conventional-style prefixes where practical:

- `feat:` new behavior
- `fix:` bug fix
- `docs:` documentation
- `refactor:` structure without behavior change
- `test:` tests
- `chore:` tooling/maintenance/version bumps

Example:

```bash
git add -A
git commit -m "fix: enforce playlist name validation before save"
```

## PR Target

- Open PRs into `development`.
- Do not open feature PRs directly into `main`.

## Versioning Rules

When bumping version, keep both files in sync:

- `VERSION`
- `.release-please-manifest.json` (the `"."` key)

Example for `0.1.1`:

```bash
printf "0.1.1\n" > VERSION
```

Set manifest value to:

```json
{
  ".": "0.1.1"
}
```

Then commit:

```bash
git add VERSION .release-please-manifest.json
git commit -m "chore: bump version to 0.1.1"
```

## Release and Package Publish

Current recommended process:

1. Merge tested changes into `development`.
2. Promote `development` into `main`.
3. Create GitHub release from `main` using tag `vX.Y.Z`.
4. Release event triggers Docker package build/push workflow.

Create release (example `0.1.1`):

```bash
gh release create v0.1.1 \
  --repo bill-roemhild/xtream2m3u-pro \
  --target main \
  --title "v0.1.1" \
  --notes "Release v0.1.1"
```

Verify publish run:

```bash
gh run list -R bill-roemhild/xtream2m3u-pro --workflow "Build and Push Docker Image" --limit 5
```

Watch run:

```bash
gh run watch <RUN_ID> -R bill-roemhild/xtream2m3u-pro --exit-status
```

## Safety Rules

- Never delete or rewrite remote history unless explicitly requested.
- Never expose secrets, tokens, or passwords in code/docs/logs.
- Avoid destructive commands unless approved.

## Quick Checklist for Agents

Before push:

- [ ] Based on `development`
- [ ] Focused changes only
- [ ] Tests pass (`pytest -q`)
- [ ] Docs updated (if needed)
- [ ] Commit message clear
- [ ] PR target is `development`
