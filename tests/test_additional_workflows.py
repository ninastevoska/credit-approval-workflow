"""Tests for credit rejection and document supplementation workflows."""

from datetime import datetime
from decimal import Decimal

import pytest

from models import (
    ApplicationStatus,
    CreditApplication,
    CreditRating,
    UserRole,
)
from services.workflow_service import (
    WorkflowError,
    get_available_actions,
    get_transition,
    validate_transition,
)


def make_application(
    current_step="approve_application",
    rating=CreditRating.C,
):
    """Create a credit application for workflow testing."""

    return CreditApplication(
        case_id="K-TEST",
        customer_id="customer1",
        requested_amount=Decimal("10000"),
        loan_purpose="nakup_vozila",
        pdf_path="uploads/test.pdf",
        status=ApplicationStatus.ASSESSED,
        current_step=current_step,
        created_at=datetime.now().astimezone(),
        credit_rating=rating,
        assigned_referent="referent1",
        monthly_income=Decimal("1500"),
    )


def test_rejection_is_allowed():
    """The assigned referent can reject an assessed application."""

    application = make_application()

    transition = validate_transition(
        application,
        "reject_application",
        UserRole.REFERENT,
        "referent1",
    )

    assert transition.next_step == "notify_rejection"
    assert transition.next_status == ApplicationStatus.DECISION_MADE


def test_rejection_is_not_allowed_for_other_referent():
    """Another referent cannot reject the application."""

    application = make_application()

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "reject_application",
            UserRole.REFERENT,
            "referent2",
        )


def test_rejection_is_not_allowed_for_customer():
    """A customer cannot reject a credit application."""

    application = make_application()

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "reject_application",
            UserRole.CUSTOMER,
            "customer1",
        )


def test_rejection_notification():
    """The system closes a rejected application."""

    application = make_application(
        current_step="notify_rejection",
    )

    transition = validate_transition(
        application,
        "notify_rejection",
        UserRole.SYSTEM,
    )

    assert transition.next_step == "completed"
    assert transition.next_status == ApplicationStatus.REJECTED


def test_completion_request_is_allowed():
    """The referent can request additional documentation."""

    application = make_application(
        current_step="assess_creditworthiness",
    )

    transition = validate_transition(
        application,
        "request_completion",
        UserRole.REFERENT,
        "referent1",
    )

    assert transition.next_step == "notify_completion_request"
    assert (
        transition.next_status
        == ApplicationStatus.AWAITING_COMPLETION
    )


def test_completion_notification():
    """The system moves the application to supplementation."""

    application = make_application(
        current_step="notify_completion_request",
    )

    transition = validate_transition(
        application,
        "notify_completion_request",
        UserRole.SYSTEM,
    )

    assert transition.next_step == "submit_supplement"


def test_customer_can_submit_supplement():
    """Only the application owner can submit a supplement."""

    application = make_application(
        current_step="submit_supplement",
    )

    transition = validate_transition(
        application,
        "submit_supplement",
        UserRole.CUSTOMER,
        "customer1",
    )

    assert transition.next_step == "review_application"
    assert (
        transition.next_status
        == ApplicationStatus.COMPLETED_DOCUMENTS
    )


def test_other_customer_cannot_submit_supplement():
    """Another customer cannot supplement somebody else's case."""

    application = make_application(
        current_step="submit_supplement",
    )

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "submit_supplement",
            UserRole.CUSTOMER,
            "customer2",
        )


def test_referent_cannot_submit_supplement():
    """Supplementation belongs to the customer."""

    application = make_application(
        current_step="submit_supplement",
    )

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "submit_supplement",
            UserRole.REFERENT,
            "referent1",
        )


def test_supplement_returns_to_review():
    """After supplementation, the referent reviews the case again."""

    application = make_application(
        current_step="review_application",
    )

    transition = validate_transition(
        application,
        "review_application",
        UserRole.REFERENT,
        "referent1",
    )

    assert transition.next_step == "assess_creditworthiness"


def test_completion_loop_can_repeat():
    """The supplementation loop can be entered multiple times."""

    application = make_application(
        current_step="assess_creditworthiness",
    )

    first = validate_transition(
        application,
        "request_completion",
        UserRole.REFERENT,
        "referent1",
    )

    assert first.next_step == "notify_completion_request"

    # Simulate a second review after the customer supplements the PDF.
    application.current_step = "assess_creditworthiness"

    second = validate_transition(
        application,
        "request_completion",
        UserRole.REFERENT,
        "referent1",
    )

    assert second.next_step == "notify_completion_request"


def test_available_actions_include_rejection():
    """Rejection is available as an alternative to approval."""

    application = make_application()

    actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
    )

    steps = {action.step for action in actions}

    assert "reject_application" in steps
    assert "approve_application" not in steps


def test_available_actions_include_completion():
    """A referent can assess or request supplementation."""

    application = make_application(
        current_step="assess_creditworthiness",
    )

    actions = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
    )

    steps = {action.step for action in actions}

    assert steps == {
        "assess_creditworthiness",
        "request_completion",
    }


def test_cannot_skip_to_rejection():
    """An application cannot be rejected before assessment."""

    application = make_application(
        current_step="review_application",
    )

    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "reject_application",
            UserRole.REFERENT,
            "referent1",
        )


def test_new_activities_are_defined():
    """All new workflow activities must have valid definitions."""

    steps = (
        "request_completion",
        "notify_completion_request",
        "submit_supplement",
        "reject_application",
        "notify_rejection",
    )

    for step in steps:
        transition = get_transition(step)
        assert transition.step == step
        assert transition.activity
