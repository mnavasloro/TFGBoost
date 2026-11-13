import os
import tempfile

# Antes de importar la aplicación: datos aislados y sin servicios externos.
_TMP = tempfile.mkdtemp(prefix="tfgboost-tests-")
os.environ.update({
    "TFGBOOST_DATA_DIR": os.path.join(_TMP, "data"),
    "TFGBOOST_UPLOAD_DIR": os.path.join(_TMP, "uploads"),
    "TFGBOOST_OLLAMA_ENABLED": "false",
    "TFGBOOST_ANTHROPIC_ENABLED": "false",
    "TFGBOOST_DEFAULT_MODEL": "none",
})

import pytest  # noqa: E402

from app.llm.base import LLMUsage  # noqa: E402

PARAGRAPH = (
    "El sistema propuesto analiza borradores académicos y detecta problemas de redacción, estructura y citas. "
    "Para ello se combinan reglas transparentes con un modelo de lenguaje que se ejecuta localmente, de modo que "
    "el texto no sale de la universidad. La evaluación se realiza con borradores cedidos voluntariamente [1].\n"
)

SAMPLE_TFG = f"""Resumen
Este trabajo presenta TFGBoost, una herramienta de apoyo a la redacción de memorias.
Palabras clave: redacción académica, modelos de lenguaje.

Abstract
This work presents TFGBoost, a writing support tool.

Índice
1. Introducción ........ 1
2. Objetivos ........ 3

1. Introducción
{PARAGRAPH * 6}Hoy en día la tecnología es muy importante y cabe destacar que la API facilita la integración.
Yo creo que el resultado es guay.

2. Objetivos
{PARAGRAPH * 3}
3. Estado del arte
{PARAGRAPH * 6}
4. Metodología
{PARAGRAPH * 4}TODO: completar la planificación.

5. Desarrollo
{PARAGRAPH * 20}Figura 1. Arquitectura general del sistema.
Como muestra la Figura 1, el sistema tiene tres capas.
Tabla 1. Resultados por modelo.

6. Resultados
{PARAGRAPH * 6}
7. Conclusiones
{PARAGRAPH * 3}
Referencias
[1] Pérez, A. (2024). Redacción académica. Editorial UPM.
[2] Página web sin fecha. https://example.com
"""


class FakeProvider:
    """Proveedor de pruebas: marca todo «por revisar» citando el primer párrafo."""
    id = "fake:model"
    label = "Modelo de prueba"
    remote = False

    def __init__(self, max_input_chars: int = 1_000_000, quote: str = "El sistema propuesto analiza borradores académicos", fail_on_call: int | None = None):
        self.max_input_chars = max_input_chars
        self.quote = quote
        self.fail_on_call = fail_on_call
        self.calls = []
        self.last_exchange = None

    def complete_json(self, system, document, instructions, schema):
        from app.llm import LLMError
        self.calls.append((document, instructions))
        self.last_exchange = {"endpoint": "fake", "request": {"model": "model", "temperature": 0.1, "messages": ["..."]}, "raw_response": None}
        if self.fail_on_call == len(self.calls):
            self.last_exchange["raw_response"] = "HTTP 500: modelo caído"
            raise LLMError("El modelo de prueba ha fallado.", raw="HTTP 500: modelo caído")
        ids = schema["properties"]["items"]["items"]["properties"]["id"]["enum"]
        items = [{"id": item_id, "status": "no_cumple", "evidence": "Prueba", "findings": [{"quote": self.quote, "feedback": "Revisa este fragmento."}]} for item_id in ids]
        import json
        self.last_exchange["raw_response"] = json.dumps({"items": items}, ensure_ascii=False)
        return {"items": items}, LLMUsage(calls=1, input_tokens=100, output_tokens=50)


@pytest.fixture
def sample_text():
    return SAMPLE_TFG
