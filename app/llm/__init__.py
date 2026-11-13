"""Registro de modelos disponibles (Ollama locales; Claude y OpenRouter remotos)."""
from __future__ import annotations

import threading

from app.config import settings
from app.llm.anthropic_provider import LABELS as CLAUDE_LABELS, AnthropicProvider
from app.llm.base import LLMError, LLMProvider, LLMUsage
from app.llm.ollama import OllamaProvider, installed_models, parse_model_spec
from app.llm.openrouter import OpenRouterProvider, catalogue as openrouter_catalogue

NO_LLM = "none"
_semaphores = {
    "ollama": threading.BoundedSemaphore(max(1, settings.ollama_concurrency)),
    "anthropic": threading.BoundedSemaphore(max(1, settings.anthropic_concurrency)),
    "openrouter": threading.BoundedSemaphore(max(1, settings.openrouter_concurrency)),
}

__all__ = ["LLMError", "LLMProvider", "LLMUsage", "NO_LLM", "available_models", "get_provider", "provider_slot"]


def _ollama_specs() -> list[tuple[str, int, bool]]:
    """(nombre, contexto, disponible) de cada modelo ofrecido. Ollama no distingue
    mayúsculas («Qwen3:8b» = «qwen3:8b»), así que se usa el nombre instalado."""
    installed = installed_models()
    by_lower = {name.lower(): name for name in installed or []}
    configured = [parse_model_spec(spec) for spec in settings.ollama_models]
    if not configured and installed:
        configured = [(name, settings.ollama_context_tokens) for name in installed]
    specs = []
    for name, context in configured:
        actual = by_lower.get(name.lower()) or by_lower.get(f"{name.lower()}:latest")
        specs.append((actual or name, context, actual is not None))
    return specs


def available_models() -> list[dict]:
    """Opciones para la interfaz. `available` es False si el servicio no responde."""
    models = [{"id": NO_LLM, "label": "Solo reglas automáticas (sin IA, instantáneo)", "provider": "rules", "remote": False, "available": True}]
    if settings.ollama_enabled:
        for name, context, available in _ollama_specs():
            models.append({"id": f"ollama:{name}", "label": f"{name} · local (Ollama, contexto {context})", "provider": "ollama", "remote": False, "available": available})
    if settings.anthropic_enabled:
        for name in settings.anthropic_models:
            models.append({"id": f"anthropic:{name}", "label": f"{CLAUDE_LABELS.get(name, name)} · Anthropic (remoto, de pago)", "provider": "anthropic", "remote": True, "available": True, "provider_name": "Anthropic"})
    if settings.openrouter_enabled:
        published = openrouter_catalogue()
        for spec in settings.openrouter_models:
            name, _, _context = spec.partition("@")
            info = (published or {}).get(name)
            price = ""
            if info:
                pricing = info.get("pricing") or {}
                price = f", {float(pricing.get('prompt') or 0) * 1e6:.2f}/{float(pricing.get('completion') or 0) * 1e6:.2f} US$ por M tokens"
            # Si el catálogo no responde, se ofrece igualmente; si responde, el modelo debe existir.
            available = bool(settings.openrouter_api_key) and (published is None or info is not None)
            models.append({"id": f"openrouter:{name}", "label": f"{name} · OpenRouter (remoto, de pago{price})", "provider": "openrouter", "remote": True, "available": available, "provider_name": "OpenRouter"})
    return models


def default_model() -> str:
    options = {m["id"]: m for m in available_models()}
    configured = next((m for m in options.values() if m["id"].lower() == settings.default_model.lower()), None)
    if configured and configured["available"]:
        return configured["id"]
    return next((m["id"] for m in options.values() if m["available"] and m["id"] != NO_LLM), NO_LLM)


def get_provider(model_id: str, routing: str | None = None) -> LLMProvider | None:
    """Proveedor para un identificador de la lista permitida (None = solo reglas)."""
    if model_id == NO_LLM:
        return None
    provider, _, model = model_id.partition(":")
    if provider == "ollama" and settings.ollama_enabled:
        for name, context, _available in _ollama_specs():
            if name.lower() == model.lower():
                return OllamaProvider(name, context)
    if provider == "anthropic" and settings.anthropic_enabled and model in settings.anthropic_models:
        return AnthropicProvider(model)
    if provider == "openrouter" and settings.openrouter_enabled:
        for spec in settings.openrouter_models:
            name, _, context = spec.partition("@")
            if name == model:
                return OpenRouterProvider(name, int(context) if context.strip().isdigit() else None, routing)
    raise ValueError(f"Modelo no permitido o no configurado: {model_id}")


def provider_slot(provider: LLMProvider) -> threading.BoundedSemaphore:
    """Semáforo que limita los análisis simultáneos por proveedor."""
    return _semaphores.get(provider.id.partition(":")[0], _semaphores["ollama"])
