import io
import time

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import SAMPLE_TFG


def _docx(text: str) -> bytes:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _client(email: str, role: str) -> TestClient:
    client = TestClient(app)
    client.post("/register", data={"name": email.split("@")[0], "email": email, "password": "contraseña-segura", "role": role})
    assert client.post("/login", data={"email": email, "password": "contraseña-segura"}, follow_redirects=False).status_code == 303
    return client


def _wait(client: TestClient, report_id: str) -> dict:
    for _ in range(100):
        report = client.get(f"/api/reports/{report_id}").json()
        if report["status"] != "processing":
            return report
        time.sleep(0.05)
    raise AssertionError("El análisis no terminó")


def test_full_student_and_tutor_flow():
    student = _client("alumna@alumnos.upm.es", "student")
    tutor = _client("tutora@upm.es", "tutor")
    other = _client("otro@alumnos.upm.es", "student")

    models = student.get("/api/models").json()
    assert models["default"] == "none"

    upload = student.post("/api/documents", files={"document": ("tfg.docx", _docx(SAMPLE_TFG))}, data={"model": "none"})
    assert upload.status_code == 202, upload.text
    report_id = upload.json()["document_id"]
    report = _wait(student, report_id)
    assert report["status"] == "done"
    assert report["items"] and "E5" in report["blocking_items"]

    # Privacidad: otro estudiante no puede ver el informe ni el texto.
    assert other.get(f"/api/reports/{report_id}").status_code == 403
    assert other.get(f"/api/reports/{report_id}/text").status_code == 403
    assert "El sistema propuesto" in student.get(f"/api/reports/{report_id}/text").text

    # Triaje: no se puede enviar con puntos imprescindibles sin resolver.
    blocked = student.post(f"/api/reports/{report_id}/submit")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["reasons"]
    assert student.post(f"/api/reports/{report_id}/responses", json={"item_id": "E5", "status": "no_aplica", "note": "corto"}).status_code == 422
    assert student.post(f"/api/reports/{report_id}/responses", json={"item_id": "E5", "status": "no_aplica", "note": "El TODO es parte de una cita textual de un log."}).status_code == 200
    assert tutor.post(f"/api/reports/{report_id}/responses", json={"item_id": "E5", "status": "corregido"}).status_code == 403

    # El panel del tutor solo muestra borradores enviados por defecto.
    assert "alumna" not in tutor.get("/tutor").text
    assert "alumna" in tutor.get("/tutor?all=true").text
    assert tutor.get(f"/api/reports/{report_id}").json()["responses"]["E5"]["status"] == "no_aplica"

    # Traza: solo tutores; contiene subida, reglas, salida y cierre.
    events = tutor.get(f"/api/reports/{report_id}/trace").json()
    assert [e["event"] for e in events][0] == "upload" and events[-1]["event"] == "done"
    assert any(e["event"] == "output" for e in events)
    assert student.get(f"/api/reports/{report_id}/trace").status_code == 403
    page = tutor.get(f"/tutor/reports/{report_id}/trace")
    assert page.status_code == 200 and "Resultado mostrado al usuario" in page.text
    assert tutor.get(f"/api/reports/{report_id}/trace.jsonl").status_code == 200
    assert any(e["event"] == "excel" for e in events)

    # Excel: se guarda al terminar y solo lo descarga el profesorado.
    from app.config import settings
    from app.services.excel_report import results_path
    assert results_path(settings.data_dir, report_id).is_file()
    assert student.get(f"/api/reports/{report_id}/results.xlsx").status_code == 403
    assert "results.xlsx" not in student.get("/").text
    excel = tutor.get(f"/api/reports/{report_id}/results.xlsx")
    assert excel.status_code == 200 and excel.content[:2] == b"PK"
    assert "attachment" in excel.headers["content-disposition"] and ".xlsx" in excel.headers["content-disposition"]
    assert other.get(f"/api/reports/{report_id}/results.xlsx").status_code == 403

    assert student.delete(f"/api/reports/{report_id}").status_code == 204
    assert student.get(f"/api/reports/{report_id}").status_code == 404
    assert not results_path(settings.data_dir, report_id).exists()


def test_remote_models_require_consent_and_known_models():
    student = _client("consent@alumnos.upm.es", "student")
    response = student.post("/api/documents", files={"document": ("tfg.docx", _docx(SAMPLE_TFG))}, data={"model": "anthropic:claude-opus-5-5"})
    assert response.status_code == 422  # Anthropic desactivado en las pruebas: modelo no ofrecido
    assert student.post("/api/documents", files={"document": ("tfg.txt", b"hola")}, data={"model": "none"}).status_code == 415
    bad = student.post("/api/documents", files={"document": ("tfg.docx", _docx(SAMPLE_TFG))}, data={"model": "none", "routing": "gratis"})
    assert bad.status_code == 422
    ok = student.post("/api/documents", files={"document": ("tfg.docx", _docx(SAMPLE_TFG))}, data={"model": "none", "routing": "fast"})
    assert ok.status_code == 202 and ok.json()["routing"] is None  # sin OpenRouter, la prioridad no aplica


def test_pages_render():
    student = _client("paginas@alumnos.upm.es", "student")
    page = student.get("/")
    assert page.status_code == 200 and "model-select" in page.text
    assert 'name="routing" value="cheap"' in page.text and 'name="routing" value="fast"' in page.text
    assert _client("tutor2@upm.es", "tutor").get("/tutor").status_code == 200
