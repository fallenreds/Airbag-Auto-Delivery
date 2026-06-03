---
name: sidis-onboard-project
description: Use when a new developer joins a Sidis project for the first time. Walks through onboarding checklist from Sidis Dev Process v1.0 section 2.1 — verifies access (GitHub, Jira, Confluence, Slack, Everhour), checks local environment (Python, uv, Docker, git, make), runs initial setup (make setup, .env, make up, make migrate, make admin, make test), shows key documentation. Trigger via /sidis-onboard-project or when user says "onboard me" / "перший раз у проекті".
---

# sidis-onboard-project

You guide a new developer through onboarding per [Sidis Dev Process v1.0 section 2.1](https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-).

## Mode

This is a **walkthrough**. After each step, wait for user confirmation before proceeding. Don't auto-fix failures — diagnose with the developer so they understand the project.

Delegate the actual walkthrough to the `sidis-onboarder` sub-agent for full focus.

## Steps

### 1. Greeting + introduction

```
Welcome to <project name>! I'll walk you through onboarding (~30 min).

Before we start, please confirm:
1. Have you been added to the GitHub organization `sidis-group`?
2. Do you have access to Jira (project key from CLAUDE.md)?
3. Do you have access to Confluence (space from CLAUDE.md)?
4. Do you have access to the project Slack channel?
5. Do you have your 1Password / Bitwarden access for secrets?

If any "no" — stop and ping your lead-developer or PM.
```

### 2. Verify access

For each of the above:
- GitHub: `gh repo view sidis-group/<repo>` → must succeed.
- Jira: try `mcp__atlassian__getJiraIssue` for a known issue — surface error if no permission.
- Confluence: try `mcp__atlassian__getConfluenceSpaces` and check for the project space.
- Slack: manual confirm (we can't check programmatically).
- Everhour: manual confirm.

### 3. Verify local environment

Check each:

```bash
python --version       # ≥ 3.12
uv --version           # any
docker --version       # any
docker compose version # v2+
git --version          # ≥ 2.40
make --version         # any
node --version         # ≥ 22 (for frontend)
pnpm --version         # any
```

For each missing tool, suggest install command:
- macOS: `brew install python@3.12 uv docker git make node pnpm`
- Linux: per-distro instructions (apt/dnf/pacman)

### 4. Clone & setup

If user is not already in the project directory:
```bash
git clone git@github.com:sidis-group/<repo>.git
cd <repo>
```

Then:
```bash
make setup
```

This runs: `uv sync` + `pnpm install` + `pre-commit install` + creates `.env` from `.env.example`.

### 5. Fill .env

Open `.env` and walk through it. For each section:
- **DATABASE_URL / REDIS_URL**: leave defaults for local docker-compose.
- **JWT_SECRET**: generate via `openssl rand -hex 32`.
- **NEXTAUTH_SECRET**: same.
- **SENTRY_DSN**: get from 1Password vault `<project>-dev` or skip for now.
- **Domain integrations** (CLAY_HMAC_SECRET, INSTANTLY_API_KEY, ANTHROPIC_API_KEY): get from 1Password.
- **BOOTSTRAP_ADMIN_EMAIL/PASSWORD**: leave empty — we'll use `make admin` instead.

Remind: NEVER commit `.env`. (`.gitignore` already covers it.)

### 6. Start services

```bash
make up
```

Wait until all services are healthy:
```bash
docker compose ps
```

### 7. Run migrations

```bash
make migrate
```

Should output: "Running upgrade ... -> ..., initial".

### 8. Create admin user

```bash
make admin EMAIL=<your-sidis-email> PASSWORD=<temporary-strong-password>
```

Note: change password after first login via `/profile` page.

### 9. Run tests (smoke)

```bash
make test
```

Should be green. If not — diagnose with developer (most common: missing service, wrong .env value).

### 10. Open the app

```bash
open http://localhost:3000     # or just visit in browser
```

Login with admin credentials. Verify:
- Login works.
- Dashboard loads (might be empty for new project).
- /admin/users — see your admin user.
- /profile — change password (if you used a temp password).

### 11. Tour the documentation (≥30 min reading)

Show in order:
1. **CLAUDE.md** — your daily reference. Read fully.
2. **README.md** — project overview.
3. **MVP doc in Confluence** — link from CLAUDE.md.
4. **All active Stories in Jira** — get familiar.
5. **Sidis Dev Process v1.0**:
   https://sidis-group.atlassian.net/wiki/spaces/PM/pages/473890817/dev-
6. **sidis-claude-skills README** — these skills you're using right now:
   https://github.com/sidis-group/sidis-claude-skills

### 12. Schedule kickoff sync

Suggest user book a 30-min sync with lead-developer for:
- Architecture overview specific to this project
- Active priorities and roadmap
- Open questions / gotchas not yet in CLAUDE.md
- Q&A

### 13. Final checklist

```
✓ Onboarding complete!

Next steps:
1. Pick your first task — ask lead which Story/Task to start.
2. Use `/sidis-start-task <JIRA-ID>` to begin.
3. Use `/sidis-create-pr` when implementation is done.
4. Use `/sidis-code-review` when reviewing PRs.

If anything broke during onboarding, please open a Jira issue or update CLAUDE.md so the next person doesn't hit the same.
```

## Edge cases

- **`make setup` fails** — diagnose with developer. Common: missing system deps, stale uv cache, network.
- **Tests fail on first run** — usually missing env var or service not ready. Walk through `docker compose logs` together.
- **No admin can be created** (DB connection error) — verify `DATABASE_URL` matches `docker compose ps` postgres mapping.
- **User can't login** (cookies / CORS) — check `NEXTAUTH_URL` matches actual host.

## What NOT to do

- Do NOT auto-fix problems silently. The point is for the developer to learn the project.
- Do NOT skip the documentation tour — Sidis Dev Process explicitly requires ≥2 hours reading on day 1.
- Do NOT share secrets via chat — always direct to 1Password vault.
