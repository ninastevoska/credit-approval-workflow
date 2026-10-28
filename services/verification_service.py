"""Automatic validation of submitted credit application data.

This module checks the basic completeness and consistency
of an application before it can proceed to referent review.

It does not calculate creditworthiness or inspect PDF contents.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePath

from models import ApplicationStatus, CreditApplication


class ApplicationVerificationError(ValueError):
    """Raised when a submitted application fails automatic checks."""


def verify_application_data(application: CreditApplication) -> None:
    """Validate a submitted application before automatic verification.

    The function raises an error when validation fails.
    Otherwise, it returns normally without changing the application.
    """
    if (
        application.status != ApplicationStatus.SUBMITTED
        or application.current_step != "verify_application"
    ):
        raise ApplicationVerificationError(
            "Application is not ready for automatic verification."
        )

    if not application.customer_id.strip():
        raise ApplicationVerificationError(
            "Customer identity is missing."
        )

    try:
        amount = Decimal(str(application.requested_amount))
    except (InvalidOperation, ValueError) as exc:
        raise ApplicationVerificationError(
            "Requested amount is invalid."
        ) from exc

    if not amount.is_finite() or amount <= 0:
        raise ApplicationVerificationError(
            "Requested amount must be positive."
        )

    if not application.loan_purpose.strip():
        raise ApplicationVerificationError(
            "Loan purpose is missing."
        )

    if (
        not application.pdf_path.strip()
        or PurePath(application.pdf_path).suffix.lower() != ".pdf"
    ):
        raise ApplicationVerificationError(
            "A PDF document reference is required."
        )
