"""Extraction and chunking, without a database."""

import pytest

from app.ai.embeddings import EMBEDDING_DIMENSIONS, fake_vector
from app.modules.knowledge.extract import (
    CHUNK_TARGET,
    MAX_FILE_BYTES,
    InvalidDocumentError,
    Page,
    chunk,
    clean,
    extract,
)
from app.modules.knowledge.models import CHUNK_MAX_LENGTH, DocumentFormat
from tests.modules.knowledge.pdfs import make_pdf


def test_pdf_text_keeps_its_page_numbers() -> None:
    data = make_pdf([["Brass pendants need a dry cloth."], ["Gozo deliveries take two days."]])
    extracted = extract("care-guide.PDF", data)
    assert extracted.format is DocumentFormat.PDF
    assert extracted.page_count == 2
    assert [p.number for p in extracted.pages] == [1, 2]
    assert "Gozo deliveries" in extracted.pages[1].text


def test_blank_pages_are_skipped_and_a_scanned_pdf_is_refused() -> None:
    extracted = extract("a.pdf", make_pdf([[], ["Only page two has text."]]))
    assert [p.number for p in extracted.pages] == [2]
    with pytest.raises(InvalidDocumentError, match="No text found"):
        extract("scan.pdf", make_pdf([[], []]))


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [
        ("notes.docx", b"PK\x03\x04", "Upload a PDF"),
        ("notes.txt", b"", "empty"),
        ("notes.txt", b"\xff\xfe\x00bad", "UTF-8"),
        ("fake.pdf", b"not a pdf at all", "not a PDF"),
        ("broken.pdf", b"%PDF-1.7\n garbage", "could not be read"),
        ("big.txt", b"a" * (MAX_FILE_BYTES + 1), "5 MB"),
        ("long.txt", ("word " * 50_000).encode(), "200,000"),
    ],
)
def test_unusable_files_are_refused_with_a_reason(filename: str, data: bytes, message: str) -> None:
    with pytest.raises(InvalidDocumentError, match=message):
        extract(filename, data)


def test_text_is_cleaned_of_control_characters_and_extra_space() -> None:
    assert clean("Hello\x00  world\r\n\r\n\r\n\tNext\x07") == "Hello world\n\nNext"


def test_markdown_and_text_files_have_no_pages() -> None:
    extracted = extract("faq.md", b"# Returns\n\nWithin 14 days.")
    assert extracted.format is DocumentFormat.MARKDOWN
    assert extracted.page_count is None
    assert extracted.pages == [Page(None, "# Returns\n\nWithin 14 days.")]


def test_chunks_stay_within_bounds_overlap_and_never_span_pages() -> None:
    paragraph = " ".join(f"Sentence {i} about lamp wiring and fittings." for i in range(60))
    pages = [Page(1, "\n\n".join([paragraph] * 4)), Page(2, "Short final page.")]
    chunks = chunk(pages)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(0 < len(c.content) <= CHUNK_MAX_LENGTH for c in chunks)
    assert all(len(c.content) <= CHUNK_TARGET + 500 for c in chunks)
    assert chunks[-1].page == 2
    assert chunks[-1].content == "Short final page."
    first, second = chunks[0].content, chunks[1].content
    assert first[-100:].split(" ", 1)[1] in second  # consecutive chunks overlap


def test_a_paragraph_without_breaks_is_split_by_words() -> None:
    chunks = chunk([Page(None, "x" * 50 + " " + "word " * 3000)])
    assert len(chunks) > 3
    assert all(len(c.content) <= CHUNK_MAX_LENGTH for c in chunks)


def test_chunking_is_deterministic() -> None:
    pages = [Page(1, "One.\n\nTwo.\n\n" + "Three. " * 900)]
    assert chunk(pages) == chunk(pages)


def test_fake_vectors_are_normalised_and_similar_for_shared_words() -> None:
    a, b, c = (
        fake_vector("brass pendant care"),
        fake_vector("pendant care brass"),
        fake_vector("menu tasting"),
    )
    assert len(a) == EMBEDDING_DIMENSIONS
    assert abs(sum(v * v for v in a) - 1) < 1e-9
    assert sum(x * y for x, y in zip(a, b, strict=True)) > 0.99
    assert abs(sum(x * y for x, y in zip(a, c, strict=True))) < 0.5
    assert fake_vector("")[0] == 1.0
