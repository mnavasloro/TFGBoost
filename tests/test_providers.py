import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from app.llm import LLMError
from app.llm.anthropic_provider import AnthropicProvider, estimate_cost
from app.llm.base import LLMUsage
from app.llm.ollama import OllamaProvider, parse_model_spec

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}, "required": ["items"], "additionalProperties": False}


def _claude_response(text='{"items": []}', stop_reason="end_turn"):
    usage = SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=1000, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason, usage=usage)


def test_claude_caches_document_and_requests_json_schema():
    client = MagicMock()
    client.beta.messages.create.return_value = _claude_response()
    with patch("app.llm.anthropic_provider._get_client", return_value=client):
        result, usage = AnthropicProvider("claude-opus-5-5").complete_json("SISTEMA", "BORRADOR", "PREGUNTAS", SCHEMA)
    kwargs = client.beta.messages.create.call_args.kwargs
    assert result == {"items": []}
    assert kwargs["system"][0]["text"] == "SISTEMA" and "cache_control" not in kwargs["system"][0]
    assert "BORRADOR" in kwargs["system"][1]["text"] and kwargs["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["messages"] == [{"role": "user", "content": "PREGUNTAS"}]
    assert kwargs["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert kwargs["fallbacks"] == "default" and kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert usage.cache_read_tokens == 1000 and usage.cost_usd > 0


def test_claude_haiku_uses_standard_endpoint_without_fallbacks():
    client = MagicMock()
    client.messages.create.return_value = _claude_response()
    with patch("app.llm.anthropic_provider._get_client", return_value=client):
        AnthropicProvider("claude-haiku-5-5").complete_json("S", "D", "I", SCHEMA)
    assert "fallbacks" not in client.messages.create.call_args.kwargs
    client.beta.messages.create.assert_not_called()


def test_claude_refusal_becomes_llm_error():
    client = MagicMock()
    client.messages.create.return_value = _claude_response(stop_reason="refusal")
    with patch("app.llm.anthropic_provider._get_client", return_value=client), pytest.raises(LLMError):
        AnthropicProvider("claude-haiku-5-5").complete_json("S", "D", "I", SCHEMA)


def test_cost_estimate_counts_cache_reads_cheaply():
    full = estimate_cost("claude-sonnet-5-5", LLMUsage(input_tokens=1_000_000))
    cached = estimate_cost("claude-sonnet-5-5", LLMUsage(cache_read_tokens=1_000_000))
    assert full == pytest.approx(2.0) and cached == pytest.approx(0.10)


def test_ollama_model_spec_parsing():
    assert parse_model_spec("qwen3:8b@8192") == ("qwen3:8b", 8192)
    assert parse_model_spec("llama3.1:8b")[0] == "llama3.1:8b"


def test_ollama_retries_without_think_for_non_reasoning_models():
    calls = []

    def fake_post(path, payload, timeout):
        calls.append(json.loads(json.dumps(payload)))
        if "think" in payload:
            raise HTTPError("url", 400, "bad", {}, io.BytesIO(b'{"error":"model does not support think"}'))
        return {"message": {"content": '{"items": []}'}, "prompt_eval_count": 10, "eval_count": 5}

    with patch("app.llm.ollama._post", side_effect=fake_post):
        result, usage = OllamaProvider("llama3.1:8b", 4096).complete_json("S", "DOC", "INSTR", SCHEMA)
    assert result == {"items": []} and usage.input_tokens == 10
    assert "think" in calls[0] and "think" not in calls[1]
    assert calls[0]["format"] == SCHEMA
    assert calls[0]["messages"][1]["content"].index("DOC") < calls[0]["messages"][1]["content"].index("INSTR")


def test_ollama_memory_error_is_explained():
    def fake_post(path, payload, timeout):
        raise HTTPError("url", 500, "err", {}, io.BytesIO(b'{"error":"model requires more system memory (5.5 GiB) than is available"}'))

    with patch("app.llm.ollama._post", side_effect=fake_post), pytest.raises(LLMError, match="memoria"):
        OllamaProvider("qwen3:8b", 4096).complete_json("S", "D", "I", SCHEMA)


def test_ollama_context_sets_chunk_size():
    assert OllamaProvider("m", 4096).max_input_chars < OllamaProvider("m", 16384).max_input_chars
