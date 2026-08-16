# Deployment

Web tier on Vercel, API + Postgres + Redis on Fly.io or Railway. The two tiers
are independent: the web tier is static and edge-cached, the API is a single
stateful instance that owns the scheduled jobs.

## Environment variables

Every variable uses the `IMPACTO_` prefix. The engine's original `GP_` prefix is
still honoured as a fallback, so an existing deployment keeps working.

### Required in any deployment

| Variable | Notes |
|---|---|
| `IMPACTO_DATABASE_URL` | `postgresql+psycopg://user:pass@host:5432/impacto` |
| `IMPACTO_JWT_SECRET` | 48+ random bytes. **Auth fails closed without it** — there is no default, because a default signing secret is indistinguishable from no auth. |
| `IMPACTO_HOLDINGS_ENCRYPTION_KEY` | base64 32 bytes. Holdings **fail closed** without it rather than being stored in the clear. Generate: `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"` |
| `IMPACTO_WEB_ORIGIN` | Exactly one origin. CORS uses no wildcard, and credentials are in play. |

> Rotating `IMPACTO_HOLDINGS_ENCRYPTION_KEY` makes existing holdings
> undecryptable. There is no re-encryption path yet; treat the key as permanent
> for the life of the data.

### Recommended

| Variable | Default | Notes |
|---|---|---|
| `IMPACTO_REDIS_URL` | — | Shared response cache and rate-limit counters. Without it each replica keeps its own in-process counters, so N replicas allow N times the intended limit. |
| `IMPACTO_SCHEDULER_ENABLED` | `false` | **Exactly one instance may set this true.** Two schedulers means every user is notified twice. |
| `IMPACTO_RUN_MIGRATIONS` | `true` | The container runs `alembic upgrade head` before starting uvicorn. Set false on every replica beyond the first: two containers racing the same upgrade is the same mistake as two schedulers. |
| `IMPACTO_COOKIE_SECURE` | `true` | Only set false for plain-HTTP local development. It also enables the magic-link debug token, which must never be on in production. |

### Narration

| Variable | Default |
|---|---|
| `IMPACTO_LLM_PROVIDER` | `none` — `anthropic`, `gemini` or `auto` |
| `IMPACTO_ANTHROPIC_API_KEY` / `IMPACTO_ANTHROPIC_MODEL` | — / `claude-opus-5` |
| `IMPACTO_GEMINI_API_KEY` / `IMPACTO_GEMINI_MODEL` | — / `gemini-2.5-flash` |
| `IMPACTO_LLM_MAX_TOKENS` | `1200` |

### Auth and push

| Variable | Notes |
|---|---|
| `IMPACTO_GOOGLE_CLIENT_ID` | OAuth client id; Google sign-in returns 401 without it |
| `IMPACTO_VAPID_PUBLIC_KEY` / `IMPACTO_VAPID_PRIVATE_KEY` | Web Push. `/push/public-key` returns 503 without them. |
| `IMPACTO_VAPID_SUBJECT` | `mailto:` contact for the push service |

### Web tier

| Variable | Notes |
|---|---|
| `API_ORIGIN` | Read at build time by the statically generated routes |
| `NEXT_PUBLIC_API_ORIGIN` | Proxy target for `/api/*` at runtime |
| `NEXT_PUBLIC_SITE_URL` | Canonical origin for sitemap, robots and `llms.txt` |

## Order of operations

1. Provision Postgres and Redis.
2. `alembic upgrade head` — the image's entrypoint does this on start, so a
   plain `docker run` of the published image is enough; there is no separate
   migration step and no command to override.
3. Start the API with `IMPACTO_SCHEDULER_ENABLED=true` on **one** instance.
4. Let the nightly precompute run once, or trigger it manually. Until it has,
   `/analogs` falls back to computing on request, which is correct but slow.
5. Build and deploy the web tier with `API_ORIGIN` pointing at the API.

## Health checks

- `/health` — **liveness only.** Deliberately does not touch Postgres or Redis:
  a dependency outage should not make the orchestrator kill a healthy process.
- `/ready` — **readiness.** Checks Postgres and Redis, returns 503 when either
  is down. This is the one to put behind a load balancer.

## Scaling

The scheduler is in-process APScheduler, single instance, on purpose. Celery or
Arq only become the right answer with more than one API replica, and reaching
for a broker and a worker fleet to run three cron jobs is a cost with no return.
To scale reads first: add API replicas with `IMPACTO_SCHEDULER_ENABLED=false`,
and point them all at the same Redis so the rate limits stay shared.

## What is not wired up

- **Email delivery for magic links.** `/auth/magic-link` issues a valid token
  and logs it; it does not send. Wire a provider into
  `api/routers/auth.py::request_magic_link` before launch.
- **Web Push sending.** Subscription management, payload construction and the
  three-strike pruning of dead endpoints are complete and tested. The transport
  is behind `PushTransport` and uses `pywebpush` when installed.
- **Sentry.** Add the DSN and initialise in `api/app.py` and `web/app/layout.tsx`;
  the request id is already propagated as `X-Request-Id` across both tiers.
