"""Typed domain model. These schemas are the contract between every layer."""
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Direction = Literal[-1, 0, 1]
Confidence = Literal["high", "medium", "low"]


class ChannelKind(StrEnum):
    EARNINGS = "earnings"
    DISCOUNT_RATE = "discount_rate"
    MACRO = "macro"


class Channel(BaseModel):
    id: str
    name: str
    kind: ChannelKind
    horizon: Literal["fast", "medium", "slow"]
    description: str
    observable_proxies: list[str] = Field(default_factory=list)


class ImpactPrior(BaseModel):
    """A hypothesis: archetype X should move target Y by this much, via these channels."""

    target: str
    direction: Direction
    magnitude_prior_bps: tuple[float, float]
    horizon: str
    confidence: Confidence
    channels: list[str]
    rationale: str

    @field_validator("magnitude_prior_bps")
    @classmethod
    def _ordered(cls, v: tuple[float, float]) -> tuple[float, float]:
        lo, hi = v
        if lo > hi:
            raise ValueError(f"magnitude_prior_bps must be [low, high], got {v}")
        return v

    @field_validator("rationale")
    @classmethod
    def _non_trivial(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("rationale must be a real explanation (>=20 chars)")
        return v


class Detection(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    indicators: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    gdelt_event_root_codes: list[str] = Field(default_factory=list)
    surprise_rule: str | None = None
    min_sample: int = 5


class Archetype(BaseModel):
    id: str
    label: str
    family: str
    description: str
    detection: Detection = Field(default_factory=Detection)
    impacts: list[ImpactPrior]
    inverse_of: str | None = None


class Sector(BaseModel):
    id: str
    symbol: str
    name: str
    proxies: list[str] = Field(default_factory=list)
    fii_ownership_bucket: Literal["high", "medium", "low"] = "medium"
    usd_revenue_share: float = 0.0
    imported_input_intensity: float = 0.0


class Basket(BaseModel):
    id: str
    name: str
    members: list[str]


class NewsItem(BaseModel):
    id: str
    published_at: datetime
    title: str
    url: str | None = None
    source: str
    summary: str | None = None
    language: str = "en"


class DetectedEvent(BaseModel):
    """A concrete real-world occurrence classified into an archetype."""

    event_id: str
    archetype_id: str
    event_date: date
    headline: str
    sources: list[str] = Field(default_factory=list)
    match_score: float = 0.0
    matched_terms: list[str] = Field(default_factory=list)
    surprise_magnitude: float | None = None
    notes: str | None = None


class ImpactScore(BaseModel):
    """Model output for one target under one detected event."""

    target: str
    target_kind: Literal["sector", "basket", "benchmark"]
    direction: Direction
    score: float = Field(description="Signed 0-100 conviction-weighted impact score")
    magnitude_prior_bps: tuple[float, float]
    horizon: str
    confidence: Confidence
    channels: list[str]
    rationale: str
    historical_hit_rate: float | None = None
    historical_median_car_bps: float | None = None
    sample_size: int = 0


class EventStudyResult(BaseModel):
    target: str
    symbol: str
    event_date: date
    window: str
    abnormal_return_bps: float
    cumulative_abnormal_return_bps: float
    t_stat: float
    p_value: float
    significant_at_5pct: bool
    alpha: float
    beta: float
    r_squared: float
    estimation_obs: int


class AnalogEvent(BaseModel):
    event_id: str
    event_date: date
    headline: str
    similarity: float
    car_bps: float


class AnalogSummary(BaseModel):
    archetype_id: str
    target: str
    window: str
    sample_size: int
    mean_car_bps: float
    median_car_bps: float
    stdev_bps: float
    hit_rate: float = Field(description="Share of analogs matching the prior's direction")
    p5_bps: float
    p95_bps: float
    t_stat: float
    p_value: float
    analogs: list[AnalogEvent] = Field(default_factory=list)


class Alert(BaseModel):
    alert_id: str
    created_at: datetime
    severity: Literal["info", "watch", "high"]
    archetype_id: str
    headline: str
    targets: list[str]
    body: str
    disclaimer: str


class DigestSection(BaseModel):
    title: str
    bullets: list[str]


class Digest(BaseModel):
    digest_date: date
    generated_at: datetime
    headline_summary: str
    sections: list[DigestSection]
    events: list[DetectedEvent]
    disclaimer: str


class ExplainRequest(BaseModel):
    question: str
    as_of: date | None = None
    target: str | None = None


class Citation(BaseModel):
    label: str
    kind: Literal["event", "event_study", "analog", "transmission_map", "news"]
    detail: str


class Explanation(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    compliance_flags: list[str] = Field(default_factory=list)
    used_llm: bool = False
    disclaimer: str


__all__ = [
    "Direction", "Confidence", "ChannelKind", "Channel", "ImpactPrior", "Detection",
    "Archetype", "Sector", "Basket", "NewsItem", "DetectedEvent", "ImpactScore",
    "EventStudyResult", "AnalogEvent", "AnalogSummary", "Alert", "DigestSection",
    "Digest", "ExplainRequest", "Citation", "Explanation",
]
