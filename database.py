"""SQLite database connection and schema initialization.

Responsibilities:
- Open and close database connections.
- Manage transactions.
- Create and migrate the database schema.
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
    """Provide a database connection with transaction handling."""

    connection = sqlite3.connect(db_path)

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        yield connection

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Add a column without deleting or changing existing records."""

    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }

    if column not in existing_columns:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def initialize_database(
    db_path: Path = DATABASE_PATH,
) -> None:
    """Create or upgrade the database without losing existing data."""

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
                monthly_income TEXT,

                CHECK (CAST(requested_amount AS REAL) > 0)
            )
            """
        )

        # Append-only history of process activities.
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
                mesecni_prihodek TEXT,

                FOREIGN KEY (case_id)
                    REFERENCES credit_applications(case_id)
            )
            """
        )

        # Upgrade databases created by the previous version.
        # Existing rows receive NULL for the new attribute.
        _add_column_if_missing(
            connection,
            "credit_applications",
            "monthly_income",
            "TEXT",
        )

        _add_column_if_missing(
            connection,
            "process_events",
            "mesecni_prihodek",
            "TEXT",
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
