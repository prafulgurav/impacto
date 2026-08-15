"""Loads and validates the YAML knowledge base (the transmission map).

The knowledge base is treated as code: it is version-controlled, schema-validated
at load time, and covered by tests. A malformed transmission map is a build
failure, not a runtime surprise.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import get_settings
from .models import Archetype, Basket, Channel, Sector


class KnowledgeBase:
    def __init__(self, directory: Path | None = None) -> None:
        self.dir = Path(directory or get_settings().knowledge_dir)
        self._universe_raw = self._read("universe.yaml")
        self._channels_raw = self._read("channels.yaml")
        self._map_raw = self._read("transmission_map.yaml")

        self.channels: dict[str, Channel] = {
            c["id"]: Channel(**c) for c in self._channels_raw["channels"]
        }
        self.sectors: dict[str, Sector] = {
            s["id"]: Sector(**s) for s in self._universe_raw["sectors"]
        }
        self.baskets: dict[str, Basket] = {
            b["id"]: Basket(**b) for b in self._universe_raw["baskets"]
        }
        self.benchmark = Sector(**self._universe_raw["benchmark"])
        self.archetypes: dict[str, Archetype] = {
            a["id"]: Archetype(**a) for a in self._map_raw["archetypes"]
        }
        self.validate()

    # ------------------------------------------------------------------ io
    def _read(self, name: str) -> dict:
        path = self.dir / name
        if not path.exists():
            raise FileNotFoundError(f"knowledge file missing: {path}")
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    # ---------------------------------------------------------- validation
    def validate(self) -> None:
        """Referential integrity across the three YAML files. Raises on any break."""
        errors: list[str] = []
        for arch in self.archetypes.values():
            if arch.inverse_of and arch.inverse_of not in self.archetypes:
                errors.append(f"{arch.id}: inverse_of '{arch.inverse_of}' not found")
            if not arch.impacts:
                errors.append(f"{arch.id}: has no impacts")
            for imp in arch.impacts:
                if not imp.channels:
                    errors.append(f"{arch.id}->{imp.target}: cites no channel")
                for ch in imp.channels:
                    if ch not in self.channels:
                        errors.append(f"{arch.id}->{imp.target}: unknown channel '{ch}'")
                if self.resolve_target(imp.target) is None:
                    errors.append(f"{arch.id}: unknown target '{imp.target}'")
                if imp.direction == 0 and imp.confidence == "high":
                    errors.append(
                        f"{arch.id}->{imp.target}: direction 0 cannot be high confidence"
                    )
        if errors:
            raise ValueError("transmission map validation failed:\n  - " + "\n  - ".join(errors))

    # ------------------------------------------------------------- lookups
    def resolve_target(self, target: str) -> dict | None:
        """Return {'kind','symbols','name'} for a sector / basket / benchmark id."""
        if target == self.benchmark.id:
            return {"kind": "benchmark", "symbols": [self.benchmark.symbol], "name": self.benchmark.name}
        if target in self.sectors:
            s = self.sectors[target]
            return {"kind": "sector", "symbols": [s.symbol], "name": s.name, "proxies": s.proxies}
        if target in self.baskets:
            b = self.baskets[target]
            return {"kind": "basket", "symbols": list(b.members), "name": b.name}
        return None

    def archetype(self, archetype_id: str) -> Archetype:
        try:
            return self.archetypes[archetype_id]
        except KeyError as exc:
            raise KeyError(f"unknown archetype '{archetype_id}'") from exc

    def channel(self, channel_id: str) -> Channel:
        return self.channels[channel_id]

    def archetypes_by_family(self) -> dict[str, list[Archetype]]:
        out: dict[str, list[Archetype]] = {}
        for a in self.archetypes.values():
            out.setdefault(a.family, []).append(a)
        return out

    def stats(self) -> dict[str, int]:
        return {
            "archetypes": len(self.archetypes),
            "channels": len(self.channels),
            "sectors": len(self.sectors),
            "baskets": len(self.baskets),
            "impact_rules": sum(len(a.impacts) for a in self.archetypes.values()),
        }


@lru_cache(maxsize=4)
def load_knowledge(directory: str | None = None) -> KnowledgeBase:
    return KnowledgeBase(Path(directory) if directory else None)


__all__ = ["KnowledgeBase", "load_knowledge"]
