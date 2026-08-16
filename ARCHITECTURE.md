# Architecture

## The one-sentence version

A hand-authored, schema-validated causal knowledge base sits at the centre; every
other component either feeds it (ingestion, classification), measures it against
reality (event study, calibration), or renders it (impact scoring, alerts, digest,
explainer) — and a compliance guardrail gates everything that reaches a user.

## Why the knowledge base is the centre

The obvious way to build this is end-to-end ML: embed headlines, embed price
reactions, learn the mapping. We deliberately did not, for four reasons.

1. **Sample size.** There have been perhaps 40 genuinely distinct OPEC decisions
   and 30 US-India trade actions in the modern Indian market era. That is not a
   training set; it is a case list. A learned model on 40 examples memorises.
2. **Non-stationarity.** The FII-ownership structure of NIFTY Bank in 2015 is not
   the structure in 2026. A learned correlation silently assumes it is.
3. **Auditability.** Under SEBI's proposed AI/ML framework a regulated entity must
   name an accountable officer, retain 5 years of documentation, and submit to
   independent fairness audits. "The embedding said so" does not survive that.
4. **The failure mode is the product.** The valuable output is *"OMC down,
   upstream oil up, under the same event"* — a distinction a correlation model
   averages away because both are "energy."

So the causal structure is written by humans, versioned in git, validated by
tests, and **scored against realised data by the calibration report**. Statistics
measure; they do not assert.

## Layers

```
┌──────────────────────────────────────────────────────────────────┐
│ knowledge/                    universe.yaml · channels.yaml      │
│                               transmission_map.yaml              │
│  Loaded by knowledge.py, referentially validated at import.      │
│  A dangling channel or unknown target is a LOAD FAILURE.         │
└──────────────────────────────────────────────────────────────────┘
        ▲                                          │
        │ cites                                    │ drives
┌───────┴──────────┐                    ┌──────────▼───────────────┐
│ ingest/          │                    │ impact/engine.py         │
│  sources.py      │  DetectedEvent     │  score = direction       │
│   fixture│rss│   ├───────────────────►│        × confidence_w    │
│   gdelt          │                    │        × surprise_w      │
│  classifier.py   │                    │        × evidence_w      │
└──────────────────┘                    └──────────┬───────────────┘
                                                   │ enriched by
┌──────────────────┐                    ┌──────────▼───────────────┐
│ market/          │   returns          │ eventstudy/              │
│  provider.py     ├───────────────────►│  car.py    AR/CAR/CAAR   │
│  fixture│yfinance│                    │  analogs.py distributions│
└──────────────────┘                    └──────────┬───────────────┘
                                                   │
        ┌──────────────────────────────────────────┼──────────┐
        ▼                     ▼                    ▼          ▼
   alerts/rules.py    alerts/digest.py    explain/explainer.py  api/
        │                     │                    │           │
        └─────────────────────┴────────────────────┴───────────┘
                              ▼
                   explain/guardrails.py   ← blocking, not advisory
```

## Component notes

### `knowledge.py`
Loads three YAML files, coerces into pydantic models, then runs referential
integrity validation. Cached via `lru_cache`. **The validation is the point** —
a transmission map with a dangling channel reference fails the build, so a bad
rule can never reach a user as a silent no-op.

### `ingest/classifier.py`
Lexical scorer with IDF weighting over archetype keywords, plus n-gram matching
for multi-word terms and entity boosts. IDF matters: "trade" appears in five
archetypes and is nearly worthless evidence, while "sahm rule" appears in one and
is decisive.

`is_ambiguous()` marks cases where the top two candidates are within 20% — those
are the only ones an LLM adjudicator should see, and it can only *choose among*
archetypes the lexical stage already surfaced. It can never invent one. That
constraint is what keeps every classification traceable to a rule in the map.

### `market/provider.py`
An interface, because every free Indian market data source is an unofficial
scraper that breaks when NSE changes its site. Two implementations ship:
`FixtureProvider` (deterministic, offline, with **injected known abnormal
returns** so the event-study engine has a ground truth to be tested against) and
`YFinanceProvider`. Production implements the same interface against Kite Connect
or a paid vendor. See [ADR-0003](docs/adr/0003-data-provider-abstraction.md).

### `eventstudy/car.py`
Standard market model. Two details worth knowing:

- **The benchmark cannot be regressed against itself.** Doing so gives β=1, α=0
  and an identically zero abnormal return — silently reporting "no effect" for
  every index-level event. For the benchmark we fall back to the constant-mean-
  return model. This was a real bug caught by the calibration report showing
  `+0` realised for every `NIFTY_50` rule.
- **Basket tests use a cross-sectional t-test**, not the time-series one, because
  sector members' residuals are demonstrably not independent of each other.

Fits are memoised on `(symbol, event_date)` — the calibration report refits the
same pairs hundreds of times.

### `impact/engine.py`
Deliberately simple and hand-reconstructable:

```
score = 100 × direction × confidence_weight × surprise_weight × evidence_weight
```

`evidence_weight` shrinks the encoded prior toward the realised hit rate as the
analog sample grows (50/50 at n=8). `surprise_weight` is concave and capped at
1.5× — a 3σ surprise is not 3× a 1σ surprise in price impact.

Ranking gives ambiguous (`direction: 0`) calls a visibility bonus when confidence
isn't low. Those are the reads a user is most likely to get wrong unaided, so
burying them at the bottom of a sorted-by-conviction list is the wrong default.

### `explain/explainer.py`
Retrieve → compose → narrate. The composed answer is complete and shippable on its
own; the LLM is a **polish layer over a finished product**, not the product. That
inversion is what makes the output auditable.

### `explain/guardrails.py`
Blocking, not advisory. See [COMPLIANCE.md](COMPLIANCE.md).

## Data flow: one event, end to end

1. `GDELTSource` / `RSSSource` returns `NewsItem`s.
2. `EventClassifier` scores each against archetype detection blocks → `DetectedEvent`.
3. `ImpactEngine.score_event` reads the archetype's impact rules from the map.
4. For each rule, `AnalogEngine.summarise` finds every *prior* occurrence
   (`before=event_date`, `exclude_event_id=event_id` — no look-ahead, asserted by
   `test_impact_uses_only_prior_history_no_lookahead`) and runs an event study on each.
5. Scores are blended, ranked, returned as `ImpactScore`.
6. `AlertEngine` / `DigestBuilder` / `Explainer` render.
7. Guardrail checks the rendered text before it reaches the user.

## Scaling notes

Nothing here is hot-path heavy. The expensive operation is the calibration report
(55 rules × up to 40 analogs × basket members ≈ 20s on the demo corpus with fit
memoisation). For production:

- Precompute analog summaries nightly into a table keyed
  `(archetype, target, window, as_of)`; the API then serves reads.
- Event studies are embarrassingly parallel across events.
- The knowledge base is small enough to live in memory permanently.

The real scaling constraint is **data licensing and freshness**, not compute.

## Testing strategy

| Layer | How it is tested |
|---|---|
| Knowledge base | schema + referential integrity + editorial rules (rationale depth, sign consistency, inverse-archetype opposition), plus a test that a *deliberately broken* map raises |
| Event study | ground-truth recovery against injected CARs; additivity across windows; false-positive rate on unaffected symbols; determinism pin |
| Impact engine | ranking, signs, no-look-ahead |
| Calibration | asserts the report is *capable* of reporting `contradicted` — a 100%-confirmed report is a bug |
| Guardrails | both directions: blocks 10 advisory phrasings, allows 6 legitimate historical ones, and asserts an imperative can't be laundered by a historical marker |
| Alerts / digest / explainer | all output must pass the guardrail |
| API | every route, including the 404 and 400 paths |

86 tests, fully hermetic (no network), ~45s.
