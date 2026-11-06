"""Tests for reading and validating interactive PDF forms."""

from decimal import Decimal

import pytest

from scripts.generate_pdf_forms import create_form
from services.pdf_form_service import (
    CreditFormData,
    PDFFormValidationError,
    read_credit_form,
)


def make_pdf(
    tmp_path,
    amount="15000",
    purpose="prenova_stanovanja",
    income="2100",
):
    """Create a temporary interactive PDF for testing."""

    path = tmp_path / "test_credit_form.pdf"
    create_form(path, amount, purpose, income)

    return path.read_bytes()


def test_valid_pdf(tmp_path):
    """A complete PDF should return validated data."""

    pdf = make_pdf(tmp_path)
    result = read_credit_form(pdf)

    assert isinstance(result, CreditFormData)
    assert result.zaprosen_znesek == Decimal("15000")
    assert result.namen_kredita == "prenova_stanovanja"
    assert result.mesecni_prihodek == Decimal("2100")


def test_missing_amount(tmp_path):
    """Requested amount is mandatory."""

    pdf = make_pdf(tmp_path, amount="")

    with pytest.raises(
        PDFFormValidationError,
        match="zaprosen_znesek",
    ):
        read_credit_form(pdf)


def test_missing_purpose(tmp_path):
    """The default dropdown option is not a valid purpose."""

    pdf = make_pdf(tmp_path, purpose="izberite")

    with pytest.raises(
        PDFFormValidationError,
        match="Izbran namen kredita ni dovoljen",
    ):
        read_credit_form(pdf)


def test_missing_income(tmp_path):
    """Monthly income is mandatory."""

    pdf = make_pdf(tmp_path, income="")

    with pytest.raises(
        PDFFormValidationError,
        match="mesecni_prihodek",
    ):
        read_credit_form(pdf)


@pytest.mark.parametrize(
    "amount",
    ["0", "-100", "abc", "NaN", "Infinity"],
)
def test_invalid_amount(tmp_path, amount):
    """Requested amount must be a valid positive number."""

    pdf = make_pdf(tmp_path, amount=amount)

    with pytest.raises(PDFFormValidationError):
        read_credit_form(pdf)


@pytest.mark.parametrize(
    "income",
    ["-100", "abc", "NaN", "Infinity"],
)
def test_invalid_income(tmp_path, income):
    """Monthly income must be a valid nonnegative number."""

    pdf = make_pdf(tmp_path, income=income)

    with pytest.raises(PDFFormValidationError):
        read_credit_form(pdf)


def test_zero_income_is_allowed(tmp_path):
    """Zero income is valid according to our current rules."""

    pdf = make_pdf(tmp_path, income="0")
    result = read_credit_form(pdf)

    assert result.mesecni_prihodek == Decimal("0")


def test_invalid_file():
    """A non-PDF file must be rejected."""

    with pytest.raises(PDFFormValidationError):
        read_credit_form(b"This is not a PDF")


def test_corrupted_pdf():
    """A corrupted PDF must be rejected."""

    with pytest.raises(PDFFormValidationError):
        read_credit_form(b"%PDF-1.4 corrupted content")


def test_empty_pdf():
    """Empty content must be rejected."""

    with pytest.raises(PDFFormValidationError):
        read_credit_form(b"")
