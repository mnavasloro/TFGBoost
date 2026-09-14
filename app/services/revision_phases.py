"""Checklist de revisión por fases, basada en revision-tfg-prompts.md."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


COMMON_INSTRUCTIONS = """Vas a revisar un Trabajo de Fin de Grado. Trabaja solo sobre el fragmento recibido: no supongas contenido ni completes huecos. Para cada respuesta indica SÍ, NO o PARCIAL y aporta evidencia textual y su sección. Si no hay evidencia, responde NO o no verificable. Busca problemas activamente. No reescribas el texto: señala el problema y, como mucho, indica en una línea la dirección de la corrección. Clasifica los hallazgos como CRÍTICO, IMPORTANTE o MENOR. Responde únicamente a las preguntas de esta fase que puedan comprobarse con el fragmento."""


@dataclass(frozen=True)
class RevisionPhase:
    number: int
    title: str
    questions: tuple[str, ...]
    section_keys: tuple[str, ...]


PHASES = (
    RevisionPhase(1, "Planteamiento, estructura y coherencia", (
        "¿Se presenta con claridad el problema y por qué merece resolverse?",
        "¿Se introducen los conceptos antes de usarlos? Lista los términos dados por sabidos.",
        "¿Los objetivos son inequívocos? Enuméralos tal como aparecen.",
        "¿Cada objetivo tiene desarrollo y conclusión asociada? Marca los que no.",
        "¿Resumen, título y estructura reflejan el contenido, método y resultados reales?",
        "¿Hay saltos, solapamientos, secciones vacías, huérfanas, TODO o restos de borrador?",
        "¿Se distingue el marco tecnológico del estado del arte? Señala contenido en el capítulo equivocado.",
        "¿El detalle entre capítulos es equilibrado y las referencias cruzadas son correctas?",
    ), ("resumen", "indice", "introduccion", "objetivos", "estado_arte", "marco_tecnologico", "metodologia", "desarrollo", "resultados", "conclusiones")),
    RevisionPhase(2, "Método y resultados", (
        "¿Las decisiones técnicas están justificadas frente a alternativas obvias?",
        "¿Hay requisitos funcionales y no funcionales identificados y verificables?",
        "¿Cada requisito se traza hasta implementación y prueba?",
        "¿Se explica una metodología aplicada realmente en el trabajo?",
        "¿Existe evaluación con criterios explícitos y resultados comparados con el estado del arte?",
        "¿Se reconocen limitaciones y líneas futuras concretas?",
        "¿Distingue aportación propia de trabajo de terceros?",
        "¿Alguna conclusión afirma más de lo que sostienen los resultados?",
    ), ("objetivos", "requisitos", "metodologia", "desarrollo", "resultados", "estado_arte", "conclusiones")),
    RevisionPhase(3, "Fuentes y citas", (
        "Extrae citas y entradas bibliográficas y marca citas sin referencia o referencias sin citar.",
        "¿Qué afirmaciones, datos o comparativas necesitarían una referencia y no la tienen?",
        "¿El estilo, calidad, actualidad y fecha de consulta de las fuentes son adecuados?",
        "¿Figuras, tablas o código ajeno incluyen fuente y licencia?",
        "¿Hay pasajes sospechosos de copia o traducción sin atribución? Señálalos solo como sospecha a verificar.",
    ), ("resumen", "introduccion", "estado_arte", "marco_tecnologico", "metodologia", "desarrollo", "resultados", "conclusiones", "referencias")),
    RevisionPhase(4, "Figuras, tablas, fragmentos y anexos", (
        "Inventáría figuras, tablas, código y anexos; indica si están citados y lista los no citados.",
        "¿La numeración, pies, encabezados y leyendas son correlativos, consistentes y autónomos?",
        "¿Hay capturas ilegibles, decorativas, redundantes o con datos personales, credenciales o rutas locales?",
        "¿El código tiene formato consistente y contexto? ¿Los anexos están en el lugar correcto?",
    ), ("indice", "desarrollo", "resultados", "anexos")),
    RevisionPhase(5, "Redacción y terminología", (
        "Localiza faltas de ortografía, acentuación y puntuación con corrección.",
        "¿Los términos técnicos y acrónimos se explican en su primer uso y aparecen en el glosario?",
        "¿Se usa un término consistente por concepto, así como registro, persona gramatical, extranjerismos y tiempos verbales?",
        "Señala frases de más de 40 palabras, párrafos muy largos, muletillas, relleno y afirmaciones vacías.",
    ), ("resumen", "introduccion", "objetivos", "estado_arte", "marco_tecnologico", "metodologia", "desarrollo", "resultados", "conclusiones", "anexos")),
    RevisionPhase(6, "Requisitos formales y éticos", (
        "¿Se pueden verificar portada, extensión, tipografía, márgenes, interlineado y numeración? Si no, indica qué comprobar manualmente.",
        "¿Están las páginas preliminares, índices, resúmenes bilingües, palabras clave, licencia y declaración de IA exigibles?",
        "¿Se trata protección de datos, consentimiento y anonimización si hay usuarios o datos reales?",
        "¿Repositorio, anexos y software indican enlace accesible, licencia y ausencia de credenciales o datos sensibles?",
    ), ("portada", "resumen", "indice", "metodologia", "desarrollo", "anexos", "referencias")),
)

SECTION_ALIASES = {
    "portada": ("portada",), "resumen": ("resumen", "abstract"), "indice": ("indice", "tabla de contenidos"),
    "introduccion": ("introduccion",), "objetivos": ("objetivos", "objetivo"), "estado_arte": ("estado del arte", "trabajos relacionados"),
    "marco_tecnologico": ("marco tecnologico", "tecnologias", "herramientas"), "requisitos": ("requisitos",),
    "metodologia": ("metodologia", "metodo"), "desarrollo": ("desarrollo", "implementacion", "analisis", "diseno"),
    "resultados": ("resultados", "evaluacion", "experimentos", "validacion"), "conclusiones": ("conclusiones", "conclusion"),
    "referencias": ("referencias", "bibliografia"), "anexos": ("anexos", "anexo"),
}


def _normalise(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(char) != "Mn")


def _section_key(line: str) -> str | None:
    heading = re.sub(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+)?", "", _normalise(line)).strip(" .:-")
    if len(heading) > 100:
        return None
    for key, aliases in SECTION_ALIASES.items():
        if any(heading == alias or heading.startswith(f"{alias} ") for alias in aliases):
            return key
    return None


def split_sections(text: str) -> list[tuple[str, str]]:
    """Extract known thesis sections and split oversized ones for local inference."""
    lines = text.splitlines()
    headings = [(index, key) for index, line in enumerate(lines) if (key := _section_key(line))]
    if not headings:
        headings = [(0, "documento")]
    sections: list[tuple[str, str]] = []
    for position, (start, key) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        for chunk_number, offset in enumerate(range(0, len(content), 9_000), start=1):
            suffix = f" (parte {chunk_number})" if len(content) > 9_000 else ""
            sections.append((f"{key}{suffix}", content[offset:offset + 9_000]))
    return sections


def phase_tasks(text: str) -> list[dict[str, str | int]]:
    sections = split_sections(text)
    tasks: list[dict[str, str | int]] = []
    for phase in PHASES:
        selected = [(name, content) for name, content in sections if name.split(" (parte")[0] in phase.section_keys]
        if not selected:
            selected = sections[:1]
        question_block = "\n".join(f"{index}. {question}" for index, question in enumerate(phase.questions, start=1))
        for section_name, content in selected:
            tasks.append({"phase": phase.number, "phase_title": phase.title, "section": section_name, "questions": question_block, "content": content})
    return tasks
