"""Tests for PDF validation and storage.

All documents are created in isolated temporary directories.
No actual application uploads are modified.
"""

from pathlib import Path

import pytest

from services.file_service import (
    FileStorageError,
    delete_pdf,
    get_pdf_path,
    read_pdf,
    save_pdf,
)


# Minimal PDF-like bytes for testing the basic file signature.
# These are intentionally not a complete readable PDF.
SAMPLE_PDF = b"%PDF-1.4\nTest PDF content\n%%EOF"


@pytest.fixture
def upload_dir(tmp_path):
    """Provide an isolated upload directory."""
    return tmp_path / "uploads"


def test_save_pdf_creates_file(upload_dir):
    """A valid PDF should be stored with a generated filename."""
    reference = save_pdf(
        "proof.pdf",
        SAMPLE_PDF,
        upload_dir=upload_dir,
    )

    path = get_pdf_path(reference, upload_dir)

    assert path.exists()
    assert path.read_bytes() == SAMPLE_PDF
    assert reference.startswith("data/uploads/")
    assert reference.endswith(".pdf")
    assert path.name != "proof.pdf"


def test_read_pdf_returns_original_content(upload_dir):
    """Reading a stored PDF must preserve its original bytes."""
    reference = save_pdf(
        "document.pdf",
        SAMPLE_PDF,
        upload_dir=upload_dir,
    )

    assert read_pdf(reference, upload_dir) == SAMPLE_PDF


def test_duplicate_filenames_do_not_overwrite(upload_dir):
    """Two uploads with the same original name must remain separate."""
    first = save_pdf("proof.pdf", SAMPLE_PDF, upload_dir)
    second = save_pdf("proof.pdf", SAMPLE_PDF, upload_dir)

    assert first != second
    assert get_pdf_path(first, upload_dir).exists()
    assert get_pdf_path(second, upload_dir).exists()


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("document.txt", SAMPLE_PDF),
        ("document.pdf", b"Not a PDF"),
        ("document.pdf", b""),
        ("", SAMPLE_PDF),
        ("../document.pdf", SAMPLE_PDF),
    ],
)
def test_invalid_uploads_are_rejected(
    upload_dir, filename, content
):
    """Invalid files must not be stored."""
    with pytest.raises(FileStorageError):
        save_pdf(filename, content, upload_dir)

    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_oversized_pdf_is_rejected(upload_dir, monkeypatch):
    """Files exceeding the configured limit must be rejected."""
    import services.file_service as file_service

    monkeypatch.setattr(file_service, "MAX_PDF_SIZE_BYTES", 10)

    with pytest.raises(FileStorageError):
        save_pdf("large.pdf", SAMPLE_PDF, upload_dir)


@pytest.mark.parametrize(
    "reference",
    [
        "../secret.pdf",
        "data/uploads/../secret.pdf",
        "data/uploads/document.pdf",
        "data/uploads/not-a-valid-id.pdf",
        "other/folder/document.pdf",
    ],
)
def test_invalid_references_are_rejected(upload_dir, reference):
    """Untrusted references must not escape the upload directory."""
    with pytest.raises(FileStorageError):
        get_pdf_path(reference, upload_dir)


def test_delete_pdf_removes_document(upload_dir):
    """A failed submission's uploaded file can be removed."""
    reference = save_pdf("proof.pdf", SAMPLE_PDF, upload_dir)
    path = get_pdf_path(reference, upload_dir)

    assert path.exists()

    delete_pdf(reference, upload_dir)

    assert not path.exists()


def test_missing_document_cannot_be_read(upload_dir):
    """Reading an absent stored document should raise a clear error."""
    reference = save_pdf("proof.pdf", SAMPLE_PDF, upload_dir)
    delete_pdf(reference, upload_dir)

    with pytest.raises(FileStorageError):
        read_pdf(reference, upload_dir)


def test_saved_document_uses_pdf_extension(upload_dir):
    """All stored documents must use the PDF extension."""
    reference = save_pdf("UPPER.PDF", SAMPLE_PDF, upload_dir)

    path = get_pdf_path(reference, upload_dir)

    assert isinstance(path, Path)
    assert path.suffix == ".pdf"
