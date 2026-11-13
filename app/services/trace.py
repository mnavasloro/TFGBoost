"""Traza por subida: qué se pidió a los modelos, qué respondieron y qué se mostró.

Cada análisis escribe `data/traces/<id_informe>.jsonl`: un evento JSON por
línea, en orden. Eventos:

- `upload`: fichero, modelo elegido, palabras, capítulos detectados.
- `rules`: resultado de cada regla (estado, evidencia, comentarios).
- `llm_request`: petición exacta al proveedor (prompt de sistema, borrador o
  fragmento, preguntas, esquema y parámetros).
- `llm_response`: respuesta en bruto y JSON interpretado, con tokens y tiempo.
- `llm_error`: mensaje y detalle en bruto del error.
- `output`: lo que ve el usuario para cada punto, con su procedencia
  (reglas, IA y qué modelo) y el estado final.
- `done` / `failed`: cierre del análisis.

El fichero contiene el texto del borrador: solo lo pueden consultar los tutores
y se borra junto con el informe.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("uvicorn.error")


def trace_path(base_dir: Path, report_id: str) -> Path:
    return base_dir / "traces" / f"{report_id}.jsonl"


class Trace:
    def __init__(self, base_dir: Path, report_id: str):
        self.path = trace_path(base_dir, report_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.report_id = report_id
        self._lock = threading.Lock()
        self._sequence = 0

    def event(self, kind: str, **data) -> None:
        with self._lock:
            self._sequence += 1
            record = {"seq": self._sequence, "ts": datetime.now(UTC).isoformat(), "event": kind, **data}
            try:
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            except OSError:
                # La traza es diagnóstica: un fallo de disco no debe tumbar el análisis.
                logger.exception("[Traza] No se pudo escribir en %s", self.path)


class NullTrace:
    """Sustituto cuando no se quiere traza (pruebas, benchmark)."""

    def event(self, kind: str, **data) -> None:
        pass


def read_trace(base_dir: Path, report_id: str) -> list[dict]:
    path = trace_path(base_dir, report_id)
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # línea a medio escribir mientras el análisis sigue en curso
    return events
