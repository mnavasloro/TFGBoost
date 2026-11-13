"""Compara modelos sobre un conjunto de borradores (fase 3 del plan: evaluación y selección).

Uso:
    python scripts/benchmark.py borradores/ --models none ollama:qwen3:8b anthropic:claude-haiku-5-5 [--gold anotaciones.json]

Escribe `benchmark.csv` con, por borrador y modelo: tiempo, llamadas, tokens,
coste estimado, madurez y estado de cada punto. Con `--gold` (JSON
{"fichero.docx": {"L1": "no_cumple", ...}} anotado por tutores) calcula la
concordancia por punto, tratando «por revisar» y «no cumple» como «aviso».

Atención: los modelos remotos envían el texto fuera de la universidad; úsalos
solo con borradores cuyos autores lo hayan autorizado expresamente.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.checklist import get_checklist  # noqa: E402
from app.llm import get_provider  # noqa: E402
from app.services.extractor import extract_document  # noqa: E402
from app.services.pipeline import analyse_document  # noqa: E402

OPEN = {"por_revisar", "no_cumple"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--models", nargs="+", default=["none"])
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--out", type=Path, default=Path("benchmark.csv"))
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text(encoding="utf-8")) if args.gold else {}
    item_ids = [item.id for item in get_checklist().items]
    files = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in {".pdf", ".docx"})
    rows, agreement = [], {}
    for path in files:
        document = extract_document(path.name, path.read_bytes())
        for model in args.models:
            started = perf_counter()
            report = analyse_document(document.text, path.name, path.stem, get_provider(model), known_headings=document.headings)
            usage = report["usage"] or {}
            statuses = {item["id"]: item["status"] for item in report["items"]}
            rows.append({"file": path.name, "model": model, "seconds": round(perf_counter() - started, 1), "calls": usage.get("calls", 0),
                         "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_read_tokens", 0) + usage.get("cache_write_tokens", 0),
                         "output_tokens": usage.get("output_tokens", 0), "cost_usd": usage.get("cost_usd", 0), "maturity": report["maturity_score"],
                         "errors": len(report["llm_errors"]), **statuses})
            for item_id, expected in gold.get(path.name, {}).items():
                if statuses.get(item_id) in (None, "no_evaluable", "manual"):
                    continue
                hit = (statuses[item_id] in OPEN) == (expected in OPEN)
                total, correct = agreement.get((model, item_id), (0, 0))
                agreement[(model, item_id)] = (total + 1, correct + hit)
            print(f"{path.name} · {model}: {rows[-1]['seconds']} s, madurez {report['maturity_score']}, coste ~{usage.get('cost_usd', 0):.3f} US$")
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "model", "seconds", "calls", "input_tokens", "output_tokens", "cost_usd", "maturity", "errors", *item_ids])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Resultados en {args.out}")
    if agreement:
        print("\nConcordancia con las anotaciones (aviso / sin aviso):")
        for model in args.models:
            pairs = [v for (m, _), v in agreement.items() if m == model]
            total, correct = sum(t for t, _ in pairs), sum(c for _, c in pairs)
            print(f"  {model}: {correct}/{total} ({correct / total:.0%})" if total else f"  {model}: sin datos")


if __name__ == "__main__":
    main()
