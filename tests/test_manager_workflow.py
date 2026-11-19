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


def test_unrestricted_referent_can_approve_above_limit():
    """An unrestricted referent may exceed the approval limit."""
    application = make_application(amount="25000")

    transition = validate_transition(
        application,
        "approve_application",
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert transition.next_step == "notify_approval"


def test_normal_mode_still_enforces_approval_limit():
    """The normal mode must retain existing authority rules."""
    application = make_application(amount="25000")

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "approve_application",
            UserRole.REFERENT,
            "referent1",
            unrestricted=False,
        )


def test_unrestricted_mode_allows_different_role():
    """An actor may perform another role's action."""
    application = make_application(step="manager_approve")

    transition = validate_transition(
        application,
        "manager_approve",
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert transition.next_step == "notify_approval"


def test_unrestricted_mode_allows_rejection_above_limit():
    """A referent may reject a high-value case in unrestricted mode."""
    application = make_application(amount="25000")

    transition = validate_transition(
        application,
        "reject_application",
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert transition.next_step == "notify_rejection"


def test_unrestricted_mode_preserves_workflow_order():
    """Unrestricted authority does not automatically permit skipping."""
    application = make_application(step="review_application")

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "manager_approve",
            UserRole.REFERENT,
            "referent1",
            unrestricted=True,
        )


def test_unrestricted_mode_cannot_modify_completed_case():
    """Completed cases cannot receive another process decision."""
    application = make_application(step="completed")

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "approve_application",
            UserRole.REFERENT,
            "referent1",
            unrestricted=True,
        )


def test_available_actions_in_unrestricted_mode():
    """Unrestricted mode exposes additional decision options."""
    application = make_application(amount="25000")

    normal_actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
    )

    unrestricted_actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert {action.step for action in normal_actions} == {
        "forward_to_manager"
    }

    assert {action.step for action in unrestricted_actions} == {
        "approve_application",
        "reject_application",
        "forward_to_manager",
    }


@pytest.mark.parametrize(
    "decision,expected_status,expected_activity",
    [
        (
            "approve_application",
            ApplicationStatus.APPROVED,
            "Odobritev vloge",
        ),
        (
            "reject_application",
            ApplicationStatus.REJECTED,
            "Zavrnitev vloge",
        ),
    ],
)
def test_unrestricted_referent_decision_is_persisted(
    tmp_path,
    decision,
    expected_status,
    expected_activity,
):
    """An unrestricted referent decision must be saved correctly."""

    db_path = tmp_path / "unrestricted_workflow.db"
    initialize_database(db_path)

    customer = User("customer1", UserRole.CUSTOMER)
    referent = User("referent1", UserRole.REFERENT)

    application = submit_application(
        customer=customer,
        requested_amount=Decimal("25000"),
        loan_purpose="prenova_stanovanja",
        pdf_path="uploads/test.pdf",
        monthly_income=Decimal("2500"),
        db_path=db_path,
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
        credit_rating=CreditRating.A,
        db_path=db_path,
    )

    # Normal mode must reject a decision above the limit.
    with pytest.raises(WorkflowError):
        perform_action(
            application.case_id,
            decision,
            referent,
            db_path=db_path,
        )

    # Unrestricted mode allows the same decision.
    application = perform_action(
        application.case_id,
        decision,
        referent,
        db_path=db_path,
        unrestricted=True,
    )

    assert application.status == expected_status
    assert application.current_step == "completed"

    saved = get_application(application.case_id, db_path)

    assert saved is not None
    assert saved.status == expected_status

    events = get_application_events(application.case_id, db_path)

    assert len(events) == 7
    assert events[-2].activity == expected_activity
    assert events[-2].resource == "referent1"
    assert events[-2].role == UserRole.REFERENT
    assert events[-1].resource == "sistem"
    assert events[-1].role == UserRole.SYSTEM


def test_unrestricted_mode_can_skip_review():
    """Unrestricted mode may skip the application review."""
    application = make_application(step="review_application")

    transition = validate_transition(
        application,
        "assess_creditworthiness",
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert transition.next_step == "approve_application"
    assert transition.next_status == ApplicationStatus.ASSESSED


def test_normal_mode_cannot_skip_review():
    """Normal mode requires the application review."""
    application = make_application(step="review_application")

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "assess_creditworthiness",
            UserRole.REFERENT,
            "referent1",
            unrestricted=False,
        )


def test_available_actions_include_skip_only_when_unrestricted():
    application = make_application(step="review_application")

    normal_actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
    )

    unrestricted_actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
        unrestricted=True,
    )

    assert {action.step for action in normal_actions} == {
        "review_application"
    }

    assert {action.step for action in unrestricted_actions} == {
        "review_application",
        "assess_creditworthiness",
    }
