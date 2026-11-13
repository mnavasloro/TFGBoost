from app.checklist import get_checklist
from app.services.llm_review import plan_tasks
from app.services.pipeline import analyse_document, compare_versions, locate
from app.services.rules import run_rules
from app.services.sections import chunk_sections, find_sections

from tests.conftest import FakeProvider


def test_checklist_is_consistent():
    checklist = get_checklist()
    assert len(checklist.items) >= 30
    covered = {category for group in checklist.groups for category in group.categories}
    assert covered == set(checklist.categories)
    # Los 22 errores de la encuesta (P8) están representados con sus estadísticas.
    assert sum(1 for item in checklist.items if item.survey) == 22


def test_sections_skip_table_of_contents(sample_text):
    sections = find_sections(sample_text, get_checklist().required_sections)
    keys = [s.key for s in sections]
    assert keys.count("introduccion") == 1
    intro = next(s for s in sections if s.key == "introduccion")
    assert "El sistema propuesto" in intro.text(sample_text)
    assert {"resumen", "abstract", "objetivos", "estado_arte", "desarrollo", "resultados", "conclusiones", "referencias"} <= set(keys)


def test_spanish_word_todo_is_not_a_draft_marker():
    checklist = get_checklist()
    text = "Introducción\n" + "El sistema funciona sobre todo con datos reales y en todo momento se registra.\n" * 3
    results, _ = run_rules(text, find_sections(text, checklist.required_sections), checklist)
    assert results["E5"].status == "cumple"


def test_known_headings_avoid_false_chapters():
    checklist = get_checklist()
    text = "Resumen\nTexto del resumen con contenido suficiente para no estar vacío en absoluto, ni mucho menos.\n1. Introducción\nTexto.\n3.6. Resumen de la pila tecnológica\nTexto.\n6.3. Objetivos de Desarrollo Sostenible\nTexto.\n"
    sections = find_sections(text, checklist.required_sections, ["1. Introducción", "3.6. Resumen de la pila tecnológica", "6.3. Objetivos de Desarrollo Sostenible"])
    assert [s.key for s in sections] == ["resumen", "introduccion", "impacto"]


def test_paragraph_lines_are_not_headings():
    text = "Introducción\nResultados de la encuesta muestran que los tutores revisan mucho, y lo hacen a menudo.\n"
    keys = [s.key for s in find_sections(text, get_checklist().required_sections)]
    assert keys == ["introduccion"]


def test_rules_detect_known_problems(sample_text):
    checklist = get_checklist()
    results, metrics = run_rules(sample_text, find_sections(sample_text, checklist.required_sections), checklist)
    assert results["E5"].status == "no_cumple"  # TODO
    assert results["L5"].status != "cumple" or results["L5"].comments  # «Yo creo», «guay»
    assert any("API" in c.feedback for c in results["N1"].comments)
    assert any("Tabla 1" in c.feedback or "tabla 1" in c.feedback for c in results["F1"].comments)
    assert "2" in results["R3"].evidence  # la entrada [2] no se cita
    for result in results.values():
        for comment in result.comments:
            start, end = comment.anchor
            assert sample_text[start:end].split()[0] in comment.quote


def test_pipeline_without_model_marks_llm_items_not_evaluable(sample_text):
    report = analyse_document(sample_text, "tfg.pdf", "id-1", None)
    statuses = {item["id"]: item["status"] for item in report["items"]}
    assert statuses["C1"] == "no_evaluable"
    assert statuses["F3"] == "manual"
    assert 0 <= report["maturity_score"] <= 100
    assert report["traffic_light"] in {"verde", "ambar", "rojo"}
    assert "E5" in report["blocking_items"]


def test_pipeline_with_model_verifies_quotes(sample_text):
    report = analyse_document(sample_text, "tfg.pdf", "id-2", FakeProvider())
    c1 = next(item for item in report["items"] if item["id"] == "C1")
    assert c1["status"] == "no_cumple"
    assert c1["comments"][0]["verified"] is True
    assert report["usage"]["calls"] == len(get_checklist().groups)


def test_unverifiable_ai_quotes_cannot_fail_an_item(sample_text):
    report = analyse_document(sample_text, "tfg.pdf", "id-3", FakeProvider(quote="Esta frase no aparece en el borrador original"))
    c1 = next(item for item in report["items"] if item["id"] == "C1")
    assert c1["status"] == "por_revisar"
    assert c1["comments"][0]["verified"] is False


def test_small_context_models_get_section_chunks(sample_text):
    checklist = get_checklist()
    sections = find_sections(sample_text, checklist.required_sections)
    provider = FakeProvider(max_input_chars=2500)
    tasks = plan_tasks(sample_text, sections, checklist, provider)
    assert len(tasks) > len(checklist.groups)
    assert all(len(chunk.text) <= 2500 for _, chunk, _ in tasks)
    assert not any(whole for _, _, whole in tasks)


def test_chunks_cover_long_sections(sample_text):
    sections = find_sections(sample_text, get_checklist().required_sections)
    chunks = chunk_sections(sample_text, sections, ("desarrollo",), 1000)
    joined = "".join(chunk.text for chunk in chunks)
    development = next(s for s in sections if s.key == "desarrollo").text(sample_text)
    assert joined == development


def test_locate_tolerates_pdf_line_breaks():
    text = "Primera línea del párrafo\ncontinúa aquí con más texto."
    assert locate(text, "del párrafo continúa aquí") is not None
    assert locate(text, "no existe en el texto") is None


def test_compare_versions_tracks_resolution():
    previous = {"document_id": "a", "maturity_score": 40, "items": [{"id": "L1", "status": "no_cumple"}, {"id": "L2", "status": "por_revisar"}, {"id": "L3", "status": "cumple"}]}
    current = {"maturity_score": 55, "items": [{"id": "L1", "status": "cumple"}, {"id": "L2", "status": "por_revisar"}, {"id": "L3", "status": "por_revisar"}]}
    evolution = compare_versions(previous, current, {"L2": {"status": "corregido"}})
    assert evolution["resolved"] == ["L1"]
    assert evolution["persisting"] == ["L2"]
    assert evolution["new"] == ["L3"]
    assert evolution["claimed_fixed_but_persisting"] == ["L2"]
    assert evolution["score_delta"] == 15


def test_repeated_title_is_not_flagged_as_redundant():
    checklist = get_checklist()
    title = "Análisis de la capacidad, seguridad y los riesgos de un agente autónomo de inteligencia artificial"
    body = "El agente se despliega en la máquina virtual {n} y se mide su resistencia a ataques de inyección.\n"
    # Portada, «Título:», el título citado en la introducción y como cabecera de página en el PDF.
    text = (f"UNIVERSIDAD POLITÉCNICA DE MADRID\n{title}\nTítulo: {title}\n\n1. Introducción\n"
            + "".join(f"{title}\n{body.format(n=n)}Página {n} con texto distinto número {n} para que no se repita la oración.\n" for n in range(4))
            + f"Este trabajo, titulado {title}, estudia el problema.\n")
    results, _ = run_rules(text, find_sections(text, checklist.required_sections), checklist)
    assert "0 oraciones repetidas" in results["L6"].evidence, results["L6"].evidence


def test_genuinely_repeated_sentence_is_still_flagged():
    checklist = get_checklist()
    sentence = "Los resultados muestran que el modelo local resiste mejor los ataques que los modelos comerciales evaluados."
    text = f"1. Introducción\n{sentence}\nOtra frase cualquiera que no se repite en ningún otro lugar del texto.\n2. Conclusiones\n{sentence}\n"
    results, _ = run_rules(text, find_sections(text, checklist.required_sections), checklist)
    assert "1 oraciones repetidas" in results["L6"].evidence


def test_repeated_table_cells_from_pdf_are_not_flagged():
    checklist = get_checklist()
    cell = "Gratuito \n(API) \n0 $ dentro de los límites \nde tasa del nivel \ngratuito \nAlternativa sin coste \n"
    text = "1. Marco tecnológico\nModelo \nProveedor \nCoste \n" + cell + "Gemma \nGoogle \n" + cell + "Texto normal del capítulo que explica la tabla anterior.\n"
    results, _ = run_rules(text, find_sections(text, checklist.required_sections), checklist)
    assert "0 oraciones repetidas" in results["L6"].evidence
