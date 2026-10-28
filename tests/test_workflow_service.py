"""Tests for happy-path workflow transitions."""

from dataclasses import replace
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
    TRANSITIONS,
    WorkflowError,
    get_available_actions,
    get_transition,
    is_completed,
    validate_transition,
)


@pytest.fixture
def application():
    """Create a sample application ready for referent review."""
    return CreditApplication(
        case_id="K-001",
        customer_id="miha.p",
        requested_amount=Decimal("10000"),
        loan_purpose="nakup_vozila",
        pdf_path="uploads/document.pdf",
        status=ApplicationStatus.IN_REVIEW,
        current_step="review_application",
        created_at=datetime(2026, 11, 3, 9, 0),
        credit_rating=None,
        assigned_referent="referent1",
    )


def test_happy_path_has_seven_transitions():
    assert len(TRANSITIONS) == 7


def test_transition_names_and_order():
    """All happy-path transitions must form one valid sequence."""
    step = "submit_application"
    visited = []

    while step != "completed":
        assert step not in visited
        visited.append(step)
        step = get_transition(step).next_step

    assert len(visited) == 7


def test_correct_referent_can_review(application):
    transition = validate_transition(
        application,
        "review_application",
        UserRole.REFERENT,
        "referent1",
    )

    assert transition.next_step == "assess_creditworthiness"
    assert transition.next_status == ApplicationStatus.IN_REVIEW


def test_wrong_role_is_rejected(application):
    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "review_application",
            UserRole.CUSTOMER,
            "miha.p",
        )


def test_wrong_referent_is_rejected(application):
    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "review_application",
            UserRole.REFERENT,
            "referent2",
        )


def test_skipping_a_step_is_rejected(application):
    with pytest.raises(WorkflowError):
        validate_transition(
            application,
            "approve_application",
            UserRole.REFERENT,
            "referent1",
        )


def test_available_actions_depend_on_user(application):
    allowed = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent1",
    )

    denied = get_available_actions(
        application,
        UserRole.REFERENT,
        "referent2",
    )

    assert len(allowed) == 1
    assert allowed[0].step == "review_application"
    assert denied == []


@pytest.mark.parametrize(
    ("amount", "rating", "allowed"),
    [
        ("10000", CreditRating.A, True),
        ("20000", CreditRating.B, True),
        ("20000.01", CreditRating.A, False),
        ("30000", CreditRating.B, False),
        ("10000", CreditRating.C, False),
        ("10000", None, False),
    ],
)
def test_referent_approval_rules(application, amount, rating, allowed):
    candidate = replace(
        application,
        requested_amount=Decimal(amount),
        credit_rating=rating,
        current_step="approve_application",
        status=ApplicationStatus.ASSESSED,
    )

    if allowed:
        validate_transition(
            candidate,
            "approve_application",
            UserRole.REFERENT,
            "referent1",
        )
    else:
        with pytest.raises(WorkflowError):
            validate_transition(
                candidate,
                "approve_application",
                UserRole.REFERENT,
                "referent1",
            )


def test_completed_application_has_no_actions(application):
    completed = replace(
        application,
        status=ApplicationStatus.APPROVED,
        current_step="completed",
    )

    assert is_completed(completed)
    assert get_available_actions(
        completed,
        UserRole.REFERENT,
        "referent1",
    ) == []


def test_unknown_step_is_rejected():
    with pytest.raises(WorkflowError):
        get_transition("unknown_step")
