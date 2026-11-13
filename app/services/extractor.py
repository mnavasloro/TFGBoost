from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path


class UnsupportedDocument(ValueError):
    pass


class TextExtractionError(ValueError):
    """The file was accepted but readable text could not be obtained."""
    pass


@dataclass
class ExtractedDocument:
    text: str
    # Encabezados conocidos por el estilo del documento (DOCX). Vacío si no se sabe.
    headings: list[str] = field(default_factory=list)


def _docx(content: bytes) -> ExtractedDocument:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as error:
        raise TextExtractionError("Falta el lector de DOCX. Instala las dependencias del proyecto con «pip install -r requirements.txt».") from error
    try:
        document = Document(BytesIO(content))
        lines, headings = [], []
        # Párrafos y tablas en orden de aparición (las tablas incluyen glosarios y resultados).
        for element in document.element.body.iterchildren():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "p":
                paragraph = Paragraph(element, document)
                text = paragraph.text.strip()
                style = (paragraph.style.name if paragraph.style is not None else "") or ""
                if text and (style.startswith(("Heading", "Título", "Titulo")) or style == "Title"):
                    headings.append(text)
                lines.append(paragraph.text)
            elif tag == "tbl":
                for row in Table(element, document).rows:
                    cells = []
                    for cell in row.cells:
                        value = " ".join(cell.text.split())
                        if value and (not cells or cells[-1] != value):  # celdas combinadas se repiten
                            cells.append(value)
                    if cells:
                        lines.append(" | ".join(cells))
                lines.append("")
        return ExtractedDocument("\n".join(lines), headings)
    except Exception as error:
        raise TextExtractionError("No se ha podido abrir este DOCX. Comprueba que el archivo no esté dañado.") from error


def _pdf(content: bytes) -> ExtractedDocument:
    # PyMuPDF es más rápido y tolerante; pypdf queda como alternativa ligera.
    try:
        import fitz
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise TextExtractionError("Falta un lector de PDF. Instala las dependencias del proyecto con «pip install -r requirements.txt».") from error
        try:
            reader = PdfReader(BytesIO(content))
            return ExtractedDocument("\n".join(page.extract_text() or "" for page in reader.pages))
        except Exception as error:
            raise TextExtractionError("No se ha podido abrir este PDF. Comprueba que no esté dañado, cifrado o protegido.") from error
    try:
        with fitz.open(stream=content, filetype="pdf") as document:
            headings = [entry[1].strip() for entry in document.get_toc(simple=True) if entry[1].strip()]
            return ExtractedDocument("\n".join(page.get_text("text") for page in document), headings)
    except Exception as error:
        raise TextExtractionError("No se ha podido abrir este PDF. Comprueba que no esté dañado, cifrado o protegido.") from error


def extract_document(filename: str, content: bytes) -> ExtractedDocument:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return _pdf(content)
    if extension == ".docx":
        return _docx(content)
    raise UnsupportedDocument("Solo se admiten documentos PDF y DOCX.")


def extract_text(filename: str, content: bytes) -> str:
    return extract_document(filename, content).text
