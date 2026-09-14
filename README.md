# TFGBoost

Prototipo local de apoyo formativo para la revisión de borradores de Trabajo de Fin de Grado. TFGBoost no redacta el trabajo del estudiante ni produce calificaciones: analiza el texto disponible, detecta aspectos que conviene revisar y propone acciones de mejora explicables.

## Incluye

- Carga de documentos `PDF` y `DOCX`.
- Extracción local de texto y almacenamiento local del documento e informe.
- Diagnóstico de estructura, claridad, coherencia, redacción y referencias.
- Checklist de secciones adaptada a una memoria de TFG; es fácilmente ampliable para cada centro.
- Panel de tutor con el estado de madurez de los informes generados.
- Registro e inicio de sesión local con perfiles de estudiante y tutor; los informes de estudiantes sólo son visibles para su autor y para tutores.
- API documentada automáticamente en `/docs`.

El diagnóstico inicial se basa en reglas transparentes y, después, Qwen3 8B mediante Ollama local revisa el borrador en seis fases: planteamiento y estructura; método y resultados; fuentes; figuras y anexos; redacción; y requisitos formales y éticos. Cada petición recibe exclusivamente la sección pertinente, dividida en fragmentos de hasta 9.000 caracteres para ajustarse a la ventana de 4.096 tokens y ejecutarse de forma fiable en CPU. El borrador no sale del equipo.

En equipos donde Qwen3 se ejecute en CPU, una comprobación de un documento completo puede tardar varios minutos. El timeout está configurado en 600 segundos y la terminal muestra el punto en curso y su tiempo transcurrido.

## Arranque local

Requiere Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull qwen3:8b
uvicorn app.main:app --reload --reload-dir app
```

Abre `http://127.0.0.1:8000`. Los datos se guardan en `data/` y `uploads/`, ambos excluidos de Git. La opción `--reload-dir app` evita que el recargador observe `.venv/` y se reinicie durante instalaciones o actualizaciones de paquetes.

Para Docker:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## Pruebas

```powershell
pip install pytest
pytest
```

## Límites y siguiente paso

Este es un prototipo funcional, no un sistema de decisión académica. Antes de un piloto real deben añadirse autenticación, consentimiento explícito, política de retención/borrado, control de acceso tutor-estudiante, criterios de la normativa concreta y evaluación con borradores autorizados. Los PDFs escaneados requieren OCR previo.

La lista de comprobación y las heurísticas viven en `app/services/analyzer.py`; es el punto previsto para incorporar las reglas de cada escuela y la futura evaluación de modelos locales.

## Identidad y SSO

El prototipo usa SQLite para las cuentas, sesiones e informes. Las contraseñas se guardan como hashes PBKDF2 con sal aleatoria; la cookie de sesión es `HttpOnly` y su token se almacena como hash en la base de datos.

La aplicación no depende del mecanismo local directamente. `app/auth/contracts.py` define el contrato `IdentityProvider` y `app/auth/local.py` es su implementación actual. Para conectar un SSO institucional (OIDC, SAML o CAS), añade otro proveedor que implemente ese contrato e inicialízalo en `app/main.py`. En producción, activa HTTPS y configura la cookie como `Secure`; el alta de tutores debe venir del directorio institucional, no de un formulario público.
