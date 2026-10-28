"""SQLite database connection and schema initialization.

Responsibilities:
- Open and close database connections.
- Manage transactions.
- Create the database schema.
- Protect the event log from modification.

Business rules and application operations belong in services,
not in this module.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DATABASE_PATH, ensure_directories


@contextmanager
def get_connection(
    db_path: Path = DATABASE_PATH,
) -> Iterator[sqlite3.Connection]:
    """Provide a database connection with transaction handling.

    Commit changes on success, roll back on failure, and always
    close the connection.
    """
    connection = sqlite3.connect(db_path)

    try:
        connection.row_factory = sqlite3.Row

        # SQLite does not enable foreign key checks by default.
        connection.execute("PRAGMA foreign_keys = ON")

        yield connection

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialize_database(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create application tables, indexes, and event-log guards.

    Existing tables and records are preserved.
    """
    if db_path == DATABASE_PATH:
        ensure_directories()
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as connection:

        # Current state of each credit application.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_applications (
                case_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                requested_amount TEXT NOT NULL,
                loan_purpose TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                status TEXT NOT NULL,
                current_step TEXT NOT NULL,
                created_at TEXT NOT NULL,
                credit_rating TEXT
                    CHECK (
                        credit_rating IS NULL
                        OR credit_rating IN ('A', 'B', 'C')
                    ),
                assigned_referent TEXT,

                CHECK (CAST(requested_amount AS REAL) > 0)
            )
            """
        )

        # Append-only history of process activities.
        # Column names follow the event log from Assignment 3.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS process_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                activity TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                resource TEXT NOT NULL,
                role TEXT NOT NULL,
                source TEXT NOT NULL
                    CHECK (source IN ('system', 'manual')),
                status TEXT NOT NULL,
                zaprosen_znesek TEXT NOT NULL,
                bonitetna_ocena TEXT
                    CHECK (
                        bonitetna_ocena IS NULL
                        OR bonitetna_ocena IN ('A', 'B', 'C')
                    ),
                namen_kredita TEXT NOT NULL,
                pdf_path TEXT NOT NULL,

                FOREIGN KEY (case_id)
                    REFERENCES credit_applications(case_id)
            )
            """
        )

        # Optimize reading a case's event history.
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_case_time
            ON process_events (case_id, timestamp, event_id)
            """
        )

        # Event logs are append-only: UPDATE is forbidden.
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_event_update
            BEFORE UPDATE ON process_events
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Process events cannot be modified'
                );
            END
            """
        )

        # Event logs are append-only: DELETE is forbidden.
        connection.execute(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_event_delete
            BEFORE DELETE ON process_events
            BEGIN
                SELECT RAISE(
                    ABORT,
                    'Process events cannot be deleted'
                );
            END
            """
        )


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized successfully: {DATABASE_PATH}")
