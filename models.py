"""Data models for users, credit applications, and process events."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class UserRole(StrEnum):
    """Roles supported by the application."""

    CUSTOMER = "stranka"
    REFERENT = "referent"
    MANAGER = "vodja"
    SYSTEM = "sistem"


class ApplicationStatus(StrEnum):
    """Business states of a credit application."""

    SUBMITTED = "oddana"
    VERIFIED = "preverjena"
    IN_REVIEW = "v_pregledu"
    AWAITING_COMPLETION = "v_dopolnitvi"
    COMPLETED_DOCUMENTS = "dopolnjena"
    ASSESSED = "ocenjena"
    WITH_MANAGER = "pri_vodji"
    DECISION_MADE = "odlocitev_sprejeta"
    APPROVED = "odobrena"
    REJECTED = "zavrnjena"


class CreditRating(StrEnum):
    """Creditworthiness categories."""

    A = "A"
    B = "B"
    C = "C"


@dataclass(frozen=True)
class User:
    """A selectable application user."""

    username: str
    role: UserRole


@dataclass
class CreditApplication:
    """Current state and data of one credit application."""

    case_id: str
    customer_id: str
    requested_amount: Decimal
    loan_purpose: str
    pdf_path: str
    status: ApplicationStatus
    current_step: str
    created_at: datetime
    credit_rating: CreditRating | None = None
    assigned_referent: str | None = None


@dataclass(frozen=True)
class ProcessEvent:
    """One immutable event in the process event log.

    """
    case_id: str
    activity: str
    timestamp: datetime
    resource: str
    role: UserRole
    source: str
    status: ApplicationStatus
    zaprosen_znesek: Decimal
    bonitetna_ocena: CreditRating | None
    namen_kredita: str
    pdf_path: str
    event_id: int | None = None
