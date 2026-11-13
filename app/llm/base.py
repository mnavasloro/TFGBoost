from __future__ import annotations

import threading

from dataclasses import asdict, dataclass
from typing import Protocol


class ExchangeRecorder:
    """`last_exchange` por hilo: con peticiones simultáneas, cada hilo ve la suya."""

    @property
    def last_exchange(self) -> dict | None:
        return getattr(self.__dict__.setdefault("_exchange_local", threading.local()), "value", None)

    @last_exchange.setter
    def last_exchange(self, value: dict | None) -> None:
        self.__dict__.setdefault("_exchange_local", threading.local()).value = value


class LLMError(RuntimeError):
    """El proveedor no ha devuelto una respuesta utilizable."""

    def __init__(self, message: str, raw: str | None = None, usage: "LLMUsage | None" = None):
        super().__init__(message)
        self.raw = raw  # respuesta o detalle de error tal cual lo devolvió el proveedor
        self.usage = usage  # consumo de una llamada fallida que el proveedor sí factura


@dataclass
class LLMUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0

    def add(self, other: "LLMUsage") -> None:
        for name in ("calls", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "seconds", "cost_usd"):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["seconds"] = round(self.seconds, 1)
        data["cost_usd"] = round(self.cost_usd, 4)
        return data


class LLMProvider(Protocol):
    id: str  # "<proveedor>:<modelo>"
    label: str
    remote: bool  # True si el texto sale de la infraestructura propia
    max_input_chars: int  # tamaño máximo de borrador por petición
    # Última petición y respuesta en bruto del hilo actual, para la traza (ver ExchangeRecorder).
    last_exchange: dict | None
    # Peticiones simultáneas dentro de un mismo análisis (1 = secuencial).
    parallel_requests: int

    def complete_json(self, system: str, document: str, instructions: str, schema: dict) -> tuple[dict, LLMUsage]:
        """Devuelve un objeto JSON conforme a `schema`.

        `document` va siempre antes que `instructions` para que las peticiones
        sucesivas sobre el mismo fragmento compartan prefijo (caché de Claude,
        caché KV de Ollama).
        """
        ...
