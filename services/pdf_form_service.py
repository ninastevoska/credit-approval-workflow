"""Reading and validation of interactive credit application PDFs."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO

from pypdf import PdfReader


# Allowed values for the purpose dropdown.
ALLOWED_PURPOSES = {
    "nakup_vozila",
    "prenova_stanovanja",
    "osebna_poraba",
}

# Field names must match the PDF template.
REQUIRED_FIELDS = {
    "zaprosen_znesek",
    "namen_kredita",
    "mesecni_prihodek",
}


class PDFFormValidationError(ValueError):
    """Raised when a PDF form contains invalid data."""


@dataclass(frozen=True)
class CreditFormData:
    """Validated data extracted from the PDF."""

    zaprosen_znesek: Decimal
    namen_kredita: str
    mesecni_prihodek: Decimal


def _required_text(fields: dict, name: str) -> str:
    """Return a required field value as text."""

    field = fields.get(name)

    if field is None:
        raise PDFFormValidationError(
            f"Manjka polje '{name}'."
        )

    value = field.get("/V")

    if not isinstance(value, str) or not value.strip():
        raise PDFFormValidationError(
            f"Polje '{name}' ni izpolnjeno."
        )

    return value.strip()


def _parse_amount(
    value: str,
    name: str,
    positive: bool = False,
) -> Decimal:
    """Convert text to a valid decimal amount."""

    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise PDFFormValidationError(
            f"Polje '{name}' mora vsebovati veljavno stevilo."
        ) from None

    if not amount.is_finite():
        raise PDFFormValidationError(
            f"Polje '{name}' mora vsebovati koncno stevilo."
        )

    if positive and amount <= 0:
        raise PDFFormValidationError(
            f"Polje '{name}' mora biti vecje od 0."
        )

    if not positive and amount < 0:
        raise PDFFormValidationError(
            f"Polje '{name}' ne sme biti negativno."
        )

    return amount


def read_credit_form(pdf_content: bytes) -> CreditFormData:
    """Extract and validate data from an interactive PDF.

    This function only reads and checks data.
    It does not write anything to the database.
    """

    if (
        not isinstance(pdf_content, bytes)
        or not pdf_content.startswith(b"%PDF-")
    ):
        raise PDFFormValidationError(
            "Datoteka ni veljaven PDF."
        )

    try:
        reader = PdfReader(BytesIO(pdf_content), strict=True)

        if reader.is_encrypted:
            raise PDFFormValidationError(
                "Zascitenih PDF-jev ni mogoce obdelati."
            )

        fields = reader.get_fields() or {}

    except PDFFormValidationError:
        raise

    except Exception as exc:
        raise PDFFormValidationError(
            "PDF-ja ni mogoce prebrati."
        ) from exc

    # Check that the PDF contains all required fields.
    missing = REQUIRED_FIELDS - fields.keys()

    if missing:
        raise PDFFormValidationError(
            "V PDF-ju manjkajo zahtevana polja: "
            + ", ".join(sorted(missing))
        )

    # Requested credit amount must be positive.
    amount = _parse_amount(
        _required_text(fields, "zaprosen_znesek"),
        "zaprosen_znesek",
        positive=True,
    )

    # Loan purpose must be a dropdown with an allowed value.
    purpose_field = fields["namen_kredita"]

    if purpose_field.get("/FT") != "/Ch":
        raise PDFFormValidationError(
            "Polje 'namen_kredita' mora biti spustni seznam."
        )

    purpose = _required_text(fields, "namen_kredita")

    if purpose not in ALLOWED_PURPOSES:
        raise PDFFormValidationError(
            "Izbran namen kredita ni dovoljen."
        )

    # Monthly income must not be negative.
    income = _parse_amount(
        _required_text(fields, "mesecni_prihodek"),
        "mesecni_prihodek",
    )

    return CreditFormData(
        zaprosen_znesek=amount,
        namen_kredita=purpose,
        mesecni_prihodek=income,
    )
