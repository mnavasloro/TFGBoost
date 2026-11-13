"""Proveedor remoto: Claude mediante la API de Anthropic (pago por tokens).

El borrador completo se envía una vez como bloque de sistema con
`cache_control`; las peticiones de cada grupo de la checklist lo leen de la
caché (~10 % del precio de entrada) y solo cambian las preguntas.
"""
from __future__ import annotations

import json
import logging
import re
from time import perf_counter

from app.config import settings
from app.llm.base import ExchangeRecorder, LLMError, LLMUsage

logger = logging.getLogger("uvicorn.error")

# USD por millón de tokens: (entrada, salida, lectura de caché). La escritura en
# caché cuesta 1,25 × la entrada. Estimación orientativa: consulta los precios vigentes.
PRICES = {
    "claude-fable-5-2": (8.0, 40.0, 0.20),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
LABELS = {
    "claude-fable-5-2": "Claude Fable 5.2",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-haiku-5-5": "Claude Haiku 5.5",
}
# Modelos con reintento automático en el servidor si declinan la petición.
SERVER_FALLBACK_MODELS = {"claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5"}
_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as error:
            raise LLMError("Falta el paquete `anthropic`. Instálalo con «pip install -r requirements.txt».") from error
        # Credenciales: ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN o perfil de `ant auth login`.
        _client = anthropic.Anthropic(timeout=settings.anthropic_timeout_seconds, max_retries=3)
    return _client


def estimate_cost(model: str, usage: LLMUsage) -> float:
    price_in, price_out, price_cache = PRICES.get(model, (0.0, 0.0, 0.0))
    return (usage.input_tokens * price_in + usage.cache_write_tokens * price_in * 1.25 + usage.cache_read_tokens * price_cache + usage.output_tokens * price_out) / 1_000_000


class AnthropicProvider(ExchangeRecorder):
    remote = True
    # La primera petición deja el borrador en caché; las demás lo leen al ~10 % del precio.
    cache_warmup = True

    @property
    def parallel_requests(self) -> int:
        return settings.llm_parallel_requests
    # ~150.000 tokens: un TFG completo cabe en una sola petición.
    max_input_chars = 600_000

    def __init__(self, model: str):
        self.model = model
        self.id = f"anthropic:{model}"
        self.label = f"{LABELS.get(model, model)} (Anthropic, remoto)"
        self.last_exchange: dict | None = None

    def complete_json(self, system: str, document: str, instructions: str, schema: dict) -> tuple[dict, LLMUsage]:
        import anthropic

        started = perf_counter()
        params: dict = {
            "model": self.model,
            "max_tokens": settings.anthropic_max_output_tokens,
            # Prefijo estable (instrucciones + borrador) en caché; solo varía el mensaje.
            "system": [
                {"type": "text", "text": system},
                {"type": "text", "text": f"<borrador>\n{document}\n</borrador>", "cache_control": {"type": "ephemeral"}},
            ],
            "messages": [{"role": "user", "content": instructions}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if not re.search(r"haiku-4|sonnet-4-5|claude-3", self.model):
            params["output_config"]["effort"] = settings.anthropic_effort
        client = _get_client()
        use_fallbacks = settings.anthropic_fallbacks and self.model in SERVER_FALLBACK_MODELS
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if use_fallbacks else {}
        self.last_exchange = {"endpoint": "POST /v1/messages" + (" (beta)" if use_fallbacks else ""), "request": {**params, **extra}, "raw_response": None}
        try:
            response = client.beta.messages.create(**extra, **params) if use_fallbacks else client.messages.create(**params)
        except anthropic.APIStatusError as error:
            raw = f"HTTP {error.status_code}: {json.dumps(error.body, ensure_ascii=False) if error.body is not None else error.message}"
            self.last_exchange["raw_response"] = raw
            if isinstance(error, anthropic.AuthenticationError):
                message = "La clave de Anthropic no es válida o no está configurada (ANTHROPIC_API_KEY)."
            elif isinstance(error, anthropic.PermissionDeniedError):
                message = f"La clave de Anthropic no tiene permiso para usar {self.model}."
            elif isinstance(error, anthropic.NotFoundError):
                message = f"Modelo no encontrado en Anthropic: {self.model}."
            elif isinstance(error, anthropic.RateLimitError):
                message = "Se ha superado el límite de peticiones de Anthropic; inténtalo más tarde."
            elif "credit balance" in str(error.message).lower():
                message = "La cuenta de Anthropic no tiene crédito suficiente. Recarga créditos en la consola de Anthropic o usa un modelo local."
            else:
                message = f"Error de la API de Anthropic ({error.status_code}): {error.message}"
            raise LLMError(message, raw=raw) from error
        except anthropic.APIConnectionError as error:
            self.last_exchange["raw_response"] = repr(error)
            raise LLMError(f"No se pudo conectar con la API de Anthropic: {error}", raw=repr(error)) from error

        text = "".join(block.text for block in response.content if block.type == "text")
        self.last_exchange.update({
            "raw_response": text,
            "stop_reason": response.stop_reason,
            # Con `fallbacks`, el modelo que responde puede no ser el solicitado.
            "served_by": getattr(response, "model", self.model),
            "request_id": getattr(response, "_request_id", None),
        })
        raw_usage = response.usage
        usage = LLMUsage(
            calls=1,
            input_tokens=raw_usage.input_tokens or 0,
            output_tokens=raw_usage.output_tokens or 0,
            cache_read_tokens=getattr(raw_usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(raw_usage, "cache_creation_input_tokens", 0) or 0,
            seconds=perf_counter() - started,
        )
        usage.cost_usd = estimate_cost(self.model, usage)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMError("El modelo declinó evaluar este fragmento.", raw=f"stop_reason=refusal; stop_details={details}; texto={text}", usage=usage)
        if response.stop_reason == "max_tokens":
            raise LLMError("La respuesta superó el máximo de tokens configurado (TFGBOOST_ANTHROPIC_MAX_OUTPUT_TOKENS).", raw=text, usage=usage)
        try:
            return json.loads(text), usage
        except json.JSONDecodeError as error:
            raise LLMError(f"Respuesta no válida de {self.model}: {text[:200]}", raw=text, usage=usage) from error
