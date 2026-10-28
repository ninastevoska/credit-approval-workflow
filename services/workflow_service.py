"""Workflow definitions and transition validation.

This module contains the business rules for the happy path
defined in Assignment 3.

It does not access the database or the user interface.
"""

from dataclasses import dataclass

from config import REFERENT_APPROVAL_LIMIT
from models import (
    ApplicationStatus,
    CreditApplication,
    CreditRating,
    UserRole,
)


class WorkflowError(ValueError):
    """Raised when a workflow action is not allowed."""


@dataclass(frozen=True)
class WorkflowTransition:
    """Definition of one allowed workflow transition."""

    step: str
    activity: str
    required_role: UserRole
    next_step: str
    next_status: ApplicationStatus


# The seven activities of the happy path.
# Their names and resulting statuses match Assignment 3.
TRANSITIONS: dict[str, WorkflowTransition] = {
    "submit_application": WorkflowTransition(
        step="submit_application",
        activity="Izpolnitev in oddaja kreditne vloge",
        required_role=UserRole.CUSTOMER,
        next_step="verify_application",
        next_status=ApplicationStatus.SUBMITTED,
    ),
    "verify_application": WorkflowTransition(
        step="verify_application",
        activity="Samodejno preverjanje vloge",
        required_role=UserRole.SYSTEM,
        next_step="claim_application",
        next_status=ApplicationStatus.VERIFIED,
    ),
    "claim_application": WorkflowTransition(
        step="claim_application",
        activity="Prevzem kreditne vloge",
        required_role=UserRole.REFERENT,
        next_step="review_application",
        next_status=ApplicationStatus.IN_REVIEW,
    ),
    "review_application": WorkflowTransition(
        step="review_application",
        activity="Pregled kreditne vloge",
        required_role=UserRole.REFERENT,
        next_step="assess_creditworthiness",
        next_status=ApplicationStatus.IN_REVIEW,
    ),
    "assess_creditworthiness": WorkflowTransition(
        step="assess_creditworthiness",
        activity="Ocena kreditne sposobnosti",
        required_role=UserRole.REFERENT,
        next_step="approve_application",
        next_status=ApplicationStatus.ASSESSED,
    ),
    "approve_application": WorkflowTransition(
        step="approve_application",
        activity="Odobritev vloge",
        required_role=UserRole.REFERENT,
        next_step="notify_approval",
        next_status=ApplicationStatus.DECISION_MADE,
    ),
    "notify_approval": WorkflowTransition(
        step="notify_approval",
        activity="Obveščanje o odobritvi",
        required_role=UserRole.SYSTEM,
        next_step="completed",
        next_status=ApplicationStatus.APPROVED,
    ),
}


def get_transition(step: str) -> WorkflowTransition:
    """Return the transition associated with a workflow step."""
    try:
        return TRANSITIONS[step]
    except KeyError as exc:
        raise WorkflowError(
            f"Unknown or completed workflow step: {step}"
        ) from exc


def validate_transition(
    application: CreditApplication,
    step: str,
    role: UserRole,
    username: str | None = None,
) -> WorkflowTransition:
    """Validate a requested action without changing application data.

    Checks:
    - The requested action is the current workflow step.
    - The actor has the required role.
    - Only the assigned referent can continue a claimed case.
    - Direct approval is restricted to amounts up to 20,000 EUR.
    - Only applications rated A or B can be approved directly.
    """
    if application.current_step != step:
        raise WorkflowError(
            f"Action '{step}' is not allowed. "
            f"Expected: '{application.current_step}'."
        )

    transition = get_transition(step)

    if role != transition.required_role:
        raise WorkflowError(
            f"Role '{role.value}' cannot perform '{step}'."
        )

    if step in {
        "review_application",
        "assess_creditworthiness",
        "approve_application",
    }:
        if not username or username != application.assigned_referent:
            raise WorkflowError(
                "Only the assigned referent can process this application."
            )

    if step == "claim_application":
        if not username:
            raise WorkflowError("A referent identity is required.")

        if application.assigned_referent is not None:
            raise WorkflowError("Application is already assigned.")

    if step == "approve_application":
        if application.requested_amount > REFERENT_APPROVAL_LIMIT:
            raise WorkflowError(
                "Application exceeds the referent approval limit."
            )

        if application.credit_rating not in {
            CreditRating.A,
            CreditRating.B,
        }:
            raise WorkflowError(
                "Only applications rated A or B can be approved directly."
            )

    return transition


def get_available_actions(
    application: CreditApplication,
    role: UserRole,
    username: str | None = None,
) -> list[WorkflowTransition]:
    """Return actions currently available to a user.

    Invalid or completed states produce an empty list.
    """
    try:
        transition = validate_transition(
            application=application,
            step=application.current_step,
            role=role,
            username=username,
        )
    except WorkflowError:
        return []

    return [transition]


def is_completed(application: CreditApplication) -> bool:
    """Return whether the happy-path process has finished."""
    return (
        application.current_step == "completed"
        and application.status == ApplicationStatus.APPROVED
    )
