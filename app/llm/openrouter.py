"""Proveedor remoto: OpenRouter (API compatible con OpenAI, pago por tokens).

Da acceso a muchos modelos abiertos (Qwen, Llama, Gemma, DeepSeek…) con una
sola clave. El catálogo público (`/models`) se consulta para conocer el
contexto y el precio de cada modelo; el coste real lo devuelve la propia API.
"""
from __future__ import annotations

import json
from io import BytesIO
import logging
from time import monotonic, perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings
from app.llm.base import ExchangeRecorder, LLMError, LLMUsage

logger = logging.getLogger("uvicorn.error")
_catalogue: tuple[float, dict[str, dict] | None] = (0.0, None)
ROUTING_MODES = {"cheap": "barato", "fast": "rápido", "default": "reparto de OpenRouter"}


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "X-Title": "TFGBoost"}
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    return headers


def catalogue(max_age: float = 3600.0) -> dict[str, dict] | None:
    """Modelos publicados por OpenRouter (id -> metadatos), o None si no responde."""
    global _catalogue
    fetched_at, models = _catalogue
    if models is not None and monotonic() - fetched_at < max_age:
        return models
    try:
        request = Request(f"{settings.openrouter_url.rstrip('/')}/models", headers=_headers())
        with urlopen(request, timeout=10) as response:
            models = {m["id"]: m for m in json.loads(response.read().decode("utf-8")).get("data", [])}
    except (URLError, OSError, ValueError, KeyError):
        models = None
    _catalogue = (monotonic(), models)
    return models


class OpenRouterProvider(ExchangeRecorder):
    remote = True
    # Cada petición puede ir a un proveedor distinto: en pruebas no hubo lecturas de caché,
    # así que esperar a la primera solo añadía tiempo.
    cache_warmup = False

    @property
    def parallel_requests(self) -> int:
        return settings.llm_parallel_requests

    def __init__(self, model: str, context_tokens: int | None = None, routing: str | None = None):
        self.model = model
        self.id = f"openrouter:{model}"
        # Prioridad elegida al subir el borrador («cheap» o «fast»); si no, la configurada.
        self.routing_mode = routing if routing in ROUTING_MODES else settings.openrouter_routing
        self.label = f"{model} (OpenRouter, remoto, prioridad: {ROUTING_MODES.get(self.routing_mode, self.routing_mode)})"
        info = (catalogue() or {}).get(model, {})
        self.context_tokens = context_tokens or int(info.get("context_length") or 32768)
        pricing = info.get("pricing") or {}
        self.price_in = float(pricing.get("prompt") or 0)  # USD por token
        self.price_out = float(pricing.get("completion") or 0)
        supported = info.get("supported_parameters") or ["structured_outputs"]
        self.supports_schema = "structured_outputs" in supported
        # Con require_parameters, enviar `reasoning` a un modelo que no lo admite lo dejaría sin proveedores.
        self.supports_reasoning = "reasoning" in supported
        # Pruebas reales (nov. 2026): en Qwen 3.5 los proveedores ignoran `effort` y el
        # presupuesto, y el modelo razona hasta agotar los tokens sin responder; solo
        # desactivarlo funciona. gpt-oss no permite desactivarlo (se pasa a effort=low).
        mode = settings.openrouter_reasoning
        self.reasoning: dict | None = {"enabled": False} if mode in ("auto", "off") else {"effort": mode} if mode in ("low", "medium", "high") else None
        self.max_output_tokens = settings.openrouter_max_output_tokens
        # Mismo criterio que en Ollama; con contextos grandes el TFG suele caber entero.
        self.max_input_chars = max(4000, int((self.context_tokens - self.max_output_tokens - 1500) * 3.2))
        self.last_exchange: dict | None = None

    def _routing(self) -> dict:
        """Preferencias de proveedor de OpenRouter.

        - fast: el de mayor rendimiento reciente, sin superar el precio publicado del
          modelo (los hay hasta 3,5 veces más caros para el mismo modelo).
        - cheap: siempre el más barato.
        - default: el reparto de carga de OpenRouter.
        """
        routing: dict = {"require_parameters": True} if settings.openrouter_require_parameters else {}
        mode = self.routing_mode
        if mode == "fast":
            routing["sort"] = "throughput"
            if self.price_in or self.price_out:  # USD por millón de tokens
                routing["max_price"] = {"prompt": round(self.price_in * 1e6, 6), "completion": round(self.price_out * 1e6, 6)}
        elif mode == "cheap":
            routing["sort"] = "price"
        return routing

    @staticmethod
    def _post(endpoint: str, payload: dict) -> dict:
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=_headers(), method="POST")
        with urlopen(request, timeout=settings.openrouter_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def complete_json(self, system: str, document: str, instructions: str, schema: dict) -> tuple[dict, LLMUsage]:
        started = perf_counter()
        payload = {
            "model": self.model,
            # Prefijo estable (sistema + borrador) antes de las preguntas: los proveedores
            # con caché automática de prefijo la aprovechan entre bloques.
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"<borrador>\n{document}\n</borrador>\n\n{instructions}"},
            ],
            "temperature": 0.1,
            "max_tokens": self.max_output_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "revision_tfg", "strict": True, "schema": schema}}
            if self.supports_schema else {"type": "json_object"},
            "usage": {"include": True},  # coste real en la respuesta
        }
        if self.supports_reasoning and self.reasoning:
            payload["reasoning"] = self.reasoning
        payload["provider"] = self._routing()
        if not self.supports_schema:
            payload["messages"][1]["content"] += f"\n\nResponde con un JSON que cumpla este esquema:\n{json.dumps(schema, ensure_ascii=False)}"
        endpoint = f"{settings.openrouter_url.rstrip('/')}/chat/completions"
        self.last_exchange = {"endpoint": endpoint, "request": json.loads(json.dumps(payload)), "raw_response": None}
        if not settings.openrouter_api_key:
            raise LLMError("Falta la clave de OpenRouter (OPENROUTER_API_KEY).", raw="sin clave")
        try:
            try:
                body = self._post(endpoint, payload)
            except HTTPError as error:
                detail = error.read().decode("utf-8", "replace")
                # Modelos de razonamiento obligatorio (gpt-oss…) rechazan desactivarlo:
                # se reintenta con esfuerzo bajo y se recuerda para el resto del análisis.
                if error.code == 400 and "reasoning" in detail.lower() and payload.get("reasoning") == {"enabled": False}:
                    self.reasoning = {"effort": "low"}
                    payload["reasoning"] = self.reasoning
                    self.last_exchange["retries"] = [f"HTTP 400: {detail} → reintento con reasoning.effort=low"]
                    self.last_exchange["request"] = json.loads(json.dumps(payload))
                    body = self._post(endpoint, payload)
                else:
                    raise HTTPError(error.url, error.code, error.msg, error.headers, BytesIO(detail.encode("utf-8"))) from error
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            self.last_exchange["raw_response"] = f"HTTP {error.code}: {detail}"
            messages = {
                401: "La clave de OpenRouter no es válida (OPENROUTER_API_KEY).",
                402: "La cuenta de OpenRouter no tiene crédito suficiente. Recarga créditos o usa un modelo local.",
                404: f"OpenRouter no tiene disponible el modelo {self.model} con estos parámetros.",
                429: "Se ha superado el límite de peticiones de OpenRouter; inténtalo más tarde.",
            }
            raise LLMError(messages.get(error.code, f"Error de OpenRouter ({error.code}): {detail[:300]}"), raw=f"HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, OSError) as error:
            self.last_exchange["raw_response"] = repr(error)
            raise LLMError(f"No se pudo conectar con OpenRouter: {error}", raw=repr(error)) from error

        # OpenRouter puede devolver 200 con un error del proveedor final.
        if body.get("error"):
            self.last_exchange["raw_response"] = json.dumps(body, ensure_ascii=False)
            raise LLMError(f"OpenRouter devolvió un error: {body['error'].get('message', body['error'])}", raw=json.dumps(body, ensure_ascii=False))
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        raw_usage = body.get("usage") or {}
        reasoning_tokens = int((raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        cached = int((raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        usage = LLMUsage(
            calls=1,
            input_tokens=int(raw_usage.get("prompt_tokens") or 0) - cached,
            output_tokens=int(raw_usage.get("completion_tokens") or 0),
            cache_read_tokens=cached,
            seconds=perf_counter() - started,
        )
        usage.cost_usd = float(raw_usage["cost"]) if raw_usage.get("cost") is not None else (usage.input_tokens + cached) * self.price_in + usage.output_tokens * self.price_out
        self.last_exchange.update({
            "raw_response": content, "stop_reason": choice.get("finish_reason"),
            "served_by": f"{body.get('model', self.model)} vía {body.get('provider', '?')}", "request_id": body.get("id"),
            "reasoning_tokens": reasoning_tokens,
            # Razonamiento devuelto por el modelo (si lo expone), útil para diagnosticar.
            "reasoning": message.get("reasoning"),
            "usage_raw": raw_usage,
        })
        if choice.get("finish_reason") == "length":
            if not content.strip():
                message_text = (f"El modelo agotó los {self.max_output_tokens} tokens de salida razonando ({reasoning_tokens} de razonamiento) sin llegar a responder. "
                                "Baja TFGBOOST_OPENROUTER_REASONING o sube TFGBOOST_OPENROUTER_MAX_OUTPUT_TOKENS.")
            else:
                message_text = "La respuesta superó el máximo de tokens configurado (TFGBOOST_OPENROUTER_MAX_OUTPUT_TOKENS)."
            raise LLMError(message_text, raw=content or json.dumps({"finish_reason": "length", "usage": raw_usage, "reasoning": (message.get("reasoning") or "")[-2000:]}, ensure_ascii=False), usage=usage)
        cleaned = content.strip()
        if cleaned.startswith("```"):  # algunos modelos envuelven el JSON en un bloque de código
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            return json.loads(cleaned), usage
        except json.JSONDecodeError as error:
            raise LLMError(f"{self.model} no devolvió JSON válido: {content[:200]}", raw=content, usage=usage) from error
