from app.checklist import get_checklist
from app.services.pipeline import analyse_document
from app.services.trace import Trace, read_trace

from tests.conftest import FakeProvider


def _events(tmp_path, provider):
    from tests.conftest import SAMPLE_TFG
    trace = Trace(tmp_path, "rep-1")
    report = analyse_document(SAMPLE_TFG, "tfg.docx", "rep-1", provider, trace=trace)
    return report, read_trace(tmp_path, "rep-1")


def test_trace_records_prompts_responses_and_output(tmp_path):
    report, events = _events(tmp_path, FakeProvider())
    kinds = [e["event"] for e in events]
    groups = len(get_checklist().groups)
    assert kinds[:3] == ["sections", "rules", "llm_plan"]
    assert kinds.count("llm_request") == groups and kinds.count("llm_response") == groups
    assert kinds[-1] == "output"
    request = next(e for e in events if e["event"] == "llm_request")
    assert "El sistema propuesto" in request["document"] and "[L1]" in request["instructions"] and request["schema"]
    assert "Eres un revisor formativo" in next(e for e in events if e["event"] == "llm_plan")["system_prompt"]
    response = next(e for e in events if e["event"] == "llm_response")
    assert '"items"' in response["raw"] and response["parsed"]["items"]
    assert "messages" not in response["params"]  # el texto no se duplica
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)


def test_trace_records_errors_with_raw_detail(tmp_path):
    report, events = _events(tmp_path, FakeProvider(fail_on_call=2))
    error = next(e for e in events if e["event"] == "llm_error")
    assert error["call"] == 2 and error["raw"] == "HTTP 500: modelo caído" and "fallado" in error["error"]
    assert report["llm_errors"]


def test_output_states_source_of_every_item(tmp_path):
    report, events = _events(tmp_path, FakeProvider())
    items = {i["id"]: i for i in report["items"]}
    # Punto solo de reglas, solo de IA y mixto.
    assert [s["source"] for s in items["R3"]["provenance"]["sources"]] == ["regla"]
    ai = items["C1"]["provenance"]["sources"]
    assert ai[0]["source"] == "ia" and ai[0]["model"] == "fake:model"
    mixed = items["L4"]["provenance"]
    assert {s["source"] for s in mixed["sources"]} == {"regla", "ia"}
    assert "ia" in mixed["decided_by"]  # el modelo de prueba dice «no cumple», el peor estado
    assert all(c["model"] == "fake:model" for c in items["C1"]["comments"] if c["source"] == "ia")
    assert all(c["model"] is None for c in items["R3"]["comments"])
    output = next(e for e in events if e["event"] == "output")
    shown = {i["id"]: i for i in output["items"]}
    assert shown["C1"]["shown_comments"][0]["model"] == "fake:model"


def test_rules_only_analysis_says_ai_was_not_used(tmp_path):
    report, events = _events(tmp_path, None)
    c1 = next(i for i in report["items"] if i["id"] == "C1")
    assert c1["provenance"]["sources"][0]["label"] == "IA (no utilizada)"
    assert not any(e["event"].startswith("llm_") for e in events)
