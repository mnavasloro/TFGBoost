"""Resume el cuestionario de tutores para priorizar la checklist de TFGBoost.

Uso:
    python scripts/survey_stats.py "TFGBoost · Cuestionario ... (respuestas)_anon.xlsx" [--json salida.json]

Requiere `openpyxl` (solo para este script; la aplicación no lo necesita).
Calcula, para cada error de la pregunta 8 (escala 1-5), la frecuencia media y
el porcentaje de tutores que lo marcan como 4-5; cuenta cuántos lo señalan como
el que más tiempo consume (pregunta 9) y la utilidad media de cada
funcionalidad (pregunta 14). Los resultados alimentan `app/checklist/tfg_checklist.json`.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from statistics import mean


def _score(value) -> int | None:
    match = re.match(r"\s*(\d)", str(value or ""))
    return int(match.group(1)) if match else None


def summarise(path: str) -> dict:
    from openpyxl import load_workbook

    sheet = load_workbook(path, read_only=True).active
    rows = list(sheet.iter_rows(values_only=True))
    header, answers = rows[0], [row for row in rows[1:] if any(row)]
    errors, features, time_consuming = {}, {}, Counter()
    time_column = None
    for column, title in enumerate(header):
        title = str(title or "")
        scores = [s for s in (_score(row[column]) for row in answers) if s]
        bracket = re.search(r"\[(.+)\]", title)
        if title.startswith("8") and bracket and scores:
            errors[bracket.group(1)] = {
                "block": title.split("[")[0].strip(" .").removeprefix("8a").removeprefix("8b").removeprefix("8c").removeprefix("8d").removeprefix("8e").strip(" ."),
                "mean_frequency": round(mean(scores), 2),
                "pct_frequent": round(100 * sum(s >= 4 for s in scores) / len(scores)),
                "n": len(scores),
            }
        elif title.startswith("14") and bracket and scores:
            features[bracket.group(1)] = {"mean_utility": round(mean(scores), 2), "pct_high": round(100 * sum(s >= 4 for s in scores) / len(scores))}
        elif title.startswith("9."):
            time_column = column
    # Las opciones contienen comas, así que se buscan por nombre en vez de partir la celda.
    for row in answers:
        cell = str(row[time_column] or "")
        for name in errors:
            if name in cell:
                time_consuming[name] += 1
    for name, item in errors.items():
        item["time_consuming_votes"] = time_consuming.get(name, 0)
        # Prioridad = frecuencia media normalizada (70 %) + votos de esfuerzo (30 %).
        item["priority"] = round(0.7 * (item["mean_frequency"] - 1) / 4 + 0.3 * item["time_consuming_votes"] / max(1, len(answers)), 3)
    return {
        "respondents": len(answers),
        "errors": dict(sorted(errors.items(), key=lambda pair: -pair[1]["priority"])),
        "features": dict(sorted(features.items(), key=lambda pair: -pair[1]["mean_utility"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx")
    parser.add_argument("--json", help="Guardar el resumen en un fichero JSON")
    args = parser.parse_args()
    summary = summarise(args.xlsx)
    print(f"Respuestas: {summary['respondents']}\n")
    print(f"{'Prioridad':>9} {'Media':>6} {'%4-5':>5} {'Votos':>5}  Error")
    for name, item in summary["errors"].items():
        print(f"{item['priority']:>9.3f} {item['mean_frequency']:>6.2f} {item['pct_frequent']:>4}% {item['time_consuming_votes']:>5}  {name}")
    print(f"\n{'Utilidad':>8} {'%4-5':>5}  Funcionalidad")
    for name, item in summary["features"].items():
        print(f"{item['mean_utility']:>8.2f} {item['pct_high']:>4}%  {name}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
