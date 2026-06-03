---
name: sidis-create-pr
description: Use when implementation of a Sidis task is complete and ready for review. Validates code quality (pre-commit, tests), pushes branch to origin, creates GitHub PR using Sidis template, assigns reviewer from CODEOWNERS or sidis-reviewers config, and updates Jira status to Code Review. Trigger via /sidis-create-pr or when user says "create PR" / "відкрий PR".
---

# sidis-create-pr

You create a Pull Request following [Sidis Dev Process v1.0 sections 5.1, 6.2](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Prerequisites

- Current branch follows naming convention `<type>/<JIRA-ID>-<slug>` (e.g. `feature/VPL-123-foo`).
- All work committed (clean working tree).

## Steps

### 1. Verify branch name

```bash
git rev-parse --abbrev-ref HEAD
```

Parse to extract: `type`, `JIRA-ID`, `slug`. If pattern doesn't match Sidis convention — STOP. Show error and current branch name.

If on `main` or `develop` — STOP. "You're on a protected branch. Create a feature branch first via /sidis-start-task."

### 2. Verify clean working tree

```bash
git status --porcelain
```

If non-empty — STOP. Ask user to commit or stash.

### 3. Run quality checks (BLOCKING — never skip)

```bash
make ci-check        # full CI mirror: ruff check + ruff format --check + mypy + eslint + tsc
make test-unit       # quick unit tests (testcontainers integration left to CI)
```

`make ci-check` is the same set of checks GitHub Actions runs in the `lint` and `type-check` jobs. **If `ci-check` fails — STOP. Do not push.** Show the failure output, fix it, re-run, then proceed.

The `--skip-checks` flag is **not honored** for `ci-check` — pushing without it is the #1 source of red CI runs and PR ping-pong. The pre-push git hook will block the push anyway (installed by `make setup`), so running `ci-check` here just catches it earlier.

If `make ci-check` fails on `ruff format --check` — run `make format` to auto-fix, then re-run `ci-check`. If fails on anything else (lint / type errors) — fix manually.

### 4. Push branch

```bash
git push -u origin HEAD
```

The `pre-push` git hook auto-runs `make ci-check`; if for any reason ci-check passed in step 3 but the hook fails (e.g. uncommitted changes affecting the result), STOP and investigate — never use `--no-verify` to bypass.

### 5. Generate PR title

Format: `<type>(<scope>): <subject> (<JIRA-ID>)`

Where:
- `type` is conventional commits: `feat` (for `feature/*` branches), `fix` (for `fix/*`), `chore` (for `chore/*`), `hotfix` for `hotfix/*`.
- `scope` is the primary domain module touched (e.g. `signals`, `users`, `auth`). Detect from changed files: `git diff develop..HEAD --name-only | grep -oP 'modules/\K[^/]+' | sort -u | head -1`.
- `subject` is short imperative, ≤72 chars total (including prefix and JIRA-ID), starts with lowercase verb.

Examples:
- `feat(signals): add intake endpoint with HMAC validation (VPL-123)`
- `fix(auth): correct JWT refresh token rotation (VPL-456)`
- `chore(deps): bump fastapi to 0.116 (VPL-789)`

### 6. Generate PR body

Use the project's `.github/pull_request_template.md` as base. Fill:

- **Що зроблено**: short summary derived from commits (`git log develop..HEAD --oneline`). Group commits by type.
- **Jira**: link to issue using JIRA-ID.
- **Як тестувалось**:
  - Auto-tick `Unit-тести` if `tests/` was modified.
  - Auto-tick `Pre-commit` (we just ran it).
  - Auto-tick `CI зелений` only when CI completes (note: "pending CI").
  - Ask user about manual testing and edge cases — list what they tested.
- **Скріншоти**: if `apps/web/**` changed → ask user to attach manually after PR creation; mention "TODO: add screenshot" placeholder.
- **DoD checklist**: tick all boxes that automated checks confirm.
- **Breaking changes**: ask user explicitly; if API changed (FastAPI router signatures changed), mention it.

### 7. Determine reviewer

Priority:
1. Read `.claude/sidis-reviewers.json` if exists. Format:
   ```json
   {
     "default": "lead-dev-handle",
     "by_path": {
       "apps/api/src/*/modules/auth/": "security-reviewer-handle",
       "alembic/": "lead-dev-handle"
     }
   }
   ```
2. Fall back to `CODEOWNERS` if exists.
3. Otherwise ask user for handle.

### 8. Create PR

```bash
gh pr create \
  --base develop \
  --title "<title>" \
  --body "$(cat <<'EOF'
<body>
EOF
)" \
  --reviewer <handle>
```

If `gh pr create` fails (e.g. PR exists for branch) — get URL of existing PR via `gh pr view --json url`.

### 9. Update Jira

Transition issue to "Code Review" status using `mcp__atlassian__transitionJiraIssue`.

If status doesn't exist or transition fails — warn but don't block.

Add comment to Jira with PR link via `mcp__atlassian__addCommentToJiraIssue`.

### 10. Print result

```
✓ PR created: https://github.com/sidis-group/<repo>/pull/<num>
✓ Reviewer assigned: @<handle>
✓ Jira VPL-NNN moved to Code Review
ℹ Wait for CI to complete (~5 min). After approve — author merges (squash) per Sidis flow.
```

## Errors and edge cases

- **Branch protection rejects push** — STOP. Tell user: "Branch protection forbids direct push. This shouldn't happen for feature branches; check repo settings."
- **CI was already failing on develop** — note in PR body: "Note: develop is currently red, see <issue>".
- **No commits ahead of develop** — STOP. "No commits to PR. Did you forget to commit?"
- **Forced push detected** (after first push) — warn user about reviewer dismissal per Sidis 6 ("Dismiss stale reviews").

## What NOT to do

- Do NOT push to `main` or `develop` directly.
- Do NOT skip pre-commit/tests without `--skip-checks` AND user explicit confirmation.
- Do NOT auto-merge the PR — Sidis rule: author merges after approve, not during PR creation.
- Do NOT create multiple PRs for the same branch — find existing one and reuse.
