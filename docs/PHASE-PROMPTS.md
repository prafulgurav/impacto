# Phase prompts for Claude Code

Copy one block per session. **Start each phase with a fresh context** —
`/clear` between phases. Long single sessions degrade quality on work this size.

Before Phase 1: place `CLAUDE.md` at the repo root and `PWA-BUILD-BRIEF.md` in
`docs/`. Every prompt below assumes Claude Code can read both.

A useful habit: end each session with `run the full test suite and show me
anything that regressed`, then commit before clearing.

---

## Phase 0 — Orientation (5 minutes, do this once)

```
Read CLAUDE.md and docs/PWA-BUILD-BRIEF.md in full.

Then explore this repository and report back:
1. The public surface of the Python engine — every FastAPI route, its
   parameters, and its response model.
2. Where the compliance guardrail is enforced, and every code path that produces
   user-facing text.
3. What state currently lives only in memory or in fixture files and will need
   to move to Postgres.
4. Anything in the existing code that will actively fight the PWA plan in
   docs/PWA-BUILD-BRIEF.md.

Do not write any code. I want your read of the codebase before we start.
```

---

## Phase 1 — Backend persistence and jobs

```
Implement Phase 1 of docs/PWA-BUILD-BRIEF.md — backend persistence and
scheduled jobs. Python only, no frontend work.

Build:
1. SQLAlchemy 2.0 typed models and Alembic migrations for the schema in §2.1 of
   the brief: users, sessions, watchlist_archetypes, holdings,
   push_subscriptions, analog_summaries, detected_events, daily_digests,
   calibration_runs, audit_log. Include the indexes listed there.
2. A repository layer in src/globalpulse/db/ so the rest of the code never
   touches raw SQL or session objects directly.
3. Three APScheduler jobs in src/globalpulse/jobs/:
   - precompute.py  — nightly, fills analog_summaries for every
     (archetype, target, window) combination across the five windows in the brief
   - ingest.py      — every 30 min in market hours, GDELT + RSS → classify →
     upsert detected_events
   - digest.py      — 07:30 IST weekdays, builds and stores the daily digest
4. docker-compose.yml extended with Postgres 16 and Redis 7, with healthchecks.
5. Tests for every job and every repository method.

Constraints:
- The existing 86 pytest tests must stay green. Run them before you finish.
- Tests stay hermetic — no network. Use FixtureProvider and fixture news.
- Do not change the event study, impact engine, or guardrail logic.
- Configuration via src/globalpulse/config.py with the GP_ prefix. No literals.

Acceptance: `alembic upgrade head` runs clean on an empty database; the
precompute job produces at least 300 rows in under 120 seconds; `make test`
and `make lint` both pass.

Before you start, show me your migration plan and the job schedule, and wait
for my confirmation.
```

---

## Phase 2 — API hardening

```
Implement Phase 2 of docs/PWA-BUILD-BRIEF.md — API hardening. Python only.

Build:
1. Auth per §2.3: Google OAuth ID-token verification and email magic link.
   Access token 15 min, refresh token 30 days in an httpOnly Secure SameSite=Lax
   cookie. Endpoints: /auth/google, /auth/magic-link, /auth/verify,
   /auth/refresh, /auth/logout, /me.
   Anonymous browsing must keep working for every knowledge, event, analog,
   calibration, digest and explain endpoint. Auth gates only /me/*, /push/* and
   portfolio.
2. Web Push per §2.4 using pywebpush and VAPID. Push payloads carry only
   {alertId, archetypeLabel, severity} — never a number, for the reason given in
   the brief. Prune subscriptions after 3 consecutive 410 responses.
3. GET /explain/stream as Server-Sent Events per §2.5. The `composed` event must
   fire with the complete deterministic grounded answer before any LLM token.
   If narration fails or trips the guardrail, the composed answer stands.
   Write every response to audit_log and return its auditId in the `done` event.
4. GET /bundle/offline per §3 — one gzipped payload with archetypes, channels,
   analog summaries for the default window, latest digest, and trailing-30-day
   events. ETag support, must return 304 on a match. Target under 300 KB gzipped;
   if you exceed it, drop the per-analog detail arrays and tell me.
5. Rate limiting with slowapi backed by Redis: 60/min anonymous, 300/min
   authenticated, 10/min on /explain/stream. Return 429 with Retry-After.
6. Redis response cache and ETag/Cache-Control headers matching the TTL table in
   CLAUDE.md.
7. CORS locked to the configured web origin. Structured JSON logging with a
   request ID echoed as X-Request-Id. Split /health and /ready.

Constraints:
- Holdings must be encrypted at rest (AES-GCM, key from env) and every read
  logged to audit_log.
- Integration tests for the full auth flow, the SSE stream, rate limiting, and
  the 304 path on /bundle/offline.

Acceptance: OpenAPI schema validates; /bundle/offline under 300 KB gzipped;
`composed` event within 500 ms; existing tests still green.

Show me the auth flow and the SSE event sequence before implementing.
```

---

## Phase 3 — Next.js skeleton and design system

```
Implement Phase 3 of docs/PWA-BUILD-BRIEF.md — the Next.js skeleton and design
system. Create the web/ directory. No feature screens yet.

Build:
1. Next.js (latest stable — check npm, the brief was written at 16.3) with App
   Router, React 19, TypeScript strict. pnpm.
2. Tailwind configured with the exact design tokens in CLAUDE.md §Design as CSS
   custom properties, wired for light and dark. Do not use Tailwind's default
   palette anywhere. system-ui font stack only — no webfont.
3. The app shell: bottom tab bar on mobile (Today, Explore, Ask, Portfolio,
   More), sidebar at ≥1024px. Theme toggle respecting prefers-color-scheme with
   a persisted manual override.
4. A typed fetch client in web/lib/api/ built on the generated types, with an
   auth refresh interceptor, request-ID propagation, and typed error handling.
5. `pnpm gen:types` running openapi-typescript against the local API into
   web/types/api.d.ts, wired into CI so a diff fails the build.
6. web/lib/copy/en-IN.ts as the single home for user-facing strings, with the
   structure the compliance scan will consume in Phase 7.
7. Vitest and Playwright configured. One smoke test each.

Constraints:
- Server Components by default. Add 'use client' only where interactivity
  requires it, with a one-line comment saying why.
- No feature screens, no charts, no data fetching beyond a health check.

Acceptance: `pnpm build` clean; `pnpm gen:types` produces no diff; the empty
shell scores Lighthouse PWA ≥90 and Performance ≥95; both themes verified.
```

---

## Phase 4 — Core screens

```
Implement Phase 4 of docs/PWA-BUILD-BRIEF.md — the core read screens.

Routes: /, /explore, /explore/[archetype], /explore/[archetype]/[target],
/calibration, /methodology, /compliance.

Components (see §4.3 of the brief for the full spec):
- <ImpactBars>       custom SVG diverging bars; bar = encoded prior range,
                     dot = realised median. Below 480px, degrade to a list with
                     inline mini-bars — do not shrink the chart.
- <CarDistribution>  histogram with median rule and zero reference. Below 480px,
                     switch to a horizontal strip plot, one dot per analog.
- <StatTile>         with a hero variant, nowrap, proportional figures
- <EvidenceBadge>    n, p-value, and an explicit "not distinguishable from
                     noise" state when p > 0.10. Every number on screen is
                     wrapped in one. No exceptions.
- <ChannelChip>      tap to expand the transmission mechanism
- <AmbiguityCallout> for direction: 0 rules — states plainly that the mechanism
                     cuts both ways
- <DisclaimerBar>    sticky, not dismissible, on any screen showing a number

Rendering:
- /explore/[archetype] and /explore/[archetype]/[target] are statically
  generated with ISR at 24 hours. Full content must be present in the server-
  rendered HTML — these pages are the SEO and LLM-citation surface. Add Article
  and FAQPage JSON-LD, canonical URLs, and OG tags.
- / reads from the API and will read from IndexedDB after Phase 5. Structure the
  data layer now so that swap is a one-line change.

Constraints:
- Follow the mark specs in CLAUDE.md §Design exactly. No chart library on the
  critical path — these two charts are bespoke SVG.
- Every component gets a Vitest test. Capture Playwright visual baselines at
  360px and 1440px in both themes.

Acceptance: `curl` on an archetype page shows the full content in the HTML
source; JSON-LD validates; every rendered number has an EvidenceBadge; first-load
JS on / stays under 130 KB gzip.

Show me the <ImpactBars> mobile fallback design before you build it.
```

---

## Phase 5 — PWA layer (the important one)

```
Implement Phase 5 of docs/PWA-BUILD-BRIEF.md — offline-first PWA.

Build:
1. Serwist (@serwist/next) service worker implementing the caching strategy
   table in CLAUDE.md exactly. /api/explain/stream and /api/me/* are NetworkOnly
   — caching an explanation is a compliance failure, not a performance win.
2. Dexie 4 with the schema in §5.2: archetypes, channels, analogSummaries,
   digests, events, holdings, meta, outbox.
3. The sync protocol: on app open and on the online event, GET /bundle/offline
   with If-None-Match. On 304 do nothing; on 200 write in a single Dexie
   transaction and update meta.lastSyncAt.
4. Read-through rendering: every screen reads Dexie first and paints
   immediately, then reconciles with the network. No loading spinner on a warm
   launch, ever.
5. Outbox with Background Sync (tag gp-outbox) and exponential backoff for
   watchlist and holdings edits made offline. Last-write-wins on updatedAt.
6. Manifest, icons (192, 512, maskable-512), narrow and wide screenshots,
   shortcuts — per §5.3.
7. Deferred install prompt: capture beforeinstallprompt, suppress the default,
   show a custom banner only when the user is on their 2nd+ session, has spent
   over 60s total, and hasn't dismissed it in 30 days.
8. <OfflineBanner> showing DATA AGE, not just connection state:
   "Showing data from 15 Aug, 02:10. You're offline."
9. /offline fallback route.
10. <IosInstallHint> for the Safari add-to-home-screen path, since iOS has no
    install prompt, no Background Sync, and no Web Push without installation.

Then write web/tests/e2e/offline.spec.ts, which is the most important test in
this repo. It must assert: with context.setOffline(true) the app loads from the
service worker, renders the cached digest, displays the correct data age, lets
the user edit their watchlist, and flushes that edit when connectivity returns.

Acceptance: the offline test passes; Lighthouse PWA = 100; a cold launch in
airplane mode on a real Android device shows the last digest with its timestamp.

Show me the sync protocol and conflict-resolution plan before implementing.
```

---

## Phase 6 — Ask and Portfolio

```
Implement Phase 6 of docs/PWA-BUILD-BRIEF.md — the explainer chat and portfolio
exposure screens.

/ask:
- Consumes GET /explain/stream over SSE. Render the `composed` grounded answer
  the instant it arrives, then swap in the LLM narration only if it arrives and
  passes compliance. The user must never see a spinner where an answer should be.
- <CitationList> under every answer, open by default on first use. If
  citations.length is 0, render the "no global event explains this" state rather
  than a bare answer.
- Suggested-question chips derived from today's detected events.
- Conversation history in IndexedDB, viewable offline, clearly marked with the
  date each answer was generated.
- An inline note that an LLM narrates pre-computed statistics and cannot
  introduce new numbers.

/portfolio (auth required):
- Holdings entry with NSE symbol autocomplete sourced from knowledge/universe.yaml.
- Calls POST /impact/portfolio and renders exposure attribution: which sectors
  the user's weight sits in, which archetypes have historically moved those
  sectors, through which channels.
- Copy says EXPOSURE, never ACTION. No "consider", no "you may want to", no
  red/green P&L framing, no ranking that implies what to do. Read §6 of the
  brief before writing a single string on this screen.

Acceptance: with GP_LLM_PROVIDER=none the UI is fully functional and visually
identical apart from prose style; portfolio copy passes the compliance scan;
holdings are encrypted in the database, verified by inspecting a row directly.
```

---

## Phase 7 — Compliance enforcement, auth UX, notifications

```
Implement Phase 7 of docs/PWA-BUILD-BRIEF.md.

1. Port the guardrail regexes from src/globalpulse/explain/guardrails.py into
   web/lib/compliance/patterns.ts. Create a shared fixture file of blocked and
   allowed phrases, and test it from BOTH pytest and vitest so the two
   implementations cannot drift.
2. Write a build-blocking vitest test that runs those patterns over every string
   in web/lib/copy/en-IN.ts and over the static content of /methodology and
   /compliance. Wire it into `pnpm test`. Then deliberately plant a violation,
   show me the failure, and remove it.
3. Auth UI: Google sign-in and magic link, with a clear explanation of why an
   account is needed (watchlist, notifications, portfolio) and what still works
   without one.
4. Notification permission flow: never on load. A pre-permission screen
   explaining exactly what will be sent and how often, shown only after the user
   taps "Notify me" on a watchlist archetype. Frequency controls in /settings.
   Assert in Playwright that Notification.requestPermission is not called on
   page load.
5. Audit beacon: POST the auditId back with a `rendered` event when an
   explanation actually paints, so the 5-year record reflects what a user saw.
6. /compliance page: SEBI position, what this product is and is not, the AI
   disclosure, and the data sources.

Acceptance: the compliance scan blocks the build on a planted violation; the
Playwright assertion on notification permission passes; auth E2E green.
```

---

## Phase 8 — Performance, accessibility, deploy

```
Implement Phase 8 of docs/PWA-BUILD-BRIEF.md.

1. Lighthouse CI in GitHub Actions enforcing the budgets in CLAUDE.md
   §Performance. Build-blocking, mobile preset, simulated slow 4G, 4x CPU throttle.
2. @axe-core/playwright sweep across every route. Zero serious or critical
   violations.
3. Bundle analysis. Report anything over 20 KB gzip and justify or remove it.
4. Deploy: web to Vercel, API + Postgres + Redis to Fly.io or Railway. Document
   every environment variable in .env.example.
5. Sentry on both tiers, with the request ID correlated across them.
6. robots.txt, sitemap.xml covering every archetype and archetype/target page,
   and llms.txt at the root listing each archetype page with a one-line
   description — this is how LLM search surfaces cite us.
7. A production smoke test: health, one archetype page, one analog query, one
   explain stream.

Then run the full suite — pytest, vitest, playwright, lighthouse, axe — and give
me a single report of what passes, what regressed, and what you had to work
around. Be specific about anything you compromised on.
```

---

## Ongoing prompts worth keeping

**After any transmission-map change**
```
Run `make calibrate` and show me every rule whose status is `contradicted` or
`sign_ok_magnitude_off`. For each, tell me whether the mechanism is still sound
and the sample is just noisy, or whether the rule should be deleted. Do not
defend a prior the data rejects.
```

**Before any release**
```
Audit every user-facing string, chart annotation, push payload template and
error message in this repo against the compliance rules in CLAUDE.md. List
anything that states or implies a forward-looking view on a named security or
index, or that reads as a transact instruction. Show me the file and line.
```

**When a Lighthouse budget regresses**
```
The <metric> budget regressed to <value>. Find the cause with bundle analysis
and a trace, then fix it without removing a feature. If the only fix is removing
a feature, tell me that instead of quietly loosening the budget.
```

**Weekly**
```
Show me every TODO, FIXME, skipped test and `any` in the codebase, grouped by
severity, with your view on which ones are real debt versus acceptable.
```
