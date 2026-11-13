"""Orquestación del análisis: reglas + modelo → informe por punto de la checklist."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from time import perf_counter

from app.checklist import Checklist, get_checklist
from app.llm import LLMProvider
from app.schemas import Comment, ItemResult, worst
from app.services.llm_review import run_llm_review
from app.services.rules import run_rules
from app.services.sections import find_sections
from app.services.trace import NullTrace

logger = logging.getLogger("uvicorn.error")
OPEN_STATUSES = {"por_revisar", "no_cumple"}
DISCLAIMER = "Este informe es una ayuda formativa generada automáticamente: puede contener errores. No es una calificación ni sustituye el criterio del tutor."


def locate(text: str, quote: str | None) -> list[int] | None:
    """Posición de una cita en el texto, tolerando saltos de línea y espacios del PDF."""
    tokens = [token.strip("«»\"“”…") for token in re.findall(r"\S+", quote or "")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    # Cita completa y, si el modelo alteró el final, sus primeras 12 o 7 palabras.
    for size in [len(tokens)] + [n for n in (12, 7) if n < len(tokens)]:
        pattern = r"\s+".join(re.escape(token) for token in tokens[:size])
        if size == 1:
            pattern = rf"(?<!\w){pattern}(?!\w)"
        match = re.search(pattern, text) or re.search(pattern, text, re.IGNORECASE)
        if match:
            return [match.start(), match.end()]
    return None


def _merge_item(item, rule: ItemResult | None, llm: ItemResult | None, llm_enabled: bool, model_name: str = "IA") -> ItemResult:
    if item.method == "manual":
        return ItemResult(item.id, "manual", "Requiere comprobación manual: el análisis del texto no puede verificar este punto.")
    parts = [part for part in (rule if item.uses_rules else None, llm if item.uses_llm else None) if part]
    if not parts:
        reason = "Requiere un modelo de IA: vuelve a analizar el borrador eligiendo un modelo." if item.uses_llm and not llm_enabled else "No se ha podido evaluar con este borrador."
        return ItemResult(item.id, "no_evaluable", reason)
    evaluated = [p.status for p in parts if p.status != "no_evaluable"]
    return ItemResult(
        item.id,
        worst(*evaluated) if evaluated else "no_evaluable",
        " ".join(f"{'Reglas' if p.sources == ['regla'] else model_name}: {p.evidence}" if len(parts) > 1 else p.evidence for p in parts if p.evidence),
        [comment for p in parts for comment in p.comments],
        [source for p in parts for source in p.sources],
    )


def _provenance(item, rule: ItemResult | None, llm: ItemResult | None, final: ItemResult, provider: LLMProvider | None) -> dict:
    """Qué dijo cada fuente sobre el punto y cuál determinó el estado final."""
    sources = []
    if item.uses_rules:
        sources.append({"source": "regla", "label": "Reglas automáticas", "status": rule.status if rule else "no_evaluable",
                        "evidence": rule.evidence if rule else "Sin resultado de reglas.", "comments": len(rule.comments) if rule else 0})
    if item.uses_llm:
        if provider is None:
            sources.append({"source": "ia", "label": "IA (no utilizada)", "model": None, "status": "no_evaluable", "evidence": "Análisis sin modelo de IA.", "comments": 0})
        else:
            sources.append({"source": "ia", "label": provider.label, "model": provider.id, "status": llm.status if llm else "no_evaluable",
                            "evidence": llm.evidence if llm else "El modelo no devolvió resultado para este punto (error o fragmento omitido).",
                            "comments": len(llm.comments) if llm else 0})
    decided_by = [s["source"] for s in sources if s["status"] == final.status and final.status not in ("no_evaluable", "manual")]
    return {"sources": sources, "decided_by": decided_by, "rule": "El estado final es el más desfavorable entre las fuentes evaluadas."}


def _verify_comments(text: str, result: ItemResult) -> None:
    """Ancla las citas de la IA; si ninguna es verificable, no se sentencia «no cumple»."""
    for comment in result.comments:
        if comment.source == "ia" and comment.quote:
            comment.anchor = locate(text, comment.quote)
            comment.verified = comment.anchor is not None
    ai_comments = [c for c in result.comments if c.source == "ia"]
    if result.status == "no_cumple" and "ia" in result.sources and "regla" not in result.sources and ai_comments and not any(c.verified for c in ai_comments):
        result.status = "por_revisar"
        result.evidence += " (Las citas aportadas por el modelo no se han localizado en el texto: verifica este punto.)"


def compute_scores(checklist: Checklist, items: list[dict]) -> dict:
    values = checklist.scoring.get("status_values", {"cumple": 1.0, "por_revisar": 0.5, "no_cumple": 0.0})
    light = checklist.scoring.get("traffic_light", {"green": 75, "amber": 50})
    def score(selection: list[dict]) -> int | None:
        weighted = [(item["weight"], values[item["status"]]) for item in selection if item["status"] in values]
        total = sum(w for w, _ in weighted)
        return round(100 * sum(w * v for w, v in weighted) / total) if total else None
    categories = {}
    for key, meta in checklist.categories.items():
        selection = [item for item in items if item["category"] == key]
        categories[key] = {
            "label": meta["label"],
            "score": score(selection),
            "open": sum(item["status"] in OPEN_STATUSES for item in selection),
            "evaluated": sum(item["status"] in values for item in selection),
        }
    maturity = score(items) or 0
    blocking = [item["id"] for item in items if item["must_fix"] and item["status"] == "no_cumple"]
    traffic = "verde" if maturity >= light["green"] and not blocking else "ambar" if maturity >= light["amber"] else "rojo"
    return {"maturity_score": maturity, "traffic_light": traffic, "categories": categories, "blocking_items": blocking}


def analyse_document(
    text: str,
    filename: str,
    document_id: str,
    provider: LLMProvider | None,
    progress: Callable[[int, int, str], None] | None = None,
    known_headings: list[str] | None = None,
    trace=None,
) -> dict:
    trace = trace or NullTrace()
    started = perf_counter()
    checklist = get_checklist()
    sections = find_sections(text, checklist.required_sections, known_headings)
    trace.event("sections", known_headings=known_headings or [], detected=[{"key": s.key, "heading": s.heading, "start": s.start} for s in sections])
    rule_results, metrics = run_rules(text, sections, checklist)
    logger.info("[Pipeline] Reglas aplicadas en %.1f s (%d secciones detectadas).", perf_counter() - started, len(sections))
    trace.event("rules", seconds=round(perf_counter() - started, 2), metrics=metrics, results={item_id: result.to_dict() for item_id, result in rule_results.items()})
    llm_results, usage, errors = {}, None, []
    if provider:
        llm_results, usage, errors = run_llm_review(text, sections, checklist, provider, progress, trace)
    items = []
    model_name = provider.label if provider else "IA"
    for item in checklist.items:
        rule, llm = rule_results.get(item.id), llm_results.get(item.id)
        result = _merge_item(item, rule, llm, provider is not None, model_name)
        _verify_comments(text, result)
        items.append({
            **result.to_dict(),
            "category": item.category, "title": item.title, "severity": item.severity,
            "must_fix": item.must_fix, "method": item.method, "guidance": item.guidance, "weight": item.weight,
            "provenance": _provenance(item, rule, llm, result, provider),
        })
    scores = compute_scores(checklist, items)
    # Lo que verá el usuario, punto por punto, con la procedencia de cada afirmación.
    trace.event("output", model=provider.id if provider else "none", maturity_score=scores["maturity_score"], traffic_light=scores["traffic_light"],
                blocking_items=scores["blocking_items"], llm_errors=errors, usage=usage.to_dict() if usage else None,
                items=[{
                    "id": item["id"], "title": item["title"], "final_status": item["status"], "provenance": item["provenance"],
                    "shown_evidence": item["evidence"],
                    "shown_comments": [{"source": c["source"], "model": c["model"], "quote": c["quote"], "feedback": c["feedback"], "verified": c["verified"]} for c in item["comments"]],
                } for item in items])
    return {
        "schema_version": 2,
        "document_id": document_id,
        "filename": filename,
        "checklist_version": checklist.version,
        "model": provider.id if provider else "none",
        "model_label": provider.label if provider else "Solo reglas automáticas",
        "routing": getattr(provider, "routing_mode", None),
        "remote_model": bool(provider and provider.remote),
        "word_count": metrics["word_count"],
        "metrics": metrics,
        "sections": [{"key": s.key, "heading": s.heading, "start": s.start} for s in sections],
        "items": items,
        **scores,
        "usage": usage.to_dict() if usage else None,
        "llm_errors": errors,
        "duration_seconds": round(perf_counter() - started, 1),
        "disclaimer": DISCLAIMER,
    }


def compare_versions(previous: dict, current: dict, previous_responses: dict[str, dict]) -> dict:
    """Evolución respecto a la versión anterior: qué avisos se resolvieron y cuáles persisten."""
    before = {item["id"]: item for item in previous.get("items", [])}
    resolved, persisting, new, claimed = [], [], [], []
    for item in current.get("items", []):
        old = before.get(item["id"])
        was_open = bool(old and old["status"] in OPEN_STATUSES)
        is_open = item["status"] in OPEN_STATUSES
        if was_open and not is_open and item["status"] != "no_evaluable":
            resolved.append(item["id"])
        elif was_open and is_open:
            persisting.append(item["id"])
            if previous_responses.get(item["id"], {}).get("status") == "corregido":
                claimed.append(item["id"])
        elif is_open and old and old["status"] == "cumple":
            new.append(item["id"])
    return {
        "previous_id": previous.get("document_id"),
        "previous_score": previous.get("maturity_score"),
        "score_delta": (current.get("maturity_score") or 0) - (previous.get("maturity_score") or 0),
        "resolved": resolved,
        "persisting": persisting,
        "new": new,
        "claimed_fixed_but_persisting": claimed,
    }
