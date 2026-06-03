---
name: sidis-commit
description: Use to generate a Conventional Commit message from staged git diff. Detects type/scope automatically from changed paths, extracts JIRA-ID from current branch name. NEVER appends Co-Authored-By / Assisted-by / Generated-by trailers — Sidis projects keep commit authorship clean. Wait for user approval before committing. Trigger via /sidis-commit or when user says "commit", "make a commit", "напиши коміт".
---

# sidis-commit

You generate a [Conventional Commit](https://www.conventionalcommits.org/) message and commit per Sidis convention.

## Steps

### 1. Check staged changes

```bash
git diff --staged --stat
```

If empty:
- Suggest: "Nothing staged. Want me to suggest `git add -p` for interactive staging? Or stage all (`git add -A`)?"
- Wait for user direction.

### 2. Detect branch and JIRA-ID

```bash
git rev-parse --abbrev-ref HEAD
```

Parse pattern `<type>/<JIRA-ID>-<slug>`. Extract `JIRA-ID` (e.g. `VPL-123`).

If branch doesn't match — note: "Branch name doesn't follow Sidis convention; commit will skip JIRA-ID footer." Continue without JIRA-ID.

### 3. Detect commit type

Priority:
1. From branch type prefix: `feature/*` → `feat`, `fix/*` → `fix`, `chore/*` → `chore`, `hotfix/*` → `hotfix`.
2. From staged file paths:
   - Only `tests/` → `test`
   - Only `docs/` or `*.md` → `docs`
   - Only `pyproject.toml` / `package.json` deps changes → `chore(deps)`
   - `.github/workflows/*` → `ci`
3. Fallback: `feat` if files added, `refactor` if only modified, `chore` if config-only.

Conventional Commits types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `style`, `build`, `ci`, `hotfix`.

### 4. Detect scope

```bash
git diff --staged --name-only
```

Find common prefix. Patterns:
- `apps/api/src/*/modules/<name>/...` → scope = `<name>` (e.g. `signals`, `users`, `auth`).
- `apps/api/src/*/core/<file>...` → scope = `core` or specific (`config`, `security`).
- `apps/web/src/app/<segment>/...` → scope = `web/<segment>` or just `web`.
- `apps/api/alembic/...` → scope = `db`.
- Cross-cutting → no scope.

### 5. Generate subject

Read the diff (or significant chunks). Generate:
- Imperative mood ("add", "fix", "refactor", not "added")
- Lowercase
- ≤72 chars total INCLUDING type/scope/JIRA-ID
- No period at end

Examples:
- `feat(signals): add HMAC validation to intake endpoint (VPL-123)`
- `fix(auth): correct JWT exp claim timezone handling (VPL-456)`
- `test(users): add coverage for password rotation (VPL-789)`
- `chore(deps): bump fastapi to 0.116`
- `docs(readme): add make admin instructions`

### 6. Generate body (only for non-trivial)

For diffs >50 lines or multi-file changes, write a body:
- Blank line after subject.
- Wrap at 72 chars.
- Explain WHY, not WHAT (the diff shows what).
- Reference issues/PRs if relevant.

For trivial fixes (typo, lint) — no body.

### 7. Footer (trailers)

Always include if JIRA-ID detected:
```
Refs: VPL-123
```

**DO NOT add `Co-Authored-By:`, `Assisted-by:`, `Generated-by:`, or any other AI-attribution trailer** — Sidis projects keep commit authorship clean (only the human committer's name appears in `git log`). Settings.json includes `includeCoAuthoredBy: false` to enforce this at the Claude Code layer; agents must not bypass it.

For breaking changes (rare, but if the diff suggests it):
```
BREAKING CHANGE: <description>
```

### 8. Show and commit

Print the full commit message, then ask: "Commit with this message? (y / edit / abort)"

- `y` → execute commit
- `edit` → let user paste a revised version
- `abort` → exit without committing

To commit (always heredoc to preserve formatting):
```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject> (<JIRA-ID>)

<body>

Refs: <JIRA-ID>
EOF
)"
```

If pre-commit hook fails — show output, fix where possible, re-stage, retry. Do NOT use `--no-verify`.

### 9. Post-commit

Print:
```
✓ Committed: <short SHA> <subject>

Total commits on branch:
  git log develop..HEAD --oneline

Ready to:
  - continue working
  - /sidis-create-pr (when done with task)
```

## Edge cases

- **Mixed concerns in one commit** (refactor + feature + test) — suggest splitting:
  "This commit mixes <type1> and <type2>. Consider splitting via `git reset HEAD` and `git add -p`."
- **Generated files in diff** (lock files, migrations) — note in body: "Includes auto-generated migration."
- **Very large commit** (>500 lines) — warn: "Large commit. Reviewer-friendly to split. Continue?"
- **Pre-commit hook reformatted files** — re-stage and offer retry.

## What NOT to do

- Do NOT use `git commit --no-verify`.
- Do NOT skip body for non-trivial changes.
- Do NOT include the diff content in the message body — commit messages explain *why*.
- Do NOT auto-commit without user approval.
