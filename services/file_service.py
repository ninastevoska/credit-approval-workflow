"""Storage and basic validation of uploaded PDF documents.

Responsibilities:
- Validate file names, sizes, and basic PDF signatures.
- Save documents under unique, generated names.
- Resolve stored references without allowing path traversal.
- Read stored PDFs and clean up failed uploads.

PDF content extraction is outside the scope of Assignment 4.
"""

from pathlib import Path
from uuid import uuid4

from config import (
    ALLOWED_DOCUMENT_EXTENSION,
    BASE_DIR,
    MAX_PDF_SIZE_BYTES,
    UPLOAD_DIR,
)


class FileStorageError(ValueError):
    """Raised when a PDF is invalid or cannot be accessed safely."""


def _resolve_upload_directory(upload_dir: Path) -> Path:
    """Return an absolute, existing upload directory."""
    directory = Path(upload_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_pdf(filename: str, content: bytes) -> None:
    """Check the original filename, file size, and PDF header."""
    if not filename or Path(filename).name != filename:
        raise FileStorageError("Invalid document filename.")

    if Path(filename).suffix.lower() != ALLOWED_DOCUMENT_EXTENSION:
        raise FileStorageError("Only PDF documents are allowed.")

    if not isinstance(content, bytes):
        raise FileStorageError("Document content must be bytes.")

    if not content:
        raise FileStorageError("The uploaded document is empty.")

    if len(content) > MAX_PDF_SIZE_BYTES:
        raise FileStorageError("PDF exceeds the maximum allowed size.")

    if not content.startswith(b"%PDF-"):
        raise FileStorageError("The file does not have a valid PDF header.")


def save_pdf(
    filename: str,
    content: bytes,
    upload_dir: Path = UPLOAD_DIR,
) -> str:
    """Validate and save a PDF under a unique filename.

    Returns a relative reference such as:
        data/uploads/<generated-id>.pdf

    The original filename is validated but not used for storage.
    """
    _validate_pdf(filename, content)

    directory = _resolve_upload_directory(upload_dir)

    # Random identifiers prevent name collisions and avoid exposing
    # customer-provided filenames in storage paths.
    stored_name = f"{uuid4().hex}.pdf"
    destination = directory / stored_name

    # Exclusive creation prevents accidental overwriting.
    try:
        with destination.open("xb") as file:
            file.write(content)
    except OSError:
        # Remove a partially written document if necessary.
        destination.unlink(missing_ok=True)
        raise

    return (Path("data") / "uploads" / stored_name).as_posix()


def get_pdf_path(
    reference: str,
    upload_dir: Path = UPLOAD_DIR,
) -> Path:
    """Resolve a stored PDF reference within the upload directory.

    Only generated PDF names are accepted. The resulting path must
    remain inside the configured upload directory.
    """
    if not reference:
        raise FileStorageError("Document reference is required.")

    reference_path = Path(reference)

    expected_prefix = Path("data") / "uploads"

    if reference_path.parent != expected_prefix:
        raise FileStorageError("Invalid PDF storage reference.")

    filename = reference_path.name

    if len(filename) != 36 or not filename.endswith(".pdf"):
        raise FileStorageError("Invalid stored PDF filename.")

    try:
        int(filename[:-4], 16)
    except ValueError as exc:
        raise FileStorageError("Invalid stored PDF identifier.") from exc

    directory = Path(upload_dir).resolve()
    destination = (directory / filename).resolve()

    if destination.parent != directory:
        raise FileStorageError("Document path is outside upload directory.")

    return destination


def read_pdf(
    reference: str,
    upload_dir: Path = UPLOAD_DIR,
) -> bytes:
    """Read a previously stored PDF."""
    path = get_pdf_path(reference, upload_dir)

    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise FileStorageError("PDF document was not found.") from exc


def delete_pdf(
    reference: str,
    upload_dir: Path = UPLOAD_DIR,
) -> None:
    """Delete an uploaded PDF when an application submission fails.

    This is intended only for cleaning up unsuccessful submissions,
    not for deleting documents belonging to committed applications.
    """
    path = get_pdf_path(reference, upload_dir)
    path.unlink(missing_ok=True)
