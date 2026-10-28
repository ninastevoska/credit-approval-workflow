"""Integration tests for failures during automatic verification."""

from decimal import Decimal

import pytest

from database import get_connection, initialize_database
from models import User, UserRole
from services.application_service import (
    list_applications,
    submit_application,
    submit_application_with_pdf,
)
from services.verification_service import ApplicationVerificationError


@pytest.fixture
def environment(tmp_path):
    """Create an isolated database and upload directory."""
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"

    initialize_database(db_path)
    return db_path, upload_dir


def reject_verification(application):
    """Simulate an unexpected failure during automatic checking."""
    raise ApplicationVerificationError(
        "Simulated automatic verification failure."
    )


def test_verification_failure_rolls_back_database(
    environment, monkeypatch
):
    """No application or event may remain after verification fails."""
    db_path, _ = environment

    monkeypatch.setattr(
        "services.application_service.verify_application_data",
        reject_verification,
    )

    customer = User("test.customer", UserRole.CUSTOMER)

    with pytest.raises(ApplicationVerificationError):
        submit_application(
            customer=customer,
            requested_amount=Decimal("10000"),
            loan_purpose="Testni kredit",
            pdf_path="data/uploads/test.pdf",
            db_path=db_path,
        )

    assert list_applications(db_path) == []

    with get_connection(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM process_events"
        ).fetchone()[0]

    assert count == 0


def test_verification_failure_removes_uploaded_pdf(
    environment, monkeypatch
):
    """Failed verification must also clean up the new PDF."""
    db_path, upload_dir = environment

    monkeypatch.setattr(
        "services.application_service.verify_application_data",
        reject_verification,
    )

    customer = User("test.customer", UserRole.CUSTOMER)

    pdf_content = b"%PDF-1.4\nTest document\n%%EOF"

    with pytest.raises(ApplicationVerificationError):
        submit_application_with_pdf(
            customer=customer,
            requested_amount=Decimal("10000"),
            loan_purpose="Testni kredit",
            pdf_filename="dokazilo.pdf",
            pdf_content=pdf_content,
            db_path=db_path,
            upload_dir=upload_dir,
        )

    assert list_applications(db_path) == []
    assert list(upload_dir.iterdir()) == []
