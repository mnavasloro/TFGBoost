from __future__ import annotations

from io import BytesIO
from pathlib import Path


class UnsupportedDocument(ValueError):
    pass


class TextExtractionError(ValueError):
    """The file was accepted but readable text could not be obtained."""
    pass


def extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        # PyMuPDF is faster and considerably more tolerant of real-world PDFs.
        # Keep pypdf as a fallback so this remains usable in lightweight installs.
        try:
            import fitz
            with fitz.open(stream=content, filetype="pdf") as document:
                return "\n".join(page.get_text("text") for page in document)
        except ImportError:
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(content))
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError as error:
                raise TextExtractionError("Falta un lector de PDF. Instala las dependencias del proyecto con «pip install -r requirements.txt».") from error
            except Exception as error:
                raise TextExtractionError("No se ha podido abrir este PDF. Comprueba que no esté dañado, cifrado o protegido.") from error
        except Exception as error:
            raise TextExtractionError("No se ha podido abrir este PDF. Comprueba que no esté dañado, cifrado o protegido.") from error
    if extension == ".docx":
        try:
            from docx import Document
        except ImportError as error:
            raise TextExtractionError("Falta el lector de DOCX. Instala las dependencias del proyecto con «pip install -r requirements.txt».") from error
        try:
            document = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as error:
            raise TextExtractionError("No se ha podido abrir este DOCX. Comprueba que el archivo no esté dañado.") from error
    raise UnsupportedDocument("Solo se admiten documentos PDF y DOCX.")
