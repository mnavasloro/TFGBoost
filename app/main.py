from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth.contracts import User
from app.auth.local import LocalIdentityProvider
from app.auth.service import AuthService
from app.config import settings
from app.services.analyzer import analyse
from app.services.database import Database
from app.services.extractor import TextExtractionError, UnsupportedDocument, extract_text
from app.services.ollama_checklist import run_checklist
from app.services.repository import ReportRepository

app = FastAPI(title="TFGBoost", description="Feedback formativo para borradores de TFG", version="0.2.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
database = Database(settings.database_path)
repository = ReportRepository(settings.database_path)
auth = AuthService(LocalIdentityProvider(database), database, settings.session_days)
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
logger = logging.getLogger("uvicorn.error")


def current_user(request: Request) -> User | None:
    return auth.current_user(request.cookies.get("tfgboost_session"))


def require_user(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return user


def require_tutor(user: User = Depends(require_user)) -> User:
    if user.role != "tutor":
        raise HTTPException(403, "Esta sección está reservada al profesorado.")
    return user


def accessible_report(report_id: str, user: User) -> dict:
    report = repository.get(report_id)
    if not report:
        raise HTTPException(404, "Informe no encontrado.")
    if user.role != "tutor" and report_id not in {item["id"] for item in repository.summaries(user.id)}:
        raise HTTPException(403, "No tienes permiso para acceder a este informe.")
    return report


@app.get("/health")
def health():
    return {"status": "ok", "storage": "local", "authentication": "local"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User | None = Depends(current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == "tutor":
        return RedirectResponse("/tutor", status_code=303)
    reports = repository.summaries(user.id)
    for report in reports:
        report["tutor_review"] = database.latest_tutor_review(report["id"])
    return templates.TemplateResponse(request, "index.html", {"user": user, "reports": reports})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse("/tutor" if user.role == "tutor" else "/", status_code=303)
    return templates.TemplateResponse(request, "login.html")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    result = auth.login(email, password)
    if not result:
        return templates.TemplateResponse(request, "login.html", {"error": "Correo o contraseña incorrectos."}, status_code=401)
    user, token = result
    response = RedirectResponse("/tutor" if user.role == "tutor" else "/", status_code=303)
    response.set_cookie("tfgboost_session", token, max_age=settings.session_days * 86400, httponly=True, samesite="lax", secure=False)
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse("/tutor" if user.role == "tutor" else "/", status_code=303)
    return templates.TemplateResponse(request, "register.html")


@app.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...), role: str = Form(...)):
    if role not in ("student", "tutor"):
        return templates.TemplateResponse(request, "register.html", {"error": "Selecciona un perfil válido."}, status_code=422)
    try:
        auth.register(email, name, password, role)  # type: ignore[arg-type]
    except ValueError as error:
        return templates.TemplateResponse(request, "register.html", {"error": str(error)}, status_code=422)
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
def logout(request: Request):
    auth.logout(request.cookies.get("tfgboost_session"))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("tfgboost_session")
    return response


@app.get("/tutor", response_class=HTMLResponse)
def tutor_dashboard(request: Request, user: User = Depends(require_tutor)):
    reports = repository.summaries()
    for report in reports:
        report["tutor_review"] = database.latest_tutor_review(report["id"])
    return templates.TemplateResponse(request, "tutor.html", {"reports": reports, "user": user})


@app.post("/api/documents", status_code=201)
async def upload_document(document: UploadFile = File(...), user: User = Depends(require_user)):
    pipeline_started_at = perf_counter()
    if user.role != "student":
        raise HTTPException(403, "El área de subida está reservada a estudiantes.")
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
    except TextExtractionError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, "No se pudo analizar el archivo por un error inesperado.") from error
    if len(text.strip()) < 80:
        raise HTTPException(422, "No se ha podido extraer suficiente texto. Para PDFs escaneados, aplica OCR antes de subirlos.")
    logger.info("[Pipeline] Extracción terminada en %.1f s (%d caracteres).", perf_counter() - pipeline_started_at, len(text))
    document_id = str(uuid4())
    safe_name = Path(filename).name
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{document_id}{Path(safe_name).suffix.lower()}").write_bytes(content)
    report = analyse(text, safe_name, document_id).to_dict()
    logger.info("[Pipeline] Análisis local terminado en %.1f s; comienza la checklist Ollama.", perf_counter() - pipeline_started_at)
    report["checklist"] = run_checklist(text)
    logger.info("[Pipeline] Checklist Ollama terminada en %.1f s.", perf_counter() - pipeline_started_at)
    previous_versions = repository.summaries(user.id)
    if previous_versions:
        previous = previous_versions[0]
        previous_review = database.latest_tutor_review(previous["id"])
        if previous_review:
            previous_path = settings.upload_dir / f"{previous['id']}{Path(previous['filename']).suffix.lower()}"
            if previous_path.is_file():
                try:
                    from app.services.revision_checker import assess_revision
                    previous_text = extract_text(previous["filename"], previous_path.read_bytes())
                    revision_check = assess_revision(previous_text, text, previous_review["comments"])
                    report["revision_check"] = revision_check
                    severity = "attention" if revision_check["status"] == "attention" else "info"
                    report["findings"].append({"category": "coherencia", "severity": severity, "title": "Comprobación de feedback del tutor", "explanation": revision_check["message"], "suggestion": "Comprueba cada recomendación del tutor y documenta los cambios realizados antes de enviar la siguiente versión."})
                except Exception:
                    # A review remains visible even if an old source file cannot be compared.
                    pass
    created_at = datetime.now(UTC).isoformat()
    repository.save(report, user.display_name, user.id, created_at)
    logger.info("[Pipeline] Informe guardado en %.1f s.", perf_counter() - pipeline_started_at)
    report["created_at"] = created_at
    return report


@app.get("/api/reports")
def list_reports(user: User = Depends(require_user)):
    return repository.summaries() if user.role == "tutor" else repository.summaries(user.id)


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, user: User = Depends(require_user)):
    report = accessible_report(report_id, user)
    report["tutor_review"] = database.latest_tutor_review(report_id)
    return report


@app.get("/api/reports/{report_id}/document")
def get_uploaded_document(report_id: str, user: User = Depends(require_user)):
    """Serve the original version only to its author or a tutor."""
    report = accessible_report(report_id, user)
    suffix = Path(report["filename"]).suffix.lower()
    stored_file = settings.upload_dir / f"{report_id}{suffix}"
    if not stored_file.is_file():
        raise HTTPException(404, "El archivo original ya no está disponible.")
    media_type = "application/pdf" if suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    disposition = "inline" if suffix == ".pdf" else "attachment"
    return FileResponse(stored_file, media_type=media_type, filename=report["filename"], content_disposition_type=disposition)


@app.post("/api/reports/{report_id}/reviews")
async def submit_tutor_review(report_id: str, comments: str = Form(..., min_length=5), annotated_document: UploadFile | None = File(None), user: User = Depends(require_tutor)):
    accessible_report(report_id, user)
    annotated_filename = stored_filename = None
    if annotated_document and annotated_document.filename:
        annotated_filename = Path(annotated_document.filename).name
        suffix = Path(annotated_filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(415, "El documento comentado debe ser PDF o DOCX.")
        content = await annotated_document.read()
        if not content:
            raise HTTPException(400, "El documento comentado está vacío.")
        if len(content) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"El archivo supera el límite de {settings.max_upload_mb} MB.")
        stored_filename = f"{uuid4()}{suffix}"
        review_dir = settings.upload_dir / "tutor-reviews"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / stored_filename).write_bytes(content)
    database.create_tutor_review(report_id, user.id, comments, annotated_filename, stored_filename)
    return RedirectResponse("/tutor", status_code=303)


@app.get("/api/reports/{report_id}/reviews/latest/document")
def get_annotated_document(report_id: str, user: User = Depends(require_user)):
    accessible_report(report_id, user)
    review = database.latest_tutor_review(report_id)
    if not review or not review["stored_filename"]:
        raise HTTPException(404, "No hay un archivo comentado para esta versión.")
    path = settings.upload_dir / "tutor-reviews" / review["stored_filename"]
    if not path.is_file():
        raise HTTPException(404, "El archivo comentado ya no está disponible.")
    suffix = Path(review["annotated_filename"]).suffix.lower()
    media_type = "application/pdf" if suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media_type, filename=review["annotated_filename"], content_disposition_type="inline" if suffix == ".pdf" else "attachment")
