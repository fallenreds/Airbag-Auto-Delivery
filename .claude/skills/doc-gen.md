---
name: doc-gen
description: Analyzes the entire project (frontend routes, backend endpoints, UI states), AUTO-SEEDS varied test data via REST API (all enum statuses, roles, types — no user prompt needed), then takes 4–9 Playwright screenshots per feature covering every UI state (empty, filled-list, filtered, search, modal-open, form-error, edit-form, row-actions, confirm-dialog) with red annotations, and creates/updates as-built requirement documentation in Confluence. Page structure: Призначення → Вимоги ("Система має можливість..." numbered points, screenshot inline after each relevant point) → Use Cases → Поля/Валідація → Бізнес-правила → i18n → API. Idempotent — first run creates everything, subsequent runs detect changed code via git diff + SHA256 and update only affected features. Trigger via /doc-gen or when user says "задокументуй", "generate docs", "update Confluence documentation", "create user documentation", "напиши документацію".
---

# doc-gen

You generate and maintain **as-built feature documentation** in Confluence: what the system does
*right now*, illustrated with real annotated screenshots placed directly next to the text they
illustrate. This is not an end-user guide and not a future-state spec — it answers
*"how does this actually work?"* for every possible requirement and Use Case.

**Key principle:** Before taking screenshots, automatically seed the system with varied realistic
test data — no user action required. Every list/table must show 5–10 filled rows covering all
enum values. Every feature gets 4–9 screenshots showing distinct UI states.

---

## Phase 0 — Load / initialize state

### 0.1 Check for `.docgen/doc-structure.json`

```bash
test -f .docgen/doc-structure.json && echo EXISTS || echo NEW
```

**If NEW (first run):**
Initialize an empty structure in memory:
```json
{
  "schemaVersion": "1.0",
  "project": { "name": "", "rootPath": "", "repos": [], "run": {} },
  "confluence": {
    "cloudId": "", "spaceKey": "", "spaceId": "", "rootPageId": "",
    "languages": [], "languageRootPageIds": {},
    "apiUpload": { "email": "", "token": "", "baseUrl": "" }
  },
  "auth": { "testCredentials": [] },
  "testData": { "seeded": {}, "seededAt": "" },
  "lastRun": { "timestamp": "", "commits": {} },
  "features": []
}
```

**If EXISTS (incremental run):**
```bash
cat .docgen/doc-structure.json
```
Extract: `lastRun.commits`, `auth.testCredentials`, `confluence.*`, `project.run`,
`testData.seeded`, `features[].codeRefs`, `features[].codeHashes`.

### 0.2 Schema migration

If file exists but lacks top-level keys, add them with empty defaults. Never crash on missing fields.

---

## Clarification dialog

Ask **only** what is missing from `doc-structure.json`. One question at a time.

| What to ask | When | Where to store |
|---|---|---|
| Path(s) to the repository / monorepo root | not in file | `project.rootPath` + `project.repos[]` |
| Command(s) to start the app locally | `project.run.startCommands` missing | `project.run` |
| Confluence Space | **always ask** (confirm current or ask new) | `confluence.spaceKey` |
| Documentation language(s) | `confluence.languages` missing | `confluence.languages` (default: `["uk"]`) |
| Test credentials for app login (email + password per role) | `auth.testCredentials` empty | `auth.testCredentials[]` |
| **Atlassian API token** | `confluence.apiUpload.token` missing or empty | `confluence.apiUpload` |
| Scope: specific features/modules to document | optional — user may narrow scope | runtime-only |

### Atlassian API token prompt

When `confluence.apiUpload.token` is missing or empty, ask:

```
To upload screenshots to Confluence I need an Atlassian API token.

Generate one at: https://id.atlassian.com/manage-profile/security/api-tokens
→ "Create API token" → copy.

Please provide:
  1. Your Atlassian account email   (e.g. you@company.com)
  2. The API token
  3. Your Confluence base URL       (e.g. https://your-org.atlassian.net)
```

Store as:
```json
"confluence": {
  "apiUpload": {
    "email": "<atlassian-email>",
    "token": "<api-token>",
    "baseUrl": "https://your-org.atlassian.net"
  }
}
```

> 📁 **File storage policy:**
> - All working files go into `.docgen/` folder (screenshots, logs, temp files)
> - `.docgen/**` is in `.gitignore` — nothing is committed except one file
> - `doc-structure.json` **IS committed** to git (tracks feature inventory and hashes for incremental runs)
> - The Atlassian token stored in `doc-structure.json` must be removed before committing — store separately in `.env`
> - After Phase 0, always run: `git add .docgen/doc-structure.json` to stage only the JSON structure

After collecting everything, show summary and wait for confirmation:
```
Ready to start doc-gen run:
  Project:    <name> at <rootPath>
  Confluence: <spaceKey>
  Languages:  <uk, en, ...>
  Mode:       <first run | incremental — N features changed>

Proceed? (y / change something / abort)
```

---

## Phase A — Project analysis

**Goal:** build a complete feature map with code mapping. Read files in parallel where possible.

### A.1 Discover services

- Scan `project.repos[]` (or project root), detect stack by markers (`package.json`,
  `pyproject.toml`, `docker-compose.yml`, `.env.example`)
- Read `Makefile` for start commands and port numbers

### A.2 Frontend analysis (Next.js App Router)

- Walk `apps/web/src/app/`, collect `page.tsx`/`layout.tsx`/`route.ts` — extract URL segments
  and protected/public status from parent layouts
- Find modals: grep for `import.*Dialog`, `import.*Sheet`, `import.*AlertDialog` from shadcn/ui
- Find dropdowns: grep for `import.*DropdownMenu`, `import.*Select`, `import.*Combobox`
- Extract forms: grep for `useForm`, `zodResolver` — collect field names + zod validation rules
- Collect i18n strings: read `apps/web/messages/*.json`
- Identify role-based rendering: grep for `RoleGuard`, `hasRole`, `require_permission`

### A.3 Backend analysis (FastAPI)

- Read `apps/api/src/*/main.py` → get list of registered routers
- For each router: extract `@router.get/post/put/patch/delete` with paths and
  `Depends(require_permission(...))` dependencies
- Extract input/output Pydantic schemas for each endpoint
- Build permission map: permission slug → roles

### A.4 UI state analysis

For each page/component: grep for `isLoading`, `isPending`, `error`, `data?.length === 0`,
`disabled`, `.skeleton`, conditional JSX → build state list per component.

### A.5 Frontend ↔ Backend mapping

Grep for API client calls (`client.GET`, `client.POST`, `fetchClient`) → map to backend endpoints.

### A.6 Use Cases derivation

For each feature: derive primary flow, alternative flows, and error flows (edge cases).

### A.7 Code mapping

Each feature gets `codeRefs` — list of files by repo that implement it.

---

## Phase B — Documentation plan

### B.1 Feature tree

Create hierarchical list: top-level features → sub-features.

Naming: human-readable function names, not tech terms.
- ✓ "Авторизація", "Управління завданнями", "Адмін: управління користувачами"
- ✗ "AuthRouter", "PUT /api/v1/users/{id}"

### B.2 Per-feature plan

For each feature document:
- **Вимоги** (Requirements): numbered list of system capabilities, each phrased as
  "Система має можливість [дія]..." — describe what IS, not what should be
- Use Cases (with type: primary / alternative / error)
- UI states
- Fields + validation (if form)
- Business rules and edge cases
- i18n messages
- API integrations
- **Screenshot plan**: for each screenshot — which **requirement number or UC step** it
  illustrates, route, interaction steps, selectors to annotate, annotation type

### B.3 Screenshot placement rule

Each screenshot in the plan carries a `"placement"` field:
```json
{
  "id": "...",
  "placement": { "section": "requirements", "item": "1.2" },
  ...
}
```
or
```json
{
  "placement": { "section": "use-cases", "uc": "UC-1", "step": 3 }
}
```
This determines exactly where in the page the image is embedded.

### B.4 Incremental delta (incremental mode only)

```bash
git diff <lastRun.commits.REPO>..HEAD --name-only
```

Intersect changed files with `features[].codeRefs` → set of affected feature IDs.
Fallback: SHA256 comparison of `codeRefs` files vs stored `codeHashes`.

Detect new features (new routes/endpoints absent from `features[]`) → add to plan.
Detect deleted features → ask user before archiving/deleting Confluence page.

If nothing changed: "Nothing changed since last run at <timestamp>. Skipping update."

---

## Phase B.5 — Auto-seed test data (runs automatically before screenshots)

**Goal:** populate the system with varied, realistic records so every list/table page shows
filled content in screenshots. **No user prompt required** — runs unconditionally before Phase C.

### B.5.1 Authenticate to the backend API

Get a short-lived access token using the credentials from `auth.testCredentials[0]`
(the first admin-level credential):

```python
import json, urllib.request

def api_login(base_url, email, password):
    req = urllib.request.Request(
        f"{base_url}/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)["access_token"]
```

### B.5.2 Read OpenAPI spec to discover schemas and enums

```bash
curl -s <project.run.baseUrl>/openapi.json -o /tmp/openapi.json
```

Parse to extract for each schema:
- All enum fields and their possible values (e.g. `status`: DRAFT, QUEUED, ACCEPTED…)
- Required fields and their types
- min/max length constraints
- Fields marked as `extra_forbidden` (to avoid 422 errors)

### B.5.3 Check existing data and decide what to seed

For each entity the feature touches:
```bash
# Check how many records exist and which enum values are covered
curl -s -H "Authorization: Bearer <token>" \
  "<baseUrl>/api/v1/<entity>?limit=50"
```

**Skip seeding if** `testData.seeded[entity]` is non-empty AND those IDs still exist in the system.
Otherwise seed to reach minimum coverage.

### B.5.4 Seed missing records

Use Python urllib to POST records. Key rules:

```python
def safe_post(base_url, token, path, payload):
    """POST with auto-retry on 422 (remove forbidden fields) and skip on duplicates."""
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        # Skip silently if duplicate/already exists
        if any(w in body.lower() for w in ["already", "duplicate", "unique", "exists"]):
            return {"_skip": True}
        # On 422: parse detail, remove forbidden fields, retry once
        if e.code == 422:
            detail = json.loads(body).get("detail", [])
            forbidden = {d["loc"][-1] for d in detail if d.get("type") == "extra_forbidden"}
            if forbidden:
                fixed = {k: v for k, v in payload.items() if k not in forbidden}
                return safe_post(base_url, token, path, fixed)
        print(f"  SEED ERR {e.code} {path}: {body[:200]}")
        return None
```

**Seeding strategy by entity type:**

| Entity | Min records | Enum values to cover |
|---|---|---|
| Main entities (tasks, orders, etc.) | 8–10 | ALL status values — one record per status |
| Users | 5–7 | One per system role; include 1 inactive/deactivated |
| Reference data (tags, categories, genres) | 8–10 | Varied names from the domain |
| Integration accounts (Anthropic, etc.) | 3–4 | ACTIVE, DISABLED + one exhausted/inactive |
| Roles | 4–5 | System roles + 2–3 custom roles with different permissions |
| Builder hosts / workers | 2–3 | ONLINE, OFFLINE, DRAINING if applicable |

**Data quality rules:**
- Names and descriptions must be realistic for the domain (e.g. for a game generator: "Lucky Spin Slot Machine", "Sky Aviator Crash Game", not "test1", "test2")
- Vary secondary fields: different types/genres/tags/categories across records
- For users: use realistic email domains and job titles matching roles
- For status coverage: if creating 8 tasks and there are 14 statuses, create 1–2 tasks per major status group (DRAFT, IN_PROGRESS variants, DONE variants, FAILED variants)

**After seeding, save IDs:**
```json
"testData": {
  "seeded": {
    "tasks": ["uuid1", "uuid2", ...],
    "users": ["uuid1", ...],
    "anthropic_accounts": ["uuid1", ...]
  },
  "seededAt": "2026-05-28T14:00:00Z"
}
```

### B.5.5 Error handling

- **422** → parse `detail[]`, remove `extra_forbidden` fields, retry once
- **409 / duplicate** → skip silently
- **Auth error** → re-login with admin credentials, retry
- **Any other error** → log warning, continue with next record
- **Never abort the full run** for one failed seed call
- Print summary: `"Seeded: 8 tasks, 6 users, 3 accounts, 5 roles, 10 tags"`

---

## Phase C — Screenshots (Playwright + annotations)

### C.1 Start the application

```bash
curl -s -o /dev/null -w "%{http_code}" <project.run.readyCheck.url>
```

- Returns 200/302/307 → already running
- Otherwise → run `project.run.startCommands`, poll every 5s up to `timeoutSec`

If startup fails: document text-only, mark all screenshots `"status": "missing"`, continue.

### C.2 Authenticate

Always set viewport to **1440×900** at the start of every browser session:
```
browser_resize: { width: 1440, height: 900 }
```

For each role in `auth.testCredentials` that appears in the feature's Use Cases:
- `browser_navigate` to login page, fill credentials, submit
- Wait for redirect to dashboard

### C.3 Standard screenshot states per feature

For each feature, take screenshots covering the applicable states from this table.
**Not all states apply to every feature** — select based on what the UI actually has.

| # | State | How to reach | fullPage | Annotation target |
|---|---|---|---|---|
| 1 | **empty** | Filter to show 0 results, or navigate before seeding | `true` | `rect` around empty-state block / CTA card |
| 2 | **filled-list** | Navigate to list after seeding (5–10 rows) | `true` | `rect` around entire table/list area |
| 3 | **filtered** | Click a status/type filter chip or select from filter dropdown | `true` | `arrow` → active filter chip; `rect` around filtered results |
| 4 | **searched** | Type query in search field | `true` | `arrow` → search input; `rect` around result rows |
| 5 | **modal-open** | Click "New" / "Add" / "Create" button; fill all form fields with realistic data | `false` (viewport only) | `rect` around the dialog |
| 6 | **form-error** | Submit modal/form with empty required fields or invalid data | `false` | `rect` around the error message(s) |
| 7 | **edit-form** | Navigate to `/entity/{id}/edit` or click "Edit" on a row | `true` | `rect` around the edit form |
| 8 | **row-actions** | Click the `⋯` or kebab-menu icon on a table row | `false` | `arrow` → the open dropdown menu |
| 9 | **confirm-dialog** | Click "Delete" / "Deactivate" / any destructive action → AlertDialog appears | `false` | `rect` around the AlertDialog |

**Selection rules by page type:**

| Page type | Use states |
|---|---|
| Read-only list / dashboard | 1, 2, 3, 4 |
| CRUD admin list page | 1, 2, 3, 5, 6, 7 |
| CRUD with destructive actions | 1, 2, 3, 5, 6, 7, 8, 9 |
| Single-record detail / overview | 7 (filled form / detail view) |
| Forms without list | 5 (filled), 6 (error) |
| Tabs / multi-section pages | 2 per tab (overview + one detail tab) |

**Between screenshots of the same page:** navigate away and back to reset state cleanly.

**Filename convention:** `<feature-id>-<state>.png` (e.g. `admin-users-filled.png`, `admin-users-modal-open.png`, `admin-users-form-error.png`)

**Step 1 — Navigate:**
```
browser_navigate: { url: "<baseUrl><route>" }
```

**Step 2 — Reach target state:**
Use `browser_click`, `browser_type`, `browser_fill_form`, `browser_select_option`,
`browser_wait_for`. For error states: submit with empty/invalid data. For modal states:
fill ALL visible form fields with realistic data before taking the screenshot.

**Step 3 — Get bounding boxes:**
```javascript
// via browser_evaluate
document.querySelector('<CSS_SELECTOR>').getBoundingClientRect()
```

**Step 4 — Take screenshot:**
```
browser_take_screenshot → .docgen/screenshots/<feature-id>-<state>-raw.png
```
Use `fullPage: true` for list/form pages. Omit (viewport only) for modals/dialogs.

**Step 5 — Annotate with Pillow:**
```bash
python3 - <<'PYEOF'
import math, json, sys
from PIL import Image, ImageDraw

data = json.loads(sys.argv[1])
img = Image.open(data["input"]).convert("RGBA")
overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)
RED = (220, 38, 38, 255)

for i, ann in enumerate(data["annotations"], 1):
    x, y, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
    if ann["type"] == "rect":
        draw.rectangle([x, y, x+w, y+h], outline=RED, width=4)
        if len(data["annotations"]) > 1:
            r = 12
            draw.ellipse([x-r, y-r, x+r, y+r], fill=RED)
            draw.text((x-6, y-10), str(i), fill=(255, 255, 255, 255))
    elif ann["type"] == "arrow":
        cx, cy = x + w/2, y + h/2
        ax, ay = cx - 70, cy - 60
        angle = math.atan2(cy - ay, cx - ax)
        aw = 18
        draw.line([ax, ay, cx, cy], fill=RED, width=3)
        draw.polygon([
            (cx, cy),
            (cx - aw*math.cos(angle-0.4), cy - aw*math.sin(angle-0.4)),
            (cx - aw*math.cos(angle+0.4), cy - aw*math.sin(angle+0.4))
        ], fill=RED)

Image.alpha_composite(img, overlay).convert("RGB").save(data["output"])
print("OK:", data["output"])
PYEOF
```

Check Pillow first: `python3 -c "import PIL"` — if fails, run `pip install pillow -q`.

**Step 6 — Handle failures:**
- 404 / redirect → mark `"status": "missing"`, log, continue
- Modal doesn't open → log, take screenshot of current state, continue
- Never abort the full run for one screenshot failure

### C.4 Shut down

Only if the skill itself started the app:
```bash
# run project.run.shutdownCommands
```

### C.5 Report
```
Screenshot summary:
  ✓ <N> captured and annotated
  ⚠ <M> missing: <list>
  
  Seeding summary:
  ✓ <entity>: <N> records created/verified
```

---

## Phase D — Write to Confluence

### D.1 Screenshot upload — always use curl REST API

**Never use `confluence_attach_file_url` MCP tool** — it cannot access localhost.
Always upload via curl with the API token from `confluence.apiUpload`:

```bash
curl -s \
  -u "<confluence.apiUpload.email>:<confluence.apiUpload.token>" \
  -H "X-Atlassian-Token: no-check" \
  -F "file=@.docgen/screenshots/<filename>.png;type=image/png" \
  "<confluence.apiUpload.baseUrl>/wiki/rest/api/content/<pageId>/child/attachment"
```

Parse the returned JSON to get `results[0].id` → save as `attachmentId` in `doc-structure.json`.

### D.2 Page create/update — always use Confluence REST API storage format

**Never use Rovo MCP `updateConfluencePage` for pages with images** — it rejects `<ac:image>`
tags in HTML mode. Use curl with the `storage` representation instead:

```python
import json, urllib.request, base64

email = "<confluence.apiUpload.email>"
token = "<confluence.apiUpload.token>"
base_url = "<confluence.apiUpload.baseUrl>"
page_id = "<pageId>"
version = <current_version + 1>

b64 = base64.b64encode(f"{email}:{token}".encode()).decode()
storage_body = """<STORAGE_FORMAT_BODY>"""

payload = {
    "version": {"number": version},
    "title": "<title>",
    "type": "page",
    "body": {"storage": {"value": storage_body, "representation": "storage"}}
}

req = urllib.request.Request(
    f"{base_url}/wiki/rest/api/content/{page_id}",
    data=json.dumps(payload).encode(),
    method="PUT"
)
req.add_header("Authorization", f"Basic {b64}")
req.add_header("Content-Type", "application/json")

with urllib.request.urlopen(req) as resp:
    result = json.load(resp)
    print("OK — version:", result["version"]["number"])
```

For **creating** a new page use `POST` to `/wiki/rest/api/content` with `ancestors: [{"id": parentId}]`.

To get the current version before update:
```bash
curl -s -u "<email>:<token>" \
  "<baseUrl>/wiki/rest/api/content/<pageId>?expand=version" | python3 -c "import json,sys; print(json.load(sys.stdin)['version']['number'])"
```

### D.3 Find or create root page

Use Rovo MCP `searchConfluenceUsingCql` to find existing pages (read-only calls work fine).

```
searchConfluenceUsingCql: "title = "Документація" AND space = "<spaceKey>" AND type = page"
```

If not found → create via REST API. Save `rootPageId` and `languageRootPageIds` to file.

### D.4 Page template — storage format

Embed images inline using `<ac:image>` macros — **the only way images display in Confluence**:
```xml
<ac:image ac:width="900"><ri:attachment ri:filename="<filename>.png" /></ac:image>
```

**Full page structure (Ukrainian):**

```xml
<h2>Призначення</h2>
<p>[Навіщо функція, яку задачу вирішує, для кого]</p>

<h2>Доступ і передумови</h2>
<ul>
  <li>[роль/права, умова доступу]</li>
</ul>

<h2>Вимоги</h2>
<p>Нумеровані пункти описують реалізовані можливості системи.</p>

<h3>1. [Назва можливості]</h3>
<p>Система має можливість [опис дії/поведінки].</p>
<p>[Умови відображення / поведінка стану / валідація якщо стосується цього пункту]</p>
<!-- screenshot directly here if it illustrates this requirement -->
<p><em>[caption: state name + what it shows]</em></p>
<ac:image ac:width="900"><ri:attachment ri:filename="<feature-id>-<state>.png" /></ac:image>

<h3>2. [Наступна можливість]</h3>
<p>Система має можливість [опис].</p>
<!-- screenshot here if relevant -->

<h2>Сценарії використання (Use Cases)</h2>

<h3>UC-1. [Назва]</h3>
<p><strong>Тип:</strong> основний | <strong>Передумова:</strong> [умова]</p>
<ol>
  <li>[крок 1]</li>
  <li>[крок 2 — якщо є скріншот для цього кроку, він йде одразу після]</li>
</ol>
<!-- screenshot for a specific UC step goes directly after that step's <li> in an outer <p> -->
<p><strong>Очікуваний результат:</strong> [результат]</p>

<h2>Поля та валідація</h2>   <!-- only if feature has a form -->
<table>
  <tbody>
    <tr><th>Поле</th><th>Тип</th><th>Обов'язкове</th><th>Ліміт</th><th>Валідація</th></tr>
    <tr><td>...</td><td>...</td><td>...</td><td>...</td><td>...</td></tr>
  </tbody>
</table>

<h2>Бізнес-правила та обмеження</h2>
<ul>
  <li>[правило]</li>
</ul>

<h2>Системні повідомлення (i18n)</h2>
<table>
  <tbody>
    <tr><th>Ключ</th><th>Тип</th><th>uk</th></tr>
    <tr><td><code>key</code></td><td>тип</td><td>Текст</td></tr>
  </tbody>
</table>

<h2>API та інтеграції</h2>   <!-- only if applicable -->
<table>
  <tbody>
    <tr><th>Метод</th><th>Шлях</th><th>Повертає</th><th>Коли</th></tr>
    <tr><td>POST</td><td><code>/api/v1/...</code></td><td>...</td><td>...</td></tr>
  </tbody>
</table>

<h2>Пов'язані сторінки</h2>
<ul>
  <li><a href="[url]">[Батьківська сторінка]</a></li>
</ul>

<hr />
<ac:structured-macro ac:name="note">
  <ac:rich-text-body>
    <p><em>Службовий блок:</em> Згенеровано з коду гілки <code>main</code>.
    Оновлено: [date].<br/>
    Код: <code>[repo/paths]</code></p>
  </ac:rich-text-body>
</ac:structured-macro>
```

**English (en):** same structure, headings: Purpose, Access & Prerequisites, Requirements,
Use Cases, Fields & Validation, Business Rules, System Messages, API & Integrations,
Related Pages.

### D.5 Screenshot placement rules

- Each screenshot appears **immediately after** the text of the requirement item or UC step
  it illustrates — never collected into a separate "Screenshots" section
- Caption (`<p><em>...</em></p>` before the image): state name + what it shows
- Width: **900px** (`ac:width="900"`)
- Red rectangles = highlight areas; red arrows = point at small elements
- Multiple annotations on one screenshot are numbered

### D.6 Destructive operations

If a feature's code files are deleted → ask user before touching Confluence:
```
Feature "<id>" code is gone. What to do with Confluence page "<title>"?
(1) Archive/delete  (2) Keep as-is  (3) Mark as [ARCHIVED] in title
```

---

## Phase E — Save state

### E.1 Update `doc-structure.json`

For each processed feature:
- `confluencePages` — pageId per language
- `codeRefs` + `codeHashes` (SHA256):
  ```bash
  sha256sum <file> | awk '{print $1}'
  ```
- `screenshots[]` — route, interaction, state, `placement` (section + item/step),
  annotations (selector + type + bbox), `attachmentIds` per language, `confluenceFilename`, `status`
- `sourceCommits` — HEAD per repo:
  ```bash
  git -C <repo.path> rev-parse HEAD
  ```
- `lastUpdated` — ISO timestamp

Top-level: `lastRun.timestamp` + `lastRun.commits` + `testData` (seeded IDs + seededAt).

### E.2 Protect credentials

```bash
grep -q "^\.docgen/" .gitignore || echo ".docgen/" >> .gitignore
```

### E.3 Write file

```bash
mkdir -p .docgen
```
Write pretty-printed JSON (2-space indent). **Never commit. Never put in Confluence.**

---

## Final report

```
✓ doc-gen complete

  Confluence space: <spaceKey>
  Languages: <uk, en, ...>
  Mode: <first run | incremental>

  Pages created:  <N>
  Pages updated:  <M>
  Screenshots:    <K> captured (avg <K/N> per page), <L> missing

  Test data seeded:
    <entity>: <N> records
    ...

  State saved: .docgen/doc-structure.json

  ⚠ Missing screenshots:
    - <feature-id>/<state>: <reason>
```

---

## Edge cases

| Situation | Behavior |
|---|---|
| App doesn't start | Text-only docs, all screenshots `missing`, report to user |
| Modal/dropdown doesn't open | Log warning, screenshot current state, continue |
| `confluence_attach_file_url` | Never use — always use curl REST API for uploads |
| Rovo MCP `updateConfluencePage` for pages with images | Never use — always use curl PUT with storage format |
| Feature deleted from code | Ask user before archiving/deleting Confluence page |
| New feature (not in doc-structure.json) | Auto-create, add to `features[]` |
| Multiple languages | Update all languages in the same run |
| Credentials already in file | Reuse, never ask again |
| Pillow not available | `pip install pillow -q`, retry |
| Confluence 429 | Back off 10s, retry up to 3 times |
| Seed 422 error | Parse detail[], remove `extra_forbidden` fields, retry once |
| Seed duplicate | Skip silently, log "already exists" |
| Existing seeded data | Check IDs still exist in system before skipping re-seed |

## What NOT to do

- Do NOT modify application source code
- Do NOT commit `.docgen/doc-structure.json`
- Do NOT delete Confluence pages without user confirmation
- Do NOT collect screenshots into a separate section — embed each one inline after its text
- Do NOT use `<img src="...">` tags — use `<ac:image>` storage format macros
- Do NOT use Rovo MCP `updateConfluencePage` for pages that have or will have images
- Do NOT hardcode project-specific paths — derive from `doc-structure.json` or analysis
- Do NOT skip a language — all `confluence.languages` must be updated in the same run
- Do NOT take only 1 screenshot per feature — aim for 4–6 covering distinct states
- Do NOT take screenshots of empty tables — always seed data first (Phase B.5)
- Do NOT skip seeding even if some data already exists — verify enum coverage
