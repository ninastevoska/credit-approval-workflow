"""Workflow definitions and transition validation.

Supports:
- Happy path (approval by referent).
- Rejection by referent.
- Document supplementation loop.

This module defines business rules without database access.
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
    """Definition of one process activity."""

    step: str
    activity: str
    required_role: UserRole
    next_step: str
    next_status: ApplicationStatus


# Original seven activities of the happy path.
TRANSITIONS: dict[str, WorkflowTransition] = {
    "submit_application": WorkflowTransition(
        "submit_application",
        "Izpolnitev in oddaja kreditne vloge",
        UserRole.CUSTOMER,
        "verify_application",
        ApplicationStatus.SUBMITTED,
    ),
    "verify_application": WorkflowTransition(
        "verify_application",
        "Samodejno preverjanje vloge",
        UserRole.SYSTEM,
        "claim_application",
        ApplicationStatus.VERIFIED,
    ),
    "claim_application": WorkflowTransition(
        "claim_application",
        "Prevzem kreditne vloge",
        UserRole.REFERENT,
        "review_application",
        ApplicationStatus.IN_REVIEW,
    ),
    "review_application": WorkflowTransition(
        "review_application",
        "Pregled kreditne vloge",
        UserRole.REFERENT,
        "assess_creditworthiness",
        ApplicationStatus.IN_REVIEW,
    ),
    "assess_creditworthiness": WorkflowTransition(
        "assess_creditworthiness",
        "Ocena kreditne sposobnosti",
        UserRole.REFERENT,
        "approve_application",
        ApplicationStatus.ASSESSED,
    ),
    "approve_application": WorkflowTransition(
        "approve_application",
        "Odobritev vloge",
        UserRole.REFERENT,
        "notify_approval",
        ApplicationStatus.DECISION_MADE,
    ),
    "notify_approval": WorkflowTransition(
        "notify_approval",
        "Obveščanje o odobritvi",
        UserRole.SYSTEM,
        "completed",
        ApplicationStatus.APPROVED,
    ),
}


# Additional workflow activities for rejection and document supplementation.
ADDITIONAL_TRANSITIONS: dict[str, WorkflowTransition] = {
    "request_completion": WorkflowTransition(
        "request_completion",
        "Priprava zahteve za dopolnitev vloge",
        UserRole.REFERENT,
        "notify_completion_request",
        ApplicationStatus.AWAITING_COMPLETION,
    ),
    "notify_completion_request": WorkflowTransition(
        "notify_completion_request",
        "Pošiljanje zahteve za dopolnitev",
        UserRole.SYSTEM,
        "submit_supplement",
        ApplicationStatus.AWAITING_COMPLETION,
    ),
    "submit_supplement": WorkflowTransition(
        "submit_supplement",
        "Dopolnitev in oddaja kreditne vloge",
        UserRole.CUSTOMER,
        "review_application",
        ApplicationStatus.COMPLETED_DOCUMENTS,
    ),
    "reject_application": WorkflowTransition(
        "reject_application",
        "Zavrnitev vloge",
        UserRole.REFERENT,
        "notify_rejection",
        ApplicationStatus.DECISION_MADE,
    ),
    "forward_to_manager": WorkflowTransition(
        "forward_to_manager",
        "Posredovanje vloge vodji",
        UserRole.REFERENT,
        "manager_review",
        ApplicationStatus.WITH_MANAGER,
    ),
    "manager_review": WorkflowTransition(
        "manager_review",
        "Pregled vloge",
        UserRole.MANAGER,
        "manager_approve",
        ApplicationStatus.WITH_MANAGER,
    ),
    "manager_approve": WorkflowTransition(
        "manager_approve",
        "Odobritev vloge",
        UserRole.MANAGER,
        "notify_approval",
        ApplicationStatus.DECISION_MADE,
    ),
    "manager_reject": WorkflowTransition(
        "manager_reject",
        "Zavrnitev vloge",
        UserRole.MANAGER,
        "notify_rejection",
        ApplicationStatus.DECISION_MADE,
    ),
    "notify_rejection": WorkflowTransition(
        "notify_rejection",
        "Obveščanje o zavrnitvi",
        UserRole.SYSTEM,
        "completed",
        ApplicationStatus.REJECTED,
    ),
}


# Alternative actions available at selected process steps.
ALTERNATIVE_ACTIONS = {
    "assess_creditworthiness": ("request_completion",),
    "approve_application": (
        "reject_application",
        "forward_to_manager",
    ),
    "manager_approve": ("manager_reject",),
}


def get_transition(step: str) -> WorkflowTransition:
    """Return a defined process transition."""

    if step in TRANSITIONS:
        return TRANSITIONS[step]

    if step in ADDITIONAL_TRANSITIONS:
        return ADDITIONAL_TRANSITIONS[step]

    raise WorkflowError(
        f"Unknown or completed workflow step: {step}"
    )


def get_candidate_steps(
    application: CreditApplication,
    unrestricted: bool = False,
) -> tuple[str, ...]:
    """Return candidate actions, including permitted deviations."""

    current = application.current_step

    if current == "completed":
        return ()

    steps = [
        current,
        *ALTERNATIVE_ACTIONS.get(current, ()),
    ]

    # In unrestricted mode, the review may be skipped.
    if unrestricted and current == "review_application":
        steps.append("assess_creditworthiness")

    return tuple(steps)



def validate_transition(
    application: CreditApplication,
    step: str,
    role: UserRole,
    username: str | None = None,
    unrestricted: bool = False,
) -> WorkflowTransition:
    """Validate a process transition and optional authority rules."""

    current = application.current_step

    if current == "completed":
        raise WorkflowError("Application is already completed.")

    allowed_steps = set(
        get_candidate_steps(application, unrestricted)
    )

    if step not in allowed_steps:
        raise WorkflowError(
            f"Action '{step}' is not allowed. "
            f"Expected one of: {sorted(allowed_steps)}."
        )

    transition = get_transition(step)

    if not unrestricted:
        # Only the authorized role may perform this activity.
        if role != transition.required_role:
            raise WorkflowError(
                f"Role '{role.value}' cannot perform '{step}'."
            )

        # Only the assigned referent may process the application.
        referent_actions = {
            "review_application",
            "assess_creditworthiness",
            "approve_application",
            "reject_application",
            "request_completion",
            "forward_to_manager",
        }

        if step in referent_actions:
            if not username or username != application.assigned_referent:
                raise WorkflowError(
                    "Only the assigned referent can process this application."
                )

        if step == "submit_supplement":
            if not username or username != application.customer_id:
                raise WorkflowError(
                    "Only the application owner can submit a supplement."
                )

        # Referent decisions are limited by the requested amount.
        if step in {"approve_application", "reject_application"}:
            if application.requested_amount > REFERENT_APPROVAL_LIMIT:
                raise WorkflowError(
                    "Application exceeds the referent decision limit."
                )

        if step == "approve_application":
            if application.credit_rating not in {
                CreditRating.A,
                CreditRating.B,
            }:
                raise WorkflowError(
                    "Only applications rated A or B can be approved directly."
                )

        if step == "forward_to_manager":
            if application.requested_amount <= REFERENT_APPROVAL_LIMIT:
                raise WorkflowError(
                    "Application is within the referent decision limit."
                )

            if application.credit_rating is None:
                raise WorkflowError(
                    "Creditworthiness must be assessed before forwarding."
                )

        if step in {"manager_approve", "manager_reject"}:
            if not username:
                raise WorkflowError("A manager identity is required.")

            if application.credit_rating is None:
                raise WorkflowError(
                    "Creditworthiness must be assessed before a decision."
                )

    # A case cannot be claimed twice, even in unrestricted mode.
    if step == "claim_application":
        if not username:
            raise WorkflowError("A referent identity is required.")

        if application.assigned_referent is not None:
            raise WorkflowError("Application is already assigned.")

    return transition





def get_available_actions(
    application: CreditApplication,
    role: UserRole,
    username: str | None = None,
    unrestricted: bool = False,
) -> list[WorkflowTransition]:
    """Return actions available under the selected execution mode."""

    current = application.current_step

    if current == "completed":
        return []

    candidate_steps = get_candidate_steps(
        application,
        unrestricted,
    )

    actions = []

    for step in candidate_steps:
        try:
            transition = validate_transition(
                application=application,
                step=step,
                role=role,
                username=username,
                unrestricted=unrestricted,
            )
        except WorkflowError:
            continue

        actions.append(transition)

    return actions


def is_completed(application: CreditApplication) -> bool:
    """Check whether the process has reached a final state."""

    return (
        application.current_step == "completed"
        and application.status in {
            ApplicationStatus.APPROVED,
            ApplicationStatus.REJECTED,
        }
    )
