---
name: sidis-code-review
description: Use when reviewing a Pull Request or branch for a Sidis project. Performs structured code review against Sidis Dev Process v1.0 checklist (architecture, naming, error handling, race conditions, N+1 queries, secrets, tests, docs). Wraps the code-review:code-review plugin with Sidis-specific criteria. Trigger via /sidis-code-review [PR-number|branch-name] or when user says "review PR X" / "ревʼю PR X".
---

# sidis-code-review

You perform code review per [Sidis Dev Process v1.0 section 6.3](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Inputs

- Optional: PR number (e.g. `42`) or branch name. If neither — review current branch vs `develop`.

## Steps

### 1. Resolve target

If PR number provided:
```bash
gh pr checkout <num>
gh pr view <num> --json title,body,baseRefName,author
```

If branch name provided:
```bash
git fetch origin <branch>
git checkout <branch>
```

If nothing — use current branch. Verify it's not `main`/`develop`.

### 2. Get base branch

For PR: from `gh pr view --json baseRefName`.
For branch: assume `develop` (unless branch starts with `hotfix/` → `main`).

### 3. Get diff and changed files

```bash
git fetch origin <base>
git diff origin/<base>..HEAD --stat
git diff origin/<base>..HEAD --name-only
```

### 4. Read changed files in full

For each changed file in the diff, use the Read tool to read the **entire file** — not just the diff hunks. Context matters; you cannot judge a function based on the diff alone.

### 5. Read related context

For changed services/repositories: read the corresponding `schemas.py`, `models.py`, `tests/` to understand the full module shape.

For new endpoints: read `core/security.py`, `core/rbac.py` to verify auth applied correctly.

### 6. Invoke code-review:code-review plugin

Use the Agent tool with `subagent_type: "code-review:code-review"`. Pass it the Sidis review checklist as the prompt context.

```
Review the changes in branch <branch> against base <base>.

Sidis-specific checklist (Dev Process v1.0 section 6.3):

1. **ТЗ compliance**: Do all acceptance criteria from the linked Jira issue appear satisfied?
   (Read the Jira issue via mcp__atlassian if PR title has JIRA-ID.)

2. **Layered architecture**: Verify router → service → repository. Routers should not touch the DB
   directly; services should not import FastAPI types; repositories should only contain SQLAlchemy
   queries.

3. **Naming**: Identifiers should be clear without comments. English only. Module names singular
   noun (`signal`, not `signals_module`).

4. **Cognitive complexity**: Any function >50 lines or with >3 levels of nesting? Flag for splitting.

5. **Error handling**: Exceptions must be raised explicitly with context. No bare `except:`.
   No silent swallowing. External calls wrapped with retries via tenacity.

6. **Race conditions**: For any code creating/updating shared state, verify it's safe under
   concurrent requests (UNIQUE constraints, advisory locks, or idempotency keys).

7. **N+1 queries**: ORM access in loops? Use `selectinload` / `joinedload` for relationships.

8. **Resource leaks**: Files, HTTP clients, DB connections must use context managers (`async with`).

9. **Secrets**: No hardcoded API keys, passwords, URLs. All via `pydantic-settings` from env.

10. **Tests**: Cover happy path AND error paths. Not "mock everything" — integration tests should
    use real Postgres/Redis via testcontainers.

11. **Documentation**: README/Swagger updated if public API changed?

12. **AI rule (Sidis 10.1.3)**: Can the author plausibly explain every line? If anything looks
    auto-generated and tricky (regex, complex generics), flag a Q: comment.

13. **Migrations**: If `alembic/versions/` changed, are migrations backward-compatible
    (expand-then-contract pattern for non-trivial changes)?

14. **Logging**: structlog only, no print, no f-strings with secrets in log messages.

15. **RBAC**: Any new endpoint must have explicit `Depends(require_role(...))` or be in the
    documented public list (auth, webhooks).

Return findings using Sidis comment prefixes:
- MUST: blocking, must fix before merge
- SHOULD: strong suggestion, can be discussed
- suggestion: optional improvement
- nit: stylistic, optional
- Q: question / clarification request

Cite specific file paths and line numbers.

Final verdict: APPROVE / REQUEST_CHANGES / COMMENT (only if findings are nit/Q).
```

### 7. Format final report

Output for the user:

```
## Code Review: <branch> → <base>

**Files changed:** N (X added, Y modified, Z deleted)
**Lines:** +A / -B
**Linked Jira:** VPL-NNN — <title>

### MUST (blocking)
1. **path/to/file.py:42** — <description>
   <suggestion or correction>

### SHOULD
1. ...

### suggestion
1. ...

### nit
1. ...

### Q
1. ...

### Verdict: <APPROVE | REQUEST_CHANGES | COMMENT>

### Pair-review recommendation
[Only if PR > 400 lines per Sidis 6.5: "Recommend 15-min sync review with author."]
```

### 8. Optional: post comments to GitHub

Ask user: "Post these comments to GitHub PR? (y/n)"

If yes and PR number known:
```bash
gh pr review <num> --request-changes --body "<MUST findings>"
# or:
gh pr review <num> --comment --body "<all findings>"
# or:
gh pr review <num> --approve --body "LGTM, see minor nits below."
```

For inline comments on specific lines (better UX): use `gh api repos/<owner>/<repo>/pulls/<num>/comments` per finding. Get user confirmation before posting.

## Edge cases

- **No diff** — branch has no commits ahead. STOP. "Nothing to review."
- **Generated files in diff** (lock files, migrations marked `# autogenerated`) — note in report, lower scrutiny.
- **Very large diff (>1000 lines)** — STRONGLY recommend pair-review; offer to review by chunks.
- **Migration files** — apply special scrutiny (data loss risk, downtime).

## What NOT to do

- Do NOT merge the PR — Sidis flow: author merges after approve.
- Do NOT approve to be polite — be technically rigorous.
- Do NOT post comments to GitHub without explicit user confirmation.
- Do NOT skip reading full files (relying only on diff is the #1 cause of missed bugs).
