"""Command-line interface. `python -m impacto.cli --help`"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .explain.guardrails import DISCLAIMER
from .service import Impacto


def _fmt_bps(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.0f}bps"


def cmd_health(svc: Impacto, args) -> int:
    print(json.dumps({"knowledge": svc.kb.stats(), "events": len(svc.history),
                      "provider": svc.provider.name}, indent=2))
    return 0


def cmd_archetypes(svc: Impacto, args) -> int:
    for family, arch_list in sorted(svc.kb.archetypes_by_family().items()):
        print(f"\n{family.upper()}")
        for a in arch_list:
            print(f"  {a.id:34s} {a.label}  ({len(a.impacts)} rules)")
    return 0


def cmd_classify(svc: Impacto, args) -> int:
    rows = svc.classifier.score(args.headline)[:5]
    if not rows:
        print("No archetype matched.")
        return 0
    print(f"\nHeadline: {args.headline}\n")
    for aid, score, terms in rows:
        print(f"  {score:6.3f}  {aid:34s} matched: {', '.join(terms[:6])}")
    return 0


def cmd_impact(svc: Impacto, args) -> int:
    ev = next((e for e in svc.history if e.event_id == args.event_id), None)
    if ev is None:
        print(f"unknown event '{args.event_id}'", file=sys.stderr)
        return 1
    print(f"\n{svc.kb.archetype(ev.archetype_id).label} — {ev.event_date}")
    print(f"{ev.headline}\n")
    print(f"{'TARGET':<24}{'DIR':>5}{'SCORE':>8}{'HIST MED':>10}{'HIT':>7}{'N':>5}  CHANNELS")
    print("-" * 100)
    for s in svc.impact.score_event(ev):
        arrow = {1: "up", -1: "down", 0: "both"}[s.direction]
        hit = f"{s.historical_hit_rate:.0%}" if s.historical_hit_rate is not None else "-"
        print(
            f"{s.target:<24}{arrow:>5}{s.score:>8.1f}"
            f"{_fmt_bps(s.historical_median_car_bps):>10}{hit:>7}{s.sample_size:>5}  "
            f"{','.join(s.channels)}"
        )
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_analogs(svc: Impacto, args) -> int:
    summary = svc.analogs.summarise(args.archetype_id, args.target, args.window)
    if summary is None:
        print("no analogs found")
        return 1
    print(f"\n{args.archetype_id} -> {args.target}   window {summary.window}")
    print(f"  n={summary.sample_size}  median={summary.median_car_bps:+.0f}bps  "
          f"mean={summary.mean_car_bps:+.0f}bps  sd={summary.stdev_bps:.0f}bps")
    print(f"  p5={summary.p5_bps:+.0f}bps  p95={summary.p95_bps:+.0f}bps  "
          f"hit_rate={summary.hit_rate:.0%}  p={summary.p_value:.4f}")
    print("\n  most recent occurrences:")
    for a in summary.analogs[:10]:
        print(f"    {a.event_date}  {a.car_bps:+9.0f}bps   {a.headline[:64]}")
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_calibrate(svc: Impacto, args) -> int:
    rows = svc.analogs.calibration_report(args.window)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"\nCalibration of transmission map priors vs realised history "
          f"(window {args.window})\n")
    print(f"{'ARCHETYPE':<34}{'TARGET':<22}{'STATUS':<24}{'PRIOR':>14}{'REALISED':>10}{'N':>5}")
    print("-" * 112)
    for r in sorted(rows, key=lambda r: (r["status"], r["archetype"])):
        prior = (f"[{r['prior_range_bps'][0]:.0f},{r['prior_range_bps'][1]:.0f}]"
                 if "prior_range_bps" in r else "-")
        realised = (f"{r['realised_median_bps']:+.0f}"
                    if "realised_median_bps" in r else "-")
        print(f"{r['archetype']:<34}{r['target']:<22}{r['status']:<24}"
              f"{prior:>14}{realised:>10}{r['sample_size']:>5}")
    print("\nSummary: " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("\nRules with status 'contradicted' should be demoted or removed from")
    print("knowledge/transmission_map.yaml. Do not defend a prior the data rejects.")
    return 0


def cmd_digest(svc: Impacto, args) -> int:
    day = date.fromisoformat(args.date) if args.date else svc.latest_event_date()
    events = svc.events_on(day, args.lookback)
    print(svc.digests.to_markdown(svc.digests.build(events, digest_date=day)))
    return 0


def cmd_alerts(svc: Impacto, args) -> int:
    day = date.fromisoformat(args.date) if args.date else svc.latest_event_date()
    alerts = svc.alerts.build_many(svc.events_on(day, args.lookback), args.min_severity)
    if not alerts:
        print("No alerts.")
        return 0
    for a in alerts:
        print(f"\n[{a.severity.upper()}] {a.archetype_id}  ({a.alert_id})")
        print(a.body)
        print(f"\n{a.disclaimer}")
        print("=" * 100)
    return 0


def cmd_explain(svc: Impacto, args) -> int:
    as_of = date.fromisoformat(args.as_of) if args.as_of else svc.latest_event_date()
    ex = svc.explainer.explain(args.question, as_of=as_of, target=args.target)
    print(f"\nQ: {ex.question}   (as of {as_of})\n")
    print(ex.answer)
    if ex.citations:
        print("\nSources:")
        for c in ex.citations:
            print(f"  [{c.kind}] {c.label} — {c.detail}")
    if ex.compliance_flags:
        print(f"\nCOMPLIANCE FLAGS: {ex.compliance_flags}")
    print(f"\n{ex.disclaimer}")
    return 0


def cmd_serve(svc: Impacto, args) -> int:
    import uvicorn

    uvicorn.run("impacto.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="impacto",
        description="Global events and policy decisions, mapped to Indian market impact.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="show system state").set_defaults(fn=cmd_health)
    sub.add_parser("archetypes", help="list event archetypes").set_defaults(fn=cmd_archetypes)

    c = sub.add_parser("classify", help="classify a headline into an archetype")
    c.add_argument("headline")
    c.set_defaults(fn=cmd_classify)

    c = sub.add_parser("impact", help="score sector impact for an event")
    c.add_argument("event_id")
    c.set_defaults(fn=cmd_impact)

    c = sub.add_parser("analogs", help="what happened last time this archetype occurred")
    c.add_argument("archetype_id")
    c.add_argument("target")
    c.add_argument("--window", default="T+1..T+5")
    c.set_defaults(fn=cmd_analogs)

    c = sub.add_parser("calibrate", help="score every encoded prior against realised history")
    c.add_argument("--window", default="T+1..T+5")
    c.set_defaults(fn=cmd_calibrate)

    c = sub.add_parser("digest", help="daily digest")
    c.add_argument("--date")
    c.add_argument("--lookback", type=int, default=3)
    c.set_defaults(fn=cmd_digest)

    c = sub.add_parser("alerts", help="generate alerts")
    c.add_argument("--date")
    c.add_argument("--lookback", type=int, default=1)
    c.add_argument("--min-severity", default="info", choices=["info", "watch", "high"])
    c.set_defaults(fn=cmd_alerts)

    c = sub.add_parser("explain", help="ask why a sector moved")
    c.add_argument("question")
    c.add_argument("--as-of")
    c.add_argument("--target")
    c.set_defaults(fn=cmd_explain)

    c = sub.add_parser("serve", help="run the API + dashboard")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=8000)
    c.add_argument("--reload", action="store_true")
    c.set_defaults(fn=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    svc = Impacto()
    return args.fn(svc, args)


if __name__ == "__main__":
    raise SystemExit(main())
