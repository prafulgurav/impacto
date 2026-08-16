# Deploying Impacto on Firebase and Google Cloud

A step-by-step runbook. Every command runs in **Cloud Shell** — a terminal in
your browser with `gcloud` and `firebase` already installed, so there is nothing
to install on your machine.

A Firebase project *is* a Google Cloud project. The web tier runs on Firebase
App Hosting and the API runs on Cloud Run, and both live in the same project,
billed together and visible from either console.

---

## Architecture

```
   Browser (installable PWA)
            │
            ▼
   Firebase App Hosting          ← Next.js: SSG + ISR + /api proxy
            │  /api/*  (same-origin rewrite)
            ▼
   Cloud Run: impacto-api        ← FastAPI, one always-on instance
            │
            ▼
   Cloud SQL for PostgreSQL      ← the event-study data and user data
```

Supporting services: **Artifact Registry** (image), **Cloud Build** (builds it),
**Secret Manager** (the two keys that fail closed).

### Why the API is not on Firebase too

Firebase App Hosting runs the Next.js app. The API is a Python FastAPI service
with scheduled jobs and a Postgres connection — Cloud Run is the Google service
for that, and it is in the same project. Nothing here leaves the Google stack.

### Why Cloud SQL and not Firestore

The persistence layer is relational: foreign keys, unique constraints, JSONB
columns, an Alembic migration, and repositories whose audit guarantee depends on
reading a holding and writing its audit row **in one SQL transaction**. Firestore
has no joins, no migrations, and different transaction semantics — moving to it
means rewriting `src/impacto/db/` and re-proving the compliance trail against
weaker guarantees, for no product gain.

---

## Before you start

Have ready:

- A Google account with **billing enabled** (Cloud SQL and Cloud Run are not on
  the free tier; App Hosting has a free allowance).
- The GitHub repository connected to your Google account — App Hosting deploys
  from GitHub, not from your laptop.

Two values you will generate and must not lose:

| Secret | If you lose it |
|---|---|
| `IMPACTO_HOLDINGS_ENCRYPTION_KEY` | **Every stored holding becomes permanently undecryptable.** There is no re-encryption path. Copy it into a password manager, not only into Secret Manager. |
| `IMPACTO_JWT_SECRET` | All sessions are invalidated; users sign in again. Recoverable. |

---

## Step 1 — Create the Firebase project

**Open:** https://console.firebase.google.com

1. **Add project**
2. Name it `impacto-prod` (note the real project ID Firebase shows you — it may
   have a suffix, e.g. `impacto-prod-4a91`)
3. Google Analytics is optional; skip it
4. **Upgrade to the Blaze plan** — required for App Hosting and Cloud Run.
   Bottom-left of the console → **Upgrade**

## Step 2 — Open Cloud Shell

**Open:** https://console.cloud.google.com

Top-right toolbar → the **`>_`** icon (*Activate Cloud Shell*). A terminal opens
at the bottom of the browser. Click **Continue** if it asks to authorise.

Everything from here is typed into that terminal. Set your project once:

```bash
export PROJECT_ID=impacto-prod          # use the real ID from step 1
export REGION=asia-south1               # Mumbai, closest to Indian users

gcloud config set project $PROJECT_ID
```

Enable the services:

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  firebaseapphosting.googleapis.com
```

Takes about a minute. Expect `Operation ... finished successfully.`

## Step 3 — Create the database

```bash
gcloud sql instances create impacto-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-size=10GB \
  --storage-auto-increase
```

**This takes 5–10 minutes.** Then:

```bash
gcloud sql databases create impacto --instance=impacto-db

export DB_PASSWORD=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
echo "DB password: $DB_PASSWORD"      # copy this somewhere safe now

gcloud sql users create impacto \
  --instance=impacto-db \
  --password="$DB_PASSWORD"

export CONN=$(gcloud sql instances describe impacto-db --format='value(connectionName)')
echo "Connection name: $CONN"         # e.g. impacto-prod:asia-south1:impacto-db
```

## Step 4 — Store the secrets

```bash
python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())" \
  | gcloud secrets create impacto-holdings-key --data-file=-

python3 -c "import secrets;print(secrets.token_urlsafe(48))" \
  | gcloud secrets create impacto-jwt-secret --data-file=-
```

Read the holdings key once and save it outside GCP:

```bash
gcloud secrets versions access latest --secret=impacto-holdings-key
```

Let Cloud Run read them:

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

for S in impacto-holdings-key impacto-jwt-secret; do
  gcloud secrets add-iam-policy-binding $S \
    --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

## Step 5 — Build the API image

Get the source into Cloud Shell:

```bash
git clone https://github.com/prafulgurav/impacto.git
cd impacto
git checkout claude/impacto-pwa-stock-impact-z0osr3   # until the PR is merged
```

Create the image repository and build:

```bash
gcloud artifacts repositories create impacto \
  --repository-format=docker \
  --location=$REGION

gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT_ID/impacto/api:v1
```

**Takes 3–5 minutes.** Expect `SUCCESS` at the end.

## Step 6 — Deploy the API to Cloud Run

```bash
gcloud run deploy impacto-api \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/impacto/api:v1 \
  --region=$REGION \
  --allow-unauthenticated \
  --add-cloudsql-instances=$CONN \
  --min-instances=1 \
  --no-cpu-throttling \
  --memory=1Gi \
  --set-env-vars="IMPACTO_DATABASE_URL=postgresql+psycopg://impacto:$DB_PASSWORD@/impacto?host=/cloudsql/$CONN,IMPACTO_SCHEDULER_ENABLED=true,IMPACTO_WEB_ORIGIN=https://placeholder.web.app" \
  --set-secrets="IMPACTO_HOLDINGS_ENCRYPTION_KEY=impacto-holdings-key:latest,IMPACTO_JWT_SECRET=impacto-jwt-secret:latest"
```

`--min-instances=1 --no-cpu-throttling` is not optional — see
[Scheduled jobs](#scheduled-jobs-and-why-the-instance-stays-awake) below.

Capture the URL:

```bash
export API_URL=$(gcloud run services describe impacto-api --region=$REGION --format='value(status.url)')
echo $API_URL
```

### Verify before going further

```bash
curl -s -o /dev/null -w "health %{http_code}\n" $API_URL/health   # 200 = process alive
curl -s -o /dev/null -w "ready  %{http_code}\n" $API_URL/ready    # 200 = Postgres reachable
```

`/health` is liveness only and deliberately does not touch Postgres — a database
outage must not make Cloud Run kill a healthy process. `/ready` is the one that
proves the database connection works.

Confirm the migrations ran:

```bash
gcloud run services logs read impacto-api --region=$REGION --limit=50 | grep -i alembic
```

Expect `impacto: running alembic upgrade head` and `Running upgrade -> 0001_initial`.

If `/ready` returns 503, the connection string is wrong. It must be the unix
socket form — `@/impacto?host=/cloudsql/...`, no hostname, no port.

## Step 7 — Seed the precompute

Until this has run once, `/analogs` computes on request: correct, but slow.

```bash
gcloud run jobs create impacto-precompute \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/impacto/api:v1 \
  --region=$REGION \
  --set-cloudsql-instances=$CONN \
  --set-env-vars="IMPACTO_DATABASE_URL=postgresql+psycopg://impacto:$DB_PASSWORD@/impacto?host=/cloudsql/$CONN,IMPACTO_RUN_MIGRATIONS=false" \
  --set-secrets="IMPACTO_HOLDINGS_ENCRYPTION_KEY=impacto-holdings-key:latest,IMPACTO_JWT_SECRET=impacto-jwt-secret:latest" \
  --task-timeout=15m \
  --command="python" \
  --args="-c","from impacto.jobs.precompute import run_precompute; run_precompute()"

gcloud run jobs execute impacto-precompute --region=$REGION --wait
```

Takes about a minute — 275 rule/window combinations.

## Step 8 — Deploy the web tier on App Hosting

**Open:** https://console.firebase.google.com → your project → **Build → App Hosting**

1. **Get started**
2. **Connect to GitHub** and authorise Firebase; pick `prafulgurav/impacto`
3. **Root directory:** `web` ← nothing works without this
4. **Live branch:** `main` (or the feature branch until the PR is merged)
5. Name the backend `impacto-web`
6. **Create**

The first rollout will fail or render empty pages until the API URL is set —
that is expected. Set it now in `web/apphosting.yaml`, replacing both
placeholders with the value of `$API_URL` from step 6, and the site URL with the
App Hosting URL the console now shows you:

```yaml
env:
  - variable: API_ORIGIN
    value: https://impacto-api-xxxxx.a.run.app
    availability: [BUILD, RUNTIME]
  - variable: NEXT_PUBLIC_API_ORIGIN
    value: https://impacto-api-xxxxx.a.run.app
    availability: [BUILD, RUNTIME]
  - variable: NEXT_PUBLIC_SITE_URL
    value: https://impacto-web--impacto-prod.web.app
    availability: [BUILD, RUNTIME]
```

Commit and push; App Hosting rebuilds automatically on every push to the live
branch.

Leave the build command alone. `web/package.json` pins `next build --webpack`
because Serwist needs webpack — switch it to Turbopack and the service worker is
silently not generated, so the app stops working offline and stops being
installable, with no error.

## Step 9 — Close the CORS loop

```bash
export WEB_URL=https://impacto-web--impacto-prod.web.app    # the real one

gcloud run services update impacto-api --region=$REGION \
  --update-env-vars="IMPACTO_WEB_ORIGIN=$WEB_URL"
```

Exactly one origin, no trailing slash. CORS uses no wildcard and credentials are
in play, so a mismatch here fails every authenticated request.

## Step 10 — Install it

Open the App Hosting URL on an Android phone in Chrome → menu → **Install app**.
On desktop Chrome, the install icon appears in the address bar.

Then confirm the offline behaviour that the whole architecture exists for: load
the app, turn on airplane mode, reopen it. The digest should still render, with
a banner stating how old the data is.

---

## Scheduled jobs, and why the instance stays awake

Three jobs run in-process on APScheduler: precompute (02:00), ingest (every 30
minutes) and the digest (07:30 IST). By default Cloud Run scales to zero and
throttles CPU between requests, so those timers never fire — the app would
quietly stop updating with nothing in the logs.

`--min-instances=1 --no-cpu-throttling` keeps one instance awake so they run.
That is the cost of one always-on small instance.

**The cheaper, more Cloud-native alternative** is Cloud Run Jobs for each job
plus Cloud Scheduler triggers, exactly as step 7 does for the precompute — then
the API can scale to zero with `IMPACTO_SCHEDULER_ENABLED=false`. The ingest and
digest jobs would need the same treatment:

```bash
gcloud scheduler jobs create http impacto-ingest \
  --schedule="*/30 * * * *" \
  --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/impacto-ingest:run" \
  --oauth-service-account-email="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
```

## Redis

Skipped on purpose. Redis is the shared response cache and rate-limit counters;
with a single instance the in-process counters are correct. Memorystore needs a
Serverless VPC connector, which adds cost and setup for no benefit at one
instance.

Add it when you add the second instance — and at the same time set
`IMPACTO_SCHEDULER_ENABLED=false` **and** `IMPACTO_RUN_MIGRATIONS=false` on every
instance beyond the first. Two schedulers notify every user twice; two
containers racing the same migration is the same class of mistake.

## Sign-in

Magic-link email is not wired — the endpoint issues a valid token and logs it
but sends nothing. Use Google sign-in, which is already implemented:

**Open:** https://console.cloud.google.com/apis/credentials

1. **Create credentials → OAuth client ID → Web application**
2. Authorised JavaScript origins: your App Hosting URL
3. Copy the client ID, then:

```bash
gcloud run services update impacto-api --region=$REGION \
  --update-env-vars="IMPACTO_GOOGLE_CLIENT_ID=<client-id>.apps.googleusercontent.com"
```

Everything that is not user-specific — the digest, Explore, Calibration, Ask —
works signed out.

## Narration

Optional. The app is fully functional with no model configured; a provider only
rewrites an answer that was already composed from retrieved facts.

```bash
gcloud run services update impacto-api --region=$REGION \
  --update-env-vars="IMPACTO_LLM_PROVIDER=gemini" \
  --update-secrets="IMPACTO_GEMINI_API_KEY=impacto-gemini-key:latest"
```

## Market data

`IMPACTO_MARKET_PROVIDER` defaults to `fixture` — a deterministic bundled corpus.
`yfinance` switches to live data, but its NSE ticker coverage has not been
validated. Do not put those figures in front of consumers until it has been.

---

## Cost

Roughly, in ascending order: Cloud SQL `db-f1-micro` and the always-on Cloud Run
instance dominate; App Hosting, Artifact Registry and Secret Manager are small
or free at this scale. Check current rates at
https://cloud.google.com/pricing/list — and use
https://console.cloud.google.com/billing/budgets to set a budget alert before
you deploy, not after.

## Rollback

```bash
gcloud run revisions list --service=impacto-api --region=$REGION
gcloud run services update-traffic impacto-api --region=$REGION --to-revisions=<REVISION>=100
```

For the web tier, App Hosting keeps every rollout: **Firebase console → App
Hosting → your backend → Rollouts → ⋮ → Roll back**.

Migrations are not rolled back by either. Check `migrations/versions/` before
reverting past a schema change.
