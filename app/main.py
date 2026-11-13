from __future__ import annotations

import logging
import threading
import traceback
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth.contracts import User
from app.auth.local import LocalIdentityProvider
from app.auth.service import AuthService
from app.checklist import get_checklist
from app.config import settings
from app.llm import NO_LLM, available_models, default_model, get_provider, provider_slot
from app.services.database import Database
from app.services.extractor import TextExtractionError, UnsupportedDocument, extract_document, extract_text
from app.services.pipeline import compare_versions, analyse_document
from app.services.revision_checker import assess_revision
from app.services.trace import Trace, read_trace, trace_path
from app.services.excel_report import download_name, results_path, save_workbook

app = FastAPI(title="TFGBoost", description="Feedback formativo para borradores de TFG", version="0.3.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
database = Database(settings.database_path)
auth = AuthService(LocalIdentityProvider(database), database, settings.session_days)
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MEDIA_TYPES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
logger = logging.getLogger("uvicorn.error")

interrupted = database.mark_interrupted_reports()
if interrupted:
    logger.warning("[Arranque] %d análisis interrumpidos marcados como fallidos.", interrupted)


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
    report = database.get_report(report_id)
    if not report:
        raise HTTPException(404, "Informe no encontrado.")
    if user.role != "tutor" and report.get("student_id") != user.id:
        raise HTTPException(403, "No tienes permiso para acceder a este informe.")
    return report


def owned_report(report_id: str, user: User) -> dict:
    report = accessible_report(report_id, user)
    if report.get("student_id") != user.id:
        raise HTTPException(403, "Solo el autor del borrador puede hacer esta acción.")
    return report


def _upload_path(report: dict) -> Path:
    return settings.upload_dir / f"{report['document_id']}{Path(report['filename']).suffix.lower()}"


def _text_path(report_id: str) -> Path:
    return settings.upload_dir / f"{report_id}.txt"


def _read_text(report: dict) -> str | None:
    path = _text_path(report["document_id"])
    if path.is_file():
        return path.read_text(encoding="utf-8")
    original = _upload_path(report)
    return extract_text(report["filename"], original.read_bytes()) if original.is_file() else None


@app.get("/health")
def health():
    return {"status": "ok", "storage": "local", "authentication": "local", "models": [m["id"] for m in available_models() if m["available"]]}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User | None = Depends(current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == "tutor":
        return RedirectResponse("/tutor", status_code=303)
    reports = database.summaries(user.id)
    for report in reports:
        report["tutor_review"] = database.latest_tutor_review(report["id"])
    return templates.TemplateResponse(request, "index.html", {
        "user": user, "reports": reports, "models": available_models(), "default_model": default_model(),
        "settings": settings,
    })


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
def tutor_dashboard(request: Request, user: User = Depends(require_tutor), all: bool = False):
    """Panel agrupado por estudiante; por defecto solo muestra borradores enviados (triaje)."""
    students: dict[str, dict] = {}
    for report in database.summaries():
        report["tutor_review"] = database.latest_tutor_review(report["id"])
        entry = students.setdefault(report["student_id"] or report["student_name"], {"name": report["student_name"], "versions": []})
        entry["versions"].append(report)
    for entry in students.values():
        entry["versions"].sort(key=lambda r: r["created_at"])
        entry["latest"] = entry["versions"][-1]
        submitted = [r for r in entry["versions"] if r["submitted_at"]]
        entry["latest_submitted"] = submitted[-1] if submitted else None
        entry["pending_review"] = bool(entry["latest_submitted"] and not entry["latest_submitted"]["tutor_review"])
    visible = [s for s in students.values() if all or s["latest_submitted"]]
    visible.sort(key=lambda s: (s["pending_review"], s["latest"]["created_at"]), reverse=True)
    return templates.TemplateResponse(request, "tutor.html", {
        "students": visible, "hidden_count": len(students) - len(visible), "show_all": all, "user": user,
        "checklist": get_checklist().public_definition(), "threshold": settings.submit_threshold,
    })


# --- API -------------------------------------------------------------------------

@app.get("/api/models")
def list_models(user: User = Depends(require_user)):
    return {"default": default_model(), "models": available_models()}


@app.get("/api/checklist")
def checklist_definition(user: User = Depends(require_user)):
    return get_checklist().public_definition()


def _process(report_id: str, student_id: str, text: str, headings: list[str], filename: str, model_id: str, routing: str | None = None) -> None:
    started = perf_counter()
    trace = Trace(settings.data_dir, report_id)
    trace.event("upload", report_id=report_id, student_id=student_id, filename=filename, model=model_id, routing=routing, characters=len(text))
    try:
        provider = get_provider(model_id, routing)
        progress = lambda done, total, label: database.update_progress(report_id, done, total, label)
        if provider:
            slot = provider_slot(provider)
            progress(0, 0, "En cola: esperando a que termine otro análisis con este modelo")
            with slot:
                trace.event("queue", waited_seconds=round(perf_counter() - started, 1))
                report = analyse_document(text, filename, report_id, provider, progress, headings, trace)
        else:
            report = analyse_document(text, filename, report_id, None, progress, headings, trace)
        current = database.get_report(report_id) or {}
        previous = database.previous_completed_report(student_id, current.get("created_at", ""))
        if previous and previous.get("schema_version", 1) >= 2:
            report["evolution"] = compare_versions(previous, report, database.item_responses(previous["document_id"]))
        if previous and (review := database.latest_tutor_review(previous["document_id"])):
            try:
                previous_text = _read_text(previous)
                if previous_text:
                    report["revision_check"] = assess_revision(previous_text, text, review["comments"])
            except Exception:  # la comparación es accesoria: no debe tumbar el informe
                logger.warning("[Pipeline] No se pudo comparar con la versión anterior %s.", previous["document_id"])
        database.complete_report(report_id, report)
        try:
            excel = save_workbook(settings.data_dir, database.get_report(report_id))
            trace.event("excel", path=str(excel))
        except Exception as excel_error:  # el Excel es un subproducto: no invalida el informe
            logger.exception("[Pipeline] No se pudo generar el Excel de %s", report_id)
            trace.event("excel_error", error=repr(excel_error))
        trace.event("done", seconds=round(perf_counter() - started, 1), maturity_score=report["maturity_score"], evolution=report.get("evolution"), revision_check=report.get("revision_check"))
        logger.info("[Pipeline] Informe %s completado en %.1f s. Traza: %s", report_id, perf_counter() - started, trace.path)
    except Exception as error:  # el estudiante debe ver el fallo en vez de un análisis eterno
        logger.exception("[Pipeline] Fallo al analizar %s", report_id)
        trace.event("failed", error=repr(error), traceback=traceback.format_exc())
        database.fail_report(report_id, f"No se pudo completar el análisis: {error}")


@app.post("/api/documents", status_code=202)
async def upload_document(
    document: UploadFile = File(...),
    model: str = Form(NO_LLM),
    consent_external: bool = Form(False),
    routing: str = Form(""),
    user: User = Depends(require_user),
):
    if user.role != "student":
        raise HTTPException(403, "El área de subida está reservada a estudiantes.")
    options = {m["id"]: m for m in available_models()}
    if model not in options:
        raise HTTPException(422, "El modelo seleccionado no está disponible.")
    if not options[model]["available"]:
        raise HTTPException(503, "El modelo seleccionado no responde ahora mismo (¿está Ollama en marcha?). Elige otro o inténtalo más tarde.")
    if options[model]["remote"]:
        if not consent_external:
            raise HTTPException(422, "Para usar un modelo externo debes aceptar que el texto del borrador se envíe a ese proveedor.")
        if settings.remote_daily_limit and database.count_remote_analyses_today(user.id) >= settings.remote_daily_limit:
            raise HTTPException(429, f"Has alcanzado el límite de {settings.remote_daily_limit} análisis diarios con modelos externos. Usa un modelo local o inténtalo mañana.")
    if routing not in ("", "cheap", "fast"):
        raise HTTPException(422, "Prioridad no válida: elige «barato» o «rápido».")
    if not model.startswith("openrouter:"):
        routing = ""  # solo tiene sentido con OpenRouter
    filename = Path(document.filename or "documento").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Solo se admiten documentos PDF y DOCX.")
    content = await document.read()
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera el límite de {settings.max_upload_mb} MB.")
    try:
        extracted = extract_document(filename, content)
        text = extracted.text
    except UnsupportedDocument as error:
        raise HTTPException(415, str(error)) from error
    except TextExtractionError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(422, "No se pudo analizar el archivo por un error inesperado.") from error
    if len(text.strip()) < 80:
        raise HTTPException(422, "No se ha podido extraer suficiente texto. Para PDFs escaneados, aplica OCR antes de subirlos.")
    report_id = str(uuid4())
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{report_id}{suffix}").write_bytes(content)
    _text_path(report_id).write_text(text, encoding="utf-8")
    created_at = database.create_pending_report(report_id, user, filename, model)
    threading.Thread(target=_process, args=(report_id, user.id, text, extracted.headings, filename, model, routing or None), daemon=True, name=f"analisis-{report_id[:8]}").start()
    return {"document_id": report_id, "status": "processing", "created_at": created_at, "filename": filename, "model": model, "routing": routing or None}


@app.get("/api/reports")
def list_reports(user: User = Depends(require_user)):
    return database.summaries() if user.role == "tutor" else database.summaries(user.id)


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, user: User = Depends(require_user)):
    report = accessible_report(report_id, user)
    report["tutor_review"] = database.latest_tutor_review(report_id)
    report["responses"] = database.item_responses(report_id)
    report["viewer_role"] = user.role
    report["submit_threshold"] = settings.submit_threshold
    return report


@app.get("/api/reports/{report_id}/text", response_class=PlainTextResponse)
def get_report_text(report_id: str, user: User = Depends(require_user)):
    text = _read_text(accessible_report(report_id, user))
    if text is None:
        raise HTTPException(404, "El texto del borrador ya no está disponible.")
    return text


@app.get("/api/reports/{report_id}/results.xlsx")
def download_results(report_id: str, user: User = Depends(require_tutor)):
    """Resultado de la entrega en Excel. Solo profesorado. Se regenera para incluir
    las respuestas más recientes del estudiante a cada aviso."""
    report = accessible_report(report_id, user)
    if report.get("status") != "done" or not report.get("items"):
        raise HTTPException(409, "El análisis de esta entrega no ha terminado o es de una versión anterior sin checklist.")
    path = save_workbook(settings.data_dir, report, database.item_responses(report_id))
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=download_name(report))


@app.get("/api/reports/{report_id}/trace")
def get_report_trace(report_id: str, user: User = Depends(require_tutor)):
    """Eventos de la traza (peticiones y respuestas de los modelos). Solo tutores."""
    accessible_report(report_id, user)
    return read_trace(settings.data_dir, report_id)


@app.get("/api/reports/{report_id}/trace.jsonl")
def download_report_trace(report_id: str, user: User = Depends(require_tutor)):
    accessible_report(report_id, user)
    path = trace_path(settings.data_dir, report_id)
    if not path.is_file():
        raise HTTPException(404, "Este informe no tiene traza (se generó antes de activar el registro).")
    return FileResponse(path, media_type="application/x-ndjson", filename=f"traza-{report_id}.jsonl")


@app.get("/tutor/reports/{report_id}/trace", response_class=HTMLResponse)
def trace_page(request: Request, report_id: str, user: User = Depends(require_tutor)):
    report = accessible_report(report_id, user)
    return templates.TemplateResponse(request, "trace.html", {"user": user, "report": report, "events": read_trace(settings.data_dir, report_id)})


@app.post("/api/reports/{report_id}/responses")
def respond_to_item(report_id: str, payload: dict = Body(...), user: User = Depends(require_user)):
    """El estudiante registra si ha corregido un aviso o por qué no aplica (encuesta, P15)."""
    report = owned_report(report_id, user)
    item_id, status, note = str(payload.get("item_id", "")), str(payload.get("status", "")), str(payload.get("note", ""))
    if item_id not in {item["id"] for item in report.get("items", [])}:
        raise HTTPException(422, "Punto de la checklist desconocido.")
    if status not in ("corregido", "no_aplica", "pendiente"):
        raise HTTPException(422, "Estado no válido.")
    if status == "no_aplica" and len(note.strip()) < 10:
        raise HTTPException(422, "Explica brevemente (al menos 10 caracteres) por qué este aviso no aplica.")
    return database.save_item_response(report_id, item_id, user.id, status, note[:1000])


def submission_blockers(report: dict, responses: dict[str, dict]) -> list[str]:
    reasons = []
    if report.get("status") != "done":
        return ["El análisis todavía no ha terminado."]
    if report.get("maturity_score", 0) < settings.submit_threshold:
        reasons.append(f"La madurez ({report.get('maturity_score', 0)}/100) no alcanza el mínimo de {settings.submit_threshold} acordado para enviar al tutor.")
    titles = {item["id"]: item["title"] for item in report.get("items", [])}
    for item_id in report.get("blocking_items", []):
        response = responses.get(item_id)
        if not (response and response["status"] == "no_aplica" and response["note"]):
            reasons.append(f"Punto imprescindible sin resolver: [{item_id}] {titles.get(item_id, '')}. Corrígelo y sube una nueva versión, o justifica por qué no aplica.")
    return reasons


@app.post("/api/reports/{report_id}/submit")
def submit_to_tutor(report_id: str, user: User = Depends(require_user)):
    """Triaje: el borrador solo llega al tutor si supera el umbral mínimo (encuesta, P17)."""
    report = owned_report(report_id, user)
    if report.get("submitted_at"):
        return {"submitted_at": report["submitted_at"]}
    blockers = submission_blockers(report, database.item_responses(report_id))
    if blockers:
        raise HTTPException(409, {"message": "Todavía no se puede enviar este borrador al tutor.", "reasons": blockers})
    return {"submitted_at": database.mark_submitted(report_id)}


@app.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: str, user: User = Depends(require_user)):
    report = owned_report(report_id, user)
    if report.get("status") == "processing":
        raise HTTPException(409, "Espera a que termine el análisis para borrar esta versión.")
    for path in (_upload_path(report), _text_path(report_id), trace_path(settings.data_dir, report_id), results_path(settings.data_dir, report_id)):
        path.unlink(missing_ok=True)
    for stored in database.delete_report(report_id):
        (settings.upload_dir / "tutor-reviews" / stored).unlink(missing_ok=True)


@app.get("/api/reports/{report_id}/document")
def get_uploaded_document(report_id: str, user: User = Depends(require_user)):
    """Sirve el original solo a su autor o a un tutor."""
    report = accessible_report(report_id, user)
    suffix = Path(report["filename"]).suffix.lower()
    stored_file = _upload_path(report)
    if not stored_file.is_file():
        raise HTTPException(404, "El archivo original ya no está disponible.")
    return FileResponse(stored_file, media_type=MEDIA_TYPES[suffix], filename=report["filename"], content_disposition_type="inline" if suffix == ".pdf" else "attachment")


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
    return FileResponse(path, media_type=MEDIA_TYPES[suffix], filename=review["annotated_filename"], content_disposition_type="inline" if suffix == ".pdf" else "attachment")
