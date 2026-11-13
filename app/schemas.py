from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Status = Literal["cumple", "por_revisar", "no_cumple", "no_evaluable", "manual"]
Source = Literal["regla", "ia"]

STATUS_RANK = {"no_cumple": 3, "por_revisar": 2, "cumple": 1, "manual": 0, "no_evaluable": -1}


@dataclass
class Comment:
    """Comentario al margen: un fragmento literal del borrador y qué revisar en él."""
    feedback: str
    quote: str | None = None
    location: str | None = None
    source: Source = "regla"
    model: str | None = None  # modelo que generó el comentario (solo si source == "ia")
    anchor: list[int] | None = None  # [inicio, fin] en el texto extraído
    verified: bool | None = None  # None = sin cita; False = la cita no aparece en el texto


@dataclass
class ItemResult:
    id: str
    status: Status
    evidence: str = ""
    comments: list[Comment] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def worst(*statuses: str) -> str:
    """Estado más desfavorable entre los evaluados (se ignora «no_evaluable» si hay otro)."""
    candidates = [s for s in statuses if s]
    return max(candidates, key=lambda s: STATUS_RANK.get(s, -1)) if candidates else "no_evaluable"
