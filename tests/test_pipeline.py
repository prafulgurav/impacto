"""Classifier, impact engine, analogs, alerts, digest, explainer — end to end."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from impacto.models import NewsItem


# ------------------------------------------------------------------ classify
@pytest.mark.parametrize(
    "headline,expected",
    [
        ("OPEC+ agrees surprise output cut, Brent crude jumps 6%", "OPEC_SUPPLY_CUT"),
        ("US raises H-1B visa fee sharply, USCIS tightens norms", "US_IMMIGRATION_VISA_TIGHTENING"),
        ("Fed hikes rates 50bps, Powell signals more tightening ahead", "FED_HAWKISH_SURPRISE"),
        ("China unveils stimulus package, PBOC announces RRR cut", "CHINA_STIMULUS"),
        ("Dollar index surges, rupee hits record low", "USD_STRENGTH_SHOCK"),
        ("US payrolls miss, Sahm rule triggers recession warning", "US_RECESSION_SIGNAL"),
        ("BIS adds firms to entity list, tightens semiconductor export controls",
         "SEMICONDUCTOR_EXPORT_CONTROL"),
    ],
)
def test_classifier_top_match(classifier, headline, expected):
    scored = classifier.score(headline)
    assert scored, f"no match for {headline!r}"
    assert scored[0][0] == expected, f"{headline!r} -> {scored[:2]}"


def test_classifier_ignores_irrelevant_headlines(classifier):
    item = NewsItem(
        id="x",
        published_at=datetime(2024, 5, 1, 9, 0),
        title="Local cricket team wins the district championship final",
        source="test",
    )
    assert classifier.classify(item) == []


def test_classifier_idf_downweights_common_terms(classifier):
    """A headline with only a generic shared keyword should score low."""
    generic = classifier.score("Markets react to trade news")
    specific = classifier.score("Sahm rule triggers as US payrolls miss badly")
    assert not generic or specific[0][1] > generic[0][1]


# -------------------------------------------------------------------- impact
def test_impact_scores_are_ranked_and_signed(impact, history, kb):
    ev = next(e for e in history if e.archetype_id == "OPEC_SUPPLY_CUT")
    scores = impact.score_event(ev)
    assert len(scores) == len(kb.archetype("OPEC_SUPPLY_CUT").impacts)
    by_target = {s.target: s for s in scores}
    assert by_target["OMC"].direction == -1
    assert by_target["UPSTREAM_OIL"].direction == 1
    assert by_target["OMC"].score < 0 < by_target["UPSTREAM_OIL"].score
    for s in scores:
        assert s.channels and s.rationale


def test_impact_attaches_historical_evidence(impact, history):
    """A late event should carry a non-trivial analog sample."""
    ev = max(
        (e for e in history if e.archetype_id == "US_CPI_UPSIDE_SURPRISE"),
        key=lambda e: e.event_date,
    )
    scores = impact.score_event(ev)
    assert any(s.sample_size >= 5 for s in scores)
    assert all(s.historical_median_car_bps is not None for s in scores if s.sample_size)


def test_impact_uses_only_prior_history_no_lookahead(impact, history):
    """Evidence for an event must exclude that event and everything after it."""
    evs = sorted((e for e in history if e.archetype_id == "GOLD_SPIKE"), key=lambda e: e.event_date)
    first, last = evs[0], evs[-1]
    n_first = max(s.sample_size for s in impact.score_event(first))
    n_last = max(s.sample_size for s in impact.score_event(last))
    assert n_first == 0
    assert n_last >= len(evs) - 2


def test_portfolio_exposure_maps_holdings_without_advising(impact, history):
    ev = next(e for e in history if e.archetype_id == "USD_STRENGTH_SHOCK")
    out = impact.portfolio_exposure(ev, {"TCS.NS": 40.0, "HDFCBANK.NS": 35.0, "ITC.NS": 25.0})
    assert out["mapped_weight_pct"] > 0
    assert out["mapped_weight_pct"] + out["unmapped_weight_pct"] == pytest.approx(100.0, abs=0.1)
    assert all("recommend" not in str(r).lower() for r in out["rows"])


# -------------------------------------------------------------------- analogs
def test_analog_summary_shape(analogs):
    s = analogs.summarise("OPEC_SUPPLY_CUT", "OMC", "T+1..T+5")
    assert s is not None
    assert s.sample_size >= 10
    assert s.p5_bps <= s.median_car_bps <= s.p95_bps
    assert 0.0 <= s.hit_rate <= 1.0
    assert len(s.analogs) == s.sample_size


def test_analog_hit_rate_scores_the_encoded_prior(analogs, kb):
    """Hit rate must score the map's own direction, not a caller-supplied guess.

    Deliberately not asserting 'high-confidence rules have high hit rates' — that
    would be asserting the priors are correct, which is exactly the question the
    calibration report is supposed to answer honestly. What we assert is that the
    default expected_direction comes from the map, and that flipping it inverts
    the hit rate.
    """
    s = analogs.summarise("OPEC_SUPPLY_CUT", "AVIATION", "T+1..T+10")
    assert s is not None
    assert analogs.prior_direction("OPEC_SUPPLY_CUT", "AVIATION") == -1
    flipped = analogs.summarise(
        "OPEC_SUPPLY_CUT", "AVIATION", "T+1..T+10", expected_direction=1
    )
    assert s.hit_rate + flipped.hit_rate == pytest.approx(1.0, abs=0.02)
    assert s.median_car_bps == flipped.median_car_bps


def test_calibration_report_is_honest(analogs):
    """The report must be able to say 'contradicted'. A 100%-confirmed report is a bug."""
    rows = analogs.calibration_report("T+1..T+5")
    statuses = {r["status"] for r in rows}
    assert "confirmed" in statuses
    assert "contradicted" in statuses, "calibration is rubber-stamping every prior"
    assert len(rows) >= 40


def test_unknown_target_raises(analogs):
    with pytest.raises(KeyError):
        analogs.summarise("OPEC_SUPPLY_CUT", "NOT_A_SECTOR", "T+1..T+5")


# --------------------------------------------------------------------- alerts
def test_alert_severity_requires_evidence(service):
    ev = max(
        (e for e in service.history if e.archetype_id == "OPEC_SUPPLY_CUT"),
        key=lambda e: e.event_date,
    )
    alert = service.alerts.build(ev)
    assert alert.severity in {"info", "watch", "high"}
    assert alert.disclaimer
    assert "channel:" in alert.body
    assert "why:" in alert.body


def test_alerts_never_contain_advice_language(service):
    from impacto.explain.guardrails import check_output

    day = service.latest_event_date()
    alerts = service.alerts.build_many(service.events_on(day, 60))
    assert alerts
    for a in alerts:
        result = check_output(a.body, strict=True)
        assert result.passed, f"alert {a.alert_id} tripped guardrail: {result.flags}"


# --------------------------------------------------------------------- digest
def test_digest_has_sections_and_disclaimer(service):
    day = service.latest_event_date()
    d = service.digests.build(service.events_on(day, 10), digest_date=day)
    titles = [s.title for s in d.sections]
    assert "What happened" in titles
    assert "Where it historically lands" in titles
    assert d.disclaimer
    md = service.digests.to_markdown(d)
    assert md.startswith("# Impacto")


def test_empty_digest_is_graceful(service):
    d = service.digests.build([], digest_date=date(2016, 1, 1))
    assert "No global events" in d.headline_summary


def test_digest_passes_guardrails(service):
    from impacto.explain.guardrails import check_output

    day = service.latest_event_date()
    md = service.digests.to_markdown(service.digests.build(service.events_on(day, 20)))
    assert check_output(md, strict=True).passed


# ------------------------------------------------------------------ explainer
def test_explainer_grounds_answer_in_citations(service):
    day = service.latest_event_date()
    ex = service.explainer.explain("Why did IT stocks move today?", as_of=day)
    assert ex.answer
    assert not ex.used_llm  # no key configured in CI
    assert ex.disclaimer


def test_explainer_admits_when_it_has_nothing(service):
    ex = service.explainer.explain("Why did IT stocks fall?", as_of=date(2016, 6, 1))
    assert "No global event" in ex.answer


def test_explainer_resolves_sector_aliases(service):
    for q, expected in [
        ("why did banks fall", "NIFTY_BANK"),
        ("what happened to pharma", "NIFTY_PHARMA"),
        ("why are airlines down", "AVIATION"),
        ("nifty psu bank move", "NIFTY_PSU_BANK"),
    ]:
        assert service.explainer._resolve_target_from_question(q) == expected


def test_explainer_output_is_compliant(service):
    from impacto.explain.guardrails import check_output

    day = service.latest_event_date()
    for q in [
        "Why did IT stocks move?",
        "What does the Fed decision mean for banks?",
        "Should I buy oil marketing companies now?",
        "Will NIFTY Bank fall tomorrow?",
    ]:
        ex = service.explainer.explain(q, as_of=day)
        assert check_output(ex.answer, strict=True).passed, f"{q} -> {ex.compliance_flags}"
