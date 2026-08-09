from dataclasses import asdict, dataclass
from typing import Literal

Category = Literal["estructura", "claridad", "coherencia", "redaccion", "referencias"]
Severity = Literal["info", "warning", "attention"]


@dataclass
class Finding:
    category: Category
    severity: Severity
    title: str
    explanation: str
    suggestion: str
    location: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisReport:
    document_id: str
    filename: str
    word_count: int
    maturity_score: int
    metrics: dict[str, int]
    sections_found: list[str]
    sections_missing: list[str]
    findings: list[Finding]
    disclaimer: str = "Este informe es una ayuda formativa. No sustituye la revisión ni el criterio del tutor."

    def to_dict(self) -> dict:
        result = asdict(self)
        result["findings"] = [item.to_dict() for item in self.findings]
        return result
