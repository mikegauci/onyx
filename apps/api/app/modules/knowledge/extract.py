"""Text extraction and chunking. Pure functions: no database, no network.

Uploaded bytes are untrusted. PDFs are read with ``pypdf`` (no JavaScript, forms or embedded
files are executed or followed); text files must be UTF-8. Only the text is kept.
"""

import io
import re
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import ErrorDetail, ValidationFailedError
from app.modules.knowledge.models import CHUNK_MAX_LENGTH, DocumentFormat

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 100
MAX_CHARACTERS = 200_000

# About 800 tokens per chunk with 100 tokens of overlap (~4 characters per token).
CHUNK_TARGET = 3200
CHUNK_OVERLAP = 400

_EXTENSIONS = {
    ".pdf": DocumentFormat.PDF,
    ".txt": DocumentFormat.TEXT,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}
_SPACES = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class InvalidDocumentError(ValidationFailedError):
    """The file cannot be indexed. The message says why, never what the file contains."""

    def __init__(self, message: str, field: str = "content_base64") -> None:
        super().__init__(
            message, details=[ErrorDetail(loc=["body", field], msg=message, type="invalid")]
        )


@dataclass(frozen=True)
class Page:
    number: int | None  # 1-based for PDFs; None for text files
    text: str


@dataclass(frozen=True)
class Extracted:
    format: DocumentFormat
    pages: list[Page]
    page_count: int | None

    @property
    def character_count(self) -> int:
        return sum(len(p.text) for p in self.pages)


@dataclass(frozen=True)
class ChunkText:
    ordinal: int
    page: int | None
    content: str


def format_for(filename: str) -> DocumentFormat:
    lower = filename.lower()
    for extension, kind in _EXTENSIONS.items():
        if lower.endswith(extension):
            return kind
    raise InvalidDocumentError("Upload a PDF, .txt or .md file.", field="filename")


def clean(text: str) -> str:
    """Normalise Unicode and whitespace; drop control characters (NUL breaks PostgreSQL)."""
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c)[0] != "C")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def extract(filename: str, data: bytes) -> Extracted:
    if not data:
        raise InvalidDocumentError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise InvalidDocumentError("Files can be at most 5 MB.")
    kind = format_for(filename)
    if kind is DocumentFormat.PDF:
        extracted = _pdf(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidDocumentError("Text files must be UTF-8.") from exc
        extracted = Extracted(kind, [Page(None, clean(text))], None)
    pages = [p for p in extracted.pages if p.text]
    if not pages:
        raise InvalidDocumentError(
            "No text found. Scanned documents need text recognition, which is not supported."
        )
    result = Extracted(extracted.format, pages, extracted.page_count)
    if result.character_count > MAX_CHARACTERS:
        raise InvalidDocumentError("Documents can hold at most 200,000 characters of text.")
    return result


def _pdf(data: bytes) -> Extracted:
    if not data.startswith(b"%PDF-"):
        raise InvalidDocumentError("The file is not a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InvalidDocumentError("Password-protected PDFs cannot be indexed.")
        count = len(reader.pages)
        if count > MAX_PAGES:
            raise InvalidDocumentError("PDFs can have at most 100 pages.")
        pages = [
            Page(i + 1, clean(page.extract_text() or "")) for i, page in enumerate(reader.pages)
        ]
    except InvalidDocumentError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise InvalidDocumentError("The PDF could not be read.") from exc
    return Extracted(DocumentFormat.PDF, pages, count)


def chunk(pages: list[Page]) -> list[ChunkText]:
    """Split each page into overlapping passages of about ``CHUNK_TARGET`` characters.

    Passages never span pages, so every citation names one page. Splits prefer paragraph, then
    sentence, then word boundaries. Deterministic: the same text gives the same chunks.
    """
    chunks: list[ChunkText] = []
    for page in pages:
        for piece in _split(page.text):
            chunks.append(ChunkText(len(chunks), page.number, piece))
    return chunks


def _split(text: str) -> list[str]:
    units = _units(text)
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= CHUNK_TARGET:
            current = candidate
            continue
        if current:
            pieces.append(current)
            tail = current[-CHUNK_OVERLAP:]
            space = tail.find(" ")
            tail = tail[space + 1 :] if space != -1 else tail
            current = f"{tail} {unit}" if len(tail) + len(unit) < CHUNK_TARGET else unit
        else:
            current = unit
    if current:
        pieces.append(current)
    return [p[:CHUNK_MAX_LENGTH] for p in pieces]


def _units(text: str) -> list[str]:
    """Paragraphs, with any paragraph longer than a chunk broken into sentences or words."""
    units: list[str] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) <= CHUNK_TARGET:
            units.append(paragraph)
            continue
        for sentence in _SENTENCE_END.split(paragraph):
            while len(sentence) > CHUNK_TARGET:
                cut = sentence.rfind(" ", 0, CHUNK_TARGET)
                cut = cut if cut > 0 else CHUNK_TARGET
                units.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                units.append(sentence)
    return units
