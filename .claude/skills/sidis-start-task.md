---
name: sidis-start-task
description: Use when starting work on a Jira task in a Sidis project. Fetches issue context from Jira (project key VPL), updates status to "In Progress (Dev)", creates a properly-named git branch from latest develop, and shows the Definition of Done checklist. Trigger explicitly via /sidis-start-task <JIRA-ID> or when user says "start task X" / "візьми задачу X".
---

# sidis-start-task

You start work on a Jira task following the [Sidis Dev Process v1.0 section 5.1](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Inputs

- JIRA-ID (e.g. `VPL-123`). If not provided, ask the user.
- Default project key: `VPL` (configurable per project — check `.claude/sidis-config.json` if exists).

## Steps

### 1. Fetch Jira issue

Use `mcp__atlassian__getJiraIssue` with:
- `cloudId`: `sidis-group.atlassian.net`
- `issueIdOrKey`: the JIRA-ID

If the call fails — surface the error to user, do not invent issue data.

### 2. Show summary

Display:
- Title
- Issue type (Story / Task / Bug / Sub-task)
- Priority
- Status
- Assignee (warn if not current user)
- Acceptance criteria (extract from description)
- Estimated hours (if custom field exists)
- Linked Story / Epic

Wait for user confirmation: "Continue? (y/n)"

### 3. Update Jira status

Use `mcp__atlassian__getTransitionsForJiraIssue` to find the transition ID for "In Progress (Dev)" (or "In Progress" if "Dev" suffix doesn't exist).

Use `mcp__atlassian__transitionJiraIssue` to apply.

If transition fails (already in progress or no permission) — show warning, continue.

### 4. Verify clean working tree

```bash
git status --porcelain
```

If output is non-empty — STOP. Show changes to user, ask: "Working tree is dirty. Stash, commit, or abort?"

### 5. Sync with origin

```bash
git fetch origin
git checkout develop
git pull origin develop
```

If pull fails (conflicts, network) — show error, abort.

### 6. Create branch

Generate slug from Jira summary:
- lowercase
- kebab-case
- replace non-ASCII with transliteration or ask user for English short-desc
- truncate to ≤40 chars
- strip stop words (a, the, of) if needed for length

Type prefix:
- `feature` (default for Story / Task)
- `fix` (for Bug)
- `chore` (for Task with technical scope)

Final format: `<type>/<JIRA-ID>-<slug>`

Examples:
- `feature/VPL-123-signal-intake-endpoint`
- `fix/VPL-456-incorrect-dedup-window`
- `chore/VPL-789-bump-fastapi-version`

```bash
git checkout -b <type>/<JIRA-ID>-<slug>
```

If branch already exists locally:
- Ask: "Branch exists. (1) switch to existing, (2) create with `-2` suffix, (3) abort?"

### 7. Show Definition of Done

Print this checklist (also in `.github/pull_request_template.md`):

```
## Definition of Done
- [ ] Implements all acceptance criteria
- [ ] Unit tests written and passing
- [ ] pre-commit passes locally (make lint && make format)
- [ ] CI green (lint + mypy + tests + build)
- [ ] No hardcoded secrets / URLs / API keys
- [ ] Logging + error handling in place
- [ ] Docs updated (README / Swagger / ReDoc) if API changed
- [ ] DB migrations backward-compatible (if any)
- [ ] You can explain every line of code line-by-line (Sidis AI rule 10.1.3)
```

### 8. Suggest next step

Print:

```
✓ Ready to implement VPL-NNN.
Options:
  1. Invoke sidis-orchestrator for full automated flow (plan → impl → test → review → PR)
  2. Continue manually (you write code, optionally invoke sidis-backend/sidis-frontend per file)
  3. Decompose first (invoke /sidis-decompose-story)
```

Wait for user choice.

## Errors and edge cases

- **Issue assigned to someone else** — warn, ask explicitly: "Take over from <name>?"
- **Issue already in "Done" status** — warn, ask: "Issue already done. Reopen, or work without status change?"
- **No develop branch** — warn that this might not be a Sidis-flow project; offer to use main as base.
- **Jira transition not allowed** — show available transitions, ask user which one to apply.
- **Network failure during fetch** — abort, ask user to check VPN/connectivity.

## What NOT to do

- Do NOT create a branch if Jira fetch failed (you might create a branch with wrong JIRA-ID).
- Do NOT skip status update silently — always show whether it succeeded or failed.
- Do NOT push the branch automatically — that's `sidis-create-pr`'s job after implementation.
