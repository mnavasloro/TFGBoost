import dataclasses
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app.config import settings
from app.llm import LLMError
from app.llm.openrouter import OpenRouterProvider

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"], "additionalProperties": False}
CATALOGUE = {"qwen/qwen3.5-35b-a3b": {"id": "qwen/qwen3.5-35b-a3b", "context_length": 262144, "pricing": {"prompt": "0.00000014", "completion": "0.000001"}, "supported_parameters": ["response_format", "structured_outputs", "reasoning", "include_reasoning"]}}
CONFIGURED = dataclasses.replace(settings, openrouter_enabled=True, openrouter_api_key="sk-or-test")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _ok(content='{"items": []}', **extra):
    body = {"id": "gen-1", "model": "qwen/qwen3.5-35b-a3b", "provider": "Alibaba", "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "prompt_tokens_details": {"cached_tokens": 400}, "cost": 0.0012}, **extra}
    return FakeResponse(json.dumps(body).encode())


def _provider():
    with patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.catalogue", return_value=CATALOGUE):
        return OpenRouterProvider("qwen/qwen3.5-35b-a3b")


def _call(response, content_check=None):
    provider = _provider()
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["headers"], sent["body"] = request.full_url, dict(request.header_items()), json.loads(request.data)
        if isinstance(response, Exception):
            raise response
        return response

    with patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.urlopen", side_effect=fake_urlopen):
        result = provider.complete_json("SISTEMA", "BORRADOR", "PREGUNTAS", SCHEMA)
    return provider, sent, result


def test_request_uses_json_schema_and_reports_real_cost():
    provider, sent, (result, usage) = _call(_ok())
    assert sent["url"].endswith("/chat/completions") and sent["headers"]["Authorization"] == "Bearer sk-or-test"
    body = sent["body"]
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["provider"] == {"require_parameters": True, "sort": "price"}  # «cheap» por defecto
    assert body["usage"] == {"include": True}
    assert body["messages"][1]["content"].index("BORRADOR") < body["messages"][1]["content"].index("PREGUNTAS")
    assert result == {"items": []}
    assert usage.cache_read_tokens == 400 and usage.input_tokens == 600 and usage.cost_usd == pytest.approx(0.0012)
    assert provider.last_exchange["served_by"] == "qwen/qwen3.5-35b-a3b vía Alibaba"
    assert provider.max_input_chars > 600_000  # 262k de contexto: el TFG cabe entero


def test_code_fences_are_tolerated():
    _, _, (result, _) = _call(_ok(content='```json\n{"items": [1]}\n```'))
    assert result == {"items": [1]}


def test_no_credit_is_explained_with_raw_detail():
    error = HTTPError("url", 402, "Payment Required", {}, io.BytesIO(b'{"error":{"message":"Insufficient credits"}}'))
    with pytest.raises(LLMError, match="crédito") as raised:
        _call(error)
    assert "Insufficient credits" in raised.value.raw


def test_provider_error_inside_200_response():
    with pytest.raises(LLMError, match="upstream"):
        _call(FakeResponse(json.dumps({"error": {"message": "upstream timeout", "code": 502}}).encode()))


def test_registry_marks_models_unavailable_without_key():
    from app import llm
    no_key = dataclasses.replace(CONFIGURED, openrouter_api_key="", ollama_enabled=False, anthropic_enabled=False, openrouter_models=("qwen/qwen3.5-35b-a3b", "no/existe"))
    with patch("app.llm.settings", no_key), patch("app.llm.openrouter_catalogue", return_value=CATALOGUE):
        options = {m["id"]: m for m in llm.available_models()}
    assert options["openrouter:qwen/qwen3.5-35b-a3b"]["available"] is False
    with_key = dataclasses.replace(no_key, openrouter_api_key="sk-or-test")
    with patch("app.llm.settings", with_key), patch("app.llm.openrouter_catalogue", return_value=CATALOGUE):
        options = {m["id"]: m for m in llm.available_models()}
    assert options["openrouter:qwen/qwen3.5-35b-a3b"]["available"] is True and "0.14/1.00" in options["openrouter:qwen/qwen3.5-35b-a3b"]["label"]
    assert options["openrouter:no/existe"]["available"] is False


def test_reasoning_effort_sent_only_to_models_that_support_it():
    _, sent, _ = _call(_ok())
    assert sent["body"]["reasoning"] == {"enabled": False}  # «auto»: sin razonamiento
    gemma = {"google/gemma-3-27b-it": {"context_length": 131072, "pricing": {}, "supported_parameters": ["response_format", "structured_outputs"]}}
    with patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.catalogue", return_value=gemma):
        provider = OpenRouterProvider("google/gemma-3-27b-it")
    captured = {}
    with patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.urlopen", side_effect=lambda r, timeout: captured.update(body=json.loads(r.data)) or _ok()):
        provider.complete_json("S", "D", "I", SCHEMA)
    assert "reasoning" not in captured["body"]  # con require_parameters lo dejaría sin proveedores


def test_empty_answer_after_reasoning_is_explained_and_billed():
    # Caso real de la traza: finish_reason=length, contenido vacío, 8000 tokens de razonamiento.
    body = {"id": "gen-2", "model": "qwen/qwen3.5-35b-a3b", "provider": "Parasail",
            "choices": [{"message": {"content": "", "reasoning": "Analizo el capítulo 1..."}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 41000, "completion_tokens": 8000, "completion_tokens_details": {"reasoning_tokens": 8000}, "cost": 0.0137}}
    with pytest.raises(LLMError, match="razonando") as raised:
        _call(FakeResponse(json.dumps(body).encode()))
    assert raised.value.usage.output_tokens == 8000 and raised.value.usage.cost_usd == pytest.approx(0.0137)
    assert "Analizo" in raised.value.raw


def test_billed_failures_count_in_report_usage():
    from app.checklist import get_checklist
    from app.llm.base import LLMUsage
    from app.services.pipeline import analyse_document
    from tests.conftest import SAMPLE_TFG, FakeProvider

    class BilledFailure(FakeProvider):
        def complete_json(self, system, document, instructions, schema):
            if len(self.calls) == 0:
                self.calls.append(1)
                raise LLMError("sin respuesta", raw="", usage=LLMUsage(calls=1, input_tokens=1000, output_tokens=8000, cost_usd=0.01))
            return super().complete_json(system, document, instructions, schema)

    report = analyse_document(SAMPLE_TFG, "tfg.docx", "x", BilledFailure())
    groups = len(get_checklist().groups)
    assert report["usage"]["calls"] == groups  # la fallida también cuenta
    assert report["usage"]["output_tokens"] == 8000 + 50 * (groups - 1)


def test_mandatory_reasoning_falls_back_to_low_effort():
    provider = _provider()
    bodies = []

    def fake_urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        if len(bodies) == 1:
            raise HTTPError("url", 400, "Bad Request", {}, io.BytesIO(b'{"error":{"message":"Reasoning is mandatory for this endpoint and cannot be disabled.","code":400}}'))
        return _ok()

    with patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.urlopen", side_effect=fake_urlopen):
        provider.complete_json("S", "D", "I", SCHEMA)
        provider.complete_json("S", "D", "I", SCHEMA)
    assert bodies[0]["reasoning"] == {"enabled": False} and bodies[1]["reasoning"] == {"effort": "low"}
    assert bodies[2]["reasoning"] == {"effort": "low"}  # se recuerda para el resto del análisis


def test_answers_with_spanish_keys_are_normalised():
    from app.services.llm_review import normalise_entries
    # Forma real devuelta por Alibaba vía OpenRouter, que ignora el esquema.
    result = {"items": [
        {"punto": "L1", "estado": "por_revisar", "quote": "introduccion", "evidence": "Falta la tilde.", "hallazgos": []},
        {"punto": "L2", "estado": "no_evaluable", "quote": "", "evidence": "Solo un encabezado.", "hallazgos": []},
        {"id": "L3", "status": "No cumple", "evidencia": "x", "findings": [{"cita": "a ,b", "comentario": "espacio"}]},
        {"punto": "Z9", "estado": "cumple"},
    ]}
    entries, discarded = normalise_entries(result, ["L1", "L2", "L3"])
    by_id = {e["id"]: e for e in entries}
    assert by_id["L1"]["status"] == "por_revisar" and by_id["L1"]["findings"] == [{"quote": "introduccion", "feedback": "Falta la tilde."}]
    assert by_id["L2"]["status"] == "no_evaluable" and by_id["L2"]["findings"] == []
    assert by_id["L3"]["status"] == "no_cumple" and by_id["L3"]["findings"][0] == {"quote": "a ,b", "feedback": "espacio"}
    assert discarded == [{"punto": "Z9", "estado": "cumple"}]


def test_answers_with_other_english_keys_are_normalised():
    from app.services.llm_review import normalise_entries
    # Formas reales de AtlasCloud y Alibaba vía OpenRouter.
    result = {"items": [
        {"point": "R1", "status": "no_cumple", "evidence": "Sin fuente.", "findings": [{"quote": "Hoy en día la tecnología", "issue": "Afirmación sin cita."}]},
        {"punto": "N1", "estado": "no_cumple", "hallazgos": [{"quote": "TFGBoost, una herramienta", "evidence": "Nombre sin definir."}]},
    ]}
    entries, discarded = normalise_entries(result, ["R1", "N1"])
    assert not discarded
    assert {e["id"]: e["findings"][0]["feedback"] for e in entries} == {"R1": "Afirmación sin cita.", "N1": "Nombre sin definir."}


@pytest.mark.parametrize("mode, expected", [
    ("fast", {"require_parameters": True, "sort": "throughput", "max_price": {"prompt": 0.14, "completion": 1.0}}),
    ("default", {"require_parameters": True}),
])
def test_other_routing_modes(mode, expected):
    with patch("app.llm.openrouter.settings", dataclasses.replace(CONFIGURED, openrouter_routing=mode)), patch("app.llm.openrouter.catalogue", return_value=CATALOGUE):
        assert OpenRouterProvider("qwen/qwen3.5-35b-a3b")._routing() == expected


def test_upload_choice_overrides_configured_routing():
    from app import llm
    with patch("app.llm.settings", CONFIGURED), patch("app.llm.openrouter.settings", CONFIGURED), patch("app.llm.openrouter.catalogue", return_value=CATALOGUE):
        fast = llm.get_provider("openrouter:qwen/qwen3.5-35b-a3b", "fast")
        default = llm.get_provider("openrouter:qwen/qwen3.5-35b-a3b")
        assert fast._routing()["sort"] == "throughput" and "prioridad: rápido" in fast.label
        assert default.routing_mode == CONFIGURED.openrouter_routing
        assert llm.get_provider("openrouter:qwen/qwen3.5-35b-a3b", "nonsense").routing_mode == CONFIGURED.openrouter_routing
