"""Tests for manual event recording."""

from decimal import Decimal

import pytest

from database import initialize_database
from models import ApplicationStatus, CreditRating, User, UserRole
from services.application_service import (
    MANUAL_EVENT_TYPES,
    get_application,
    get_application_events,
    perform_action,
    record_manual_event,
    submit_application,
)
from services.workflow_service import WorkflowError


@pytest.fixture
def prepared_case(tmp_path):
    """Create an application assigned to a referent."""
    db_path = tmp_path / "manual_events.db"
    initialize_database(db_path)

    customer = User("stranka1", UserRole.CUSTOMER)
    referent = User("referent1", UserRole.REFERENT)

    application = submit_application(
        customer=customer,
        requested_amount=Decimal("15000"),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/test.pdf",
        monthly_income=Decimal("2100"),
        db_path=db_path,
    )

    application = perform_action(
        application.case_id,
        "claim_application",
        referent,
        db_path=db_path,
    )

    return db_path, application, referent


def test_five_predefined_event_types():
    assert len(MANUAL_EVENT_TYPES) == 5
    assert len(set(MANUAL_EVENT_TYPES)) == 5


def test_record_predefined_manual_event(prepared_case):
    db_path, application, referent = prepared_case

    event = record_manual_event(
        application.case_id,
        "Telefonski klic stranki",
        referent,
        db_path=db_path,
    )

    assert event.event_id is not None
    assert event.activity == "Telefonski klic stranki"
    assert event.source == "manual"
    assert event.resource == "referent1"
    assert event.role == UserRole.REFERENT
    assert event.status == ApplicationStatus.IN_REVIEW
    assert event.zaprosen_znesek == Decimal("15000")
    assert event.mesecni_prihodek == Decimal("2100")

    events = get_application_events(application.case_id, db_path)

    assert len(events) == 4
    assert events[-1].activity == "Telefonski klic stranki"
    assert events[-1].source == "manual"


def test_custom_manual_event(prepared_case):
    db_path, application, referent = prepared_case

    event = record_manual_event(
        application.case_id,
        "Preverjanje dodatnih informacij",
        referent,
        db_path=db_path,
    )

    assert event.activity == "Preverjanje dodatnih informacij"
    assert event.source == "manual"


def test_manual_event_preserves_workflow_state(prepared_case):
    db_path, application, referent = prepared_case

    before = get_application(application.case_id, db_path)

    record_manual_event(
        application.case_id,
        "Posvet s sodelavcem",
        referent,
        db_path=db_path,
    )

    after = get_application(application.case_id, db_path)

    assert after.status == before.status
    assert after.current_step == before.current_step
    assert after.assigned_referent == before.assigned_referent


def test_other_referent_cannot_record_event(prepared_case):
    db_path, application, _ = prepared_case
    other = User("referent2", UserRole.REFERENT)

    with pytest.raises(WorkflowError):
        record_manual_event(
            application.case_id,
            "Posvet z vodjo",
            other,
            db_path=db_path,
        )

    assert len(get_application_events(application.case_id, db_path)) == 3


@pytest.mark.parametrize("role", [
    UserRole.CUSTOMER,
    UserRole.MANAGER,
    UserRole.SYSTEM,
])
def test_other_roles_cannot_record_event(prepared_case, role):
    db_path, application, _ = prepared_case
    actor = User("uporabnik", role)

    with pytest.raises(WorkflowError):
        record_manual_event(
            application.case_id,
            "Telefonski klic stranki",
            actor,
            db_path=db_path,
        )


@pytest.mark.parametrize("activity", [
    "",
    "   ",
    "A" * 101,
])
def test_invalid_event_name(prepared_case, activity):
    db_path, application, referent = prepared_case

    with pytest.raises(ValueError):
        record_manual_event(
            application.case_id,
            activity,
            referent,
            db_path=db_path,
        )


def test_unknown_application(prepared_case):
    db_path, _, referent = prepared_case

    with pytest.raises(ValueError):
        record_manual_event(
            "K-999",
            "Telefonski klic stranki",
            referent,
            db_path=db_path,
        )


def test_completed_case_rejects_manual_event(prepared_case):
    db_path, application, referent = prepared_case

    perform_action(
        application.case_id,
        "review_application",
        referent,
        db_path=db_path,
    )

    perform_action(
        application.case_id,
        "assess_creditworthiness",
        referent,
        credit_rating=CreditRating.A,
        db_path=db_path,
    )

    perform_action(
        application.case_id,
        "approve_application",
        referent,
        db_path=db_path,
    )

    with pytest.raises(WorkflowError):
        record_manual_event(
            application.case_id,
            "Poslana e-pošta stranki",
            referent,
            db_path=db_path,
        )
