"""Integration tests for PDF uploads and application submission."""

from decimal import Decimal

import pytest

from database import initialize_database
from models import User, UserRole
from services.application_service import (
    get_application_events,
    list_applications,
    submit_application_with_pdf,
)
from services.file_service import get_pdf_path, read_pdf


SAMPLE_PDF = b"%PDF-1.4\nTest content\n%%EOF"


@pytest.fixture
def environment(tmp_path):
    """Create an isolated database and upload directory."""
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"

    initialize_database(db_path)

    return db_path, upload_dir


def test_successful_submission_with_pdf(environment):
    """Submitting a valid PDF creates the application and events."""
    db_path, upload_dir = environment
    customer = User("miha.p", UserRole.CUSTOMER)

    application = submit_application_with_pdf(
        customer=customer,
        requested_amount=Decimal("10000"),
        loan_purpose="nakup_vozila",
        pdf_filename="dokazilo.pdf",
        pdf_content=SAMPLE_PDF,
        db_path=db_path,
        upload_dir=upload_dir,
    )

    assert application.case_id == "K-001"
    assert application.status.value == "preverjena"

    assert read_pdf(application.pdf_path, upload_dir) == SAMPLE_PDF

    events = get_application_events(application.case_id, db_path)

    assert len(events) == 2
    assert all(
        event.pdf_path == application.pdf_path
        for event in events
    )


def test_failed_submission_removes_uploaded_pdf(environment):
    """An invalid application must not leave an orphan PDF."""
    db_path, upload_dir = environment
    customer = User("miha.p", UserRole.CUSTOMER)

    with pytest.raises(ValueError):
        submit_application_with_pdf(
            customer=customer,
            requested_amount=Decimal("-100"),
            loan_purpose="nakup_vozila",
            pdf_filename="dokazilo.pdf",
            pdf_content=SAMPLE_PDF,
            db_path=db_path,
            upload_dir=upload_dir,
        )

    assert list_applications(db_path) == []
    assert list(upload_dir.iterdir()) == []


def test_invalid_pdf_does_not_create_application(environment):
    """An invalid PDF must be rejected before database changes."""
    db_path, upload_dir = environment
    customer = User("miha.p", UserRole.CUSTOMER)

    with pytest.raises(ValueError):
        submit_application_with_pdf(
            customer=customer,
            requested_amount=Decimal("10000"),
            loan_purpose="nakup_vozila",
            pdf_filename="invalid.pdf",
            pdf_content=b"Not a PDF",
            db_path=db_path,
            upload_dir=upload_dir,
        )

    assert list_applications(db_path) == []
    assert not upload_dir.exists() or not list(upload_dir.iterdir())
