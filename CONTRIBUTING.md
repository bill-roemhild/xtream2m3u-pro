# Contributing Guide

This document defines the standard process for making code updates and publishing releases/packages for `xtream2m3u-pro`.

## 1. Prerequisites

- Git
- Python 3.10+
- Docker (optional, for container validation)
- GitHub CLI (`gh`) authenticated for this repo

Authenticate GitHub CLI:

```bash
gh auth login
```

Verify:

```bash
gh auth status -h github.com
```

## 2. Repository Setup

```bash
git clone https://github.com/bill-roemhild/xtream2m3u-pro.git
cd xtream2m3u-pro
git checkout development
git pull origin development
```

Create a feature branch from `development`:

```bash
git checkout -b feat/short-description
```

## 3. Make Code Changes

- Keep changes scoped and reviewable.
- Update docs when behavior changes.
- If endpoints or workflow behavior change, update `README.md` and this file.

## 4. Run Tests Locally

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

## 5. Commit and Push

Stage changes:

```bash
git add -A
```

Commit:

```bash
git commit -m "feat: describe your change"
```

Push branch:

```bash
git push -u origin feat/short-description
```

Open PR to `development`.

## 6. CI Behavior (Automatic)

### Tests workflow

File: `.github/workflows/tests.yml`

Runs on:
- push to `main`
- PRs targeting `main`

It executes `pytest -q`.

### Docker Build and Push workflow

File: `.github/workflows/docker-build-push.yml`

Runs on:
- GitHub Release published (`release.published`)
- manual dispatch (`workflow_dispatch`)

When triggered by release tag `vX.Y.Z`, it builds/pushes image tags including:
- `ghcr.io/<owner>/<repo>:vX.Y.Z`
- `ghcr.io/<owner>/<repo>:X.Y.Z`
- `ghcr.io/<owner>/<repo>:latest`
- `ghcr.io/<owner>/<repo>:sha-<shortsha>`

## 7. How to Change Version Number

Version values must stay aligned in two files:

- `VERSION`
- `.release-please-manifest.json` (the `"."` value)

Example change to `0.1.1`:

1. Edit `VERSION`:

```text
0.1.1
```

2. Edit `.release-please-manifest.json`:

```json
{
  ".": "0.1.1"
}
```

3. Commit:

```bash
git add VERSION .release-please-manifest.json
git commit -m "chore: bump version to 0.1.1"
git push
```

## 8. Release + Package Publish (Recommended Flow)

This repo is currently configured so the most reliable publish flow is:

1. Merge your feature PR into `development`.
2. Promote `development` to `main` (PR or merge commit, based on your repo policy).
3. Ensure `main` contains the desired code and version files.
4. Create a GitHub release tag from `main`:

```bash
gh release create v0.1.1 \
  --repo bill-roemhild/xtream2m3u-pro \
  --target main \
  --title "v0.1.1" \
  --notes "Release v0.1.1"
```

5. Confirm release exists:

```bash
gh release list -R bill-roemhild/xtream2m3u-pro --limit 5
```

6. Confirm Docker publish run started:

```bash
gh run list -R bill-roemhild/xtream2m3u-pro --workflow "Build and Push Docker Image" --limit 5
```

7. Watch run to completion:

```bash
gh run watch <RUN_ID> -R bill-roemhild/xtream2m3u-pro --exit-status
```

8. Confirm package tags in logs:

```bash
gh run view <RUN_ID> -R bill-roemhild/xtream2m3u-pro --log | rg "pushing manifest for ghcr.io"
```

## 9. Optional: Release Please Workflow

File: `.github/workflows/release-please.yml`

Manual trigger example:

```bash
gh workflow run "Release Please" \
  -R bill-roemhild/xtream2m3u-pro \
  -f release_as=0.1.1
```

Notes:
- Release Please relies on commit parsing and conventional commit style.
- If no releasable commits are detected, it may skip creating a release.
- Use the recommended flow in Section 8 if immediate publish is required.

## 10. Post-Release Validation Checklist

After publish:

1. App release exists in GitHub Releases.
2. Docker workflow is green.
3. GHCR package `xtream2m3u-pro` exists with expected tags.
4. `docker compose pull` (if using registry image) retrieves the new tag.
5. `/version` endpoint reports the expected version in a deployed container.

## 11. Hotfix Process

For urgent fixes:

1. Branch from current `development`.
2. Apply minimal change.
3. Run tests.
4. Bump patch version (`X.Y.Z` -> `X.Y.(Z+1)`).
5. Merge to `development`.
6. Promote `development` to `main`.
7. Publish with Section 8 flow.

## 12. Commit Message Guidance

Preferred conventional commit prefixes:

- `feat:` new functionality
- `fix:` bug fix
- `docs:` documentation only
- `refactor:` code change without behavior change
- `test:` tests
- `chore:` maintenance tasks (version bumps, tooling)

Keeping commit messages structured improves release automation compatibility.
