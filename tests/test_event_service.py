"""Tests for event creation, persistence, and CSV export."""

import csv
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from database import get_connection, initialize_database
from models import (
    ApplicationStatus,
    CreditApplication,
    UserRole,
)
from services.event_service import (
    EVENT_LOG_COLUMNS,
    append_event,
    create_event,
    export_event_log,
)
from services.workflow_service import get_transition


@pytest.fixture
def test_db(tmp_path):
    """Create an isolated database for each test."""
    path = tmp_path / "events.db"
    initialize_database(path)
    return path


@pytest.fixture
def application():
    """Provide a credit application after submission."""
    return CreditApplication(
        case_id="K-001",
        customer_id="miha.p",
        requested_amount=Decimal("10000"),
        loan_purpose="nakup_vozila",
        pdf_path="uploads/proof.pdf",
        status=ApplicationStatus.SUBMITTED,
        current_step="verify_application",
        created_at=datetime(2026, 11, 3, 9, 0),
    )


def save_application(connection, application):
    """Insert the parent application into the database."""
    connection.execute(
        """
        INSERT INTO credit_applications (
            case_id, customer_id, requested_amount,
            loan_purpose, pdf_path, status,
            current_step, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application.case_id,
            application.customer_id,
            str(application.requested_amount),
            application.loan_purpose,
            application.pdf_path,
            application.status.value,
            application.current_step,
            application.created_at.isoformat(),
        ),
    )


def test_create_event_contains_correct_attributes(application):
    """Created events must match the conceptual log."""
    event = create_event(
        application,
        get_transition("submit_application"),
        resource="miha.p",
        role=UserRole.CUSTOMER,
        timestamp=datetime(2026, 11, 3, 9, 0),
    )

    assert event.case_id == "K-001"
    assert event.status == ApplicationStatus.SUBMITTED
    assert event.role == UserRole.CUSTOMER
    assert event.source == "system"
    assert event.zaprosen_znesek == Decimal("10000")
    assert event.bonitetna_ocena is None
    assert event.pdf_path == "uploads/proof.pdf"


def test_append_event_persists_data(test_db, application):
    """An event must be stored with its parent application."""
    event = create_event(
        application,
        get_transition("submit_application"),
        resource="miha.p",
        role=UserRole.CUSTOMER,
    )

    with get_connection(test_db) as connection:
        save_application(connection, application)
        event_id = append_event(connection, event)

    with get_connection(test_db) as connection:
        row = connection.execute(
            "SELECT * FROM process_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()

    assert row is not None
    assert row["case_id"] == "K-001"
    assert row["activity"] == event.activity


def test_csv_export_is_sorted_and_complete(
    test_db, application, tmp_path
):
    """CSV must contain every event in the correct order."""
    second_application = CreditApplication(
        case_id="K-002",
        customer_id="ana.k",
        requested_amount=Decimal("15000"),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/second.pdf",
        status=ApplicationStatus.SUBMITTED,
        current_step="verify_application",
        created_at=datetime(2026, 11, 3, 10, 0),
    )

    transition = get_transition("submit_application")

    with get_connection(test_db) as connection:
        save_application(connection, application)
        save_application(connection, second_application)

        # Insert K-002 first to verify sorting by case_id.
        for app, hour in [
            (second_application, 10),
            (application, 9),
        ]:
            event = create_event(
                app,
                transition,
                resource=app.customer_id,
                role=UserRole.CUSTOMER,
                timestamp=datetime(
                    2026, 11, 3, hour, 0,
                    tzinfo=timezone.utc,
                ),
            )
            append_event(connection, event)

    export_path = tmp_path / "dnevnik.csv"

    with get_connection(test_db) as connection:
        export_event_log(connection, export_path)

    with export_path.open(
        encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)

        assert reader.fieldnames == list(EVENT_LOG_COLUMNS)

    assert len(rows) == 2
    assert [row["case_id"] for row in rows] == [
        "K-001",
        "K-002",
    ]
    assert rows[0]["pdf_path"] == "uploads/proof.pdf"
    assert rows[1]["zaprosen_znesek"] == "15000"
