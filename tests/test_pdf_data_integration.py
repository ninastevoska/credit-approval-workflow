"""Integration tests for PDF data persistence and CSV export."""

import csv
from decimal import Decimal
from pathlib import Path

from database import get_connection, initialize_database
from models import User, UserRole
from services.application_service import (
    get_application,
    get_application_events,
    submit_application,
)
from services.event_service import export_event_log
from services.pdf_form_service import read_credit_form


def test_pdf_data_is_saved_and_exported(tmp_path):
    """PDF attributes must persist in SQLite and appear in the CSV."""

    # 1. Create an isolated test database.
    db_path = tmp_path / "test.db"
    initialize_database(db_path)

    # 2. Read the completed interactive PDF.
    pdf_path = Path("forms/kreditna_vloga_popolna.pdf")
    form_data = read_credit_form(pdf_path.read_bytes())

    # 3. Create an application using data extracted from the PDF.
    customer = User("test.customer", UserRole.CUSTOMER)

    application = submit_application(
        customer=customer,
        requested_amount=form_data.zaprosen_znesek,
        loan_purpose=form_data.namen_kredita,
        pdf_path="uploads/test.pdf",
        db_path=db_path,
        monthly_income=form_data.mesecni_prihodek,
    )

    assert application.monthly_income == Decimal("2100")

    # 4. Verify that the value survives a database read.
    saved = get_application(application.case_id, db_path)

    assert saved is not None
    assert saved.requested_amount == Decimal("15000")
    assert saved.loan_purpose == "prenova_stanovanja"
    assert saved.monthly_income == Decimal("2100")

    # 5. Verify that both initial events contain the PDF attribute.
    events = get_application_events(application.case_id, db_path)

    assert len(events) == 2
    assert all(
        event.mesecni_prihodek == Decimal("2100")
        for event in events
    )

    # 6. Export events and verify the new CSV column.
    csv_path = tmp_path / "events.csv"

    with get_connection(db_path) as connection:
        export_event_log(connection, csv_path)

    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2
    assert all(row["mesecni_prihodek"] == "2100" for row in rows)
    assert all(row["zaprosen_znesek"] == "15000" for row in rows)
    assert all(
        row["namen_kredita"] == "prenova_stanovanja"
        for row in rows
    )


def test_legacy_application_has_no_monthly_income(tmp_path):
    """Older applications must remain supported."""

    db_path = tmp_path / "legacy.db"
    initialize_database(db_path)

    customer = User("old.customer", UserRole.CUSTOMER)

    application = submit_application(
        customer=customer,
        requested_amount=Decimal("10000"),
        loan_purpose="nakup_vozila",
        pdf_path="uploads/old.pdf",
        db_path=db_path,
    )

    saved = get_application(application.case_id, db_path)
    events = get_application_events(application.case_id, db_path)

    assert saved is not None
    assert saved.monthly_income is None
    assert all(event.mesecni_prihodek is None for event in events)
