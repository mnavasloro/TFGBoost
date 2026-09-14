"""Local Ollama enrichment for the formative TFG checklist."""
from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import settings
from app.services.revision_phases import COMMON_INSTRUCTIONS, phase_tasks

logger = logging.getLogger("uvicorn.error")

# Keep these checks explicit and independently auditable by the student.
def _request_check(task: dict[str, str | int]) -> dict[str, str]:
    started_at = perf_counter()
    prompt = f"""{COMMON_INSTRUCTIONS}

FASE {task['phase']}: {task['phase_title']}
SECCIÓN: {task['section']}

PREGUNTAS:
{task['questions']}

FRAGMENTO DEL BORRADOR:
---
{task['content']}
---

Devuelve JSON válido, sin markdown, con exactamente estas claves:
- status: "cumple", "por_revisar" o "no_evaluable"
- evidence: evidencia breve del borrador o "No se ha encontrado evidencia suficiente"
- feedback: orientación concreta para que el estudiante lo revise. No redactes texto para entregar.
"""
    payload = json.dumps({
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 256,
            # qwen3:8b supports up to 40,960 tokens. Set it per request so
            # this pipeline does not inherit Ollama's smaller VRAM default.
            "num_ctx": settings.ollama_context_tokens,
        },
    }).encode("utf-8")
    request = Request(
        f"{settings.ollama_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=settings.ollama_timeout_seconds) as response:
        body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    result = json.loads(body["response"])
    status = result.get("status", "no_evaluable")
    if status not in {"cumple", "por_revisar", "no_evaluable"}:
        status = "no_evaluable"
    logger.info("[Ollama] Respuesta recibida para checklist en %.1f s (estado: %s).", perf_counter() - started_at, status)
    return {
        "status": status,
        "evidence": str(result.get("evidence", "No se ha encontrado evidencia suficiente")),
        "feedback": str(result.get("feedback", "Revisa este punto con tu tutor.")),
    }


def run_checklist(text: str) -> list[dict[str, str]]:
    """Evaluate checklist items one at a time, without exposing a failed model call."""
    started_at = perf_counter()
    if not settings.ollama_enabled:
        logger.info("[Ollama] Checklist omitida: Ollama está desactivado.")
        return []

    tasks = phase_tasks(text)
    logger.info("[Ollama] Inicio de revisión: %d tareas por fase/sección, modelo %s, contexto %d tokens.", len(tasks), settings.ollama_model, settings.ollama_context_tokens)
    results: list[dict[str, str]] = []
    try:
        for index, task in enumerate(tasks, start=1):
            item = f"Fase {task['phase']} · {task['phase_title']} · {task['section']}"
            logger.info("[Ollama] Tarea %d/%d iniciada (transcurrido: %.1f s): %s", index, len(tasks), perf_counter() - started_at, item)
            results.append({"item": item, **_request_check(task)})
    except (URLError, TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        logger.error("[Ollama] Revisión detenida tras %.1f s y %d/%d tareas (%s); se marcarán las restantes como no evaluables.", perf_counter() - started_at, len(results), len(tasks), error)
        for task in tasks[len(results):]:
            item = f"Fase {task['phase']} · {task['phase_title']} · {task['section']}"
            results.append({"item": item, "status": "no_evaluable", "evidence": f"Ollama/Qwen3:8b no ha completado la petición: {error}", "feedback": "Consulta la traza de la terminal. Si el modelo usa CPU, espera a que finalice o reduce TFGBOOST_OLLAMA_CONTEXT_TOKENS."})
    else:
        logger.info("[Ollama] Revisión completada: %d/%d tareas en %.1f s.", len(results), len(tasks), perf_counter() - started_at)
    return results
