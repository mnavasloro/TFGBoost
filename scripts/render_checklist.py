"""Genera docs/CHECKLIST.md a partir de app/checklist/tfg_checklist.json.

Uso: python scripts/render_checklist.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METHOD = {"rule": "Regla automática", "llm": "Modelo de IA", "rule+llm": "Regla + IA", "manual": "Comprobación manual"}
SEVERITY = {"critico": "Crítico", "importante": "Importante", "menor": "Menor"}


def render(data: dict) -> str:
    items = data["items"]
    lines = [
        f"# {data['title']}",
        "",
        f"Versión `{data['version']}`. Documento generado desde [`app/checklist/tfg_checklist.json`](../app/checklist/tfg_checklist.json) con `python scripts/render_checklist.py`: edita el JSON, no este fichero.",
        "",
        "## Fuentes",
        "",
        *[f"- **{key}**: {text}" for key, text in data["sources"].items()],
        "",
        "## Cómo se usa",
        "",
        "- Cada punto se evalúa con reglas transparentes, con un modelo de lenguaje o con ambos; el estado final es el más desfavorable.",
        "- Estados: **cumple**, **por revisar**, **no cumple**, **no evaluable** (sin evidencia suficiente o sin modelo) y **revisión manual**.",
        "- Las citas aportadas por la IA se buscan literalmente en el borrador; si ninguna aparece, el punto no puede quedar en «no cumple» (mitiga las alucinaciones, la principal preocupación de los tutores en la encuesta).",
        f"- **Madurez**: {data['scoring']['description']}",
        f"- **Semáforo**: verde ≥ {data['scoring']['traffic_light']['green']} sin puntos imprescindibles en «no cumple»; ámbar ≥ {data['scoring']['traffic_light']['amber']}; rojo por debajo.",
        "- **Imprescindible**: errores que los tutores piden corregir siempre antes de enviar (encuesta, P11). Si alguno queda en «no cumple», el estudiante debe corregirlo o justificar por qué no aplica antes de enviar el borrador al tutor.",
        "- La herramienta nunca reescribe el texto (encuesta, P16): señala el problema, explica por qué importa y orienta la corrección.",
        "",
        "## Resumen priorizado",
        "",
        "Ordenado por peso (prioridad según la encuesta a 16 tutores; los puntos sin dato de encuesta usan el peso por defecto).",
        "",
        "| ID | Punto | Categoría | Método | Imprescindible | Frecuencia media (1-5) | % tutores 4-5 | Votos «más tiempo» | Peso |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    default = data["scoring"]["default_weight"]
    for item in sorted(items, key=lambda i: -(i["survey"]["priority"] if i["survey"] else default)):
        survey = item["survey"]
        lines.append(
            f"| {item['id']} | {item['title']} | {data['categories'][item['category']]['label']} | {METHOD[item['method']]} | {'Sí' if item['must_fix'] else ''} | "
            f"{survey['mean_frequency'] if survey else '–'} | {str(survey['pct_frequent']) + ' %' if survey else '–'} | {survey['time_votes'] if survey else '–'} | {survey['priority'] if survey else default} |"
        )
    lines += ["", "## Detalle por categoría", ""]
    for key, category in data["categories"].items():
        lines += [f"### {category['label']}", ""]
        for item in (i for i in items if i["category"] == key):
            lines += [
                f"#### {item['id']} · {item['title']}",
                "",
                f"- **Método**: {METHOD[item['method']]} · **Gravedad**: {SEVERITY[item['severity']]}{' · **Imprescindible**' if item['must_fix'] else ''}",
                f"- **Origen**: {', '.join(item['sources'])}",
            ]
            if item.get("question"):
                lines.append(f"- **Pregunta al modelo**: {item['question']}")
            lines += [f"- **Orientación al estudiante**: {item['guidance']}", ""]
    lines += [
        "## Apartados de la memoria reconocidos",
        "",
        "| Apartado | Obligatorio | Encabezados aceptados |",
        "|---|---|---|",
        *[f"| {spec['label']} | {'Sí' if spec['required'] else 'No'} | {', '.join(spec['aliases'])} |" for spec in data["required_sections"].values()],
        "",
        "> Ajusta `required_sections` a la normativa oficial de TFG de cada escuela antes del piloto.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    data = json.loads((ROOT / "app/checklist/tfg_checklist.json").read_text(encoding="utf-8"))
    output = ROOT / "docs/CHECKLIST.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text(render(data), encoding="utf-8")
    print(f"Escrito {output.relative_to(ROOT)} ({len(data['items'])} puntos).")
