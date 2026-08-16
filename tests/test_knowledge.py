"""The transmission map is the product. These tests are its spec."""
from __future__ import annotations

import pytest

from impacto.knowledge import KnowledgeBase


def test_loads_and_validates(kb: KnowledgeBase):
    stats = kb.stats()
    assert stats["archetypes"] >= 12
    assert stats["impact_rules"] >= 40
    assert stats["channels"] >= 8


def test_every_impact_cites_a_defined_channel(kb: KnowledgeBase):
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            assert imp.channels, f"{arch.id}->{imp.target} cites no channel"
            for ch in imp.channels:
                assert ch in kb.channels, f"{arch.id}->{imp.target}: unknown channel {ch}"


def test_every_target_resolves(kb: KnowledgeBase):
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            assert kb.resolve_target(imp.target) is not None, f"{arch.id}: bad target {imp.target}"


def test_every_impact_has_a_real_rationale(kb: KnowledgeBase):
    """No unexplained signs. A direction without a mechanism is astrology."""
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            words = imp.rationale.split()
            assert len(words) >= 12, f"{arch.id}->{imp.target}: rationale too thin"


def test_magnitude_ranges_are_ordered_and_sign_consistent(kb: KnowledgeBase):
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            lo, hi = imp.magnitude_prior_bps
            assert lo <= hi
            if imp.direction > 0:
                assert hi > 0, f"{arch.id}->{imp.target}: positive direction, non-positive range"
            if imp.direction < 0:
                assert lo < 0, f"{arch.id}->{imp.target}: negative direction, non-negative range"


def test_ambiguous_calls_are_never_high_confidence(kb: KnowledgeBase):
    for arch in kb.archetypes.values():
        for imp in arch.impacts:
            if imp.direction == 0:
                assert imp.confidence != "high"


def test_inverse_archetypes_have_opposite_signs(kb: KnowledgeBase):
    """CRUDE_COLLAPSE must not agree with OPEC_SUPPLY_CUT on a shared target."""
    for arch in kb.archetypes.values():
        if not arch.inverse_of:
            continue
        other = kb.archetype(arch.inverse_of)
        a = {i.target: i.direction for i in arch.impacts}
        b = {i.target: i.direction for i in other.impacts}
        shared = set(a) & set(b)
        assert shared, f"{arch.id} declares inverse_of {other.id} but shares no target"
        for t in shared:
            if a[t] != 0 and b[t] != 0:
                assert a[t] == -b[t], f"{arch.id} vs {other.id} agree on {t}; inverse must oppose"


def test_detection_blocks_have_keywords(kb: KnowledgeBase):
    for arch in kb.archetypes.values():
        assert arch.detection.keywords or arch.detection.indicators, f"{arch.id} undetectable"


def test_broken_map_is_rejected(tmp_path):
    """A malformed knowledge base must fail loudly at load, not at runtime."""
    import shutil
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "knowledge"
    shutil.copytree(src, tmp_path / "kb")
    bad = (tmp_path / "kb" / "transmission_map.yaml").read_text().replace(
        "channels: [fii_flow, rate_differential]",
        "channels: [does_not_exist]",
        1,
    )
    (tmp_path / "kb" / "transmission_map.yaml").write_text(bad)
    with pytest.raises(ValueError, match="validation failed"):
        KnowledgeBase(tmp_path / "kb")
