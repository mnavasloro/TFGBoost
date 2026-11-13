"""Detección de capítulos de la memoria a partir del texto extraído."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PREFIX = re.compile(r"^\s*(?:cap[ií]tulo\s+[\divxlc]+\s*[.:\-–]?\s*)?(?:\d+(?:\.\d+)*[.)]?\s+)?", re.IGNORECASE)
_TOC_LINE = re.compile(r"(\.{3,}|…{2,}|\s\d{1,3}$)")
WORD = re.compile(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ'-]+\b")


def normalise(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(char) != "Mn")


def word_count(text: str) -> int:
    return len(WORD.findall(text))


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    start: int  # desplazamiento (en caracteres) del encabezado en el texto completo
    end: int

    def text(self, document: str) -> str:
        return document[self.start:self.end]


def heading_text(line: str) -> str:
    """Encabezado normalizado sin numeración: «1.3. Objetivos del TFG» -> «objetivos del tfg»."""
    return _PREFIX.sub("", normalise(line.strip())).strip(" .:-–")


# Páginas preliminares y finales: a menudo sin estilo de título, pero con un
# encabezado inequívoco. Se aceptan aunque el documento declare sus encabezados.
UNSTYLED_KEYS = {"portada", "resumen", "abstract", "indice", "glosario", "referencias", "anexos"}
# Solo coincidencia exacta: «Resumen de la pila tecnológica» no es el resumen.
EXACT_KEYS = {"portada", "resumen", "abstract", "indice"}
_ANNEX = re.compile(r"^(anexo|apendice)\s+[a-z0-9ivx]{1,4}\b")


def _heading_key(line: str, aliases: dict[str, tuple[str, ...]]) -> tuple[str, bool] | None:
    """(clave, coincidencia exacta) del capítulo que encabeza la línea, si lo hay."""
    stripped = line.strip()
    if not stripped or len(stripped) > 90 or _TOC_LINE.search(stripped) or "http" in stripped:
        return None
    heading = heading_text(stripped)
    if not heading:
        return None
    if _ANNEX.match(heading) and "anexos" in aliases:
        return "anexos", True
    original = _PREFIX.sub("", stripped)
    words = heading.split()
    best: tuple[int, str, bool] | None = None
    for key, names in aliases.items():
        for alias in names:
            exact = heading == alias
            # «Conclusiones y trabajo futuro» sí; una línea de párrafo que empieza
            # por «Resultados de…» o «Arquitectura general: …» no.
            prefix = key not in EXACT_KEYS and (heading.startswith(alias + " ") or heading.startswith(alias + "(")) and len(words) <= 8 \
                and not stripped.endswith((".", ",")) and ":" not in heading and original[:1].isupper()
            # Se prefiere el alias más largo: «Objetivos de Desarrollo Sostenible» es impacto, no objetivos.
            if (exact or prefix) and (best is None or len(alias) > best[0]):
                best = (len(alias), key, exact)
    return (best[1], best[2]) if best else None


def find_sections(text: str, required_sections: dict[str, dict], known_headings: list[str] | None = None) -> list[Section]:
    """Capítulos reconocidos. Si el documento declara sus encabezados (estilos de
    DOCX o marcadores del PDF), solo se consideran esas líneas, salvo las páginas
    preliminares y finales con encabezado exacto."""
    aliases = {key: tuple(normalise(a) for a in spec["aliases"]) for key, spec in required_sections.items()}
    allowed = {heading_text(h) for h in known_headings or [] if heading_text(h)}
    # Si los encabezados declarados no incluyen ningún capítulo reconocible, se ignoran.
    if allowed and not any(_heading_key(h, aliases) for h in known_headings or []):
        allowed = set()
    headings: list[tuple[int, str, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        match = _heading_key(line, aliases)
        key = match[0] if match else None
        if key and allowed and heading_text(line) not in allowed and not (key in UNSTYLED_KEYS and match[1]):
            key = None
        if key:
            headings.append((offset, key, line.strip()))
        offset += len(line)
    sections = [
        Section(key, heading, start, headings[i + 1][0] if i + 1 < len(headings) else len(text))
        for i, (start, key, heading) in enumerate(headings)
    ]
    # Las entradas del índice generan encabezados casi vacíos: si el mismo
    # capítulo aparece más adelante con contenido, se descarta la entrada vacía.
    kept: list[Section] = []
    for index, section in enumerate(sections):
        body_words = word_count(section.text(text)) - word_count(section.heading)
        has_later_twin = any(other.key == section.key for other in sections[index + 1:])
        if body_words < 15 and has_later_twin:
            continue
        kept.append(section)
    # Si se descartan entradas, el capítulo anterior absorbe su rango.
    merged = [Section(s.key, s.heading, s.start, kept[i + 1].start if i + 1 < len(kept) else len(text)) for i, s in enumerate(kept)]
    return merged


def section_texts(text: str, sections: list[Section]) -> dict[str, str]:
    """Texto concatenado por clave (un capítulo puede tener varios bloques)."""
    result: dict[str, str] = {}
    for section in sections:
        result[section.key] = (result.get(section.key, "") + "\n" + section.text(text)).strip()
    return result


@dataclass(frozen=True)
class Chunk:
    label: str
    text: str
    start: int


def chunk_sections(text: str, sections: list[Section], keys: tuple[str, ...], max_chars: int) -> list[Chunk]:
    """Fragmentos de las secciones pedidas, partidos por párrafos hasta `max_chars`.

    Si no se reconoce ningún encabezado, se trocea el documento completo
    (clave "documento").
    """
    selected = [s for s in sections if s.key in keys]
    if not selected:
        if sections or "documento" not in keys:
            return []
        selected = [Section("documento", "", 0, len(text))]
    chunks: list[Chunk] = []
    for section in selected:
        body = section.text(text)
        if len(body) <= max_chars:
            chunks.append(Chunk(section.key, body, section.start))
            continue
        part, part_start, number = "", 0, 1
        for match in re.finditer(r"[^\n]*(?:\n|$)", body):
            paragraph = match.group(0)
            if not paragraph:
                break
            if part and len(part) + len(paragraph) > max_chars:
                chunks.append(Chunk(f"{section.key} (parte {number})", part, section.start + part_start))
                number, part, part_start = number + 1, "", match.start()
            if not part:
                part_start = match.start()
            # Un único párrafo gigantesco (PDF sin saltos) se corta en seco.
            while len(paragraph) > max_chars:
                chunks.append(Chunk(f"{section.key} (parte {number})", paragraph[:max_chars], section.start + match.start()))
                number, paragraph = number + 1, paragraph[max_chars:]
            part += paragraph
        if part.strip():
            chunks.append(Chunk(f"{section.key} (parte {number})" if number > 1 else section.key, part, section.start + part_start))
    return chunks
