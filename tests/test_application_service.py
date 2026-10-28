"""Integration tests for the credit application service.

Tests use isolated SQLite databases and verify complete operations,
including workflow validation, state changes, and event logging.
"""

from decimal import Decimal

import pytest

from database import get_connection, initialize_database
from models import ApplicationStatus, CreditRating, User, UserRole
from services.application_service import (
    get_application,
    get_application_events,
    list_applications,
    perform_action,
    submit_application,
)
from services.workflow_service import WorkflowError


@pytest.fixture
def test_db(tmp_path):
    """Create a fresh database for each test."""
    db_path = tmp_path / "applications.db"
    initialize_database(db_path)
    return db_path


@pytest.fixture
def customer():
    """Provide a customer identity."""
    return User("miha.p", UserRole.CUSTOMER)


@pytest.fixture
def referent():
    """Provide a referent identity."""
    return User("referent1", UserRole.REFERENT)


def submit_sample(test_db, customer, amount="10000"):
    """Submit a sample application using the public service API."""
    return submit_application(
        customer=customer,
        requested_amount=Decimal(amount),
        loan_purpose="nakup_vozila",
        pdf_path="uploads/proof.pdf",
        db_path=test_db,
    )


def advance_to_assessment(test_db, customer, referent):
    """Create, claim, and review an application."""
    application = submit_sample(test_db, customer)

    for step in ("claim_application", "review_application"):
        application = perform_action(
            case_id=application.case_id,
            step=step,
            actor=referent,
            db_path=test_db,
        )

    return application


def test_submission_creates_application_and_two_events(
    test_db, customer
):
    """Submission must automatically trigger verification."""
    application = submit_sample(test_db, customer)

    events = get_application_events(application.case_id, test_db)

    assert application.case_id == "K-001"
    assert application.status == ApplicationStatus.VERIFIED
    assert application.current_step == "claim_application"
    assert len(events) == 2

    assert [event.activity for event in events] == [
        "Izpolnitev in oddaja kreditne vloge",
        "Samodejno preverjanje vloge",
    ]

    assert [event.status for event in events] == [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.VERIFIED,
    ]

    assert events[0].resource == "miha.p"
    assert events[1].resource == "sistem"


def test_complete_happy_path(test_db, customer, referent):
    """A successful case must produce exactly seven events."""
    application = submit_sample(test_db, customer)

    for step in (
        "claim_application",
        "review_application",
    ):
        application = perform_action(
            application.case_id, step, referent, db_path=test_db
        )

    application = perform_action(
        application.case_id,
        "assess_creditworthiness",
        referent,
        credit_rating=CreditRating.A,
        db_path=test_db,
    )

    application = perform_action(
        application.case_id,
        "approve_application",
        referent,
        db_path=test_db,
    )

    events = get_application_events(application.case_id, test_db)

    expected_activities = [
        "Izpolnitev in oddaja kreditne vloge",
        "Samodejno preverjanje vloge",
        "Prevzem kreditne vloge",
        "Pregled kreditne vloge",
        "Ocena kreditne sposobnosti",
        "Odobritev vloge",
        "Obveščanje o odobritvi",
    ]

    assert [event.activity for event in events] == expected_activities
    assert len(events) == 7
    assert application.status == ApplicationStatus.APPROVED
    assert application.current_step == "completed"
    assert application.credit_rating == CreditRating.A

    # Notification must be performed automatically by the system.
    assert events[-1].resource == "sistem"
    assert events[-1].role == UserRole.SYSTEM


def test_claim_assigns_referent(test_db, customer, referent):
    """Claiming a case must record the assigned referent."""
    application = submit_sample(test_db, customer)

    claimed = perform_action(
        application.case_id,
        "claim_application",
        referent,
        db_path=test_db,
    )

    assert claimed.assigned_referent == "referent1"
    assert claimed.status == ApplicationStatus.IN_REVIEW
    assert claimed.current_step == "review_application"


def test_second_referent_cannot_claim_case(
    test_db, customer, referent
):
    """A claimed application must not be claimed a second time."""
    application = submit_sample(test_db, customer)

    perform_action(
        application.case_id,
        "claim_application",
        referent,
        db_path=test_db,
    )

    second_referent = User("referent2", UserRole.REFERENT)

    with pytest.raises(WorkflowError):
        perform_action(
            application.case_id,
            "claim_application",
            second_referent,
            db_path=test_db,
        )

    assert len(get_application_events(application.case_id, test_db)) == 3


def test_cannot_skip_review(test_db, customer, referent):
    """A referent cannot approve an application prematurely."""
    application = submit_sample(test_db, customer)

    with pytest.raises(WorkflowError):
        perform_action(
            application.case_id,
            "approve_application",
            referent,
            db_path=test_db,
        )

    saved = get_application(application.case_id, test_db)

    assert saved.current_step == "claim_application"
    assert len(get_application_events(application.case_id, test_db)) == 2


def test_only_assigned_referent_can_continue(
    test_db, customer, referent
):
    """Another referent cannot process a claimed application."""
    application = submit_sample(test_db, customer)

    perform_action(
        application.case_id,
        "claim_application",
        referent,
        db_path=test_db,
    )

    other = User("referent2", UserRole.REFERENT)

    with pytest.raises(WorkflowError):
        perform_action(
            application.case_id,
            "review_application",
            other,
            db_path=test_db,
        )

    assert len(get_application_events(application.case_id, test_db)) == 3


def test_credit_rating_is_saved_in_event_log(
    test_db, customer, referent
):
    """Credit rating is introduced at the assessment activity."""
    application = advance_to_assessment(test_db, customer, referent)

    assessed = perform_action(
        application.case_id,
        "assess_creditworthiness",
        referent,
        credit_rating=CreditRating.B,
        db_path=test_db,
    )

    events = get_application_events(application.case_id, test_db)

    assert assessed.credit_rating == CreditRating.B
    assert assessed.status == ApplicationStatus.ASSESSED
    assert events[-1].bonitetna_ocena == CreditRating.B
    assert all(
        event.bonitetna_ocena is None
        for event in events[:-1]
    )


def test_approval_limit_is_enforced(
    test_db, customer, referent
):
    """Referents cannot directly approve applications above 20,000 EUR."""
    application = submit_sample(test_db, customer, "25000")

    for step in ("claim_application", "review_application"):
        application = perform_action(
            application.case_id, step, referent, db_path=test_db
        )

    perform_action(
        application.case_id,
        "assess_creditworthiness",
        referent,
        credit_rating=CreditRating.A,
        db_path=test_db,
    )

    with pytest.raises(WorkflowError):
        perform_action(
            application.case_id,
            "approve_application",
            referent,
            db_path=test_db,
        )

    saved = get_application(application.case_id, test_db)

    assert saved.status == ApplicationStatus.ASSESSED
    assert len(get_application_events(application.case_id, test_db)) == 5


@pytest.mark.parametrize(
    ("amount", "purpose", "pdf_path"),
    [
        ("0", "nakup_vozila", "uploads/proof.pdf"),
        ("-100", "nakup_vozila", "uploads/proof.pdf"),
        ("NaN", "nakup_vozila", "uploads/proof.pdf"),
        ("Infinity", "nakup_vozila", "uploads/proof.pdf"),
        ("10000", "", "uploads/proof.pdf"),
        ("10000", "nakup_vozila", ""),
    ],
)
def test_invalid_submission_creates_no_application(
    test_db, customer, amount, purpose, pdf_path
):
    """Invalid input must not generate application data."""
    with pytest.raises((ValueError, WorkflowError)):
        submit_application(
            customer=customer,
            requested_amount=amount,
            loan_purpose=purpose,
            pdf_path=pdf_path,
            db_path=test_db,
        )

    assert list_applications(test_db) == []


def test_nonexistent_application_is_rejected(test_db, referent):
    """Actions on unknown cases must be rejected."""
    with pytest.raises(ValueError):
        perform_action(
            "K-999",
            "claim_application",
            referent,
            db_path=test_db,
        )


def test_data_persists_and_case_ids_are_unique(test_db, customer):
    """Applications must survive separate database connections."""
    first = submit_sample(test_db, customer)
    second = submit_sample(test_db, customer, "15000")

    assert first.case_id == "K-001"
    assert second.case_id == "K-002"

    applications = list_applications(test_db)

    assert len(applications) == 2
    assert get_application("K-001", test_db) is not None
    assert get_application("K-002", test_db) is not None

    with get_connection(test_db) as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM process_events"
        ).fetchone()[0]

    assert event_count == 4
