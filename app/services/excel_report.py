"""Resultado de cada entrega en Excel: lo que vio el usuario y de dónde procede.

Hojas:
- Resumen: entrega, modelo, madurez, semáforo, consumo y errores del modelo.
- Resultados: un punto de la checklist por fila, con el veredicto de las reglas,
  el de la IA (y qué modelo) y cuál fijó el estado final.
- Comentarios: cada comentario mostrado, con su fuente, modelo y cita.
- Categorías: puntuación y avisos abiertos por categoría.
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

STATUS = {"cumple": "Cumple", "por_revisar": "Por revisar", "no_cumple": "No cumple", "no_evaluable": "No evaluable", "manual": "Revisión manual"}
FILLS = {
    "cumple": "E8F6EE", "por_revisar": "FFF4E0", "no_cumple": "FDECEF", "no_evaluable": "EEF1F5", "manual": "ECEBFF",
    "verde": "E8F6EE", "ambar": "FFF4E0", "rojo": "FDECEF",
}
RESPONSES = {"corregido": "Lo he corregido", "no_aplica": "No aplica", "pendiente": "Pendiente"}
HEADER_FILL = PatternFill("solid", fgColor="5146E5")
HEADER_FONT = Font(bold=True, color="FFFFFF")
WRAP = Alignment(wrap_text=True, vertical="top")


def results_path(base_dir: Path, report_id: str) -> Path:
    return base_dir / "results" / f"{report_id}.xlsx"


def download_name(report: dict) -> str:
    student = re.sub(r"[^\w-]+", "_", report.get("student_name") or "estudiante").strip("_")
    stem = re.sub(r"[^\w-]+", "_", Path(report.get("filename") or "borrador").stem).strip("_")
    return f"TFGBoost_{student}_{stem}_{(report.get('created_at') or '')[:10]}.xlsx"


def _source_label(source: str) -> str:
    return "Reglas" if source == "regla" else "IA"


def _table(sheet, headers: list[str], rows: list[list], widths: list[int], status_column: int | None = None) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill, cell.font, cell.alignment = HEADER_FILL, HEADER_FONT, Alignment(wrap_text=True, vertical="center")
    for row in rows:
        sheet.append(row)
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
        if status_column is not None:
            key = next((k for k, v in STATUS.items() if v == row[status_column].value), None)
            if key:
                row[status_column].fill = PatternFill("solid", fgColor=FILLS[key])
    sheet.freeze_panes = "A2"
    if rows:
        sheet.auto_filter.ref = sheet.dimensions


def build_workbook(report: dict, responses: dict[str, dict] | None = None) -> bytes:
    responses = responses or {}
    workbook = Workbook()

    # --- Resumen ---
    summary = workbook.active
    summary.title = "Resumen"
    usage = report.get("usage") or {}
    evolution = report.get("evolution") or {}
    rows = [
        ("Estudiante", report.get("student_name")),
        ("Archivo", report.get("filename")),
        ("Fecha de subida (UTC)", (report.get("created_at") or "")[:19].replace("T", " ")),
        ("Enviado al tutor (UTC)", (report.get("submitted_at") or "No enviado")[:19].replace("T", " ")),
        ("Modelo de IA", report.get("model_label") or "Solo reglas automáticas"),
        ("Identificador del modelo", report.get("model") or "none"),
        ("Modelo remoto", "Sí" if report.get("remote_model") else "No"),
        ("Prioridad (OpenRouter)", {"cheap": "Barato", "fast": "Rápido", "default": "Reparto de OpenRouter"}.get(report.get("routing"), "—")),
        ("Versión de la checklist", report.get("checklist_version")),
        ("Palabras", report.get("word_count")),
        ("Madurez (0-100)", report.get("maturity_score")),
        ("Semáforo", report.get("traffic_light")),
        ("Imprescindibles en «no cumple»", ", ".join(report.get("blocking_items") or []) or "Ninguno"),
        ("Duración del análisis (s)", report.get("duration_seconds")),
        ("Llamadas al modelo", usage.get("calls", 0)),
        ("Tokens de entrada", (usage.get("input_tokens", 0) + usage.get("cache_read_tokens", 0) + usage.get("cache_write_tokens", 0)) if usage else 0),
        ("  · leídos de caché", usage.get("cache_read_tokens", 0)),
        ("Tokens de salida", usage.get("output_tokens", 0)),
        ("Coste estimado (US$)", usage.get("cost_usd", 0)),
        ("Errores del modelo", "\n".join(report.get("llm_errors") or []) or "Ninguno"),
    ]
    if evolution:
        rows += [
            ("Cambio de madurez respecto a la versión anterior", evolution.get("score_delta")),
            ("Avisos resueltos", ", ".join(evolution.get("resolved", [])) or "—"),
            ("Avisos que persisten", ", ".join(evolution.get("persisting", [])) or "—"),
            ("Marcados como corregidos pero persisten", ", ".join(evolution.get("claimed_fixed_but_persisting", [])) or "—"),
        ]
    rows.append(("Aviso", report.get("disclaimer")))
    for label, value in rows:
        summary.append([label, value])
    summary.column_dimensions["A"].width = 44
    summary.column_dimensions["B"].width = 90
    for row in summary.iter_rows():
        row[0].font = Font(bold=True)
        for cell in row:
            cell.alignment = WRAP
    light = next((row[1] for row in summary.iter_rows() if row[0].value == "Semáforo"), None)
    if light is not None and light.value in FILLS:
        light.fill = PatternFill("solid", fgColor=FILLS[light.value])

    # --- Resultados ---
    sheet = workbook.create_sheet("Resultados")
    result_rows = []
    for item in report.get("items", []):
        sources = {s["source"]: s for s in (item.get("provenance") or {}).get("sources", [])}
        rule, ai = sources.get("regla"), sources.get("ia")
        decided = (item.get("provenance") or {}).get("decided_by") or []
        response = responses.get(item["id"]) or {}
        result_rows.append([
            item["id"], item.get("category"), item.get("title"), "Sí" if item.get("must_fix") else "No", item.get("severity"),
            STATUS.get(item["status"], item["status"]),
            " + ".join(_source_label(d) for d in decided) or "—",
            STATUS.get(rule["status"]) if rule else "No aplica",
            rule["evidence"] if rule else "",
            (ai.get("model") or "IA no utilizada") if ai else "No aplica",
            STATUS.get(ai["status"]) if ai else "",
            ai["evidence"] if ai else "",
            sum(1 for c in item.get("comments", []) if c["source"] == "regla"),
            sum(1 for c in item.get("comments", []) if c["source"] == "ia"),
            item.get("evidence"),
            RESPONSES.get(response.get("status"), ""),
            response.get("note", ""),
            item.get("weight"),
        ])
    _table(sheet, [
        "ID", "Categoría", "Punto de la checklist", "Imprescindible", "Gravedad", "Estado final", "Decidido por",
        "Reglas: estado", "Reglas: evidencia", "IA: modelo", "IA: estado", "IA: evidencia",
        "Comentarios de reglas", "Comentarios de IA", "Evidencia mostrada al usuario", "Respuesta del estudiante", "Justificación del estudiante", "Peso",
    ], result_rows, [6, 13, 38, 12, 11, 14, 13, 14, 50, 22, 14, 50, 11, 11, 60, 18, 40, 7], status_column=5)
    for row in sheet.iter_rows(min_row=2):
        for column in (7, 10):  # estados de reglas e IA
            key = next((k for k, v in STATUS.items() if v == row[column].value), None)
            if key:
                row[column].fill = PatternFill("solid", fgColor=FILLS[key])

    # --- Comentarios ---
    comments = workbook.create_sheet("Comentarios")
    comment_rows = []
    for item in report.get("items", []):
        for comment in item.get("comments", []):
            verified = comment.get("verified")
            comment_rows.append([
                item["id"], item.get("title"), STATUS.get(item["status"], item["status"]),
                "Regla" if comment["source"] == "regla" else "IA", comment.get("model") or ("Reglas automáticas" if comment["source"] == "regla" else ""),
                comment.get("quote") or "", comment.get("feedback"), comment.get("location") or "",
                "Sí" if verified else "No (posible alucinación)" if verified is False else "Sin cita",
                comment["anchor"][0] if comment.get("anchor") else "",
            ])
    _table(comments, ["ID", "Punto", "Estado del punto", "Fuente", "Modelo", "Cita del borrador", "Comentario mostrado", "Ubicación", "Cita localizada en el texto", "Posición (carácter)"],
           comment_rows, [6, 34, 14, 8, 22, 55, 60, 22, 18, 10], status_column=2)

    # --- Categorías ---
    categories = workbook.create_sheet("Categorías")
    _table(categories, ["Categoría", "Puntuación (0-100)", "Puntos evaluados", "Avisos abiertos"],
           [[c.get("label"), c.get("score"), c.get("evaluated"), c.get("open")] for c in (report.get("categories") or {}).values()], [32, 18, 16, 15])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def save_workbook(base_dir: Path, report: dict, responses: dict[str, dict] | None = None) -> Path:
    path = results_path(base_dir, report["document_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_workbook(report, responses))
    return path
