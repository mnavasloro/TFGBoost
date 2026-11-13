"""Proveedor local: cualquier modelo servido por Ollama."""
from __future__ import annotations

import json
import logging
from time import monotonic, perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings
from app.llm.base import ExchangeRecorder, LLMError, LLMUsage

logger = logging.getLogger("uvicorn.error")
_tags_cache: tuple[float, list[str] | None] = (0.0, None)


def _post(path: str, payload: dict, timeout: int) -> dict:
    request = Request(f"{settings.ollama_url.rstrip('/')}{path}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def installed_models(max_age: float = 30.0) -> list[str] | None:
    """Modelos instalados en Ollama, o None si el servicio no responde."""
    global _tags_cache
    fetched_at, models = _tags_cache
    if models is not None and monotonic() - fetched_at < max_age:
        return models
    try:
        with urlopen(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=3) as response:
            models = sorted(model["name"] for model in json.loads(response.read().decode("utf-8")).get("models", []))
    except (URLError, OSError, ValueError, KeyError):
        models = None
    _tags_cache = (monotonic(), models)
    return models


def parse_model_spec(spec: str) -> tuple[str, int]:
    """"qwen3:8b@8192" -> ("qwen3:8b", 8192)."""
    name, _, context = spec.partition("@")
    return name.strip(), int(context) if context.strip().isdigit() else settings.ollama_context_tokens


class OllamaProvider(ExchangeRecorder):
    remote = False
    parallel_requests = 1  # en CPU, peticiones simultáneas no terminan antes

    def __init__(self, model: str, context_tokens: int):
        self.model = model
        self.context_tokens = context_tokens
        self.id = f"ollama:{model}"
        self.label = f"{model} (local, Ollama)"
        self.max_output_tokens = settings.ollama_max_output_tokens
        # ~3,2 caracteres por token en español; se reservan ~900 tokens para instrucciones.
        self.max_input_chars = max(2000, int((context_tokens - self.max_output_tokens - 900) * 3.2))
        self.last_exchange: dict | None = None

    def complete_json(self, system: str, document: str, instructions: str, schema: dict) -> tuple[dict, LLMUsage]:
        started = perf_counter()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"<borrador>\n{document}\n</borrador>\n\n{instructions}"},
            ],
            "stream": False,
            "format": schema,
            "think": False,
            "keep_alive": "15m",
            "options": {"temperature": 0.1, "num_predict": self.max_output_tokens, "num_ctx": self.context_tokens},
        }
        body = None
        retries: list[str] = []
        # Se guarda una copia: `payload` puede cambiar al adaptar parámetros tras un error.
        self.last_exchange = {"endpoint": f"{settings.ollama_url.rstrip('/')}/api/chat", "request": json.loads(json.dumps(payload)), "retries": retries, "raw_response": None}
        for attempt in range(3):
            try:
                body = _post("/api/chat", payload, settings.ollama_timeout_seconds)
                break
            except HTTPError as error:
                detail = error.read().decode("utf-8", "replace")
                # Modelos sin modo de razonamiento rechazan `think`; versiones antiguas de
                # Ollama no aceptan un esquema JSON en `format`.
                if "think" in detail and "think" in payload:
                    retries.append(f"HTTP {error.code}: {detail} → reintento sin «think»")
                    payload.pop("think")
                elif "format" in detail and isinstance(payload["format"], dict):
                    retries.append(f"HTTP {error.code}: {detail} → reintento con format=json")
                    payload["format"] = "json"
                    payload["messages"][1]["content"] += f"\n\nEsquema JSON obligatorio:\n{json.dumps(schema, ensure_ascii=False)}"
                elif "memory" in detail:
                    raise LLMError(f"El servidor no tiene memoria libre suficiente para cargar {self.model}. Cierra otras aplicaciones, usa un modelo más pequeño o reduce el contexto.", raw=f"HTTP {error.code}: {detail}") from error
                else:
                    raise LLMError(f"Ollama rechazó la petición ({error.code}): {detail[:300]}", raw=f"HTTP {error.code}: {detail}") from error
            except (URLError, TimeoutError, OSError) as error:
                raise LLMError(f"No se pudo contactar con Ollama en {settings.ollama_url}: {error}", raw=repr(error)) from error
        if retries:
            self.last_exchange["request"] = json.loads(json.dumps(payload))  # petición que finalmente se aceptó
        if body is None:
            raise LLMError("Ollama no aceptó la petición tras adaptar los parámetros.", raw="\n".join(retries))
        content = body.get("message", {}).get("content", "")
        self.last_exchange.update({"raw_response": content, "done_reason": body.get("done_reason"), "metadata": {k: v for k, v in body.items() if k != "message"}})
        try:
            result = json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMError(f"{self.model} no devolvió JSON válido: {content[:200]}", raw=content) from error
        usage = LLMUsage(calls=1, input_tokens=int(body.get("prompt_eval_count") or 0), output_tokens=int(body.get("eval_count") or 0), seconds=perf_counter() - started)
        if body.get("done_reason") == "length":
            logger.warning("[Ollama] %s alcanzó el límite de salida (%d tokens).", self.model, self.max_output_tokens)
        return result, usage
