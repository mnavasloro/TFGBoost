"""Comprobaciones deterministas y explicables de la checklist.

Cada regla devuelve un `ItemResult` con evidencias y, cuando hay un fragmento
concreto, un comentario anclado a su posición exacta en el texto. Las reglas
son deliberadamente conservadoras: marcan «por revisar», no sentencian.
"""
from __future__ import annotations

import re
from collections import Counter

from app.checklist import Checklist
from app.schemas import Comment, ItemResult
from app.services.sections import Section, normalise, section_texts, word_count

MAX_COMMENTS = 8
CORE_SECTIONS = ("introduccion", "objetivos", "estado_arte", "marco_tecnologico", "requisitos", "metodologia", "desarrollo", "resultados", "impacto", "conclusiones", "trabajo_futuro")
# Fuera del «cuerpo» para las reglas de redacción y citas (el abstract está en inglés).
NON_BODY_SECTIONS = ("indice", "referencias", "anexos", "glosario", "abstract", "portada")

# TODO/FIXME/TBD distinguen mayúsculas: «todo» es una palabra española corriente.
DRAFT_MARKERS = re.compile(
    r"\b(?:TODO|FIXME|TBD)\b|\?{2,}|(?i:lorem ipsum|\[(?:completar|pendiente|por hacer|cita|ref|referencia)\]"
    r"|Error! Reference source not found|¡Error! No se encuentra el origen de la referencia"
    r"|(?:Figura|Tabla|Secci[oó]n|Cap[ií]tulo)\s+\?\?)"
)
FIRST_PERSON = re.compile(
    r"\b(?:yo|me he|creo que|pienso que|me parece|personalmente|mi opini[oó]n"
    r"|he (?:decidido|realizado|implementado|hecho|desarrollado|utilizado|usado|elegido|creado|dise[nñ]ado|optado|aprendido|tenido|podido|querido|intentado|conseguido))\b",
    re.IGNORECASE,
)
COLLOQUIAL = re.compile(
    r"\b(?:un mont[oó]n|a tope|guay|s[uú]per|cosas?|b[aá]sicamente|obviamente|la verdad es que|en plan|pillar|chulo|currar|o sea|un poco de todo)\b",
    re.IGNORECASE,
)
FILLER = re.compile(
    r"\b(?:cabe (?:destacar|mencionar|se[nñ]alar|resaltar) que|es importante (?:destacar|mencionar|se[nñ]alar|resaltar)"
    r"|hoy en d[ií]a|a d[ií]a de hoy|en el mundo actual|en la sociedad actual|cada vez m[aá]s"
    r"|como (?:se ha|ya se ha|hemos) (?:mencionado|comentado|dicho|visto) (?:anteriormente|antes|previamente)?"
    r"|a nivel de|en lo que respecta a|juega un papel (?:muy )?(?:importante|fundamental|clave)|y mucho m[aá]s|entre otros muchos)\b",
    re.IGNORECASE,
)
ACRONYM = re.compile(r"(?<![\w-])([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9]{1,7})s?(?![\w-])")
ACRONYM_STOPLIST = {
    "TFG", "TFM", "UPM", "ETSISI", "OK", "EEUU", "UU", "EE", "DOI", "ISBN", "ISSN", "PDF", "Nº", "SA", "SL",
    "NO", "SI", "SÍ", "EL", "LA", "LOS", "LAS", "DE", "DEL", "EN", "UN", "UNA", "GET", "POST", "PUT", "DELETE",
    "KB", "MB", "GB", "TB",
}
ROMAN = re.compile(r"^[IVXLCDM]+$")
LABEL = re.compile(r"^[A-Z]{1,3}\d{1,3}$")  # etiquetas como C1, V4, RQ2, ASI01
NUMERIC_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)\]")
AUTHOR_YEAR_CITE = re.compile(r"\(([A-ZÁÉÍÓÚÑ][\w'´-]+)(?:\s+et al\.?|\s+(?:y|&|and)\s+[A-ZÁÉÍÓÚÑ][\w'-]+)?,?\s+(\d{4}[a-z]?)(?:[;,][^)]*)?\)")
NARRATIVE_CITE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][\w'´-]+)(?:\s+et al\.?|\s+(?:y|&|and)\s+[A-ZÁÉÍÓÚÑ][\w'-]+)?\s+\((\d{4}[a-z]?)\)")
CAPTION = re.compile(r"(?m)^[ \t]*(Figura|Fig\.|Ilustraci[oó]n|Tabla|Cuadro|Gr[aá]fico|Listado|C[oó]digo)\s+(\d+(?:[.\-]\d+)?)\s*[.:\-–]?[ \t]*(.*)$")
MENTION = re.compile(r"\b(Figuras?|Figs?\.|Ilustraci[oó]n(?:es)?|Tablas?|Cuadros?|Gr[aá]ficos?|Listados?|C[oó]digos?)\s+(\d+(?:[.\-]\d+)?)", re.IGNORECASE)
SECRET = re.compile(r"(?i)\b(?:password|passwd|contrase[nñ]a|api[_-]?key|secret|token)\s*[:=]\s*\S+|\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b")
LOCAL_PATH = re.compile(r"[A-Za-z]:\\Users\\[^\s\\]+|/home/[a-z_][\w-]*/|/Users/[A-Za-z][\w-]*/")


def _kind(word: str) -> str:
    word = normalise(word)
    if word.startswith(("tabla", "cuadro")):
        return "tabla"
    if word.startswith(("listado", "codigo")):
        return "código"
    return "figura"


def quote_at(text: str, start: int, end: int, width: int = 50) -> tuple[str, list[int]]:
    """Fragmento literal alrededor de [start, end) ajustado a límites de palabra."""
    left = max(0, start - width)
    right = min(len(text), end + width)
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    while right < len(text) and not text[right].isspace():
        right += 1
    left = min(start, left)
    snippet = text[left:right].strip()
    offset = text.index(snippet, left) if snippet else left
    return re.sub(r"\s+", " ", snippet), [offset, offset + len(snippet)]


def _comment(text: str, start: int, end: int, feedback: str, location: str | None = None, width: int = 50) -> Comment:
    quote, anchor = quote_at(text, start, end, width)
    return Comment(feedback=feedback, quote=quote, location=location, source="regla", anchor=anchor, verified=True)


class _Document:
    """Vista auxiliar del borrador: secciones, rangos del cuerpo y oraciones."""

    def __init__(self, text: str, sections: list[Section]):
        self.text = text
        self.sections = sections
        self.by_key = section_texts(text, sections)
        excluded = [(s.start, s.end) for s in sections if s.key in NON_BODY_SECTIONS]
        if sections:
            excluded.append((0, sections[0].start))  # portada, agradecimientos y demás preliminares
        self.excluded = excluded
        self.words = word_count(text)

    def in_body(self, position: int) -> bool:
        return not any(start <= position < end for start, end in self.excluded)

    def section_at(self, position: int) -> str | None:
        for section in self.sections:
            if section.start <= position < section.end:
                return section.heading
        return None

    def body_matches(self, pattern: re.Pattern) -> list[re.Match]:
        return [m for m in pattern.finditer(self.text) if self.in_body(m.start())]

    def boilerplate(self) -> list[str]:
        """Textos que se repiten por diseño (normalizados, de más largo a más corto):
        el título (líneas de la portada y «Título: …») y las cabeceras o pies de
        página que el PDF repite en cada hoja."""
        lines = [line.strip() for line in self.text.splitlines() if line.strip()]
        candidates: set[str] = set()
        front_end = self.sections[0].start if self.sections else 0
        for line in self.text[:front_end].splitlines():
            line = re.sub(r"^\s*t[ií]tulo\s*[:.]\s*", "", line.strip(), flags=re.IGNORECASE)
            if len(line.split()) >= 3:
                candidates.add(_sentence_key(line))
        for match in re.finditer(r"(?im)^\s*t[ií]tulo\s*[:.]\s*(.+)$", self.text):
            candidates.add(_sentence_key(match.group(1)))
        counts = Counter(_sentence_key(line) for line in lines if not line.endswith((".", "?", "!")))
        candidates.update(key for key, count in counts.items() if count >= 3 and len(key.split()) >= 3)
        candidates.discard("")
        return sorted(candidates, key=len, reverse=True)

    def sentences(self) -> list[tuple[int, int]]:
        """Oraciones del cuerpo. Una línea continúa el párrafo anterior solo si este
        no terminó en puntuación y la línea empieza en minúscula (renglón partido
        por la maquetación del PDF); en DOCX cada línea ya es un párrafo."""
        spans: list[tuple[int, int]] = []
        start, previous = None, ""
        position = 0
        for line in self.text.splitlines(keepends=True):
            stripped = line.strip()
            line_start = position
            position += len(line)
            continues = (
                start is not None and stripped and not previous.endswith((".", "!", "?", ":", ";"))
                and (stripped[0].islower() or previous.endswith((",", "-")))
            )
            if not continues and start is not None:
                spans.append((start, line_start))
                start = None
            if not stripped or " | " in stripped:  # líneas vacías y filas de tabla
                previous = ""
                continue
            if start is None:
                start = line_start
            previous = stripped
        if start is not None:
            spans.append((start, len(self.text)))
        sentences: list[tuple[int, int]] = []
        for block_start, block_end in spans:
            if not self.in_body(block_start):
                continue
            block = self.text[block_start:block_end]
            cursor = 0
            for match in re.finditer(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"«(])", block):
                sentences.append((block_start + cursor, block_start + match.start()))
                cursor = match.end()
            sentences.append((block_start + cursor, block_end))
        return [(s, e) for s, e in sentences if self.text[s:e].strip()]


def _looks_tabular(text: str) -> bool:
    """Fragmento de una tabla del PDF: muchas líneas muy cortas seguidas."""
    lines = [line for line in text.splitlines() if line.strip()]
    return len(lines) >= 3 and sum(len(line.strip()) for line in lines) / len(lines) < 30


def _sentence_key(text: str) -> str:
    return re.sub(r"\W+", " ", normalise(text)).strip()


def _status_by_count(count: int, review_at: int, fail_at: int | None = None) -> str:
    if fail_at is not None and count >= fail_at:
        return "no_cumple"
    return "por_revisar" if count >= review_at else "cumple"


# --- Reglas -----------------------------------------------------------------

def _required_sections(doc: _Document, checklist: Checklist) -> ItemResult:
    found = {s.key for s in doc.sections}
    # Un capítulo «Metodología y desarrollo» cubre ambos apartados.
    headings = [normalise(s.heading) for s in doc.sections]
    for key, spec in checklist.required_sections.items():
        if any(re.search(rf"\b{re.escape(normalise(alias))}\b", heading) for alias in spec["aliases"] for heading in headings):
            found.add(key)
    missing = [spec["label"] for key, spec in checklist.required_sections.items() if spec.get("required") and key not in found]
    present = [spec["label"] for key, spec in checklist.required_sections.items() if key in found]
    if missing:
        return ItemResult("E1", "no_cumple", f"No se han identificado estos apartados obligatorios: {', '.join(missing)}. Detectados: {', '.join(present) or 'ninguno'}.", sources=["regla"])
    return ItemResult("E1", "cumple", f"Se han identificado los apartados obligatorios: {', '.join(present)}.", sources=["regla"])


def _chapter_balance(doc: _Document, checklist: Checklist) -> tuple[ItemResult, dict[str, int]]:
    counts = {key: word_count(body) for key, body in doc.by_key.items() if key in CORE_SECTIONS}
    total = sum(counts.values())
    if total < 1500:
        return ItemResult("E2", "no_evaluable", f"El cuerpo detectado tiene {total} palabras: es pronto para valorar el equilibrio entre capítulos.", sources=["regla"]), counts
    labels = {key: checklist.required_sections[key]["label"] for key in counts}
    issues = []
    for key, words in counts.items():
        share = words / total
        limit = 0.6 if key == "desarrollo" else 0.4
        if share > limit:
            issues.append(f"«{labels[key]}» concentra el {share:.0%} del cuerpo")
    for key, minimum in (("introduccion", 0.03), ("resultados", 0.06), ("conclusiones", 0.025)):
        if key in counts and counts[key] / total < minimum:
            issues.append(f"«{labels[key]}» es escaso ({counts[key]} palabras, {counts[key] / total:.0%} del cuerpo)")
    distribution = ", ".join(f"{labels[k]}: {v}" for k, v in sorted(counts.items(), key=lambda pair: -pair[1]))
    if issues:
        return ItemResult("E2", "por_revisar", f"{'; '.join(issues)}. Palabras por capítulo: {distribution}.", sources=["regla"]), counts
    return ItemResult("E2", "cumple", f"Distribución por capítulo: {distribution}.", sources=["regla"]), counts


def _abstract(doc: _Document) -> ItemResult:
    found = {s.key for s in doc.sections}
    issues = []
    if "resumen" not in found:
        issues.append("no se detecta el resumen en español")
    if "abstract" not in found:
        issues.append("no se detecta el abstract en inglés")
    head = normalise(doc.text[: max(6000, len(doc.text) // 8)])
    if "palabras clave" not in head and "keywords" not in head and "key words" not in head:
        issues.append("no se detectan palabras clave")
    if issues:
        return ItemResult("E4", "por_revisar", "Revisión formal: " + "; ".join(issues) + ".", sources=["regla"])
    return ItemResult("E4", "cumple", "Se detectan resumen, abstract y palabras clave.", sources=["regla"])


def _draft_leftovers(doc: _Document) -> ItemResult:
    comments = [_comment(doc.text, m.start(), m.end(), "Marcador o resto de borrador: elimínalo o completa el contenido antes de enviar.", doc.section_at(m.start())) for m in DRAFT_MARKERS.finditer(doc.text)]
    empty = [s.heading for s in doc.sections if s.key not in ("indice", "portada", "glosario") and word_count(s.text(doc.text)) - word_count(s.heading) < 20]
    evidence = []
    if comments:
        evidence.append(f"{len(comments)} marcadores de borrador o referencias cruzadas rotas")
    if empty:
        evidence.append(f"apartados casi vacíos: {', '.join(empty)}")
    status = "no_cumple" if comments else "por_revisar" if empty else "cumple"
    return ItemResult("E5", status, "; ".join(evidence).capitalize() + "." if evidence else "No se detectan marcadores de borrador.", comments[:MAX_COMMENTS], ["regla"])


def _punctuation(doc: _Document) -> ItemResult:
    comments = []
    space_before = doc.body_matches(re.compile(r"(?<=\w) +[,;:](?=\s)|(?<=\w) +\.(?=\s+[A-ZÁÉÍÓÚÑ])"))
    for match in space_before[:3]:
        comments.append(_comment(doc.text, match.start(), match.end(), "Sobra el espacio antes del signo de puntuación.", doc.section_at(match.start()), 30))
    missing_open = []
    for start, end in doc.sentences():
        sentence = doc.text[start:end]
        for match in re.finditer(r"[^.!?]*\?", sentence):
            if "¿" not in match.group(0) and len(match.group(0).split()) > 2:
                missing_open.append((start + match.start(), start + match.end()))
    for s, e in missing_open[:3]:
        comments.append(_comment(doc.text, s, e, "En español, las preguntas llevan signo de apertura (¿).", doc.section_at(s), 10))
    double_spaces = len(doc.body_matches(re.compile(r"(?<=\S) {2,}(?=\S)")))
    total = len(space_before) + len(missing_open) + (double_spaces // 5)
    evidence = f"Espacios antes de signo: {len(space_before)}; preguntas sin «¿»: {len(missing_open)}; espacios dobles: {double_spaces}."
    return ItemResult("L3", _status_by_count(total, 3), evidence, comments, ["regla"])


def _long_sentences(doc: _Document) -> ItemResult:
    sentences = doc.sentences()
    long_ones = [(s, e, word_count(doc.text[s:e])) for s, e in sentences if word_count(doc.text[s:e]) > 40]
    # Las tablas y listados aplanados por el PDF no son oraciones: se exige un verbo conjugado plausible y comas.
    long_ones = [(s, e, n) for s, e, n in long_ones if doc.text[s:e].count(",") >= 1 and n < 200]
    comments = [_comment(doc.text, s, min(e, s + 160), f"Oración de {n} palabras: comprueba si contiene varias ideas que puedes separar.", doc.section_at(s), 0) for s, e, n in long_ones[:MAX_COMMENTS]]
    ratio = len(long_ones) / len(sentences) if sentences else 0
    average = sum(word_count(doc.text[s:e]) for s, e in sentences) / len(sentences) if sentences else 0
    status = "no_cumple" if ratio > 0.15 else "por_revisar" if len(long_ones) >= 3 or ratio > 0.05 else "cumple"
    return ItemResult("L4", status, f"{len(long_ones)} de {len(sentences)} oraciones superan las 40 palabras ({ratio:.0%}); longitud media: {average:.0f} palabras.", comments, ["regla"])


def _register(doc: _Document) -> ItemResult:
    first = doc.body_matches(FIRST_PERSON)
    colloquial = doc.body_matches(COLLOQUIAL)
    comments = [_comment(doc.text, m.start(), m.end(), f"Primera persona del singular («{m.group(0)}»): usa un registro impersonal o el plural de modestia de forma consistente.", doc.section_at(m.start())) for m in first[:4]]
    comments += [_comment(doc.text, m.start(), m.end(), f"Expresión coloquial o imprecisa («{m.group(0)}»): sustitúyela por un término preciso o un dato.", doc.section_at(m.start())) for m in colloquial[:4]]
    total = len(first) + len(colloquial)
    return ItemResult("L5", _status_by_count(total, 3, 15), f"Primera persona del singular: {len(first)} apariciones; expresiones coloquiales o vagas: {len(colloquial)}.", comments, ["regla"])


def _filler(doc: _Document) -> ItemResult:
    matches = doc.body_matches(FILLER)
    comments = [_comment(doc.text, m.start(), m.end(), f"«{m.group(0)}» suele ser relleno: comprueba si la frase aporta información sin esta expresión.", doc.section_at(m.start())) for m in matches[:5]]
    normalised = Counter()
    first_position: dict[str, int] = {}
    boilerplate = doc.boilerplate()
    for s, e in doc.sentences():
        if _looks_tabular(doc.text[s:e]):
            continue  # celdas de una tabla aplanada por el PDF, no prosa
        key = _sentence_key(doc.text[s:e])
        # El título y las cabeceras/pies de página se repiten por diseño: no son redundancia.
        for repeated_text in boilerplate:
            key = f" {key} ".replace(f" {repeated_text} ", " ").strip()
        if len(key.split()) >= 8:
            normalised[key] += 1
            first_position.setdefault(key, s)
    repeated = [key for key, count in normalised.items() if count > 1]
    for key in repeated[:3]:
        position = first_position[key]
        comments.append(_comment(doc.text, position, position + min(160, len(key)), "Esta oración aparece repetida literalmente en el documento.", doc.section_at(position), 0))
    per_thousand = 1000 * len(matches) / max(1, doc.words)
    status = "por_revisar" if len(matches) >= 4 or per_thousand > 2 or repeated else "cumple"
    return ItemResult("L6", status, f"{len(matches)} expresiones de relleno ({per_thousand:.1f} por cada 1.000 palabras); {len(repeated)} oraciones repetidas.", comments, ["regla"])


def _acronyms(doc: _Document) -> ItemResult:
    glossary = doc.by_key.get("glosario", "")
    first_use: dict[str, int] = {}
    for match in ACRONYM.finditer(doc.text):
        acronym = match.group(1)
        line_start = doc.text.rfind("\n", 0, match.start()) + 1
        line_end = doc.text.find("\n", match.end())
        line = doc.text[line_start: line_end if line_end != -1 else len(doc.text)]
        letters = [c for c in line if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            continue  # encabezado en mayúsculas
        if acronym in ACRONYM_STOPLIST or ROMAN.match(acronym) or LABEL.match(acronym) or not doc.in_body(match.start()):
            continue
        first_use.setdefault(acronym, match.start())
    undefined, late = [], []
    for acronym, position in first_use.items():
        escaped = re.escape(acronym)
        # «(API)», «API (Application…)», «API: …» o una fila de glosario «API | …».
        definition = re.search(rf"\(\s*{escaped}s?\s*[),;]|\b{escaped}s?\s*\(\s*[a-záéíóúñA-Z]{{3,}}|\b{escaped}\s*[:–—|-]\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]{{3,}}", doc.text)
        if definition and definition.start() <= position + 200:
            continue
        if re.search(rf"\b{escaped}\b", glossary):
            continue
        (late if definition else undefined).append((acronym, position))
    comments = [_comment(doc.text, p, p + len(a), f"La sigla «{a}» se usa sin definir: desarrolla su significado en el primer uso y añádela al glosario.", doc.section_at(p), 40) for a, p in undefined[:MAX_COMMENTS]]
    comments += [_comment(doc.text, p, p + len(a), f"La sigla «{a}» se define después de su primer uso: muévela a la primera aparición.", doc.section_at(p), 40) for a, p in late[: max(0, MAX_COMMENTS - len(comments))]]
    names = ", ".join(a for a, _ in undefined[:20])
    evidence = f"{len(first_use)} siglas detectadas; {len(undefined)} sin definición localizable{': ' + names if names else ''}; {len(late)} definidas tarde."
    return ItemResult("N1", _status_by_count(len(undefined) + len(late), 1, 6), evidence, comments, ["regla"])


def _bibliography_entries(references: str) -> list[str]:
    body = re.sub(r"^\s*\S.*\n", "", references, count=1)  # quitar el encabezado
    if re.search(r"(?m)^\s*\[\d+\]", body):
        parts = re.split(r"(?m)^\s*(?=\[\d+\])", body)
    elif re.search(r"(?m)^\s*\d{1,3}\.\s+[A-ZÁÉÍÓÚÑ]", body):
        parts = re.split(r"(?m)^\s*(?=\d{1,3}\.\s+[A-ZÁÉÍÓÚÑ])", body)
    else:
        parts = re.split(r"(?m)^(?=[A-ZÁÉÍÓÚÑ][\w'´-]+,\s+[A-ZÁÉÍÓÚÑ])|\n\s*\n", body)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if len(p.strip()) > 15]


def _citations(doc: _Document) -> tuple[ItemResult, ItemResult, ItemResult]:
    references = doc.by_key.get("referencias", "")
    entries = _bibliography_entries(references) if references else []
    numeric = doc.body_matches(NUMERIC_CITE)
    author_year = doc.body_matches(AUTHOR_YEAR_CITE) + doc.body_matches(NARRATIVE_CITE)

    # R2 · formato
    issues, comments = [], []
    if len(numeric) >= 3 and len(author_year) >= 3:
        issues.append(f"se mezclan citas numéricas ({len(numeric)}) y autor-año ({len(author_year)})")
        comments.append(_comment(doc.text, numeric[0].start(), numeric[0].end(), "Cita numérica: comprueba que todo el documento usa el mismo estilo.", doc.section_at(numeric[0].start()), 30))
        comments.append(_comment(doc.text, author_year[0].start(), author_year[0].end(), "Cita autor-año: comprueba que todo el documento usa el mismo estilo.", doc.section_at(author_year[0].start()), 30))
    web_without_date = [e for e in entries if re.search(r"https?://|www\.", e) and not re.search(r"(?i)consult|accedido|acceso|accessed|visitad|recuperado|retrieved|disponible el", e)]
    if len(web_without_date) >= 2:
        issues.append(f"{len(web_without_date)} referencias web sin fecha de consulta")
    without_year = [e for e in entries if not re.search(r"\b(19|20)\d{2}\b", e)]
    if len(without_year) >= 2:
        issues.append(f"{len(without_year)} entradas sin año")
    if entries:
        r2 = ItemResult("R2", "por_revisar" if issues else "cumple", ("; ".join(issues).capitalize() + ".") if issues else f"{len(entries)} entradas con formato aparentemente homogéneo.", comments, ["regla"])
    else:
        r2 = ItemResult("R2", "no_evaluable", "No se ha podido leer la bibliografía.", sources=["regla"])

    # R3 · correspondencia
    if doc.words < 800:
        r3 = ItemResult("R3", "no_evaluable", "Borrador demasiado breve para comprobar citas.", sources=["regla"])
    elif not entries and not (numeric or author_year):
        r3 = ItemResult("R3", "no_cumple", "No se detectan ni citas en el texto ni bibliografía.", sources=["regla"])
    elif not entries:
        r3 = ItemResult("R3", "no_cumple", f"Hay {len(numeric) + len(author_year)} citas en el texto pero no se ha localizado la bibliografía.", sources=["regla"])
    elif not (numeric or author_year):
        r3 = ItemResult("R3", "no_cumple", f"La bibliografía tiene {len(entries)} entradas, pero no se detectan citas en el cuerpo del texto.", sources=["regla"])
    elif len(numeric) >= len(author_year):
        cited: set[int] = set()
        first_cite: dict[int, re.Match] = {}
        for match in numeric:
            for part in re.split(r"\s*,\s*", match.group(1)):
                bounds = [int(n) for n in re.split(r"\s*[–-]\s*", part) if n]
                numbers = range(bounds[0], bounds[-1] + 1) if len(bounds) == 2 and bounds[1] - bounds[0] < 30 else bounds
                for number in numbers:
                    cited.add(number)
                    first_cite.setdefault(number, match)
        numbered = [int(m.group(1)) for e in entries if (m := re.match(r"\[?(\d{1,3})[\].]", e))]
        available = set(numbered) if numbered else set(range(1, len(entries) + 1))
        missing = sorted(cited - available)
        uncited = sorted(available - cited)
        comments = [_comment(doc.text, first_cite[n].start(), first_cite[n].end(), f"La cita [{n}] no tiene entrada en la bibliografía.", doc.section_at(first_cite[n].start()), 30) for n in missing[:MAX_COMMENTS]]
        evidence = f"{len(cited)} referencias citadas, {len(available)} entradas. Citas sin entrada: {missing or 'ninguna'}. Entradas no citadas: {uncited or 'ninguna'}."
        r3 = ItemResult("R3", "no_cumple" if missing else "por_revisar" if uncited else "cumple", evidence, comments, ["regla"])
    else:
        body_norm = normalise(" ".join(doc.text[s.start:s.end] for s in doc.sections if s.key not in NON_BODY_SECTIONS) or doc.text)
        refs_norm = normalise(references)
        missing_cites = []
        for match in author_year:
            if normalise(match.group(1)) not in refs_norm and match.group(1) not in [m.group(1) for m in missing_cites]:
                missing_cites.append(match)
        uncited = [e[:80] for e in entries if (m := re.match(r"\[?\d*[\].]?\s*([A-ZÁÉÍÓÚÑ][\w'´-]+)", e)) and normalise(m.group(1)) not in body_norm]
        comments = [_comment(doc.text, m.start(), m.end(), f"No se encuentra «{m.group(1)}» en la bibliografía.", doc.section_at(m.start()), 30) for m in missing_cites[:MAX_COMMENTS]]
        evidence = f"{len(author_year)} citas autor-año y {len(entries)} entradas. Citas sin entrada: {len(missing_cites)}. Entradas posiblemente no citadas: {len(uncited)}{' (p. ej., ' + uncited[0] + '…)' if uncited else ''}."
        r3 = ItemResult("R3", "no_cumple" if missing_cites else "por_revisar" if uncited else "cumple", evidence, comments, ["regla"])

    # R4 · fuentes
    if len(entries) >= 3:
        academic = [e for e in entries if re.search(r"(?i)doi|isbn|issn|journal|proceedings|conference|congreso|revista|\bvol\.|\bpp\.|editorial|press|springer|ieee|acm|elsevier|arxiv|wiley|tesis|thesis", e)]
        web_only = [e for e in entries if re.search(r"https?://|www\.", e) and e not in academic]
        wiki = [e for e in entries if "wikipedia" in e.lower()]
        issues = []
        if len(web_only) / len(entries) > 0.6:
            issues.append(f"el {len(web_only) / len(entries):.0%} de las entradas son solo web")
        if wiki:
            issues.append(f"{len(wiki)} referencias a Wikipedia")
        evidence = f"{len(entries)} entradas: {len(academic)} académicas o editoriales, {len(web_only)} solo web."
        r4 = ItemResult("R4", "por_revisar" if issues else "cumple", evidence + (" " + "; ".join(issues).capitalize() + "." if issues else ""), sources=["regla"])
    else:
        r4 = ItemResult("R4", "por_revisar" if doc.words > 3000 else "no_evaluable", f"Solo se han identificado {len(entries)} entradas bibliográficas.", sources=["regla"])
    return r2, r3, r4


def _figures(doc: _Document) -> ItemResult:
    captions = [m for m in CAPTION.finditer(doc.text) if doc.in_body(m.start())]
    if not captions:
        return ItemResult("F1", "no_evaluable" if doc.words < 3000 else "por_revisar", "No se detectan pies de figura o tabla con el formato «Figura N» / «Tabla N».", sources=["regla"])
    caption_lines = {(m.start(), m.end()) for m in captions}
    mentions: Counter = Counter()
    for match in MENTION.finditer(doc.text):
        if not doc.in_body(match.start()) or any(s <= match.start() < e for s, e in caption_lines):
            continue
        mentions[(_kind(match.group(1)), match.group(2))] += 1
    comments, uncited, no_caption = [], [], []
    numbers: dict[str, list[str]] = {}
    for match in captions:
        kind, number, title = _kind(match.group(1)), match.group(2), match.group(3).strip()
        if not title:
            # En PDF el título del pie suele quedar en la línea siguiente.
            following = doc.text[match.end():].lstrip("\r\n").split("\n", 1)[0].strip()
            title = following if 0 < len(following) < 160 else ""
        numbers.setdefault(kind, []).append(number)
        if mentions[(kind, number)] == 0:
            uncited.append(f"{kind} {number}")
            comments.append(_comment(doc.text, match.start(), match.end(), f"La {kind} {number} no se menciona en el texto: refiérete a ella y explica qué muestra.", doc.section_at(match.start()), 0))
        if len(title) < 4:
            no_caption.append(f"{kind} {number}")
    gaps = []
    for kind, values in numbers.items():
        if all(v.isdigit() for v in values):
            sequence = [int(v) for v in values]
            expected = list(range(1, max(sequence) + 1))
            if sorted(set(sequence)) != expected:
                gaps.append(f"numeración de {kind}s no correlativa")
    issues = ([f"sin mención en el texto: {', '.join(uncited[:10])}"] if uncited else []) + ([f"sin pie descriptivo: {', '.join(no_caption[:10])}"] if no_caption else []) + gaps
    summary = ", ".join(f"{len(v)} {k}s" for k, v in numbers.items())
    return ItemResult("F1", "por_revisar" if issues else "cumple", f"Detectadas {summary}. " + ("; ".join(issues).capitalize() + "." if issues else "Todas se mencionan en el texto."), comments[:MAX_COMMENTS], ["regla"])


def _sensitive(doc: _Document) -> ItemResult:
    secrets = list(SECRET.finditer(doc.text))
    paths = list(LOCAL_PATH.finditer(doc.text))
    comments = [_comment(doc.text, m.start(), m.end(), "Posible credencial o clave: elimínala del documento (y revócala si es real).", doc.section_at(m.start()), 10) for m in secrets[:4]]
    comments += [_comment(doc.text, m.start(), m.end(), "Ruta local de tu equipo: puede revelar datos personales; sustitúyela por una ruta relativa.", doc.section_at(m.start()), 10) for m in paths[:4]]
    status = "no_cumple" if secrets else "por_revisar" if paths else "cumple"
    return ItemResult("P3", status, f"Posibles credenciales: {len(secrets)}; rutas locales: {len(paths)}.", comments, ["regla"])


def run_rules(text: str, sections: list[Section], checklist: Checklist) -> tuple[dict[str, ItemResult], dict]:
    doc = _Document(text, sections)
    balance, section_words = _chapter_balance(doc, checklist)
    r2, r3, r4 = _citations(doc)
    results = [
        _required_sections(doc, checklist), balance, _abstract(doc), _draft_leftovers(doc),
        _punctuation(doc), _long_sentences(doc), _register(doc), _filler(doc), _acronyms(doc),
        r2, r3, r4, _figures(doc), _sensitive(doc),
    ]
    known = {item.id for item in checklist.items}
    by_id = {result.id: result for result in results if result.id in known}
    metrics = {
        "word_count": doc.words,
        "section_words": section_words,
        "sections_found": [s.key for s in sections],
        "sections_missing": [key for key, spec in checklist.required_sections.items() if spec.get("required") and key not in {s.key for s in sections}],
    }
    return by_id, metrics
