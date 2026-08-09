from app.services.analyzer import analyse


def test_report_detects_sections_and_uses_bounded_scores():
    text = """Resumen
Este trabajo presenta un sistema de apoyo a la redacción académica.

Índice

Introducción
El contexto del problema se explica aquí. Por tanto, se justifica la propuesta.

Objetivos
El objetivo es evaluar la herramienta.

Metodología
Se describe el estudio.

Desarrollo
Se implementa una aplicación local.

Resultados
Se evalúa con borradores autorizados.

Conclusiones
El prototipo ofrece feedback formativo.

Referencias
Autor, A. (2025). Título."""
    report = analyse(text, "borrador.docx", "test-id")
    assert report.document_id == "test-id"
    assert "introducción" in report.sections_found
    assert not report.sections_missing
    assert all(0 <= value <= 100 for value in report.metrics.values())


def test_report_flags_missing_sections():
    report = analyse("Introducción\n" + "palabra " * 200, "corto.pdf")
    assert "referencias" in report.sections_missing
    assert any(f.category == "estructura" for f in report.findings)
