---
name: sidis-hotfix
description: Use during P0 (production outage) or P1 (critical broken function) incidents to manage the fast-track hotfix flow per Sidis Dev Process v1.0 section 9. Branches from main (NOT develop), enforces minimal-diff fix + regression test, opens fast-track PR, reminds about tag + backmerge + post-mortem. Trigger via /sidis-hotfix <JIRA-ID> or when user says "P0" / "hotfix" / "prod down".
---

# sidis-hotfix

You manage critical incident response per [Sidis Dev Process v1.0 section 9](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Inputs

- JIRA-ID of the incident (required). If user says "P0 prod down" without ID — first create one:
  `mcp__atlassian__createJiraIssue` with priority=Highest, type=Bug, summary from user input.

## Step 1: Confirm priority

Ask explicitly: "Confirm priority — P0 (full outage) or P1 (critical broken)?"

If user says P2/P3 — STOP. "This is not a hotfix scenario. Use normal `/sidis-start-task` flow."

## Step 2: Bootstrap from main

```bash
git fetch origin
git status --porcelain                # MUST be clean
git checkout main
git pull origin main
git checkout -b hotfix/<JIRA-ID>-<short-slug>
```

If working tree dirty — STOP. Ask user to stash/abort. **Never** lose hotfix-time-pressure work to dirty stash.

## Step 3: Help diagnose root cause

Delegate to `superpowers:debugging` skill if available, or `systematic-debugging` agent.

Key checks for incidents:
1. Recent deploys (`git log --since="6 hours ago" main`).
2. Sentry errors increase pattern (ask user for Sentry link).
3. Database (slow queries, lock contention).
4. External dependencies (Instantly/Anthropic outage status).

Once root cause is hypothesized — confirm with user before proceeding to fix.

## Step 4: Implement MINIMAL fix

Constraints (Sidis hotfix philosophy):
- **Smallest possible diff.** A 5-line change beats a 50-line refactor.
- No unrelated cleanup.
- No "while we're here" improvements.
- A single regression test that fails before fix and passes after.

Delegate implementation to `sidis-backend` (or `sidis-frontend`) with explicit constraint: "MINIMAL fix only. No refactoring."

## Step 5: Verify

```bash
make lint
make test-unit               # at least your new regression test passes
```

If full test suite would take >5 min — skip and note in PR.

## Step 6: Push and open fast-track PR

```bash
git push -u origin HEAD
gh pr create \
  --base main \
  --title "hotfix(<scope>): <desc> (<JIRA-ID>) [FAST-TRACK]" \
  --label "hotfix,fast-track" \
  --body "$(cat <<'EOF'
## Incident summary
<one paragraph: what was broken, how it was detected>

## Root cause
<1-2 sentences>

## Fix
<what this PR does, technically>

## Risk assessment
- Blast radius: <small/medium/large>
- Affected users/requests: <estimate>
- Side effects: <none expected | list>

## Rollback plan
If fix introduces regression:
1. `git revert <commit>` on main
2. Redeploy via `gh workflow run deploy.yml --ref v<previous-tag>`

## Test
- [ ] Regression test added
- [ ] Manual reproduction blocked

## Post-merge checklist (REMINDERS)
- [ ] Tag: `git tag -a v1.X.Y -m "Hotfix: <desc>" && git push --tags`
- [ ] Backmerge to develop: `git checkout develop && git merge main && git push`
- [ ] Post-mortem within 48h (template will be provided)

⚠️ Fast-track review (≤15 min) per Sidis Dev Process 9.3.
EOF
)"
```

Assign reviewer: lead-dev (per Sidis section 9.3 — only lead merges hotfixes).

## Step 7: After merge — REMIND about tag, backmerge, post-mortem

Print to user:

```
🚨 Hotfix merged to main. CRITICAL next steps (Sidis 9.3):

1. **Tag the release**:
   git checkout main && git pull
   git tag -a v1.X.Y -m "Hotfix: <one-line desc>"
   git push --tags

2. **Backmerge to develop** (so the fix doesn't disappear in next release):
   git checkout develop && git pull
   git merge main
   # resolve conflicts if any
   git push origin develop

3. **Production deploy** (auto-triggered by tag, monitor via gh workflow view).
   Smoke test: <link to dashboard>
   Monitor Sentry: <link>

4. **Post-mortem within 48h**. Template:
```

Then output the post-mortem template:

```markdown
# Post-mortem: <short incident name>

- **Date / time:** YYYY-MM-DD, HH:MM–HH:MM UTC
- **Duration:** Xh Ymin
- **Priority:** P0 | P1
- **Impact:** <what was broken, how many users/requests affected, financial impact if applicable>

## Timeline
HH:MM — <what happened>
HH:MM — <detection: monitoring / customer / internal>
HH:MM — <diagnosis>
HH:MM — <fix deployed>
HH:MM — <verified resolved>

## Root cause
<technical explanation, 2–4 sentences>

## How we fixed
<what we deployed, which commit/release>

## What to improve (action items)
- [ ] <item> — owner: @X — by: YYYY-MM-DD
- [ ] ...

## What went well
<reinforce positive>

---

**Не шукаємо винних.** Шукаємо системні причини.
```

Ask user to publish in Confluence under VL space and link to the Jira incident.

## Edge cases

- **Hotfix can't be minimal** (rewrite required) — STOP. This is not a hotfix; it's an emergency change. Escalate to CTO; consider rolling back the prod release that introduced the bug instead.
- **Fix on main not develop** — that's correct for hotfix; do NOT branch from develop.
- **Backmerge causes conflicts** — help resolve, but err on side of "main wins" for the hotfix bits.
- **No regression test possible** (e.g., infra issue) — note explicitly in PR + post-mortem.

## What NOT to do

- Do NOT branch from develop.
- Do NOT skip the regression test (without explicit lead approval).
- Do NOT skip backmerge — this is the #1 cause of hotfix regression.
- Do NOT skip post-mortem — Sidis treats this as compliance.
- Do NOT use `--no-verify` to bypass pre-commit (per Sidis 4.1.6 ❌).
