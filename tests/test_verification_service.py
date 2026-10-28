"""Tests for automatic application data verification."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from models import ApplicationStatus, CreditApplication
from services.verification_service import (
    ApplicationVerificationError,
    verify_application_data,
)


@pytest.fixture
def application():
    return CreditApplication(
        case_id="K-TEST",
        customer_id="ana.k",
        requested_amount=Decimal("15000"),
        loan_purpose="Prenova stanovanja",
        pdf_path="data/uploads/document.pdf",
        status=ApplicationStatus.SUBMITTED,
        current_step="verify_application",
        created_at=datetime(2026, 10, 28, 12, 0),
    )


def test_valid_application_passes(application):
    verify_application_data(application)


@pytest.mark.parametrize(
    "field,value",
    [
        ("customer_id", ""),
        ("requested_amount", Decimal("-100")),
        ("requested_amount", Decimal("NaN")),
        ("loan_purpose", "   "),
        ("pdf_path", ""),
        ("pdf_path", "document.txt"),
        ("current_step", "claim_application"),
        ("status", ApplicationStatus.APPROVED),
    ],
)
def test_invalid_application_is_rejected(application, field, value):
    invalid = replace(application, **{field: value})

    with pytest.raises(ApplicationVerificationError):
        verify_application_data(invalid)


def test_verification_does_not_modify_application(application):
    before = replace(application)

    verify_application_data(application)

    assert application == before
