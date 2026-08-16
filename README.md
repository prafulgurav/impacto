# Impacto

**Global events, Indian market impact.** Impacto tells you what Indian equity
sectors actually did after past occurrences of a global event — with the sample
size, the p-value, and the economic mechanism that links the two.

It is an installable, offline-first PWA over a Python event-study engine.

---

## What it is, and what it is deliberately not

It reports **what happened**: median cumulative abnormal return, sample size,
p-value, and the transmission channel, for each of 15 event archetypes across
Indian sectors and baskets.

It never reports **what will happen**. No forward-looking claim about any named
security or index can render, and no buy/sell/hold language can reach a user.
Under SEBI's Research Analyst and Investment Adviser regulations that is not a
styling preference — it is the difference between a legal product and an
unregistered one. The boundary is enforced in code, twice: once in the Python
guardrail over generated text, and again over every string the UI ships.

Three rules the codebase will not let you break:

1. **Every number carries its sample size and its uncertainty.** A median with
   no `n` and no p-value does not render. Where `p > 0.10` the interface says
   the distribution is not distinguishable from noise, beside the figure.
2. **A two-sided linkage stays two-sided.** `direction: 0` rules render an
   explicit callout. The ambiguity is the finding.
3. **Explanations are never cached.** A stale explanation attached to today's
   market move is the exact misleading output the architecture exists to
   prevent.

---

## Quick start

```bash
# Backend
pip install -e ".[dev]"
export IMPACTO_HOLDINGS_ENCRYPTION_KEY=$(python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
export IMPACTO_JWT_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
alembic upgrade head
uvicorn impacto.api:app --reload            # http://localhost:8000

# Frontend
cd web && pnpm install && pnpm dev           # http://localhost:3000
```

Or the whole stack, with Postgres and Redis:

```bash
docker compose up
```

Everything runs offline out of the box: the market provider defaults to a
deterministic bundled fixture corpus, and no LLM is required.

---

## The narration layer — Claude or Gemini

Answers are **composed deterministically from retrieved facts before any model
is consulted.** A language model only ever rewrites that composition into
fluent prose, is given nothing but the retrieved evidence, cannot introduce a
figure, and its output is re-checked by the compliance guardrail before it can
reach a user.

That inversion is what makes the provider swappable — no provider is
load-bearing, and the product is fully functional with none configured:

```bash
IMPACTO_LLM_PROVIDER=none        # default; fully deterministic, and how CI runs
IMPACTO_LLM_PROVIDER=anthropic   # pip install 'impacto[llm]'
IMPACTO_LLM_PROVIDER=gemini      # pip install 'impacto[gemini]'
IMPACTO_LLM_PROVIDER=auto        # whichever key is configured, Anthropic first
```

```bash
IMPACTO_ANTHROPIC_API_KEY=...
IMPACTO_ANTHROPIC_MODEL=claude-opus-5
IMPACTO_GEMINI_API_KEY=...
IMPACTO_GEMINI_MODEL=gemini-2.5-flash
```

Switching providers changes the prose style and nothing else. Any failure to
reach a provider degrades silently to the grounded answer — a narration outage
is a style regression, never an outage.

---

## Layout

```
src/impacto/          Python engine
  eventstudy/         market-model event study (AR/CAR/CAAR, t-tests)
  impact/             impact scoring over the transmission map
  explain/            grounded explainer + compliance guardrails
  llm/                narration providers: none | anthropic | gemini
  db/                 SQLAlchemy models, repositories, encryption
  jobs/               precompute (02:00), ingest (30 min), digest (07:30 IST)
  api/                FastAPI: auth, push, SSE, offline bundle, rate limits
knowledge/            transmission map — 15 archetypes, 11 channels, 55 rules
migrations/           Alembic
lib/                  compliance fixture shared by pytest AND vitest
web/                  Next.js 16 PWA
tests/                pytest
```

## Documentation

| File | What it covers |
|---|---|
| `docs/PWA-BUILD-BRIEF.md` | The build brief this was implemented from |
| `docs/DEPLOYMENT.md` | Deploying the web and API tiers, every env var |
| `docs/DEPLOYMENT-FIREBASE.md` | Step-by-step runbook for Firebase App Hosting + Cloud Run + Cloud SQL |
| `web/BUDGETS.md` | Measured performance budgets and one the brief could not meet |
| `COMPLIANCE.md` | The full control set behind the SEBI position |
| `ARCHITECTURE.md` | How the engine is put together |

## Testing

```bash
make test                       # pytest, excluding the slow acceptance sweep
python -m pytest tests -m slow  # full precompute sweep, ~50s
make lint

cd web
pnpm test                       # vitest, including the build-blocking copy scan
pnpm exec playwright test       # E2E, offline, accessibility
```

The two tests worth knowing about:

- `web/tests/e2e/offline.spec.ts` — loads from the service worker with the
  network off, renders the cached digest, shows its data age, queues a watchlist
  edit, and flushes it on reconnect. The one people skip, and the one that
  catches real bugs. Note the comment on `cutTheNetwork`: Playwright's
  `setOffline` does not apply to requests the service worker makes, so an
  offline test built on it alone leaves the app fully online and proves nothing.
- `lib/compliance-fixtures.json` — one fixture of blocked and allowed phrases,
  run from **both** pytest and vitest, so the Python guardrail and its
  TypeScript port cannot drift apart silently.

## Licence

MIT. See `LICENCE`.

**Impacto is not investment advice, not a research recommendation, and makes no
claim about future prices. Past abnormal returns do not predict future returns.
Consult a SEBI-registered investment adviser before making any investment
decision.**
