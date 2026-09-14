from types import SimpleNamespace
from unittest.mock import patch

from app.services.ollama_checklist import run_checklist
from app.services.revision_phases import PHASES, phase_tasks


SETTINGS = SimpleNamespace(ollama_enabled=True, ollama_model="qwen3:8b", ollama_context_tokens=4096)


def test_revision_has_six_phases_and_requested_checks():
    assert len(PHASES) == 6
    first_phase_questions = " ".join(PHASES[0].questions).lower()
    assert "términos" in first_phase_questions
    assert "marco tecnológico" in first_phase_questions


def test_phase_tasks_use_only_relevant_sections():
    text = """Introducción
La API se define en este apartado.

Referencias
Autor, A. (2025). Fuente.
"""
    tasks = phase_tasks(text)
    structure_intro = next(task for task in tasks if task["phase"] == 1 and task["section"] == "introduccion")
    assert "Referencias" not in structure_intro["content"]
    assert "API" in structure_intro["content"]


def test_checklist_processes_phase_section_tasks_sequentially():
    with patch("app.services.ollama_checklist.settings", SETTINGS), patch("app.services.ollama_checklist._request_check", return_value={"status": "cumple", "evidence": "Evidencia", "feedback": "Feedback"}) as request:
        result = run_checklist("Introducción\nTexto de prueba.")

    assert result
    assert request.call_count == len(result)
    assert result[0]["item"].startswith("Fase 1")


def test_checklist_degrades_remaining_tasks_when_ollama_fails():
    with patch("app.services.ollama_checklist.settings", SETTINGS), patch("app.services.ollama_checklist._request_check", side_effect=OSError("conexión perdida")):
        result = run_checklist("Introducción\nTexto de prueba.")

    assert result
    assert all(item["status"] == "no_evaluable" for item in result)
