"""Checklist de revisión: definición declarativa en `tfg_checklist.json`.

El JSON es la única fuente de verdad: lo usan las reglas, los prompts de los
modelos, el cálculo de madurez y `docs/CHECKLIST.md` (generado con
`scripts/render_checklist.py`). Para adaptarlo a otra escuela basta con copiar
el fichero y apuntar `TFGBOOST_CHECKLIST` a la copia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

STATUSES = ("cumple", "por_revisar", "no_cumple", "no_evaluable", "manual")
SEVERITIES = ("critico", "importante", "menor")


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    category: str
    title: str
    method: str  # "rule", "llm", "rule+llm" o "manual"
    severity: str
    must_fix: bool
    question: str | None
    guidance: str
    survey: dict | None
    sources: tuple[str, ...]
    weight: float

    @property
    def uses_llm(self) -> bool:
        return "llm" in self.method

    @property
    def uses_rules(self) -> bool:
        return "rule" in self.method


@dataclass(frozen=True)
class ChecklistGroup:
    id: str
    title: str
    categories: tuple[str, ...]
    sections: tuple[str, ...]


@dataclass(frozen=True)
class Checklist:
    version: str
    items: tuple[ChecklistItem, ...]
    groups: tuple[ChecklistGroup, ...]
    categories: dict[str, dict]
    required_sections: dict[str, dict]
    scoring: dict
    raw: dict = field(repr=False)

    def item(self, item_id: str) -> ChecklistItem:
        return self._by_id()[item_id]

    def _by_id(self) -> dict[str, ChecklistItem]:
        return {item.id: item for item in self.items}

    def llm_items(self, group: ChecklistGroup) -> list[ChecklistItem]:
        return [item for item in self.items if item.uses_llm and item.category in group.categories]

    def public_definition(self) -> dict:
        """Lo que necesita la interfaz para mostrar categorías y orientaciones."""
        return {
            "version": self.version,
            "categories": self.categories,
            "items": {item.id: {"title": item.title, "category": item.category, "guidance": item.guidance, "must_fix": item.must_fix, "method": item.method} for item in self.items},
        }


def load_checklist(path: Path) -> Checklist:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    default_weight = float(raw.get("scoring", {}).get("default_weight", 0.45))
    items = []
    for entry in raw["items"]:
        if entry["severity"] not in SEVERITIES:
            raise ValueError(f"Severidad no válida en {entry['id']}: {entry['severity']}")
        if entry["category"] not in raw["categories"]:
            raise ValueError(f"Categoría desconocida en {entry['id']}: {entry['category']}")
        if "llm" in entry["method"] and not entry.get("question"):
            raise ValueError(f"El punto {entry['id']} usa IA pero no tiene pregunta.")
        survey = entry.get("survey")
        items.append(ChecklistItem(
            id=entry["id"], category=entry["category"], title=entry["title"], method=entry["method"],
            severity=entry["severity"], must_fix=bool(entry.get("must_fix")), question=entry.get("question"),
            guidance=entry["guidance"], survey=survey, sources=tuple(entry.get("sources", ())),
            weight=float(survey["priority"]) if survey else default_weight,
        ))
    if len({item.id for item in items}) != len(items):
        raise ValueError("Hay identificadores de checklist duplicados.")
    groups = tuple(ChecklistGroup(g["id"], g["title"], tuple(g["categories"]), tuple(g["sections"])) for g in raw["groups"])
    return Checklist(raw.get("version", ""), tuple(items), groups, raw["categories"], raw["required_sections"], raw.get("scoring", {}), raw)


@lru_cache(maxsize=4)
def get_checklist(path: str | None = None) -> Checklist:
    from app.config import settings
    return load_checklist(Path(path) if path else settings.checklist_path)
