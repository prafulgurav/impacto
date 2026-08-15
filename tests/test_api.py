from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["knowledge"]["archetypes"] >= 12
    assert body["compliance_mode"] is True


def test_archetype_listing_and_detail(client):
    r = client.get("/knowledge/archetypes")
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()]
    assert "OPEC_SUPPLY_CUT" in ids

    r = client.get("/knowledge/archetypes/OPEC_SUPPLY_CUT")
    assert r.status_code == 200
    detail = r.json()
    assert detail["impacts"]
    assert all(i["channels"] for i in detail["impacts"])

    assert client.get("/knowledge/archetypes/NOPE").status_code == 404


def test_channels(client):
    r = client.get("/knowledge/channels")
    assert r.status_code == 200
    assert any(c["id"] == "fii_flow" for c in r.json())


def test_classify_endpoint(client):
    r = client.post("/events/classify", params={"headline": "OPEC+ announces output cut"})
    assert r.status_code == 200
    assert r.json()[0]["archetype_id"] == "OPEC_SUPPLY_CUT"


def test_events_and_impact(client):
    r = client.get("/events", params={"archetype_id": "OPEC_SUPPLY_CUT", "limit": 3})
    assert r.status_code == 200
    events = r.json()
    assert events
    eid = events[0]["event_id"]

    r = client.get(f"/impact/{eid}")
    assert r.status_code == 200
    scores = r.json()
    assert scores
    assert {s["target"] for s in scores} >= {"OMC", "UPSTREAM_OIL"}

    assert client.get("/impact/does-not-exist").status_code == 404


def test_eventstudy_endpoint(client):
    r = client.get(
        "/eventstudy",
        params={"symbol": "^CNXIT", "event_date": "2023-06-15", "window": "T+1..T+5"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "cumulative_abnormal_return_bps" in body
    assert body["estimation_obs"] >= 60

    bad = client.get(
        "/eventstudy", params={"symbol": "^CNXIT", "event_date": "2023-06-15", "window": "junk"}
    )
    assert bad.status_code == 400


def test_analogs_endpoint(client):
    r = client.get("/analogs", params={"archetype_id": "OPEC_SUPPLY_CUT", "target": "OMC"})
    assert r.status_code == 200
    body = r.json()
    assert body["sample_size"] > 0
    assert body["disclaimer"]

    assert client.get(
        "/analogs", params={"archetype_id": "OPEC_SUPPLY_CUT", "target": "BOGUS"}
    ).status_code == 404


def test_digest_and_alerts(client):
    r = client.get("/digest")
    assert r.status_code == 200
    assert r.json()["sections"]

    r = client.get("/digest.md")
    assert r.status_code == 200
    assert r.text.startswith("# Impacto")

    r = client.get("/alerts", params={"lookback_days": 10})
    assert r.status_code == 200


def test_explain_endpoint_is_compliant(client):
    from impacto.explain.guardrails import check_output

    r = client.get("/explain", params={"q": "Should I buy IT stocks after this Fed decision?"})
    assert r.status_code == 200
    body = r.json()
    assert check_output(body["answer"], strict=True).passed
    assert body["disclaimer"]


def test_portfolio_exposure_endpoint(client):
    events = client.get("/events", params={"archetype_id": "USD_STRENGTH_SHOCK", "limit": 1}).json()
    r = client.post(
        "/impact/portfolio",
        json={"event_id": events[0]["event_id"], "holdings": {"TCS.NS": 50, "HDFCBANK.NS": 50}},
    )
    assert r.status_code == 200
    assert r.json()["disclaimer"]


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Impacto" in r.text
