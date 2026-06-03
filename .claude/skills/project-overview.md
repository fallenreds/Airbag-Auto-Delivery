---
name: project-overview
description: Walk a developer (or Claude itself) through this project's stack, file structure, and the mandatory rules (responsive design, i18n, validation, no browser dialogs, documentation discipline). Invoke at the start of any non-trivial task or onboarding.
---

# Project overview

Read this whenever you (or a teammate) start a non-trivial task in this repo. It captures the things that are NOT obvious from looking at the code: which patterns to follow, which mistakes are non-negotiable, where each kind of file lives.

If you are a fresh dev — read it top to bottom. If you are returning — jump to **Mandatory rules** (section 4) to refresh on what would block your PR.

---

## 1. Stack at a glance

**Backend** (`apps/api/`):
- Python 3.12 + FastAPI 0.115 + SQLAlchemy 2 (async) + Pydantic v2
- Postgres 16, Redis 7, arq for background jobs
- structlog (JSON), Sentry, bcrypt, python-jose (JWT)
- Tooling: uv (deps), ruff (lint+format), mypy strict, pytest + testcontainers

**Frontend** (`apps/web/`):
- Next.js 15 (App Router) + React 19, TypeScript strict
- shadcn/ui + Tailwind 4 (CSS variables, dark mode via next-themes)
- NextAuth v5 (JWT in HttpOnly cookie), next-intl (en + uk)
- react-hook-form + zod, openapi-fetch, Sentry

**Contract pipeline**: Pydantic schemas → FastAPI OpenAPI → `make api-client` → `apps/web/src/lib/api/schema.ts`. Backend is the single source of truth — never hand-write TS types that mirror DTOs.

---

## 2. Backend file layout (`apps/api/src/api/`)

```
core/
├── config.py          # pydantic-settings, all env vars
├── deps.py            # FastAPI dependencies (get_db_session, get_current_user)
├── exceptions.py      # DomainError + global FastAPI exception handler
├── logging.py         # structlog setup, contextvars for request_id
├── permissions.py     # CATALOG: list[Perm] + SYSTEM_ROLE_{ADMIN,VIEWER}
├── rbac.py            # require_permission(slug) dependency factory
├── security.py        # bcrypt hash/verify, JWT encode/decode, HMAC
├── sentry.py          # init_sentry() + PII scrubbing hook
└── i18n.py            # SupportedLocale = Literal["en", "uk"]; mirror with frontend

db/
├── base.py            # DeclarativeBase
├── session.py         # AsyncSessionLocal + get_session
└── outbox.py          # transactional outbox helpers (for guaranteed delivery)

modules/<name>/         # ONE per domain area; create with `make new-module NAME=<name>`
├── router.py          # FastAPI APIRouter (HTTP layer ONLY)
├── service.py         # business logic; takes repo + other services
├── repository.py      # SQLAlchemy queries; no business rules
├── schemas.py         # Pydantic DTOs (Create / Update / Response)
├── models.py          # SQLAlchemy 2 Mapped[...] classes
├── tasks.py           # arq jobs (only if needed)
└── tests/
    ├── unit/          # pure logic, mocks at boundary
    └── integration/   # real Postgres + Redis via testcontainers

workers/
└── main.py            # arq WorkerSettings.functions = [job1, job2, ...]

cli/
└── admin.py           # typer commands: create-admin, set-role, list-users, sync-permissions

main.py                # FastAPI app + middleware + lifespan + router includes
```

**Layered law (never break)**:
- `router.py` → calls service. Never imports SQLAlchemy / runs queries.
- `service.py` → calls repository, other services, external clients. Never imports FastAPI primitives.
- `repository.py` → only SQLAlchemy queries. No `if`-business-rules.

If a function feels like it belongs nowhere — it's probably a missing service method.

---

## 3. Frontend file layout (`apps/web/src/`)

```
app/
└── [locale]/                     # next-intl URL prefix (en|uk); ALL routes live here
    ├── layout.tsx                # html lang={locale} + NextIntlClientProvider + Providers
    ├── page.tsx                  # / → redirect to /login or /dashboard
    ├── (auth)/login/             # public route
    │   ├── page.tsx              # Server Component, layout
    │   └── LoginForm.tsx         # "use client", react-hook-form
    ├── (app)/                    # protected; layout.tsx checks session.accessToken
    │   ├── layout.tsx            # SideNav (≥lg) + TopBar (lg:hidden) + main padding
    │   ├── dashboard/page.tsx
    │   ├── profile/              # change own password
    │   └── admin/
    │       ├── users/            # list + new + [id]
    │       └── roles/            # list + new + [id] (system roles immutable)
    └── actions/locale.ts         # setUserLocale server action

components/
├── ui/                           # shadcn primitives (owned-code, via `npx shadcn add ...`)
├── auth/
│   ├── PermissionGuard.tsx       # server component; locale-aware redirect
│   ├── PermissionPicker.tsx      # group permissions by resource + tooltips
│   └── LogoutButton.tsx          # client; signOut({ callbackUrl: `/${locale}/login` })
├── nav/
│   ├── NavContent.tsx            # shared body (header + nav links + footer)
│   ├── SideNav.tsx               # `hidden lg:flex sticky`
│   ├── MobileNav.tsx             # client; Sheet drawer with hamburger
│   └── TopBar.tsx                # `lg:hidden sticky`; contains MobileNav
├── i18n/LanguageSwitcher.tsx     # DropdownMenu + setUserLocale + router.replace
├── theme-provider.tsx            # next-themes wrapper
├── theme-toggle.tsx              # DropdownMenu Light/Dark/System (i18n labels)
└── providers.tsx                 # SessionProvider + ThemeProvider

i18n/
├── routing.ts                    # locales: ["en", "uk"], defaultLocale, localeCookie
├── request.ts                    # getRequestConfig — loads messages/<locale>.json
└── navigation.ts                 # locale-aware Link, redirect, useRouter, usePathname

lib/
├── api/
│   ├── client.ts                 # browser-side openapi-fetch (NEXT_PUBLIC_API_URL)
│   ├── server.ts                 # server-side w/ auth middleware (INTERNAL_API_URL)
│   ├── internal.ts               # no auth (used by NextAuth callbacks)
│   └── schema.ts                 # AUTO-GENERATED by `make api-client` — do not hand-edit
├── auth.ts                       # NextAuth config + jwt callback w/ silent token refresh
├── errors.ts                     # backend code → translation key map (errorToKey)
└── utils.ts                      # cn(), small helpers

middleware.ts                     # MUST live in src/, NOT repo root; next-intl middleware

messages/
├── en.json                       # source of truth for keys
└── uk.json                       # MUST contain every key from en.json
```

---

## 4. Mandatory rules — never break these

These are blocking issues at PR review. Each rule has a one-line "why" so edge cases can be judged.

### Responsive design
- 320px must work without horizontal scroll, overlap, or unreachable controls.
- Sidebar: `hidden lg:flex` only (≥1024px). Below — shadcn `<Sheet side="left">` drawer with hamburger in `<TopBar lg:hidden>`.
- Tables: secondary cols `hidden sm:table-cell` or `hidden md:table-cell`. Phone shows essential identification + actions.
- Touch targets ≥ 44px on mobile (default shadcn `<Button>` is fine; bare `<a>` needs `py-3` or wrap in `<Button>`).
- Audit before PR: `grep -rnE 'className=.*\bw-(48|56|60|64|72|80|96)\b' apps/web/src` → matches only inside `lg:`/`xl:` modifiers (or `size-*` icon utilities).

### i18n
- Every user-facing string via `t('key')` from `useTranslations()` (Client) or `getTranslations()` (Server).
- Keys MUST exist in every `messages/<locale>.json`. If you don't speak the language, add the English text with `[NEEDS TRANSLATION: <lang>]` marker.
- Variables via ICU MessageFormat: `t('greeting', { name })` ↔ `"greeting": "Hello {name}"`.
- Backend returns short error codes (e.g. `email_already_exists`); frontend maps via `lib/errors.ts` → key → `t(...)`.
- Per-user locale persists in `users.locale` (cross-device sync); cookie `NEXT_LOCALE` is fallback for unauth.

### Validation (mandatory)
- Every input form MUST use `react-hook-form` + `zod` resolver. Raw `<form action={serverAction}>` is OK only for one-input pseudo-forms (logout, locale switcher), never for feature forms.
- Frontend zod schema mirrors backend Pydantic DTO 1-to-1 (fields, min/max, regex). Backend = source of truth; frontend = UX layer.
- Inline field errors via shadcn `<FormMessage>`. Submit-level errors via `sonner` toast (`toast.error(t(errorToKey(code)))`).
- Pydantic DTOs: `model_config = ConfigDict(extra="forbid")` + strict types (`SupportedLocale`, `EmailStr`, `Field(min_length=...)`).
- Audit: `grep -rL 'zodResolver' apps/web/src/app/**/*Form.tsx` → empty.

### No browser dialogs
- `window.alert()`, `window.confirm()`, `window.prompt()` are forbidden — browsers can disable them, breaking flow silently.
- Confirmations → shadcn `<AlertDialog>`. Modal forms → `<Dialog>`. Notifications → `sonner` toast.
- Audit: `grep -rE 'window\.(alert|confirm|prompt)|^\s*(alert|confirm|prompt)\(' apps/web/src` → empty.

### Documentation discipline
Every code change has a docs footprint. Audit before PR:

| Change | Docs to touch |
|--------|---------------|
| Endpoint signature | Router docstring (powers Swagger) + `make api-client` |
| New domain module | `docs/MODULES.md` |
| Cross-cutting concept (auth, RBAC, outbox) | `docs/ARCHITECTURE.md` |
| New convention or `make` target | `CLAUDE.md` |
| New env var / dep | `README.md` + `.env.example` |
| New backend error code | Router docstring + frontend `lib/errors.ts` |
| New i18n string | EVERY `messages/<locale>.json` |

### Auth lifecycle (don't reinvent)
- Backend `access_token` TTL: **15 min**. `refresh_token` TTL: **7 days**.
- NextAuth `jwt` callback (`apps/web/src/lib/auth.ts`) proactively refreshes the access token 30 s before expiry by calling `POST /api/v1/auth/refresh`.
- If refresh fails (refresh expired / backend down), `session.error = "RefreshAccessTokenError"`. `(app)/layout.tsx` redirects to `/login`.
- Result: long-idle sessions (≥ 15 min) refresh transparently, no manual re-login needed.

---

## 5. Component creation cheatsheet

### New backend domain module
```bash
make new-module NAME=foo
# Edits: apps/api/src/api/modules/foo/{router,service,repository,schemas,models,tasks}.py + tests/
make migration NAME="add foo table"
make migrate
```
Then in router add `dependencies=[Depends(require_permission("foo.read"))]` and add the perm to `core/permissions.py > CATALOG`.

### New frontend page (Server Component)
```tsx
// apps/web/src/app/[locale]/(app)/foo/page.tsx
import { setRequestLocale, getTranslations } from "next-intl/server";
import { serverApiClient } from "@/lib/api/server";
import { PermissionGuard } from "@/components/auth/PermissionGuard";

export default async function FooPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("foo");

  const { data, error } = await serverApiClient.GET("/api/v1/foo");

  return (
    <PermissionGuard required="foo.read" locale={locale}>
      {/* render data */}
    </PermissionGuard>
  );
}
```

### New frontend form (Client Component, validated)
```tsx
"use client";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslations } from "next-intl";
import {
  Form, FormControl, FormField, FormItem, FormLabel, FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const Schema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
});
type FormData = z.infer<typeof Schema>;

export function FooForm() {
  const t = useTranslations("foo.create");
  const form = useForm<FormData>({
    resolver: zodResolver(Schema),
    defaultValues: { name: "", email: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    // call server action, handle error via toast.error(t(errorToKey(code)))
  });

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="grid gap-4">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("name")}</FormLabel>
              <FormControl><Input {...field} /></FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? t("submitting") : t("submit")}
        </Button>
      </form>
    </Form>
  );
}
```

### New shadcn primitive
```bash
cd apps/web && npx shadcn@latest add <name>
# NEVER `pnpm dlx` — msw build script blocks pnpm dlx isolated env
```
Add the radix dep gets installed automatically.

### New i18n key
1. Add to `apps/web/messages/en.json` (under existing namespace, e.g. `users.create.email`).
2. Add to `apps/web/messages/uk.json` with translation OR `[NEEDS TRANSLATION]` marker.
3. Use `t('users.create.email')` in the component.

If new locale entirely: edit `apps/web/src/i18n/routing.ts > locales`, then `apps/api/src/api/core/i18n.py > SupportedLocale`, then create `messages/<code>.json`.

---

## 6. Sub-agents and slash-commands

**Slash-commands** (`.claude/skills/`):
- `/project-overview` — this skill
- `/sidis-start-task <JIRA-ID>` — fetch ticket, switch Jira to In Progress, create branch
- `/sidis-create-pr` — push, open PR with template, assign reviewer, update Jira
- `/sidis-code-review [PR# | branch]` — invoke sidis-reviewer agent
- `/sidis-estimate-task <JIRA-ID>` — Planning Poker prep
- `/sidis-decompose-story <JIRA-ID>` — break story into BE/FE/QA subtasks
- `/sidis-hotfix <JIRA-ID>` — P0/P1 incident flow
- `/sidis-onboard-project` — guided onboarding
- `/sidis-commit` — Conventional commit from staged diff

**Sub-agents** (`.claude/agents/`):
- `sidis-orchestrator` — master coordinator. Use PROACTIVELY for full Jira-task flow (plan → branch → implement → test → review → PR). Delegates to specialists.
- `sidis-backend` — Python+FastAPI implementation
- `sidis-frontend` — Next.js+shadcn implementation (knows the responsive/i18n/validation rules)
- `sidis-tester` — pytest + Playwright (separately, never same turn as implementation per AI rule 10.4)
- `sidis-reviewer` — code review per Sidis Dev Process § 6.3
- `sidis-planner` — story decomposition + estimation
- `sidis-hotfix` — P0/P1 incident commander
- `sidis-onboarder` — onboarding walk-through

**Updating skills/agents**:
```bash
make sync-claude-skills     # pulls latest sidis-*.md from ../sidis-claude-skills
```
`project-overview.md` is project-local — sync does NOT overwrite it.

---

## 7. When in doubt

- Read the **reference module** in `apps/api/src/api/modules/users/` — it's the canonical example for backend modules.
- Read the **reference page** in `apps/web/src/app/[locale]/(app)/admin/users/` — canonical for frontend list + form pages.
- Run `make help` to see all Make targets.
- Read `CLAUDE.md` for Sidis § 11 (Frontend UX & i18n) and § 12 (Documentation discipline).
- If the rule is silent on your case, ask in PR comment — adding a precedent is better than guessing.
