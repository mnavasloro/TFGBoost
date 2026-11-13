# TFGBoost

Plataforma de apoyo formativo para la revisión de borradores de Trabajo de Fin de Grado (piloto UPM, ETSISI). TFGBoost no redacta el trabajo del estudiante ni lo califica: analiza el borrador con una checklist elaborada a partir de la propuesta del proyecto y de una encuesta a tutores, señala qué revisar y por qué, y deja las correcciones en manos del alumno.

## Funcionalidades

**Estudiante**
- Subida de borradores `PDF` o `DOCX`, con historial de versiones y opción de borrarlas.
- Elección del modelo de revisión: solo reglas (inmediato), modelos locales de Ollama, o modelos remotos de Claude (Anthropic) y OpenRouter con consentimiento explícito.
- Informe interactivo: madurez 0-100 con semáforo, resumen por categoría, checklist ordenada por prioridad y **borrador con comentarios al margen** filtrables por categoría.
- Para cada aviso: «Lo he corregido» o «No aplica» con justificación (el tutor lo ve).
- Evolución respecto a la versión anterior (avisos resueltos, persistentes y nuevos) y comprobación de si se aplicó el feedback del tutor.
- **Triaje**: el borrador solo puede enviarse al tutor cuando supera la madurez mínima y no quedan puntos imprescindibles sin resolver o justificar.

**Tutor**
- Panel agrupado por estudiante, con los borradores enviados primero y los pendientes de revisión destacados.
- Semáforo, evolución de la madurez entre versiones, avisos abiertos por categoría, respuestas del alumno a cada aviso, avisos «marcados como corregidos pero que persisten» e indicio de pasajes genéricos o posible texto generado.
- Comentarios para la siguiente versión y documento anotado opcional.

## Checklist

La checklist (34 puntos en 8 categorías) se define en [`app/checklist/tfg_checklist.json`](app/checklist/tfg_checklist.json) y se documenta en [`docs/CHECKLIST.md`](docs/CHECKLIST.md). Ese documento se genera con `python scripts/render_checklist.py`. Cada punto indica de dónde procede (propuesta, pregunta de la encuesta o guía de revisión), cómo se evalúa (regla, IA o ambas) y su peso. El peso sale de la frecuencia y del esfuerzo de corrección que declararon los tutores; `scripts/survey_stats.py` recalcula esas estadísticas desde el Excel de respuestas.

Para adaptarla a otra escuela, copia el JSON, ajusta `required_sections` a su normativa y apunta `TFGBOOST_CHECKLIST` a la copia.

## Cómo funciona el análisis

1. **Extracción**: texto del PDF/DOCX (incluidas las tablas) y encabezados declarados por el documento (estilos de título de DOCX, marcadores del PDF) para reconocer los capítulos.
2. **Reglas transparentes**: apartados obligatorios, equilibrio entre capítulos, restos de borrador, oraciones largas, registro, relleno, siglas sin definir, formato y correspondencia de citas, fiabilidad de fuentes, figuras y tablas sin mencionar, y credenciales o rutas locales.
3. **Modelo de lenguaje** (opcional), con cinco bloques de preguntas y respuesta en JSON estructurado:
   - Si el borrador cabe en el contexto del modelo, se envía completo. En Claude va en un bloque de sistema con caché, así que las peticiones siguientes lo leen a ~10 % del precio.
   - Si no cabe (modelos locales con contexto pequeño), se envían solo los capítulos pertinentes, troceados, y se agrupan las peticiones sobre el mismo fragmento para aprovechar la caché de Ollama.
4. **Verificación**: cada cita que aporta la IA se busca literalmente en el borrador. Las no localizadas se marcan como posible alucinación y no pueden dejar un punto en «no cumple».
5. **Madurez**: media ponderada por la prioridad de la encuesta; semáforo y puntos imprescindibles bloqueantes.

### Procedencia y traza

Cada punto del informe muestra su procedencia: qué dijeron las **reglas** y qué dijo la **IA** (con el nombre del modelo), y cuál de ellas fijó el estado final. Cada comentario lleva la etiqueta «Regla» o «IA · <modelo>».

**Resultado en Excel.** Cada entrega genera `data/results/<id_informe>.xlsx`, que solo el profesorado descarga con el enlace «Excel» (`/api/reports/<id>/results.xlsx`). Al descargarlo se regenera para incluir las últimas respuestas del estudiante. Hojas:
- *Resumen*: entrega, modelo, madurez, semáforo, tokens, coste y errores.
- *Resultados*: un punto por fila, con el estado y la evidencia de las reglas, el modelo de IA con su estado y su evidencia, quién decidió el estado final y la respuesta del estudiante.
- *Comentarios*: cada comentario mostrado, con su fuente, el modelo, la cita y si esa cita se localizó en el texto.
- *Categorías*: puntuación y avisos abiertos por categoría.

Cada subida genera además una traza en `data/traces/<id_informe>.jsonl` (un evento JSON por línea; formato descrito en [`app/services/trace.py`](app/services/trace.py)). Registra:
- la petición exacta a cada modelo: prompt de sistema, borrador o fragmento enviado, preguntas, esquema y parámetros;
- la respuesta en bruto y su interpretación, con tokens, tiempo y modelo que respondió;
- los errores con su detalle en bruto (HTTP, falta de memoria, falta de crédito…);
- los resultados de las reglas;
- lo que se mostró al usuario punto por punto.

Los tutores la consultan desde el enlace «Traza» del panel o del informe (`/tutor/reports/<id>/trace`), o la descargan como `.jsonl`. La traza contiene el texto del borrador: no es visible para otros estudiantes y se borra junto con la versión.

El análisis corre en segundo plano: la página muestra el progreso y el estudiante puede cerrarla. Los análisis con Ollama se encolan (uno a la vez por defecto) para no saturar la CPU.

## Arranque local

Requiere Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # revisa los modelos y el umbral
ollama pull qwen3:8b
uvicorn app.main:app --reload --reload-dir app --env-file .env
```

Abre `http://127.0.0.1:8000`. Los datos se guardan en `data/` y `uploads/`, ambos excluidos de Git. Las bases de datos existentes se migran automáticamente; los informes antiguos se muestran en formato simplificado.

### Modelos

- **Ollama**: `TFGBOOST_OLLAMA_MODELS` lista los modelos ofrecidos, con contexto opcional por modelo: `qwen3:8b@4096,qwen3:14b@8192`. Si la lista está vacía, se ofrecen todos los modelos instalados. Más contexto implica menos fragmentos y mejor visión global, pero más memoria. Si el equipo no tiene memoria para cargar el modelo, el informe lo indica y se queda con las reglas.
- **Claude**: activa `TFGBOOST_ANTHROPIC_ENABLED=true` y define `ANTHROPIC_API_KEY`. El servidor ofrece los modelos de `TFGBOOST_ANTHROPIC_MODELS` (por defecto Opus 5.5, Sonnet 5.5 y Haiku 5.5). Funcionamiento:
  - Se usan salidas estructuradas y caché del borrador.
  - En Opus y Sonnet hay reintento automático en el servidor (`fallbacks`) si el modelo declina una petición; se desactiva con `TFGBOOST_ANTHROPIC_FALLBACKS=false`.
  - El estudiante debe aceptar que el texto salga de la universidad, y `TFGBOOST_REMOTE_DAILY_LIMIT` limita los análisis diarios.
  - El informe del tutor muestra tokens y coste estimado.
- **OpenRouter**: activa `TFGBOOST_OPENROUTER_ENABLED=true` y define `OPENROUTER_API_KEY`. Se ofrecen los modelos de `TFGBOOST_OPENROUTER_MODELS`, identificados como en [openrouter.ai/models](https://openrouter.ai/models); por defecto Qwen 3.5, gpt-oss-120b y Gemma 3 27B. Funcionamiento:
  - El catálogo público aporta el contexto y el precio de cada modelo, que se muestran en el selector. Con contextos grandes el borrador se envía entero.
  - Se pide respuesta con esquema JSON y, con `TFGBOOST_OPENROUTER_REQUIRE_PARAMETERS=true`, solo se enruta a proveedores que lo admitan.
  - El coste que se registra es el que devuelve OpenRouter, incluidas las llamadas que fallan pero se facturan.
  - Razonamiento (`TFGBOOST_OPENROUTER_REASONING=auto`): se desactiva y, si el modelo no lo permite (gpt-oss), se pasa a esfuerzo bajo. En pruebas con Qwen 3.5, los valores `low`/`medium`/`high` hacían que el modelo razonase hasta agotar los tokens sin responder.
  - Velocidad: con modelos remotos las peticiones de un análisis se lanzan en paralelo (`TFGBOOST_LLM_PARALLEL_REQUESTS=4`), con los mismos tokens y el mismo coste. Con Claude la primera va sola para dejar el borrador en caché. `TFGBOOST_OPENROUTER_ROUTING=cheap` usa siempre el proveedor más barato; en pruebas tardó lo mismo que `fast` y costó la mitad. Ollama (local) sigue en secuencia.
  - Algunos proveedores ignoran el esquema y usan otras claves (`punto`, `estado`, `point`, `issue`…). Las respuestas se normalizan y, si algún elemento no puede asociarse a un punto, queda registrado en la traza.
  - Como con Claude, se exige el consentimiento del estudiante y se aplica el límite diario.
- **Comparar modelos**: `python scripts/benchmark.py carpeta/ --models none ollama:qwen3:8b anthropic:claude-haiku-5-5 [--gold anotaciones.json]` genera un CSV con tiempos, tokens, coste y estado de cada punto. Si se añaden anotaciones de tutores, calcula además la concordancia.

### Docker

```powershell
Copy-Item .env.example .env   # TFGBOOST_OLLAMA_URL=http://host.docker.internal:11434
docker compose up --build
```

## Pruebas

```powershell
pip install -r requirements-dev.txt
pytest
```

## Límites

Es un prototipo para un piloto con supervisión humana, no un sistema de decisión académica.
- Las reglas son heurísticas y los modelos pueden equivocarse. Por eso todo aviso se presenta como algo «a revisar» y el estudiante puede justificar que no aplica.
- El indicio de texto generado no es una prueba.
- La maquetación (márgenes, tipografía, tamaño de figuras) no puede verificarse desde el texto extraído.
- Los PDF escaneados requieren OCR previo.
- Antes del piloto deben revisarse `required_sections` frente a la normativa oficial, la asignación tutor-estudiante (ahora todos los tutores ven a todos los estudiantes que envían), el consentimiento y la política de retención.

## Identidad y SSO

El prototipo usa SQLite para cuentas, sesiones e informes:
- Las contraseñas se guardan como hashes PBKDF2 con sal.
- La cookie de sesión es `HttpOnly`.

`app/auth/contracts.py` define el contrato `IdentityProvider`, y `app/auth/local.py` es su implementación local. Para conectar un SSO institucional (OIDC, SAML o CAS), añade otro proveedor e inicialízalo en `app/main.py`. En producción, activa HTTPS y la cookie `Secure`. El alta de tutores debe venir del directorio institucional.
