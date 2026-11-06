"""Event logging and CSV export.

Responsibilities:
- Create events using the process event log schema.
- Append events to the database.
- Export the complete event log to CSV.

The caller manages database transactions.
Existing events are never modified or deleted.
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from config import EVENT_LOG_EXPORT_PATH
from models import CreditApplication, ProcessEvent, UserRole
from services.workflow_service import WorkflowTransition


# Keep existing columns and add the new PDF attribute.
EVENT_LOG_COLUMNS = (
    "case_id",
    "activity",
    "timestamp",
    "resource",
    "role",
    "source",
    "status",
    "zaprosen_znesek",
    "bonitetna_ocena",
    "namen_kredita",
    "pdf_path",
    "mesecni_prihodek",
)


def create_event(
    application: CreditApplication,
    transition: WorkflowTransition,
    resource: str,
    role: UserRole,
    timestamp: datetime | None = None,
) -> ProcessEvent:
    """Create an event from the application's current data."""

    if timestamp is None:
        timestamp = datetime.now().astimezone()

    return ProcessEvent(
        case_id=application.case_id,
        activity=transition.activity,
        timestamp=timestamp,
        resource=resource,
        role=role,
        source="system",
        status=application.status,
        zaprosen_znesek=application.requested_amount,
        bonitetna_ocena=application.credit_rating,
        namen_kredita=application.loan_purpose,
        pdf_path=application.pdf_path,
        mesecni_prihodek=application.monthly_income,
    )


def append_event(
    connection: sqlite3.Connection,
    event: ProcessEvent,
) -> int:
    """Append one event without committing the transaction."""

    cursor = connection.execute(
        """
        INSERT INTO process_events (
            case_id,
            activity,
            timestamp,
            resource,
            role,
            source,
            status,
            zaprosen_znesek,
            bonitetna_ocena,
            namen_kredita,
            pdf_path,
            mesecni_prihodek
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.case_id,
            event.activity,
            event.timestamp.isoformat(timespec="seconds"),
            event.resource,
            event.role.value,
            event.source,
            event.status.value,
            str(event.zaprosen_znesek),
            (
                event.bonitetna_ocena.value
                if event.bonitetna_ocena is not None
                else None
            ),
            event.namen_kredita,
            event.pdf_path,
            (
                str(event.mesecni_prihodek)
                if event.mesecni_prihodek is not None
                else None
            ),
        ),
    )

    return cursor.lastrowid


def export_event_log(
    connection: sqlite3.Connection,
    output_path: Path = EVENT_LOG_EXPORT_PATH,
) -> Path:
    """Export events ordered by case ID, timestamp and event ID."""

    rows = connection.execute(
        """
        SELECT
            case_id,
            activity,
            timestamp,
            resource,
            role,
            source,
            status,
            zaprosen_znesek,
            bonitetna_ocena,
            namen_kredita,
            pdf_path,
            mesecni_prihodek
        FROM process_events
        ORDER BY case_id, timestamp, event_id
        """
    ).fetchall()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(EVENT_LOG_COLUMNS)

        for row in rows:
            writer.writerow(
                [row[column] for column in EVENT_LOG_COLUMNS]
            )

    return output_path
