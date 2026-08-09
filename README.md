# TFGBoost

Prototipo local de apoyo formativo para la revisión de borradores de Trabajo de Fin de Grado. TFGBoost no redacta el trabajo del estudiante ni produce calificaciones: analiza el texto disponible, detecta aspectos que conviene revisar y propone acciones de mejora explicables.

## Incluye

- Carga de documentos `PDF` y `DOCX`.
- Extracción local de texto y almacenamiento local del documento e informe.
- Diagnóstico de estructura, claridad, coherencia, redacción y referencias.
- Checklist de secciones adaptada a una memoria de TFG; es fácilmente ampliable para cada centro.
- Panel de tutor con el estado de madurez de los informes generados.
- API documentada automáticamente en `/docs`.

El diagnóstico inicial se basa en reglas transparentes para que sea útil sin depender de un proveedor externo. La configuración deja preparado el uso de Ollama local para una futura capa de análisis lingüístico, sin enviar borradores a terceros.

## Arranque local

Requiere Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
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
