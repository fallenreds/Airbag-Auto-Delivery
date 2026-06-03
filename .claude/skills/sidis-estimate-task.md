---
name: sidis-estimate-task
description: Use when preparing for Planning Poker on a Jira Story or Task. Reads the issue plus linked Confluence MVP doc, decomposes into ≤8h subtasks (BE/FE/QA/DevOps prefixes), produces person-hour estimates with Risk %, lists assumptions, and generates questions for CTO/PM. Trigger via /sidis-estimate-task <JIRA-ID> or when user says "estimate X" / "оціни X".
---

# sidis-estimate-task

You prepare a Story for Planning Poker per [Sidis Dev Process v1.0 section 3](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Inputs

- JIRA-ID (required). Default project key: `VPL`.

## Steps

### 1. Fetch Jira issue

`mcp__atlassian__getJiraIssue` with `cloudId=sidis-group.atlassian.net`.

If issue is a Sub-task — get the parent Story instead.

### 2. Find linked Confluence MVP doc

Look in Jira issue description and "remote links" for Confluence URLs.

If found — fetch via `mcp__atlassian__getConfluencePage`. Read fully.

If not found — ask user to provide Confluence link (estimation without MVP context = unreliable).

### 3. Read MVP doc with Sidis 3.1 checklist

While reading, identify:

- **Integrations** (MVP section 5): which external systems, who provides access, SLA?
- **Data boundaries** (section 6): volume, periodicity, real-time vs batch?
- **NFRs**: load, response time, multi-tenancy, localization?
- **Security**: auth scheme, PII, compliance (GDPR)?
- **Out of scope**: explicitly listed exclusions — do not estimate these.
- **Future extensions** (section 1): need to leave extension points now?

### 4. Delegate decomposition + estimation to sidis-planner

Use the Agent tool with `subagent_type: "sidis-planner"`. Pass it the Jira issue + Confluence doc context.

Ask sidis-planner to produce:

#### A. Subtask decomposition

Each subtask:
- **Title** with prefix `[BE]` / `[FE]` / `[QA]` / `[DevOps]`
- **Description** (1–3 sentences)
- **Acceptance criteria** (2–5 bullet points)
- **Dependencies** (which subtasks block this one)
- **Estimate** in person-hours (must be ≤8h; if larger — split further)

#### B. Estimate summary

| Subtask | Hours | Risk % | Assumptions |
|---------|------:|:-----:|-------------|
| [BE] ... | 4 | 10% | "за умови що Clay HMAC секрет надано" |
| [FE] ... | 6 | 25% | "за умови що Figma макет вже готовий" |

Total + risk-weighted total.

#### C. Risk assessment

Per Sidis 3.3:
- ≤10% — standard, no special handling
- 10–25% — medium risk, note assumptions clearly
- 25–50% — high risk, explicit fallback plan needed
- >50% — STOP, return Story to CTO for refinement

If any subtask has Risk >50% — recommend STOPPING estimation and asking CTO to refine.

#### D. Questions to CTO/PM

Format per Sidis 3.2:

```
[architecture | api | data | ux | infra] <short request>
Context: <link to MVP section or Story field>
Hypotheses: A / B / C  (if you have ideas)
```

Examples:
- `[api] Schema of Clay payload — guaranteed fields?`
  `Context: MVP section 5.1, "signal payload"`
  `Hypotheses: A) email is always present, B) only domain is guaranteed`
- `[infra] Redis instance — клієнт надає managed чи self-hosted?`
- `[architecture] Authentication — Bearer token чи OAuth для admin UI?`

### 5. Output as Markdown

Print the decomposition + estimate table + risk + questions in a single Markdown block that the user can copy-paste into Confluence/Jira/Slack.

Add header:

```
# Estimation: VPL-NNN — <Story title>

**Estimator:** Claude (review with team on Planning Poker)
**Source MVP doc:** <Confluence link>
**Date:** <YYYY-MM-DD>
```

### 6. Optionally update Jira

Ask user: "Update issue with decomposition? Options:"
1. Add comment with the table to the parent Story.
2. Create sub-tasks in Jira.
3. Just print, don't touch Jira.

If (2): for each subtask, call `mcp__atlassian__createJiraIssue` with the parent linked. Wait for user explicit "create all" before iterating.

## Edge cases

- **No MVP doc** — STOP. Ask user to provide Confluence link or paste content.
- **Story too vague** (<200 chars description, no AC) — output a single question: "Story needs refinement before estimation; please provide AC and example flow."
- **Story already has subtasks** — list them, ask user: "Re-estimate existing or rebuild from scratch?"
- **No Jira access** — ask user to paste issue content; estimate from text.

## What NOT to do

- Do NOT use story points — Sidis convention is person-hours.
- Do NOT estimate unilaterally without `Risk %` — every estimate requires risk classification.
- Do NOT auto-create Jira sub-tasks without explicit confirmation per subtask or "create all" approval.
- Do NOT skip the questions to CTO step — even "no questions" should be explicitly stated.
