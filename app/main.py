from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.analyzer import analyse
from app.services.extractor import UnsupportedDocument, extract_text
from app.services.repository import ReportRepository

app = FastAPI(title="TFGBoost", description="Feedback formativo para borradores de TFG", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
repository = ReportRepository(settings.database_path)
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@app.get("/health")
def health():
    return {"status": "ok", "storage": "local"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/tutor", response_class=HTMLResponse)
def tutor_dashboard(request: Request):
    return templates.TemplateResponse(request, "tutor.html", {"reports": repository.summaries()})


@app.post("/api/documents", status_code=201)
async def upload_document(student_name: str = Form(..., max_length=120), document: UploadFile = File(...)):
    filename = document.filename or "documento"
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Solo se admiten documentos PDF y DOCX.")
    content = await document.read()
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera el límite de {settings.max_upload_mb} MB.")
    try:
        text = extract_text(filename, content)
    except UnsupportedDocument as error:
        raise HTTPException(415, str(error)) from error
    except Exception as error:
        raise HTTPException(422, "No se pudo extraer texto del documento. Comprueba que no sea un PDF escaneado o protegido.") from error
    if len(text.strip()) < 80:
        raise HTTPException(422, "No se ha podido extraer suficiente texto. Para PDFs escaneados, aplica OCR antes de subirlos.")
    document_id = str(uuid4())
    safe_name = Path(filename).name
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{document_id}{Path(safe_name).suffix.lower()}").write_bytes(content)
    report = analyse(text, safe_name, document_id).to_dict()
    repository.save(report, student_name.strip())
    return report


@app.get("/api/reports")
def list_reports():
    return repository.summaries()


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    report = repository.get(report_id)
    if not report:
        raise HTTPException(404, "Informe no encontrado.")
    return report
