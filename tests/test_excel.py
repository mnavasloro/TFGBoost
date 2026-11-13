from io import BytesIO

from openpyxl import load_workbook

from app.services.excel_report import build_workbook, download_name
from app.services.pipeline import analyse_document
from tests.conftest import SAMPLE_TFG, FakeProvider


def _workbook(responses=None):
    report = analyse_document(SAMPLE_TFG, "tfg.docx", "rep-x", FakeProvider())
    report.update({"student_name": "Ana Pérez", "created_at": "2026-11-12T10:00:00+00:00"})
    return report, load_workbook(BytesIO(build_workbook(report, responses)))


def test_workbook_has_one_row_per_item_with_provenance():
    report, book = _workbook({"E5": {"status": "no_aplica", "note": "Es parte de un log citado."}})
    assert book.sheetnames == ["Resumen", "Resultados", "Comentarios", "Categorías"]
    sheet = book["Resultados"]
    headers = [c.value for c in sheet[1]]
    rows = {row[0]: dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert len(rows) == len(report["items"])
    assert rows["R3"]["IA: modelo"] == "No aplica" and rows["R3"]["Reglas: estado"]  # solo reglas
    assert rows["C1"]["IA: modelo"] == "fake:model" and rows["C1"]["Reglas: estado"] == "No aplica"  # solo IA
    assert rows["L4"]["Decidido por"] == "IA"  # el modelo de prueba es más severo que las reglas
    assert rows["E5"]["Respuesta del estudiante"] == "No aplica" and "log" in rows["E5"]["Justificación del estudiante"]


def test_comments_sheet_names_source_and_model():
    _, book = _workbook()
    sheet = book["Comentarios"]
    headers = [c.value for c in sheet[1]]
    rows = [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]
    assert {r["Fuente"] for r in rows} == {"Regla", "IA"}
    assert all(r["Modelo"] == "fake:model" for r in rows if r["Fuente"] == "IA")
    assert all(r["Modelo"] == "Reglas automáticas" for r in rows if r["Fuente"] == "Regla")


def test_summary_and_filename():
    report, book = _workbook()
    summary = {row[0]: row[1] for row in book["Resumen"].iter_rows(values_only=True)}
    assert summary["Madurez (0-100)"] == report["maturity_score"] and summary["Identificador del modelo"] == "fake:model"
    assert download_name(report) == "TFGBoost_Ana_Pérez_tfg_2026-11-12.xlsx"
