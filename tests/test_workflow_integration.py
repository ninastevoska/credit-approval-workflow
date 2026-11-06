"""Integration tests for rejection and document supplementation.

Tests verify complete workflows, database persistence,
PDF storage, and process event history.
"""

from decimal import Decimal

import pytest

from database import initialize_database
from models import (
    ApplicationStatus,
    CreditRating,
    User,
    UserRole,
)
from scripts.generate_pdf_forms import create_form
from services.application_service import (
    get_application,
    get_application_events,
    list_applications,
    perform_action,
    submit_application,
    submit_application_supplement,
)
from services.file_service import read_pdf
from services.pdf_form_service import PDFFormValidationError
from services.workflow_service import WorkflowError


@pytest.fixture
def environment(tmp_path):
    """Create an isolated database and user identities."""

    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"

    initialize_database(db_path)

    return {
        "db_path": db_path,
        "upload_dir": upload_dir,
        "customer": User("customer1", UserRole.CUSTOMER),
        "referent": User("referent1", UserRole.REFERENT),
    }


def create_test_pdf(
    tmp_path,
    amount="15000",
    purpose="prenova_stanovanja",
    income="2100",
):
    """Create a real interactive PDF with specified values."""

    path = tmp_path / "credit_form.pdf"

    create_form(
        path,
        amount=amount,
        purpose=purpose,
        income=income,
    )

    return path.read_bytes()


def prepare_application(environment):
    """Submit, claim, and review an application."""

    db_path = environment["db_path"]
    customer = environment["customer"]
    referent = environment["referent"]

    application = submit_application(
        customer=customer,
        requested_amount=Decimal("15000"),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/original.pdf",
        db_path=db_path,
        monthly_income=Decimal("2100"),
    )

    for step in ("claim_application", "review_application"):
        application = perform_action(
            case_id=application.case_id,
            step=step,
            actor=referent,
            db_path=db_path,
        )

    return application


def test_complete_rejection_workflow(environment):
    """A rejected case must close with an automatic notification."""

    db_path = environment["db_path"]
    referent = environment["referent"]

    application = prepare_application(environment)

    application = perform_action(
        case_id=application.case_id,
        step="assess_creditworthiness",
        actor=referent,
        credit_rating=CreditRating.C,
        db_path=db_path,
    )

    application = perform_action(
        case_id=application.case_id,
        step="reject_application",
        actor=referent,
        db_path=db_path,
    )

    saved = get_application(application.case_id, db_path)
    events = get_application_events(application.case_id, db_path)

    assert saved is not None
    assert saved.status == ApplicationStatus.REJECTED
    assert saved.current_step == "completed"

    assert len(events) == 7

    assert [event.activity for event in events][-2:] == [
        "Zavrnitev vloge",
        "Obveščanje o zavrnitvi",
    ]

    assert events[-1].role == UserRole.SYSTEM
    assert events[-1].resource == "sistem"
    assert events[-1].status == ApplicationStatus.REJECTED


def test_complete_supplementation_workflow(
    environment,
    tmp_path,
):
    """A supplemented case must retain its ID and return to review."""

    db_path = environment["db_path"]
    upload_dir = environment["upload_dir"]
    customer = environment["customer"]
    referent = environment["referent"]

    application = prepare_application(environment)

    original_case_id = application.case_id
    original_pdf_path = application.pdf_path

    # Referent requests additional documentation.
    application = perform_action(
        case_id=application.case_id,
        step="request_completion",
        actor=referent,
        db_path=db_path,
    )

    assert application.status == ApplicationStatus.AWAITING_COMPLETION
    assert application.current_step == "submit_supplement"

    events = get_application_events(application.case_id, db_path)

    assert events[-1].activity == "Pošiljanje zahteve za dopolnitev"
    assert events[-1].role == UserRole.SYSTEM

    # Customer uploads a completed interactive PDF.
    pdf_content = create_test_pdf(
        tmp_path,
        amount="16000",
        purpose="nakup_vozila",
        income="2300",
    )

    application = submit_application_supplement(
        case_id=application.case_id,
        customer=customer,
        pdf_filename="supplement.pdf",
        pdf_content=pdf_content,
        db_path=db_path,
        upload_dir=upload_dir,
    )

    # The same case is updated, not duplicated.
    assert application.case_id == original_case_id
    assert application.pdf_path != original_pdf_path
    assert application.status == ApplicationStatus.COMPLETED_DOCUMENTS
    assert application.current_step == "review_application"

    saved = get_application(original_case_id, db_path)

    assert saved is not None
    assert saved.requested_amount == Decimal("16000")
    assert saved.loan_purpose == "nakup_vozila"
    assert saved.monthly_income == Decimal("2300")

    assert read_pdf(saved.pdf_path, upload_dir) == pdf_content
    assert len(list_applications(db_path)) == 1

    # Referent reviews the supplemented application.
    application = perform_action(
        case_id=original_case_id,
        step="review_application",
        actor=referent,
        db_path=db_path,
    )

    application = perform_action(
        case_id=original_case_id,
        step="assess_creditworthiness",
        actor=referent,
        credit_rating=CreditRating.B,
        db_path=db_path,
    )

    application = perform_action(
        case_id=original_case_id,
        step="approve_application",
        actor=referent,
        db_path=db_path,
    )

    assert application.status == ApplicationStatus.APPROVED
    assert application.current_step == "completed"

    events = get_application_events(original_case_id, db_path)

    assert len(events) == 11

    activities = [event.activity for event in events]

    assert activities.count("Pregled kreditne vloge") == 2
    assert "Priprava zahteve za dopolnitev vloge" in activities
    assert "Pošiljanje zahteve za dopolnitev" in activities
    assert "Dopolnitev in oddaja kreditne vloge" in activities

    # Historical events retain their original attributes.
    assert events[0].zaprosen_znesek == Decimal("15000")
    assert events[0].mesecni_prihodek == Decimal("2100")

    # Events after supplementation contain updated attributes.
    assert events[-1].zaprosen_znesek == Decimal("16000")
    assert events[-1].mesecni_prihodek == Decimal("2300")


def test_invalid_supplement_does_not_change_case(
    environment,
    tmp_path,
):
    """An incomplete PDF must not modify stored application data."""

    db_path = environment["db_path"]
    upload_dir = environment["upload_dir"]
    customer = environment["customer"]
    referent = environment["referent"]

    application = prepare_application(environment)

    perform_action(
        case_id=application.case_id,
        step="request_completion",
        actor=referent,
        db_path=db_path,
    )

    before = get_application(application.case_id, db_path)
    events_before = get_application_events(
        application.case_id,
        db_path,
    )

    # The requested amount is missing.
    invalid_pdf = create_test_pdf(
        tmp_path,
        amount="",
    )

    with pytest.raises(PDFFormValidationError):
        submit_application_supplement(
            case_id=application.case_id,
            customer=customer,
            pdf_filename="incomplete.pdf",
            pdf_content=invalid_pdf,
            db_path=db_path,
            upload_dir=upload_dir,
        )

    after = get_application(application.case_id, db_path)
    events_after = get_application_events(
        application.case_id,
        db_path,
    )

    assert after is not None
    assert before is not None

    assert after.status == before.status
    assert after.current_step == before.current_step
    assert after.pdf_path == before.pdf_path
    assert after.monthly_income == before.monthly_income

    assert len(events_after) == len(events_before)
    assert not upload_dir.exists() or not list(upload_dir.iterdir())


def test_other_customer_cannot_submit_supplement(
    environment,
    tmp_path,
):
    """A customer cannot change another customer's application."""

    db_path = environment["db_path"]
    upload_dir = environment["upload_dir"]
    referent = environment["referent"]

    application = prepare_application(environment)

    perform_action(
        case_id=application.case_id,
        step="request_completion",
        actor=referent,
        db_path=db_path,
    )

    other_customer = User("customer2", UserRole.CUSTOMER)
    valid_pdf = create_test_pdf(tmp_path)

    events_before = get_application_events(
        application.case_id,
        db_path,
    )

    with pytest.raises(WorkflowError):
        submit_application_supplement(
            case_id=application.case_id,
            customer=other_customer,
            pdf_filename="supplement.pdf",
            pdf_content=valid_pdf,
            db_path=db_path,
            upload_dir=upload_dir,
        )

    saved = get_application(application.case_id, db_path)
    events_after = get_application_events(
        application.case_id,
        db_path,
    )

    assert saved is not None
    assert saved.current_step == "submit_supplement"
    assert len(events_after) == len(events_before)
    assert not upload_dir.exists() or not list(upload_dir.iterdir())
