"""Evaluación de los puntos de la checklist que requieren un modelo de lenguaje."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from app.checklist import Checklist, ChecklistGroup, ChecklistItem
from app.llm import LLMError, LLMProvider, LLMUsage
from app.schemas import Comment, ItemResult, worst
from app.services.sections import Chunk, Section, chunk_sections
from app.services.trace import NullTrace

logger = logging.getLogger("uvicorn.error")
MAX_FINDINGS_PER_ITEM = 6

# Texto fijo: no incluir nada variable aquí para no romper la caché del prefijo.
SYSTEM_PROMPT = """Eres un revisor formativo de memorias de Trabajo de Fin de Grado (TFG) de una universidad española. Tu función es ayudar al estudiante a detectar problemas para que los corrija por sí mismo; no evalúas ni calificas.

Reglas obligatorias:
1. Trabaja solo con el texto del <borrador>. No supongas contenido que no aparece. Si recibes un fragmento, evalúa solo lo que contiene; si un punto no puede comprobarse con ese texto, usa el estado "no_evaluable".
2. NUNCA reescribas el texto del estudiante ni redactes frases para copiar. Explica qué falla y por qué, y orienta sobre cómo corregirlo con sus propias palabras.
3. Cada hallazgo debe incluir en "quote" una cita LITERAL y breve (entre 5 y 25 palabras) copiada exactamente del borrador, sin cambiar ni una letra. Sin cita literal no hay hallazgo.
4. Estados: "cumple" (sin problemas relevantes), "por_revisar" (problemas puntuales o dudosos), "no_cumple" (problema claro o extendido), "no_evaluable".
5. Sé específico y conciso: como máximo 5 hallazgos por punto, empezando por los más importantes. "evidence" resume en una o dos frases en qué te basas.
6. Los indicios de texto generado automáticamente o de copia son sospechas que el estudiante y el tutor deben verificar, nunca acusaciones.
7. Responde en español y únicamente con el objeto JSON pedido."""


def response_schema(item_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": item_ids},
                        "status": {"type": "string", "enum": ["cumple", "por_revisar", "no_cumple", "no_evaluable"]},
                        "evidence": {"type": "string"},
                        "findings": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"quote": {"type": "string"}, "feedback": {"type": "string"}},
                                "required": ["quote", "feedback"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["id", "status", "evidence", "findings"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def build_instructions(group: ChecklistGroup, items: list[ChecklistItem], chunk_label: str, whole_document: bool) -> str:
    scope = "el borrador completo" if whole_document else f"el fragmento «{chunk_label}» (el resto del documento no está disponible)"
    questions = "\n".join(f"- [{item.id}] {item.title}: {item.question}" for item in items)
    return (
        f"Bloque de revisión: {group.title}. Evalúa {scope} según estos puntos de la checklist:\n{questions}\n\n"
        f"Devuelve un objeto JSON con la clave \"items\": exactamente un elemento por cada punto ({', '.join(item.id for item in items)})."
    )


def plan_tasks(text: str, sections: list[Section], checklist: Checklist, provider: LLMProvider) -> list[tuple[ChecklistGroup, Chunk, bool]]:
    if len(text) <= provider.max_input_chars:
        whole = Chunk("documento completo", text, 0)
        return [(group, whole, True) for group in checklist.groups if checklist.llm_items(group)]
    tasks = []
    for group in checklist.groups:
        if not checklist.llm_items(group):
            continue
        for chunk in chunk_sections(text, sections, group.sections, provider.max_input_chars):
            tasks.append((group, chunk, False))
    # Las peticiones sobre el mismo fragmento, seguidas: Ollama reutiliza la caché KV del prefijo.
    return sorted(tasks, key=lambda task: (task[1].start, task[1].label))


def _provider_params(exchange: dict | None) -> dict:
    """Parámetros de la petición sin repetir el texto (ya está en `llm_request`)."""
    request = (exchange or {}).get("request") or {}
    return {key: value for key, value in request.items() if key not in ("messages", "system")}


def run_llm_review(
    text: str,
    sections: list[Section],
    checklist: Checklist,
    provider: LLMProvider,
    progress: Callable[[int, int, str], None] | None = None,
    trace=None,
) -> tuple[dict[str, ItemResult], LLMUsage, list[str]]:
    trace = trace or NullTrace()
    started = perf_counter()
    tasks = plan_tasks(text, sections, checklist, provider)
    mode = "documento completo" if tasks and tasks[0][2] else "por fragmentos"
    # Proveedores remotos: varias peticiones a la vez. Local (Ollama en CPU): de una en una.
    workers = max(1, int(getattr(provider, "parallel_requests", 1) or 1))
    logger.info("[IA] %s: %d peticiones (%s, hasta %d simultáneas).", provider.id, len(tasks), mode, workers)
    trace.event("llm_plan", model=provider.id, model_label=provider.label, remote=provider.remote, mode=mode, max_input_chars=provider.max_input_chars,
                parallel_requests=workers,
                tasks=[{"call": i, "group": g.id, "chunk": c.label, "chars": len(c.text)} for i, (g, c, _) in enumerate(tasks, start=1)],
                system_prompt=SYSTEM_PROMPT)
    outcomes: dict[int, dict] = {}
    done_lock = threading.Lock()

    def call(index: int) -> dict:
        group, chunk, whole = tasks[index - 1]
        label = f"{group.title} · {chunk.label}"
        items = checklist.llm_items(group)
        instructions = build_instructions(group, items, chunk.label, whole)
        schema = response_schema([item.id for item in items])
        logger.info("[IA] Petición %d/%d (%.0f s): %s", index, len(tasks), perf_counter() - started, label)
        trace.event("llm_request", call=index, total_calls=len(tasks), model=provider.id, group=group.id, group_title=group.title, chunk=chunk.label,
                    items=[item.id for item in items], system_prompt="(ver llm_plan.system_prompt)", document=chunk.text, instructions=instructions, schema=schema)
        call_started = perf_counter()
        outcome = {"index": index, "label": label, "chunk": chunk.label, "items": [item.id for item in items], "result": None, "usage": None, "error": None}
        try:
            outcome["result"], outcome["usage"] = provider.complete_json(SYSTEM_PROMPT, chunk.text, instructions, schema)
        except LLMError as error:
            outcome["error"], outcome["usage"] = f"{label}: {error}", error.usage  # una llamada fallida puede facturarse
            logger.error("[IA] %s", outcome["error"])
            exchange = getattr(provider, "last_exchange", None) or {}
            trace.event("llm_error", call=index, model=provider.id, group=group.id, chunk=chunk.label, seconds=round(perf_counter() - call_started, 2),
                        error=str(error), raw=error.raw, endpoint=exchange.get("endpoint"), params=_provider_params(exchange), retries=exchange.get("retries"),
                        usage=error.usage.to_dict() if error.usage else None, served_by=exchange.get("served_by"), stop_reason=exchange.get("stop_reason"),
                        reasoning_tokens=exchange.get("reasoning_tokens"), reasoning=exchange.get("reasoning"))
        else:
            exchange = getattr(provider, "last_exchange", None) or {}
            trace.event("llm_response", call=index, model=provider.id, served_by=exchange.get("served_by"), group=group.id, chunk=chunk.label,
                        seconds=round(perf_counter() - call_started, 2), usage=outcome["usage"].to_dict(), raw=exchange.get("raw_response"), parsed=outcome["result"],
                        endpoint=exchange.get("endpoint"), params=_provider_params(exchange), retries=exchange.get("retries"),
                        stop_reason=exchange.get("stop_reason") or exchange.get("done_reason"), request_id=exchange.get("request_id"),
                        reasoning_tokens=exchange.get("reasoning_tokens"), reasoning=exchange.get("reasoning"))
        with done_lock:
            outcomes[index] = outcome
            if progress:
                progress(len(outcomes), len(tasks), label)
        return outcome

    def skip(index: int) -> None:
        group, chunk, _ = tasks[index - 1]
        outcomes[index] = {"index": index, "label": f"{group.title} · {chunk.label}", "chunk": chunk.label, "items": [], "result": None, "usage": None,
                           "error": f"{group.title} · {chunk.label}: omitido tras fallos consecutivos del modelo"}
        trace.event("llm_skipped", call=index, group=group.id, chunk=chunk.label, reason="dos fallos consecutivos del modelo")

    # 1) De una en una hasta el primer acierto: así el borrador queda en la caché del
    #    proveedor antes de lanzar el resto, y una clave o un servicio caído no
    #    dispara todas las peticiones. Tras dos fallos seguidos se omite el resto.
    # 2) El resto, en paralelo (remoto) o en secuencia (local), en el mismo orden.
    if progress and tasks:
        progress(0, len(tasks), f"{tasks[0][0].title} · {tasks[0][1].label}")
    pending = list(range(1, len(tasks) + 1))
    consecutive_failures = 0
    # Sin caché que aprovechar (p. ej. OpenRouter reparte entre proveedores), no se espera a la primera.
    warm_up = workers == 1 or getattr(provider, "cache_warmup", True)
    while pending and warm_up and (workers == 1 or not any(o["error"] is None for o in outcomes.values())):
        index = pending.pop(0)
        if consecutive_failures >= 2:
            skip(index)
            continue
        consecutive_failures = consecutive_failures + 1 if call(index)["error"] else 0
    if pending:
        with ThreadPoolExecutor(max_workers=min(workers, len(pending)), thread_name_prefix="llm") as pool:
            list(pool.map(call, pending))

    partial: dict[str, list[tuple[str, dict]]] = {}
    usage, errors = LLMUsage(), []
    for index in sorted(outcomes):
        outcome = outcomes[index]
        if outcome["usage"]:
            usage.add(outcome["usage"])
        if outcome["error"]:
            errors.append(outcome["error"])
            continue
        normalised, discarded = normalise_entries(outcome["result"], outcome["items"])
        if discarded:
            trace.event("llm_normalisation", call=index, discarded=discarded,
                        note="Elementos de la respuesta que no se pudieron asociar a ningún punto de la checklist.")
        for entry in normalised:
            partial.setdefault(entry["id"], []).append((outcome["chunk"], entry))
    if progress:
        progress(len(tasks), len(tasks), "Combinando resultados")
    elapsed = perf_counter() - started
    # `usage.seconds` suma la duración de cada llamada; `wall_seconds` es lo que esperó el usuario.
    trace.event("llm_timing", wall_seconds=round(elapsed, 1), sum_of_calls_seconds=round(usage.seconds, 1), parallel_requests=workers)
    logger.info("[IA] Revisión terminada en %.0f s (suma de llamadas %.0f s): %d llamadas, %d tokens de entrada, %d de salida.", elapsed, usage.seconds, usage.calls, usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens, usage.output_tokens)
    return {item_id: _merge(item_id, entries, provider.id) for item_id, entries in partial.items()}, usage, errors


_KEY_ALIASES = {
    "id": ("id", "punto", "point", "item", "item_id", "codigo", "código", "clave", "criterion", "check"),
    "status": ("status", "estado", "resultado"),
    "evidence": ("evidence", "evidencia", "justificacion", "justificación"),
    "findings": ("findings", "hallazgos", "comentarios", "problemas"),
    "quote": ("quote", "cita", "fragmento"),
    "feedback": ("feedback", "comentario", "sugerencia", "orientacion", "orientación", "explicacion", "explicación", "issue", "problem", "problema", "description", "descripcion", "descripción", "reason", "motivo", "evidence", "evidencia"),
}
_STATUS_ALIASES = {"cumple": "cumple", "si": "cumple", "sí": "cumple", "por_revisar": "por_revisar", "por revisar": "por_revisar", "parcial": "por_revisar",
                   "no_cumple": "no_cumple", "no cumple": "no_cumple", "no": "no_cumple", "no_evaluable": "no_evaluable", "no evaluable": "no_evaluable"}


def _pick(entry: dict, field: str):
    return next((entry[key] for key in _KEY_ALIASES[field] if key in entry), None)


def normalise_entries(result, valid_ids: list[str]) -> tuple[list[dict], list]:
    """Adapta la respuesta al formato esperado aunque el proveedor no respete el
    esquema (p. ej. claves en español como «punto» o «estado»). Devuelve las
    entradas válidas y las descartadas, para dejar constancia en la traza."""
    raw_items = result.get("items") if isinstance(result, dict) else result if isinstance(result, list) else []
    if isinstance(result, dict) and raw_items is None:
        raw_items = next((v for v in result.values() if isinstance(v, list)), [])
    entries, discarded = [], []
    for entry in raw_items or []:
        if not isinstance(entry, dict):
            discarded.append(entry)
            continue
        item_id = str(_pick(entry, "id") or "").strip().strip("[]").upper()
        if item_id not in valid_ids:
            discarded.append(entry)
            continue
        status = _STATUS_ALIASES.get(str(_pick(entry, "status") or "").strip().lower().replace("-", "_"), "no_evaluable")
        findings = []
        for finding in _pick(entry, "findings") or []:
            if isinstance(finding, dict):
                findings.append({"quote": str(_pick(finding, "quote") or ""), "feedback": str(_pick(finding, "feedback") or "")})
            elif isinstance(finding, str):
                findings.append({"quote": "", "feedback": finding})
        # Algunos modelos ponen una cita suelta en el propio punto en lugar de en «findings».
        loose_quote = _pick(entry, "quote")
        if loose_quote and not findings and status in ("por_revisar", "no_cumple"):
            findings.append({"quote": str(loose_quote), "feedback": str(_pick(entry, "evidence") or "")})
        entries.append({"id": item_id, "status": status, "evidence": str(_pick(entry, "evidence") or ""), "findings": findings})
    return entries, discarded


def _merge(item_id: str, entries: list[tuple[str, dict]], model: str) -> ItemResult:
    statuses, evidence, comments, seen = [], [], [], set()
    for label, entry in entries:
        status = entry.get("status") if entry.get("status") in {"cumple", "por_revisar", "no_cumple"} else None
        if status:
            statuses.append(status)
            note = str(entry.get("evidence", "")).strip()
            if note:
                evidence.append(note if len(entries) == 1 else f"[{label}] {note}")
        for finding in entry.get("findings", []) or []:
            quote = str(finding.get("quote", "")).strip().strip("«»\"“”")
            feedback = str(finding.get("feedback", "")).strip()
            if not feedback or (quote, feedback) in seen:
                continue
            seen.add((quote, feedback))
            comments.append(Comment(feedback=feedback, quote=quote or None, location=label, source="ia", model=model))
    return ItemResult(item_id, worst(*statuses) if statuses else "no_evaluable", " ".join(evidence)[:1500], comments[:MAX_FINDINGS_PER_ITEM * max(1, len(entries))], ["ia"])
