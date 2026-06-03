---
name: sidis-decompose-story
description: Use when a User Story needs to be broken down into BE/FE/QA/DevOps subtasks of ≤8h each before development starts. Each subtask gets title, description, acceptance criteria, dependencies. Optionally creates the subtasks in Jira. Trigger via /sidis-decompose-story <JIRA-ID> or when user says "decompose X" / "розбий X на підзадачі".
---

# sidis-decompose-story

You decompose a User Story into actionable subtasks per [Sidis Dev Process v1.0 section 3.4](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Inputs

- JIRA-ID of a Story (required). Default project key: `VPL`.

## Steps

### 1. Fetch the Story

`mcp__atlassian__getJiraIssue`. Verify issue type is Story (or Epic with sub-stories).

If it's a Sub-task — escalate to its parent.

### 2. Read linked context

- Description fully
- Acceptance criteria
- Linked Confluence MVP doc (if available)
- Existing sub-tasks (if any)

### 3. Delegate to sidis-planner agent

Use the Agent tool with `subagent_type: "sidis-planner"` and focus on decomposition (not estimation per se).

Request:

```
Decompose this Story into subtasks per Sidis Dev Process v1.0 section 3.4.

Rules:
- Each subtask ≤8h. If larger — split further (smaller = more accurate).
- Title prefix: [BE] / [FE] / [QA] / [DevOps].
- Title format: "[BE] Add X for Y" (imperative, English).
- Description: 1–3 sentences explaining WHAT and WHY.
- Acceptance criteria: 2–5 bullets, each testable / verifiable.
- Dependencies: which other subtasks block this one (use placeholder IDs SUB-1, SUB-2, ...).

Cover (in this order):
1. Backend: data model + migration first, then repository, then service, then router/endpoint.
2. Frontend (if applicable): types from API, then components, then pages, then route.
3. Tests: unit (with the code) and integration (after backend done) and E2E (after frontend).
4. DevOps: only if config changes (new env var, new service in docker-compose).
5. Docs: only if public API changes (Swagger description, README, RUNBOOK).

Avoid:
- Bundling backend and frontend in one subtask (different reviewers).
- "Implement X" subtasks without AC — every subtask must be testable.
- Subtasks <0.5h (overhead overhead).

For each subtask, include estimate hours and Risk % per Sidis 3.3.
```

### 4. Format result

Output as Markdown table:

```markdown
# Decomposition: VPL-NNN — <Story title>

## Subtasks

| ID | Title | Hours | Risk | Dependencies | AC |
|----|-------|------:|:----:|:------------:|----|
| SUB-1 | [BE] Add Signal model + migration | 2 | 10% | — | <AC bullets> |
| SUB-2 | [BE] Add SignalsRepository | 2 | 10% | SUB-1 | ... |
| SUB-3 | [BE] Add SignalsService.create | 3 | 15% | SUB-2 | ... |
| SUB-4 | [BE] Add POST /signals/intake endpoint | 4 | 20% | SUB-3 | ... |
| SUB-5 | [BE] Integration tests for intake | 3 | 10% | SUB-4 | ... |
| SUB-6 | [FE] Generate API client types | 0.5 | 5% | SUB-4 | ... |
| SUB-7 | [QA] E2E smoke test for intake | 2 | 15% | SUB-6 | ... |

**Total:** 16.5h
**Risk-weighted:** ~19h

## Suggested execution order

1. SUB-1 → SUB-2 → SUB-3 → SUB-4 (sequential, BE only)
2. SUB-5 in parallel with SUB-6 (after SUB-4)
3. SUB-7 last

## Open questions for PM/CTO

[architecture] ...
[api] ...
```

### 5. Optional: create subtasks in Jira

Ask user explicitly:
- "Create all subtasks in Jira VPL? (y/n/select)"
  - `y` → create all
  - `n` → just print
  - `select` → ask per-subtask

For "y" or selected: for each, call `mcp__atlassian__createJiraIssue` with:
- `projectKey`: VPL
- `summary`: subtask title
- `issueTypeName`: "Sub-task"
- `parent`: original Story key
- `description`: subtask description + AC + estimate

After creation, replace placeholder IDs (SUB-1, ...) with real Jira keys (VPL-NNN) in the dependencies links via `mcp__atlassian__editJiraIssue` or `createIssueLink`.

### 6. Update parent Story

Add a comment to the parent Story with link to the decomposition (or list of created sub-task keys).

## Edge cases

- **Story already has sub-tasks** — list them, ask: "Add to existing, or replace?" (do NOT silently duplicate).
- **Story too small** (<4h total estimated work) — note: "This Story might be a single subtask. Skip decomposition?"
- **Story too large** (>40h total) — note: "This Story should likely be an Epic. Suggest CTO splits it."
- **Cross-cutting work** (e.g., refactor that touches 10 modules) — propose temporal split (phase 1: prep, phase 2: rename, phase 3: cleanup) instead of by-module split.

## What NOT to do

- Do NOT bundle BE+FE+QA in one subtask.
- Do NOT skip Risk %.
- Do NOT auto-create Jira issues without explicit user confirmation.
- Do NOT create circular dependencies.
