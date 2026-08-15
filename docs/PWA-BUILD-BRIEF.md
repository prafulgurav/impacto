# GlobalPulse India — PWA Build Brief

**Hand this document to Claude Code.** It is written to be executable, not
inspirational. Every phase has acceptance criteria a machine can check.

- **Target:** installable, offline-first PWA on top of the existing
  `globalpulse-india` Python engine
- **Stack:** Next.js 16.3 (current LTS, Aug 2026) + React 19 + TypeScript,
  Serwist service worker, FastAPI + Postgres + Redis backend
- **Primary device:** ₹12–18k Android on 4G in an Indian metro. Not a MacBook.
- **Version note for Claude Code:** verify every package version against npm at
  build time. Versions below are correct as of 15 Aug 2026 and will drift.

---

## 0. Read this before writing any code

### What already exists (do not rebuild)

The `globalpulse-india` repo contains a working Python engine:

| Component | Location | Status |
|---|---|---|
| Transmission map (15 archetypes, 11 channels, 55 rules) | `knowledge/*.yaml` | Done, schema-validated |
| Market-model event study (AR/CAR/CAAR, t-tests) | `src/globalpulse/eventstudy/` | Done, 86 tests |
| Analog engine + calibration report | `src/globalpulse/eventstudy/analogs.py` | Done |
| Impact scoring | `src/globalpulse/impact/engine.py` | Done |
| Alerts, digest, grounded explainer | `src/globalpulse/{alerts,explain}/` | Done |
| FastAPI surface | `src/globalpulse/api/app.py` | Done, needs hardening |
| Compliance guardrails | `src/globalpulse/explain/guardrails.py` | Done, blocking |

**Never reimplement the statistics in TypeScript.** `scipy.stats.linregress` and
the t-distribution CDF are load-bearing. The web tier is a rendering and caching
layer over a Python compute service.

### The three non-negotiables

1. **Compliance.** No forward-looking statement about any named security or
   index may ever render. No buy/sell/hold language. This is enforced in the
   Python guardrail *and* must be enforced again on UI copy (Phase 7). Under
   SEBI's Research Analyst and Investment Adviser regulations this is not a
   styling preference — it is the difference between a legal product and an
   unregistered one. See `COMPLIANCE.md` in the engine repo.
2. **Every number carries its sample size and its uncertainty.** A median with
   no `n` and no p-value is not shippable. If `p > 0.10`, the UI must say the
   distribution is not distinguishable from noise, in the same visual block as
   the number — not in a footnote.
3. **Performance on a cheap Android phone.** Budgets in §8 are gates, not goals.
   CI fails the build if they regress.

---

## 1. Repository layout

Add the web app **inside the existing engine repo**. One repo, one CI, types
generated from the live OpenAPI schema — this eliminates the single most common
failure mode in split-stack projects (frontend types drifting from backend
reality).

```
globalpulse-india/
├── src/globalpulse/          # existing Python engine (unchanged core)
│   ├── api/                  # EXTEND: auth, push, SSE, rate limits
│   ├── db/                   # NEW: SQLAlchemy models, Alembic migrations
│   ├── jobs/                 # NEW: nightly precompute, digest generation
│   └── ...
├── knowledge/                # existing YAML knowledge base
├── tests/                    # existing pytest suite — keep green
├── web/                      # NEW: Next.js 16 PWA
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   ├── types/api.d.ts        # GENERATED from OpenAPI — never hand-edit
│   └── tests/
├── docker-compose.yml        # EXTEND: postgres, redis, web
└── CLAUDE.md                 # persistent instructions (provided separately)
```

**Type generation is mandatory and automated:**

```bash
# web/package.json
"gen:types": "openapi-typescript http://localhost:8000/openapi.json -o types/api.d.ts"
```

CI regenerates and fails on any diff. If the Python API changes shape, the
frontend build breaks immediately rather than at runtime in a user's hand.

---

## 2. Backend work required (Phase 1–2)

The current FastAPI app is a demo surface. It needs six things before a PWA can
sit on it.

### 2.1 Persistence — Postgres via SQLAlchemy 2.0 + Alembic

```sql
-- Auth
users(id uuid pk, email citext unique, created_at, last_seen_at,
      locale text default 'en-IN', tz text default 'Asia/Kolkata')
sessions(id uuid pk, user_id fk, refresh_token_hash text, expires_at, user_agent, ip_hash)

-- Personalisation
watchlist_archetypes(user_id fk, archetype_id text, min_severity text,
                     PRIMARY KEY(user_id, archetype_id))
holdings(id uuid pk, user_id fk, symbol text, weight numeric,
         created_at, updated_at)          -- see §2.6 on encryption
push_subscriptions(id uuid pk, user_id fk, endpoint text unique,
                   p256dh text, auth text, ua text, created_at, failed_count int default 0)

-- Precomputed analytics (the hot read path)
analog_summaries(archetype_id text, target text, window text, as_of date,
                 sample_size int, mean_car_bps numeric, median_car_bps numeric,
                 stdev_bps numeric, hit_rate numeric, p5_bps numeric, p95_bps numeric,
                 t_stat numeric, p_value numeric, analogs jsonb,
                 PRIMARY KEY(archetype_id, target, window, as_of))
detected_events(event_id text pk, archetype_id text, event_date date, headline text,
                sources jsonb, match_score numeric, surprise_magnitude numeric,
                created_at)
daily_digests(digest_date date pk, payload jsonb, generated_at)
calibration_runs(id uuid pk, window text, run_at, summary jsonb, rows jsonb)

-- SEBI: 5-year retention of every generated output and its citations
audit_log(id uuid pk, user_id fk null, kind text, question text, answer text,
          citations jsonb, compliance_flags jsonb, model text, used_llm bool,
          created_at timestamptz)
```

Indexes: `detected_events(event_date desc)`, `analog_summaries(archetype_id, target)`,
`audit_log(created_at)` with a partition or retention policy at 5 years + 1 day.

### 2.2 Nightly precompute job

The API currently computes analog summaries on request — ~20 seconds for a full
calibration sweep. That is fine for a CLI and unacceptable for a mobile request.

```
jobs/precompute.py       runs 02:00 IST daily
  for archetype in 15:
    for target in archetype.impacts:
      for window in ["T+0","T+0..T+3","T+1..T+5","T+0..T+10","T+1..T+21"]:
        upsert analog_summaries(..., as_of=today)
  → ~375 rows. Under 2 minutes. Trivial.

jobs/ingest.py           runs every 30 min during 06:00–23:00 IST
  fetch GDELT + RSS → classify → upsert detected_events
  → on new event above severity threshold, enqueue push fan-out

jobs/digest.py           runs 07:30 IST weekdays
  build digest for the trailing session → daily_digests
  → enqueue push to subscribers whose watchlist matches
```

Use **APScheduler** in-process for v1 (single instance, simple). Move to Celery
or Arq only when you have more than one API replica. Do not start with Celery.

### 2.3 Auth — Google OAuth + email magic link

No passwords. Indian mobile users abandon password forms.

- `POST /auth/google` — verify Google ID token, upsert user, return access
  (15 min) + refresh (30 day, httpOnly Secure SameSite=Lax cookie)
- `POST /auth/magic-link` → `POST /auth/verify`
- `POST /auth/refresh`, `POST /auth/logout`
- Anonymous browsing is fully supported. Auth is required **only** for
  watchlist, push subscriptions, and portfolio. Gating the explorer behind a
  login wall would kill the SEO surface, which is the acquisition channel.

Phone OTP is deliberately deferred: it costs ₹0.12–0.25/SMS, needs a DLT
template registration, and adds a vendor dependency for a v1 with no revenue.

### 2.4 Web Push

- `pywebpush` + VAPID keypair in env (`GP_VAPID_PUBLIC_KEY`, `GP_VAPID_PRIVATE_KEY`)
- `POST /push/subscribe`, `DELETE /push/subscribe`
- Payload is **minimal** — `{alertId, archetypeLabel, severity}`. The service
  worker fetches the full alert on notification click. Never put a number in a
  push payload: push bodies are not guardrail-checked at send time and a stale
  figure on a lock screen is exactly the wrong failure mode.
- Prune subscriptions after 3 consecutive `410 Gone` responses.

### 2.5 Streaming explainer

`GET /explain` currently returns a complete object. For chat UX, add
`GET /explain/stream` as **Server-Sent Events**:

```
event: composed      data: {"answer": "...", "citations": [...]}   # instant, grounded
event: token         data: {"t": "..."}                            # LLM narration, if enabled
event: done          data: {"complianceFlags": [], "usedLlm": true, "auditId": "..."}
```

The `composed` event fires immediately with the full deterministic answer. If the
LLM narration succeeds and passes the guardrail, the UI swaps it in. If it fails,
the composed answer is already on screen. **The user never sees a loading spinner
where an answer should be, and never sees an ungrounded answer.** Use SSE not
WebSockets — it survives the mobile network transitions Indian users actually
experience, and it reconnects for free.

### 2.6 Hardening

- **CORS** locked to the web origin. No wildcards.
- **Rate limits** via `slowapi` + Redis: 60 req/min anonymous, 300 authenticated,
  10/min on `/explain/stream` (it costs LLM tokens).
- **Response caching** in Redis: knowledge endpoints 7 days, analogs 24 hours,
  digest 1 hour. `ETag` + `Cache-Control` on every GET so the service worker can
  revalidate cheaply.
- **Holdings encryption:** application-level AES-GCM with a key from env, or
  Postgres `pgcrypto`. Portfolio holdings are financial PII. Log access to
  `audit_log`.
- **Structured JSON logging** with a request ID propagated to the client via
  `X-Request-Id` so a user-reported bug is traceable.
- **`/health` and `/ready`** distinguished — `/ready` checks Postgres and Redis.

---

## 3. API contract the PWA consumes

Existing (keep the shapes; they are already typed by pydantic):

```
GET  /health
GET  /knowledge/archetypes                 → [{id,label,family,description,n_impacts,targets}]
GET  /knowledge/archetypes/{id}            → {..., detection, impacts[]}
GET  /knowledge/channels                   → [{id,name,kind,horizon,description}]
GET  /events?since&until&archetype_id&limit
POST /events/classify?headline
GET  /impact/{event_id}                    → ImpactScore[]
POST /impact/portfolio                     → exposure attribution
GET  /eventstudy?symbol&event_date&window
GET  /analogs?archetype_id&target&window   → AnalogSummary
GET  /calibration?window
GET  /alerts?day&lookback_days&min_severity
GET  /digest?day&lookback_days
GET  /digest.md
GET  /explain?q&as_of&target
```

New for the PWA:

```
POST /auth/google | /auth/magic-link | /auth/verify | /auth/refresh | /auth/logout
GET  /me                                   → {user, watchlist, pushEnabled}
PUT  /me/watchlist                         → {archetypeIds[], minSeverity}
GET  /me/holdings | PUT /me/holdings
POST /push/subscribe | DELETE /push/subscribe
GET  /explain/stream                       → SSE
GET  /bundle/offline?since=<iso>           → delta bundle for IndexedDB sync
```

`GET /bundle/offline` is the offline-first workhorse. It returns everything the
app needs in one round trip, gzipped, with an `ETag`:

```json
{
  "generatedAt": "2026-08-15T02:10:00Z",
  "archetypes": [...],           // full, ~40KB
  "channels": [...],             // full, ~8KB
  "analogSummaries": [...],      // ~375 rows, default window only, ~180KB
  "digest": {...},               // latest
  "recentEvents": [...],         // trailing 30 days
  "disclaimer": "..."
}
```

Target under 300 KB gzipped. If it exceeds that, drop `analogs[]` detail arrays
from the bundle and fetch them per-view.

---

## 4. Frontend architecture

### 4.1 Route map

| Route | Rendering | Auth | Purpose |
|---|---|---|---|
| `/` | Client (cached shell) | No | **Today** — digest, active alerts, watchlist |
| `/explore` | SSG | No | Archetype browser, grouped by family |
| `/explore/[archetype]` | **SSG + ISR 24h** | No | Impact map, channels, distribution. **SEO/GEO surface** |
| `/explore/[archetype]/[target]` | **SSG + ISR 24h** | No | Deep dive: full analog table, event study detail |
| `/ask` | Client | No | Explainer chat, SSE streaming |
| `/portfolio` | Client | **Yes** | Exposure attribution |
| `/calibration` | SSG + ISR 24h | No | The honesty page — every prior scored |
| `/methodology` | Static | No | How CAR is computed, what the windows mean |
| `/compliance` | Static | No | SEBI position, disclaimers, what this is not |
| `/settings` | Client | Partial | Watchlist, notifications, theme, offline status |
| `/offline` | Static | No | Service worker fallback |

**Why SSG on the explore routes matters commercially:** these pages are the free
public surface. They are what Google indexes and what Perplexity/ChatGPT/Claude
cite when someone asks "how do Fed rate hikes affect Indian IT stocks." Every
archetype page must ship complete server-rendered content, `Article` +
`FAQPage` JSON-LD, and an `llms.txt` at the root. That is the acquisition
channel — treat it as a feature, not as SEO chores.

### 4.2 Navigation

Bottom tab bar on mobile (thumb reach), sidebar ≥1024px:

```
Today · Explore · Ask · Portfolio · More
```

Five tabs maximum. `Calibration`, `Methodology`, `Compliance`, `Settings` live
under More.

### 4.3 Key components

| Component | Notes |
|---|---|
| `<ImpactBars>` | Diverging horizontal bars. **Custom SVG, not Recharts.** Bar = encoded prior range; dot = realised median. On <480px, drop to a stacked list with an inline mini-bar per row — a 5-series diverging chart is unreadable at 360px. |
| `<CarDistribution>` | Histogram of analog CARs, median rule, zero reference. Below 480px, switch to a horizontal strip plot (one dot per analog) — histograms need width. |
| `<StatTile>` | label / value / sub. Hero variant for the median. `white-space: nowrap`, proportional figures. |
| `<EvidenceBadge>` | The most important small component. Renders `n=33 · p=0.77 · not distinguishable from noise` and turns muted when `p > 0.10`. Every number on screen is wrapped in one. |
| `<ChannelChip>` | Transmission channel with a tap-to-expand mechanism explanation. |
| `<AmbiguityCallout>` | For `direction: 0` rules. Explicitly says the mechanism cuts both ways. Never collapse this into a sign. |
| `<CitationList>` | Under every explainer answer. Collapsible, defaults open on first use. |
| `<DisclaimerBar>` | Sticky footer on any screen showing a number. Not dismissible. |
| `<OfflineBanner>` | "Showing data from 15 Aug, 02:10. You're offline." Must show **data age**, not just connection state. |

### 4.4 Design tokens

Use the validated palette from the existing dashboard (`ui/index.html`). It has
been run through a colorblindness/contrast validator in both modes — do not
substitute Tailwind defaults.

```css
/* light → dark */
--surface-1:   #fcfcfb → #1a1a19
--plane:       #f9f9f7 → #0d0d0d
--text-primary:#0b0b0b → #ffffff
--text-secondary:#52514e → #c3c2b7
--muted:       #898781 → #898781
--grid:        #e1e0d9 → #2c2c2a
--baseline:    #c3c2b7 → #383835
--border:      rgba(11,11,11,.10) → rgba(255,255,255,.10)

/* diverging pair — polarity, validated CVD-safe in both modes */
--pos:         #2a78d6 → #3987e5      /* historically positive */
--neg:         #e34948 → #e66767      /* historically negative */
--neutral:     #f0efec → #383835      /* two-sided / ambiguous */

/* status — fixed, never themed, always paired with icon + label */
--good #0ca30c  --warning #fab219  --serious #ec835a  --critical #d03b3b
```

**Typography: `system-ui` only.** No webfont. A 40–120 KB font download is the
single easiest win to give up on an Indian 4G connection, and system-ui renders
Devanagari correctly for the future Hindi digest.

Mark specs: bars ≤24px thick with 4px rounded data-ends, 2px lines, ≥8px
markers with a 2px surface ring, 2px surface gap between adjacent bars, hairline
solid gridlines. Text never wears the series colour — identity comes from the
mark beside it.

Dark mode is the default on `/` (users check markets early and late). Respect
`prefers-color-scheme`, allow manual override, persist in `localStorage`.

---

## 5. PWA layer — this is why we're not just building a website

### 5.1 Service worker: Serwist

`next-pwa` is effectively unmaintained. Use **Serwist** (`@serwist/next`), its
maintained successor, which supports the App Router.

Caching strategy per resource — get this table right and everything else follows:

| Resource | Strategy | TTL | Rationale |
|---|---|---|---|
| App shell, JS, CSS, fonts | Precache | build hash | Instant repeat launch |
| `/api/knowledge/*` | StaleWhileRevalidate | 7 days | The transmission map changes on deploy, not hourly |
| `/api/analogs`, `/api/calibration` | CacheFirst | 24 h | Recomputed nightly; serving 12-hour-old stats is correct |
| `/api/digest`, `/api/alerts` | NetworkFirst (3s timeout) | 24 h fallback | Fresh if possible, yesterday's if not — **always labelled with its age** |
| `/api/explain/stream` | **NetworkOnly** | — | Never cache. A stale explanation attached to today's market move is the exact misleading-output failure the compliance layer exists to prevent. |
| `/api/me/*`, `/api/auth/*` | NetworkOnly | — | Never cache auth or PII |
| Images / icons | CacheFirst | 30 days | |

### 5.2 IndexedDB (Dexie 4)

```ts
db.version(1).stores({
  archetypes:      'id, family',
  channels:        'id',
  analogSummaries: '[archetypeId+target+window], archetypeId, asOf',
  digests:         'digestDate',
  events:          'eventId, eventDate, archetypeId',
  holdings:        'symbol',                    // local mirror; server is source of truth
  meta:            'key',                       // lastSyncAt, bundleEtag, schemaVersion
  outbox:          '++id, kind, createdAt'      // queued mutations made offline
})
```

**Sync protocol:** on app open and on `online` event, `GET /bundle/offline` with
`If-None-Match: <bundleEtag>`. On `304`, do nothing. On `200`, write in a single
Dexie transaction and update `meta.lastSyncAt`. Every screen reads from Dexie
first and renders immediately, then reconciles — no loading spinner on a warm
launch, ever.

**Outbox:** watchlist edits and holdings changes made offline queue into
`outbox` and flush via Background Sync (`sync` event, tag `gp-outbox`) with
exponential backoff. Conflict resolution is last-write-wins on `updatedAt`,
which is correct for single-user preference data.

### 5.3 Manifest and install

```json
{
  "name": "GlobalPulse India",
  "short_name": "GlobalPulse",
  "start_url": "/?source=pwa",
  "display": "standalone",
  "background_color": "#0d0d0d",
  "theme_color": "#0d0d0d",
  "orientation": "portrait",
  "categories": ["finance", "news"],
  "icons": [
    {"src":"/icons/192.png","sizes":"192x192","type":"image/png"},
    {"src":"/icons/512.png","sizes":"512x512","type":"image/png"},
    {"src":"/icons/maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
  ],
  "screenshots": [
    {"src":"/screenshots/mobile-today.png","sizes":"1080x1920","form_factor":"narrow"},
    {"src":"/screenshots/wide-explore.png","sizes":"1920x1080","form_factor":"wide"}
  ],
  "shortcuts": [
    {"name":"Today's digest","url":"/"},
    {"name":"Ask why","url":"/ask"}
  ]
}
```

**Install prompt UX — get this right or you burn the one chance you get.**
Capture `beforeinstallprompt`, suppress the default, and show a custom banner
only when *all* of: the user is on their 2nd+ session, has spent >60s total, and
hasn't dismissed it in the last 30 days. Prompting on first paint is the single
most common PWA mistake and permanently poisons the install rate.

### 5.4 Notifications

Request permission **contextually**, never on load: after a user taps "Notify me"
on an archetype in their watchlist. Explain what they'll get and how often
before the browser prompt appears — one pre-permission screen. Default cadence:
one pre-market digest on weekdays, plus `high` severity alerts only. Give a
frequency cap in settings.

### 5.5 iOS reality check — state this to stakeholders now

| Capability | Android/Chrome | iOS/Safari |
|---|---|---|
| Install | Prompt + banner | Manual "Add to Home Screen" only |
| Web Push | Yes | Only if installed to home screen, iOS 16.4+ |
| Periodic Background Sync | Yes | **No** |
| Background Sync | Yes | **No** — flush outbox on next foreground instead |
| Storage eviction | Rare | Possible after 7 days unused |

India skews heavily Android, so a PWA is the right call — but do not promise iOS
users push notifications without an install-to-home-screen education step. Build
`<IosInstallHint>` for that path.

---

## 6. Compliance implementation in the frontend

The Python guardrail protects generated text. It does not protect the copy your
UI ships. Both need enforcing.

1. **Centralise all user-facing strings** in `web/lib/copy/en-IN.ts`. No inline
   string literals in JSX for anything a user reads.
2. **Write a test that runs the guardrail patterns over every string in that
   file** and fails the build on a violation. Port the regexes from
   `src/globalpulse/explain/guardrails.py` into `web/lib/compliance/patterns.ts`
   and keep them in sync with a shared fixture file of blocked/allowed phrases
   tested on both sides. This is ~60 lines and it is the highest-leverage test
   in the codebase.
3. **`<DisclaimerBar>` on every screen showing a number.** Not dismissible, not
   collapsed behind an info icon.
4. **Explainer answers always render citations.** If `citations.length === 0`,
   render the "no global event explains this" state instead of a bare answer.
5. **Portfolio screen says "exposure", never "action".** No "consider", no
   "you may want to", no red/green P&L framing. Copy is reviewed by a human
   before launch.
6. **Audit log every rendered explanation** — send `auditId` back with a
   `rendered` beacon so the 5-year record reflects what a user actually saw, not
   just what the server produced.
7. **AI disclosure** in `/compliance` and inline on `/ask`: state plainly that
   an LLM narrates pre-computed statistics and cannot introduce new numbers.

---

## 7. Testing

| Layer | Tool | Gate |
|---|---|---|
| Unit (lib, hooks, formatters) | Vitest | ≥80% on `web/lib` |
| Component | Vitest + Testing Library | Every component in §4.3 |
| Compliance copy scan | Vitest | **Zero violations. Build-blocking.** |
| E2E happy paths | Playwright | Today, Explore, Ask, Portfolio |
| **E2E offline** | Playwright `context.setOffline(true)` | App loads, renders cached digest, shows data age, queues a watchlist edit, flushes on reconnect |
| Accessibility | `@axe-core/playwright` | Zero serious/critical |
| Performance | Lighthouse CI | Budgets in §8, build-blocking |
| Visual regression | Playwright screenshots | `<ImpactBars>`, `<CarDistribution>` in light + dark, 360px + 1440px |
| Python suite | pytest | Existing 86 tests stay green |

The offline E2E test is the one people skip and the one that catches real bugs.
Write it in Phase 5, not at the end.

---

## 8. Performance budgets (CI-enforced)

Measured on Lighthouse mobile preset, simulated slow 4G, 4× CPU throttle:

| Metric | Budget |
|---|---|
| LCP | < 2.5 s |
| INP | < 200 ms |
| CLS | < 0.1 |
| First-load JS (route `/`) | **< 130 KB gzip** |
| Total transferred, first visit | < 400 KB |
| Repeat launch (warm SW) | < 1.0 s to interactive |
| Lighthouse Performance | ≥ 90 |
| Lighthouse PWA | 100 |
| Lighthouse Accessibility | ≥ 95 |

Tactics: server components by default (`'use client'` only where genuinely
needed), `next/dynamic` for chart components, no chart library on the critical
path, `system-ui` font stack, AVIF/WebP icons, route-level code splitting,
`next/image` for screenshots only.

---

## 9. Build phases

Each phase is a separate Claude Code session with a clean context. Do not attempt
this as one prompt.

### Phase 1 — Backend persistence and jobs (Python)
**Deliver:** SQLAlchemy 2.0 models + Alembic migrations for §2.1; APScheduler
jobs for precompute, ingest, digest; `docker-compose` with Postgres 16 and Redis 7.
**Accept:** `alembic upgrade head` clean on empty DB; precompute job populates
`analog_summaries` with ≥300 rows in <120 s; existing 86 pytest tests still pass;
new tests for each job.

### Phase 2 — API hardening
**Deliver:** auth (§2.3), push endpoints (§2.4), SSE explainer (§2.5), rate
limiting, Redis response cache, ETag/Cache-Control, CORS lockdown, `GET
/bundle/offline`, structured logging, `/ready`.
**Accept:** OpenAPI schema validates; `/bundle/offline` < 300 KB gzipped;
SSE emits `composed` within 500 ms; rate limits return 429 with `Retry-After`;
integration tests for the full auth flow.

### Phase 3 — Next.js skeleton + design system
**Deliver:** Next 16 App Router scaffold in `web/`, TypeScript strict, Tailwind
configured with the §4.4 tokens (not defaults), dark mode, bottom tab shell,
`openapi-typescript` generation wired into the build, typed fetch client with
auth refresh interceptor.
**Accept:** `pnpm build` clean; `pnpm gen:types` produces no diff in CI; empty
shell scores Lighthouse PWA ≥90; tokens verified in both modes.

### Phase 4 — Core screens
**Deliver:** `/`, `/explore`, `/explore/[archetype]`, `/explore/[archetype]/[target]`,
`/calibration`, `/methodology`, `/compliance`. All components in §4.3 including
the mobile chart fallbacks.
**Accept:** archetype pages are statically generated with full content in the
HTML source (verify with `curl | grep`); JSON-LD present; every number wrapped in
`<EvidenceBadge>`; visual regression baselines captured at 360px and 1440px.

### Phase 5 — PWA layer
**Deliver:** Serwist SW with the §5.1 strategy table, Dexie schema + sync
protocol, outbox + Background Sync, manifest + icons + screenshots, deferred
install prompt, `<OfflineBanner>` with data age, `/offline` fallback.
**Accept:** **the offline Playwright test passes**; Lighthouse PWA = 100; airplane
mode on a real Android device loads the app and shows the last digest with its
timestamp; an offline watchlist edit survives a reload and syncs on reconnect.

### Phase 6 — Ask + Portfolio
**Deliver:** `/ask` with SSE streaming, suggested-question chips, citation list,
conversation history in IndexedDB; `/portfolio` with holdings entry (NSE symbol
autocomplete from the universe), exposure attribution, encrypted server storage.
**Accept:** `composed` answer renders before any LLM token arrives; disabling the
LLM env var degrades gracefully with no UI change; portfolio copy passes the
compliance scan; holdings encrypted at rest, verified by inspecting the DB.

### Phase 7 — Compliance, auth UX, notifications
**Deliver:** centralised copy file + build-blocking compliance scan (§6.2),
`<DisclaimerBar>`, Google OAuth + magic link UI, contextual notification
permission flow with pre-permission screen, `<IosInstallHint>`, audit beacon.
**Accept:** compliance scan is wired into `pnpm test` and fails on a deliberately
planted violation; notification permission is never requested on load (assert in
Playwright); auth flow E2E green.

### Phase 8 — Performance, a11y, deploy
**Deliver:** Lighthouse CI in GitHub Actions with §8 budgets, axe-core sweep,
bundle analysis, Vercel (web) + Fly.io/Railway (API + Postgres + Redis) deploy,
Sentry, `robots.txt`, `sitemap.xml`, `llms.txt`.
**Accept:** all §8 budgets green in CI; zero serious axe violations; production
smoke test passes; `llms.txt` lists every archetype page.

---

## 10. Two ways to sequence this

**Recommended — ship the public surface first.** Reorder to 1 → 2 → 3 → 4 → 8,
launch `/explore` and `/calibration` as a public site, *then* do 5 → 6 → 7. You
get the SEO/GEO acquisition channel compounding from month two while you build
the app layer. Indexing takes months; the PWA shell takes weeks. Start the slow
clock first.

**Out-of-the-box — build the Receipts Engine as the front door.** Skip the
explorer as the primary surface entirely. Ship one screen: a daily card scoring
the market-explanation claims Indian financial media made yesterday against
realised abnormal returns — supported / not supported / contested, with receipts.
It is inherently shareable, sits *further* from SEBI's advice line than anything
else in the product (you are auditing statements about the past), and every
scored claim feeds the calibration asset. The explorer then becomes the "see the
working" destination people land on from a shared card, rather than a homepage
nobody has a reason to visit. Higher variance, materially higher ceiling, and it
uses the one thing this engine does that nothing else does.

---

## 11. What to push back on

If Claude Code — or a stakeholder — proposes any of these, the answer is no:

- **Reimplementing the event study in TypeScript.** The Python engine is tested
  against injected ground truth. A JS reimplementation is untested by
  construction and will silently diverge.
- **Caching `/explain` responses.** Stale explanations are the failure mode the
  entire compliance architecture exists to prevent.
- **Showing a median without `n` and `p`.** Non-negotiable.
- **Resolving a `direction: 0` rule to a sign because "the UI looks cleaner."**
  The ambiguity is the information.
- **Adding a price chart with a trend line, a "signal" badge, or anything that
  implies a forward view.** That is the RA registration boundary.
- **A webfont.** Ship system-ui and spend the 100 KB elsewhere.
- **Prompting for install or notification permission on first load.** One shot,
  don't waste it.

---

*Companion files: `CLAUDE.md` (drop in repo root), `PHASE-PROMPTS.md`
(copy-paste per phase).*
