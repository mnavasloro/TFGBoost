"""Transparent heuristic to compare a revised draft with tutor suggestions."""
from __future__ import annotations

import re

STOP_WORDS = {"para", "como", "esta", "este", "estos", "estas", "sobre", "desde", "entre", "también", "tambien", "debería", "deberia", "puede", "puedes", "debes", "trabajo", "texto", "versión", "version", "documento", "añade", "anade", "revisa", "mejora", "cambia", "hacer", "hacerlo", "con", "por", "una", "uno", "unos", "unas", "que", "del", "las", "los", "para", "más", "mas", "sin"}


def _terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}", text) if word.lower() not in STOP_WORDS}


def _suggestions(comments: str) -> list[str]:
    items = [item.strip(" -•\t") for item in re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])", comments) if item.strip()]
    return items or [comments.strip()]


def assess_revision(previous_text: str, revised_text: str, tutor_comments: str) -> dict:
    """Return evidence, not a claim of semantic correctness.

    A suggestion is marked as having *possible evidence* when at least two of its
    meaningful terms appear in newly introduced vocabulary. This intentionally
    alerts the student and tutor to review the result rather than grading it.
    """
    previous_terms, revised_terms = _terms(previous_text), _terms(revised_text)
    added_terms = revised_terms - previous_terms
    addressed, pending = [], []
    for suggestion in _suggestions(tutor_comments):
        matches = sorted(_terms(suggestion) & added_terms)
        target = addressed if len(matches) >= 2 else pending
        target.append({"suggestion": suggestion, "evidence_terms": matches})
    changed = len(added_terms)
    status = "attention" if not addressed or changed < 8 else "review"
    return {"status": status, "added_terms": changed, "addressed": addressed, "pending": pending, "message": "No se ha encontrado evidencia suficiente de aplicar las sugerencias; revisa la nueva versión antes de entregarla." if status == "attention" else "Se han detectado cambios relacionados con parte del feedback. Confirma con tu tutor que la implementación es correcta."}
