from app.services.revision_checker import assess_revision


def test_revision_checker_flags_no_evidence():
    result = assess_revision("El sistema procesa documentos.", "El sistema procesa documentos.", "Añade una evaluación cuantitativa y métricas de precisión.")
    assert result["status"] == "attention"
    assert result["pending"]


def test_revision_checker_finds_added_suggestion_terms():
    result = assess_revision("El sistema procesa documentos.", "El sistema procesa documentos. La evaluación cuantitativa incluye métricas de precisión.", "Añade una evaluación cuantitativa y métricas de precisión.")
    assert result["addressed"]
