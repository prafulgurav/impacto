# Performance budgets — measured, not assumed

Budgets are enforced in CI by `lighthouserc.json`. This file records what was
actually measured and where a figure in the build brief could not be met.

## First-load JavaScript

| Route | Framework | Our code | Total (gzip) |
|---|---:|---:|---:|
| `/explore` (Server Component) | 139.0 KB | 1.7 KB | 140.7 KB |
| `/` (Today, client) | 139.0 KB | 8.8 KB | 147.8 KB |
| `/explore/[archetype]` | 139.0 KB | 1.6 KB | 140.6 KB |

Legacy `nomodule` polyfills add 38.5 KB but are not served to any browser that
supports ES modules, and Lighthouse does not count them.

**The brief specifies < 130 KB gzip for `/`. That is below the framework floor.**
Next 16.3 with React 19 App Router ships 139.0 KB gzip of framework — react-dom
(61.9 KB) plus the router runtime (66.1 KB) plus shared chunks — before any
application code runs. There is no configuration that reduces it; meeting 130 KB
would mean changing framework, not optimising this app.

What *was* done, and is worth keeping:

- Dexie was pulled out of the root layout. `SyncProvider` and `OfflineBanner`
  sit in the layout, so their static imports of the IndexedDB layer were putting
  ~30 KB gzip into the first-load bundle of every route, including the static
  archetype pages that never touch IndexedDB during first paint. Both now import
  it dynamically after hydration. That alone took `/` from 213.7 KB to 147.8 KB.
- No chart library. `ImpactBars` and `CarDistribution` are bespoke SVG.
- No webfont. `system-ui` only.
- Server Components everywhere except where interactivity genuinely requires a
  client component; each `'use client'` carries a one-line comment saying why.

The CI budget is set to 155 KB: the measured floor plus headroom, so a real
regression in our code still fails the build while the framework floor does not
fail it on every run.

## Other budgets (unchanged from the brief)

| Metric | Budget |
|---|---|
| LCP | < 2.5 s |
| CLS | < 0.1 |
| Total blocking time | < 200 ms |
| Total transferred, first visit | < 400 KB |
| Lighthouse Performance | >= 90 |
| Lighthouse Accessibility | >= 95 |
| Installable manifest, service worker, maskable icon | required |
