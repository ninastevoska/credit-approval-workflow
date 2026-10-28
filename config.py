"""Central configuration for the credit application system."""

from pathlib import Path

# Root directory of the project.
BASE_DIR = Path(__file__).resolve().parent

# Directory for persistent application data.
DATA_DIR = BASE_DIR / "data"

# SQLite database location.
DATABASE_PATH = DATA_DIR / "iup.db"

# Directory for uploaded PDF documents.
UPLOAD_DIR = DATA_DIR / "uploads"

# Default location of the exported event log.
EVENT_LOG_EXPORT_PATH = BASE_DIR / "dnevnik.csv"

# Business rule from the conceptual process (Assignment 3).
# Applications above this amount require manager approval.
REFERENT_APPROVAL_LIMIT = 20_000

# Maximum allowed PDF size: 10 MiB.
# This is our implementation limit, not an assignment requirement.
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024

# Allowed file extension.
ALLOWED_DOCUMENT_EXTENSION = ".pdf"


def ensure_directories() -> None:
    """Create directories required for persistent data and uploads."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
