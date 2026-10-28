"""Application service for the credit approval process.

Coordinates:
- Credit application creation and updates.
- Workflow validation and transitions.
- Automatic system activities.
- Event logging within database transactions.

"""

import sqlite3
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from config import DATABASE_PATH
from database import get_connection
from models import (
    ApplicationStatus,
    CreditApplication,
    CreditRating,
    ProcessEvent,
    User,
    UserRole,
)
from services.event_service import append_event, create_event
from services.workflow_service import (
    WorkflowError,
    get_transition,
    validate_transition,
)
from services.verification_service import verify_application_data

from config import UPLOAD_DIR
from services.file_service import delete_pdf, save_pdf


SYSTEM_USER = User(username="sistem", role=UserRole.SYSTEM)


def _application_from_row(row: sqlite3.Row) -> CreditApplication:
    """Convert a database row into a CreditApplication."""
    return CreditApplication(
        case_id=row["case_id"],
        customer_id=row["customer_id"],
        requested_amount=Decimal(row["requested_amount"]),
        loan_purpose=row["loan_purpose"],
        pdf_path=row["pdf_path"],
        status=ApplicationStatus(row["status"]),
        current_step=row["current_step"],
        created_at=datetime.fromisoformat(row["created_at"]),
        credit_rating=(
            CreditRating(row["credit_rating"])
            if row["credit_rating"] is not None
            else None
        ),
        assigned_referent=row["assigned_referent"],
    )


def _event_from_row(row: sqlite3.Row) -> ProcessEvent:
    """Convert a database row into a ProcessEvent."""
    return ProcessEvent(
        event_id=row["event_id"],
        case_id=row["case_id"],
        activity=row["activity"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        resource=row["resource"],
        role=UserRole(row["role"]),
        source=row["source"],
        status=ApplicationStatus(row["status"]),
        zaprosen_znesek=Decimal(row["zaprosen_znesek"]),
        bonitetna_ocena=(
            CreditRating(row["bonitetna_ocena"])
            if row["bonitetna_ocena"] is not None
            else None
        ),
        namen_kredita=row["namen_kredita"],
        pdf_path=row["pdf_path"],
    )


def _next_case_id(connection: sqlite3.Connection) -> str:
    """Generate the next application ID while holding a write lock."""
    row = connection.execute(
        """
        SELECT COALESCE(MAX(CAST(SUBSTR(case_id, 3) AS INTEGER)), 0)
        FROM credit_applications
        WHERE case_id GLOB 'K-[0-9]*'
        """
    ).fetchone()

    next_number = row[0] + 1
    return f"K-{next_number:03d}"


def _save_application(
    connection: sqlite3.Connection,
    application: CreditApplication,
) -> None:
    """Persist the current application state."""
    connection.execute(
        """
        UPDATE credit_applications
        SET status = ?,
            current_step = ?,
            credit_rating = ?,
            assigned_referent = ?
        WHERE case_id = ?
        """,
        (
            application.status.value,
            application.current_step,
            (
                application.credit_rating.value
                if application.credit_rating is not None
                else None
            ),
            application.assigned_referent,
            application.case_id,
        ),
    )


def _execute_transition(
    connection: sqlite3.Connection,
    application: CreditApplication,
    step: str,
    actor: User,
    credit_rating: CreditRating | None = None,
) -> CreditApplication:
    """Validate and execute one transition within a transaction.

    The caller is responsible for committing the transaction.
    """
    transition = validate_transition(
        application=application,
        step=step,
        role=actor.role,
        username=actor.username,
    )

    updated = replace(
        application,
        status=transition.next_status,
        current_step=transition.next_step,
    )

    if step == "claim_application":
        updated.assigned_referent = actor.username

    if step == "assess_creditworthiness":
        if credit_rating is None:
            raise WorkflowError("A credit rating is required.")

        updated.credit_rating = CreditRating(credit_rating)

    _save_application(connection, updated)

    event = create_event(
        application=updated,
        transition=transition,
        resource=actor.username,
        role=actor.role,
    )
    append_event(connection, event)

    return updated



def _run_automatic_steps(
    connection: sqlite3.Connection,
    application: CreditApplication,
) -> CreditApplication:
    """Execute automatic steps and their required checks."""
    while application.current_step in {
        "verify_application",
        "notify_approval",
    }:
        if application.current_step == "verify_application":
            # Check the submitted application before marking it verified.
            verify_application_data(application)

        application = _execute_transition(
            connection=connection,
            application=application,
            step=application.current_step,
            actor=SYSTEM_USER,
        )

    return application



def submit_application(
    customer: User,
    requested_amount: Decimal,
    loan_purpose: str,
    pdf_path: str,
    db_path: Path = DATABASE_PATH,
) -> CreditApplication:
    """Submit a new application and perform automatic verification.

    pdf_path must reference a PDF already saved by the file service.
    The application and both initial events are saved atomically.
    """
    if customer.role != UserRole.CUSTOMER:
        raise WorkflowError("Only customers can submit applications.")

    if not customer.username.strip():
        raise ValueError("Customer identity is required.")

    try:
        amount = Decimal(str(requested_amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid requested amount.") from exc

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Requested amount must be positive.")

    if not loan_purpose.strip():
        raise ValueError("Loan purpose is required.")

    if not pdf_path.strip():
        raise ValueError("A stored PDF reference is required.")

    with get_connection(db_path) as connection:
        # Serialize case ID generation and subsequent writes.
        connection.execute("BEGIN IMMEDIATE")

        case_id = _next_case_id(connection)
        created_at = datetime.now().astimezone()

        # The application begins at the submission step.
        application = CreditApplication(
            case_id=case_id,
            customer_id=customer.username,
            requested_amount=amount,
            loan_purpose=loan_purpose.strip(),
            pdf_path=pdf_path,
            status=ApplicationStatus.SUBMITTED,
            current_step="submit_application",
            created_at=created_at,
        )

        connection.execute(
            """
            INSERT INTO credit_applications (
                case_id, customer_id, requested_amount,
                loan_purpose, pdf_path, status,
                current_step, created_at,
                credit_rating, assigned_referent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application.case_id,
                application.customer_id,
                str(application.requested_amount),
                application.loan_purpose,
                application.pdf_path,
                application.status.value,
                application.current_step,
                application.created_at.isoformat(),
                None,
                None,
            ),
        )

        application = _execute_transition(
            connection=connection,
            application=application,
            step="submit_application",
            actor=customer,
        )

        # Automatically verify the submitted application.
        application = _run_automatic_steps(connection, application)

        return application


def perform_action(
    case_id: str,
    step: str,
    actor: User,
    credit_rating: CreditRating | None = None,
    db_path: Path = DATABASE_PATH,
) -> CreditApplication:
    """Execute one user action and any resulting automatic steps.

    Each transition updates the application and appends one event.
    All database changes are committed together.
    """
    if actor.role == UserRole.SYSTEM:
        raise WorkflowError(
            "System activities cannot be triggered manually."
        )

    with get_connection(db_path) as connection:
        # Lock before reading to prevent competing updates.
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            "SELECT * FROM credit_applications WHERE case_id = ?",
            (case_id,),
        ).fetchone()

        if row is None:
            raise ValueError(f"Application '{case_id}' not found.")

        application = _application_from_row(row)

        application = _execute_transition(
            connection=connection,
            application=application,
            step=step,
            actor=actor,
            credit_rating=credit_rating,
        )

        # Approval automatically produces a notification event.
        application = _run_automatic_steps(connection, application)

        return application


def get_application(
    case_id: str,
    db_path: Path = DATABASE_PATH,
) -> CreditApplication | None:
    """Retrieve a credit application by its case ID."""
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM credit_applications WHERE case_id = ?",
            (case_id,),
        ).fetchone()

    return _application_from_row(row) if row is not None else None


def list_applications(
    db_path: Path = DATABASE_PATH,
) -> list[CreditApplication]:
    """Retrieve all applications ordered by case ID number."""
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM credit_applications
            ORDER BY CAST(SUBSTR(case_id, 3) AS INTEGER)
            """
        ).fetchall()

    return [_application_from_row(row) for row in rows]


def get_application_events(
    case_id: str,
    db_path: Path = DATABASE_PATH,
) -> list[ProcessEvent]:
    """Retrieve the chronological event history of an application."""
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM process_events
            WHERE case_id = ?
            ORDER BY timestamp, event_id
            """,
            (case_id,),
        ).fetchall()

    return [_event_from_row(row) for row in rows]


def submit_application_with_pdf(
    customer: User,
    requested_amount: Decimal,
    loan_purpose: str,
    pdf_filename: str,
    pdf_content: bytes,
    db_path: Path = DATABASE_PATH,
    upload_dir: Path = UPLOAD_DIR,
) -> CreditApplication:
    """Store an uploaded PDF and submit its credit application.

    The PDF is saved before the database operation.
    If application submission fails, the newly uploaded PDF
    is removed to avoid leaving an orphan document.

    Database changes remain atomic through submit_application().
    """
    # Step 1: Validate and store the uploaded PDF.
    pdf_reference = save_pdf(
        filename=pdf_filename,
        content=pdf_content,
        upload_dir=upload_dir,
    )

    try:
        # Step 2: Create the application and its initial events.
        return submit_application(
            customer=customer,
            requested_amount=requested_amount,
            loan_purpose=loan_purpose,
            pdf_path=pdf_reference,
            db_path=db_path,
        )

    except Exception:
        # Step 3: Clean up this upload if submission fails.
        delete_pdf(pdf_reference, upload_dir=upload_dir)
        raise

