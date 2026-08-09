"""Explainable, local-first checks used before optional LLM enrichment.

The analyser deliberately identifies opportunities to revise; it never generates
replacement thesis prose, in keeping with TFGBoost's formative purpose.
"""
from __future__ import annotations

import re
from collections import Counter
from uuid import uuid4

from app.schemas import AnalysisReport, Finding

EXPECTED_SECTIONS = [
    "resumen", "índice", "introducción", "objetivos", "metodología",
    "desarrollo", "resultados", "conclusiones", "referencias",
]
SECTION_ALIASES = {
    "resumen": ("resumen", "abstract"),
    "índice": ("índice", "indice", "tabla de contenidos"),
    "introducción": ("introducción", "introduccion"),
    "objetivos": ("objetivos", "objetivo"),
    "metodología": ("metodología", "metodologia", "método", "metodo"),
    "desarrollo": ("desarrollo", "implementación", "implementacion", "análisis", "analisis"),
    "resultados": ("resultados", "evaluación", "evaluacion", "experimentos"),
    "conclusiones": ("conclusiones", "conclusión", "conclusion"),
    "referencias": ("referencias", "bibliografía", "bibliografia"),
}
CONNECTORS = ("por tanto", "sin embargo", "además", "ademas", "en cambio", "por ejemplo", "en consecuencia", "no obstante")
VAGUE_WORDS = ("cosa", "cosas", "bastante", "muy", "etc.", "obviamente", "fácil", "facil")


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _find_sections(text: str) -> tuple[list[str], list[str]]:
    lower = text.lower()
    found = [section for section, aliases in SECTION_ALIASES.items() if any(re.search(rf"(?m)^\s*(?:\d+(?:\.\d+)*\s+)?{re.escape(alias)}\s*$", lower) for alias in aliases)]
    missing = [item for item in EXPECTED_SECTIONS if item not in found]
    return found, missing


def analyse(text: str, filename: str, document_id: str | None = None) -> AnalysisReport:
    """Produce an inspectable report from extracted draft text."""
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    words = re.findall(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ'-]+\b", normalized)
    word_count = len(words)
    sentences = _sentences(normalized)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    found, missing = _find_sections(text)
    findings: list[Finding] = []

    if word_count < 800:
        findings.append(Finding("estructura", "attention", "Borrador todavía breve", "El texto contiene menos de 800 palabras; algunas secciones pueden estar aún sin desarrollar.", "Contrasta la extensión esperada con la guía de tu titulación y completa primero el esquema de cada capítulo."))
    if missing:
        findings.append(Finding("estructura", "warning", "Secciones por comprobar", f"No se han identificado estos encabezados habituales: {', '.join(missing)}.", "Revisa la normativa de tu centro: adapta o añade los apartados requeridos y usa encabezados inequívocos.", "Índice / encabezados"))

    average_sentence = (sum(len(re.findall(r"\w+", s)) for s in sentences) / len(sentences)) if sentences else 0
    long_sentences = [s for s in sentences if len(re.findall(r"\w+", s)) > 42]
    if long_sentences:
        findings.append(Finding("claridad", "warning", "Oraciones extensas", f"Se han detectado {len(long_sentences)} oraciones con más de 42 palabras.", "Relee cada una: separa las ideas independientes y comprueba que sujeto, verbo y complemento se entienden en una sola lectura.", long_sentences[0][:100] + "…"))
    very_long_paragraphs = [p for p in paragraphs if len(re.findall(r"\w+", p)) > 180]
    if very_long_paragraphs:
        findings.append(Finding("claridad", "info", "Párrafos densos", f"Hay {len(very_long_paragraphs)} párrafos de más de 180 palabras.", "Considera dividirlos cuando cambie la idea principal; empieza cada párrafo con la idea que vas a defender."))

    lower = normalized.lower()
    vague_counts = Counter(word for word in VAGUE_WORDS if re.search(rf"\b{re.escape(word)}", lower))
    if vague_counts:
        terms = ", ".join(f"«{term}» ({count})" for term, count in vague_counts.items())
        findings.append(Finding("redaccion", "info", "Expresiones imprecisas", f"Aparecen expresiones que pueden requerir precisión: {terms}.", "Comprueba si puedes sustituirlas por una medida, una definición o una referencia concreta."))
    repeated_spaces = len(re.findall(r" {2,}", text))
    if repeated_spaces:
        findings.append(Finding("redaccion", "info", "Espaciado irregular", f"Se han encontrado {repeated_spaces} grupos de espacios consecutivos.", "Normaliza el formato antes de la entrega para que la revisión se centre en el contenido."))

    connector_hits = sum(lower.count(connector) for connector in CONNECTORS)
    if word_count > 500 and connector_hits < max(2, word_count // 1000):
        findings.append(Finding("coherencia", "info", "Conexión entre ideas", "Se han detectado pocos conectores argumentativos en relación con la extensión del texto.", "Al revisar transiciones entre párrafos, explicita la relación: causa, contraste, ejemplo o consecuencia."))

    citations = len(re.findall(r"\([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ-]+(?:\s+et al\.)?,?\s*\d{4}[a-z]?\)", text))
    has_references = "referencias" in found
    if citations and not has_references:
        findings.append(Finding("referencias", "attention", "Citas sin sección de referencias detectable", f"Se han identificado aproximadamente {citations} citas en el texto.", "Incluye una sección de referencias y comprueba que cada cita del texto tenga una entrada completa según el estilo exigido."))
    elif has_references and citations == 0:
        findings.append(Finding("referencias", "info", "Comprobación de trazabilidad", "Hay una sección de referencias, pero no se detectó el patrón habitual de citas autor-fecha.", "Verifica que las fuentes se citen en el cuerpo con el formato establecido por tu titulación."))

    structure = _clamp(100 * len(found) / len(EXPECTED_SECTIONS))
    clarity = _clamp(100 - max(0, average_sentence - 22) * 2 - len(very_long_paragraphs) * 4)
    coherence = _clamp(58 + min(26, connector_hits * 4) + min(16, len(found) * 2))
    writing = _clamp(92 - min(30, len(vague_counts) * 5 + repeated_spaces))
    references = _clamp(35 + (30 if has_references else 0) + min(35, citations * 4))
    metrics = {"estructura": structure, "claridad": clarity, "coherencia": coherence, "redaccion": writing, "referencias": references}
    maturity = _clamp(sum(metrics.values()) / len(metrics))
    return AnalysisReport(document_id=document_id or str(uuid4()), filename=filename, word_count=word_count, maturity_score=maturity, metrics=metrics, sections_found=found, sections_missing=missing, findings=findings)
