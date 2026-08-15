"""Classify a news item into an event archetype.

Two-stage by design:
  1. A transparent lexical/entity scorer (this file) that always runs. Cheap,
     deterministic, auditable, and works offline.
  2. An optional LLM adjudicator (explain/llm.py) that only sees items the
     lexical stage found *ambiguous*, and can only choose among archetypes the
     lexical stage already surfaced.

Stage 2 can never invent an archetype the knowledge base does not define. That
constraint is what keeps the pipeline auditable: every classification traces to
a rule in transmission_map.yaml.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date

from ..knowledge import KnowledgeBase
from ..models import DetectedEvent, NewsItem

_TOKEN_RE = re.compile(r"[a-z0-9\-\+]+")
# Words that carry no discriminative signal in financial headlines.
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "is", "at",
    "by", "with", "from", "after", "amid", "over", "its", "it", "says", "said",
    "may", "will", "new", "market", "markets", "stock", "stocks", "share", "shares",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def _ngrams(tokens: list[str], n: int) -> set[str]:
    return {" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


class EventClassifier:
    """Scores a headline against every archetype's detection block."""

    def __init__(self, kb: KnowledgeBase, threshold: float = 0.30) -> None:
        self.kb = kb
        self.threshold = threshold
        self._idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        """Down-weight keywords that appear in many archetypes.

        'trade' or 'china' appearing in five archetypes is much weaker evidence
        than 'sahm rule' appearing in one.
        """
        df: Counter[str] = Counter()
        n_arch = len(self.kb.archetypes)
        for arch in self.kb.archetypes.values():
            terms = {k.lower() for k in arch.detection.keywords}
            for t in terms:
                df[t] += 1
        return {t: math.log((1 + n_arch) / (1 + c)) + 1.0 for t, c in df.items()}

    # ------------------------------------------------------------------
    def score(self, text: str) -> list[tuple[str, float, list[str]]]:
        toks = _tokens(text)
        tokset = set(toks) | _ngrams(toks, 2) | _ngrams(toks, 3)
        lowered = text.lower()
        results: list[tuple[str, float, list[str]]] = []

        for arch in self.kb.archetypes.values():
            det = arch.detection
            matched: list[str] = []
            weight = 0.0
            for kw in det.keywords:
                k = kw.lower()
                if k in tokset or (" " in k and k in lowered):
                    matched.append(kw)
                    weight += self._idf.get(k, 1.0)
            for ent in det.entities:
                if ent.lower() in lowered:
                    matched.append(ent)
                    weight += 1.5
            if not matched:
                continue
            # normalise so archetypes with many keywords are not automatically favoured
            denom = math.sqrt(sum(self._idf.get(k.lower(), 1.0) for k in det.keywords) + 1e-9)
            results.append((arch.id, round(weight / max(denom, 1e-9), 4), matched))

        return sorted(results, key=lambda r: -r[1])

    # ------------------------------------------------------------------
    def classify(self, item: NewsItem, top_k: int = 3) -> list[tuple[str, float, list[str]]]:
        text = f"{item.title}. {item.summary or ''}"
        scored = self.score(text)
        return [s for s in scored if s[1] >= self.threshold][:top_k]

    def is_ambiguous(self, scored: list[tuple[str, float, list[str]]]) -> bool:
        """True when the top two candidates are within 20% — send to the LLM adjudicator."""
        if len(scored) < 2:
            return False
        return scored[1][1] > 0.8 * scored[0][1]

    # ------------------------------------------------------------------
    def to_events(self, items: list[NewsItem], top_k: int = 1) -> list[DetectedEvent]:
        events: list[DetectedEvent] = []
        seen: set[tuple[str, date]] = set()
        for item in items:
            for arch_id, score, matched in self.classify(item, top_k=top_k):
                key = (arch_id, item.published_at.date())
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    DetectedEvent(
                        event_id=f"{arch_id}:{item.published_at.date().isoformat()}",
                        archetype_id=arch_id,
                        event_date=item.published_at.date(),
                        headline=item.title,
                        sources=[item.url] if item.url else [item.source],
                        match_score=score,
                        matched_terms=matched,
                    )
                )
        return sorted(events, key=lambda e: e.event_date)


__all__ = ["EventClassifier"]
