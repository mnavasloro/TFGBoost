from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth.contracts import User
from app.auth.local import LocalIdentityProvider
from app.auth.service import AuthService
from app.config import settings
from app.services.analyzer import analyse
from app.services.database import Database
from app.services.extractor import UnsupportedDocument, extract_text
from app.services.repository import ReportRepository

app = FastAPI(title="TFGBoost", description="Feedback formativo para borradores de TFG", version="0.2.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
database = Database(settings.database_path)
repository = ReportRepository(settings.database_path)
auth = AuthService(LocalIdentityProvider(database), database, settings.session_days)
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


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


@app.get("/health")
def health():
    return {"status": "ok", "storage": "local", "authentication": "local"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: User | None = Depends(current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == "tutor":
        return RedirectResponse("/tutor", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"user": user})


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
    return templates.TemplateResponse(request, "tutor.html", {"reports": repository.summaries(), "user": user})


@app.post("/api/documents", status_code=201)
async def upload_document(document: UploadFile = File(...), user: User = Depends(require_user)):
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
    except Exception as error:
        raise HTTPException(422, "No se pudo extraer texto del documento. Comprueba que no sea un PDF escaneado o protegido.") from error
    if len(text.strip()) < 80:
        raise HTTPException(422, "No se ha podido extraer suficiente texto. Para PDFs escaneados, aplica OCR antes de subirlos.")
    document_id = str(uuid4())
    safe_name = Path(filename).name
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / f"{document_id}{Path(safe_name).suffix.lower()}").write_bytes(content)
    report = analyse(text, safe_name, document_id).to_dict()
    repository.save(report, user.display_name, user.id)
    return report


@app.get("/api/reports")
def list_reports(user: User = Depends(require_user)):
    return repository.summaries() if user.role == "tutor" else repository.summaries(user.id)


@app.get("/api/reports/{report_id}")
def get_report(report_id: str, user: User = Depends(require_user)):
    report = repository.get(report_id)
    if not report:
        raise HTTPException(404, "Informe no encontrado.")
    if user.role != "tutor" and report_id not in {item["id"] for item in repository.summaries(user.id)}:
        raise HTTPException(403, "No tienes permiso para acceder a este informe.")
    return report
