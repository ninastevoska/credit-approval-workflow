"""Tests for referent and manager decision authority."""

from datetime import datetime
from decimal import Decimal

import pytest

from models import (
    ApplicationStatus,
    CreditApplication,
    CreditRating,
    User,
    UserRole,
)
from services.workflow_service import (
    WorkflowError,
    get_available_actions,
    validate_transition,
)

def make_application(
    amount="25000",
    rating=CreditRating.A,
    step="approve_application",
):
    """Create a credit application for authority testing."""

    return CreditApplication(
        case_id="K-TEST",
        customer_id="customer1",
        requested_amount=Decimal(amount),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/test.pdf",
        status=ApplicationStatus.ASSESSED,
        current_step=step,
        created_at=datetime.now().astimezone(),
        credit_rating=rating,
        assigned_referent="referent1",
        monthly_income=Decimal("2500"),
    )


def test_referent_can_approve_at_limit():
    application = make_application(amount="20000")

    transition = validate_transition(
        application, "approve_application",
        UserRole.REFERENT, "referent1",
    )

    assert transition.next_step == "notify_approval"


def test_referent_cannot_approve_above_limit():
    application = make_application(amount="20000.01")

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "approve_application",
            UserRole.REFERENT, "referent1",
        )


def test_referent_cannot_reject_above_limit():
    application = make_application(amount="25000")

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "reject_application",
            UserRole.REFERENT, "referent1",
        )


def test_referent_can_forward_above_limit():
    application = make_application(amount="25000")

    transition = validate_transition(
        application, "forward_to_manager",
        UserRole.REFERENT, "referent1",
    )

    assert transition.next_step == "manager_review"
    assert transition.next_status == ApplicationStatus.WITH_MANAGER


def test_referent_cannot_forward_within_limit():
    application = make_application(amount="20000")

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "forward_to_manager",
            UserRole.REFERENT, "referent1",
        )


def test_other_referent_cannot_forward():
    application = make_application()

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "forward_to_manager",
            UserRole.REFERENT, "referent2",
        )


def test_manager_can_review_forwarded_case():
    application = make_application(step="manager_review")

    transition = validate_transition(
        application, "manager_review",
        UserRole.MANAGER, "vodja1",
    )

    assert transition.next_step == "manager_approve"


@pytest.mark.parametrize(
    "step,expected_next",
    [
        ("manager_approve", "notify_approval"),
        ("manager_reject", "notify_rejection"),
    ],
)
def test_manager_can_make_decision(step, expected_next):
    application = make_application(step="manager_approve")

    transition = validate_transition(
        application, step,
        UserRole.MANAGER, "vodja1",
    )

    assert transition.next_step == expected_next


def test_manager_cannot_skip_review():
    application = make_application(step="manager_review")

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "manager_approve",
            UserRole.MANAGER, "vodja1",
        )


def test_referent_cannot_perform_manager_decision():
    application = make_application(step="manager_approve")

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "manager_approve",
            UserRole.REFERENT, "referent1",
        )


def test_manager_decision_requires_credit_rating():
    application = make_application(
        rating=None,
        step="manager_approve",
    )

    with pytest.raises(WorkflowError):
        validate_transition(
            application, "manager_approve",
            UserRole.MANAGER, "vodja1",
        )


def test_available_actions_depend_on_authority():
    application = make_application(amount="25000")

    actions = get_available_actions(
        application, UserRole.REFERENT, "referent1",
    )

    steps = {action.step for action in actions}

    assert steps == {"forward_to_manager"}


def test_manager_has_two_decision_options():
    application = make_application(step="manager_approve")

    actions = get_available_actions(
        application, UserRole.MANAGER, "vodja1",
    )

    assert {action.step for action in actions} == {
        "manager_approve",
        "manager_reject",
    }


from database import initialize_database
from services.application_service import (
    get_application,
    get_application_events,
    perform_action,
    submit_application,
)


@pytest.mark.parametrize(
    "decision,rating,expected_status,expected_notification",
    [
        (
            "manager_approve",
            CreditRating.A,
            ApplicationStatus.APPROVED,
            "Obveščanje o odobritvi",
        ),
        (
            "manager_reject",
            CreditRating.B,
            ApplicationStatus.REJECTED,
            "Obveščanje o zavrnitvi",
        ),
    ],
)
def test_complete_manager_workflow(
    tmp_path,
    decision,
    rating,
    expected_status,
    expected_notification,
):
    """Manager paths must persist all nine process events."""

    db_path = tmp_path / "manager_workflow.db"
    initialize_database(db_path)

    customer = User("customer1", UserRole.CUSTOMER)
    referent = User("referent1", UserRole.REFERENT)
    manager = User("vodja1", UserRole.MANAGER)

    application = submit_application(
        customer=customer,
        requested_amount=Decimal("25000"),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/test.pdf",
        db_path=db_path,
        monthly_income=Decimal("2500"),
    )

    for step in ("claim_application", "review_application"):
        application = perform_action(
            application.case_id,
            step,
            referent,
            db_path=db_path,
        )

    application = perform_action(
        application.case_id,
        "assess_creditworthiness",
        referent,
        credit_rating=rating,
        db_path=db_path,
    )

    application = perform_action(
        application.case_id,
        "forward_to_manager",
        referent,
        db_path=db_path,
    )

    assert application.status == ApplicationStatus.WITH_MANAGER
    assert application.current_step == "manager_review"

    application = perform_action(
        application.case_id,
        "manager_review",
        manager,
        db_path=db_path,
    )

    application = perform_action(
        application.case_id,
        decision,
        manager,
        db_path=db_path,
    )

    assert application.status == expected_status
    assert application.current_step == "completed"

    saved = get_application(application.case_id, db_path)
    assert saved is not None
    assert saved.status == expected_status

    events = get_application_events(application.case_id, db_path)

    assert len(events) == 9

    assert [event.activity for event in events][5:] == [
        "Posredovanje vloge vodji",
        "Pregled vloge",
        (
            "Odobritev vloge"
            if decision == "manager_approve"
            else "Zavrnitev vloge"
        ),
        expected_notification,
    ]

    assert events[6].resource == "vodja1"
    assert events[7].resource == "vodja1"
    assert events[8].resource == "sistem"
