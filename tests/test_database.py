"""Tests for SQLite schema, constraints, and event-log integrity.

Each test uses a temporary database to avoid modifying real data.
"""

import sqlite3

import pytest

from database import get_connection, initialize_database


@pytest.fixture
def test_db(tmp_path):
    """Create a fresh SQLite database for each test."""
    db_path = tmp_path / "test_iup.db"
    initialize_database(db_path)
    return db_path


def insert_application(connection, case_id="K-001"):
    """Insert a valid credit application for testing."""
    connection.execute(
        """
        INSERT INTO credit_applications (
            case_id, customer_id, requested_amount,
            loan_purpose, pdf_path, status,
            current_step, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            "miha.p",
            "10000",
            "nakup_vozila",
            "uploads/document.pdf",
            "oddana",
            "verify_application",
            "2026-11-03T09:00:00",
        ),
    )


def insert_event(connection, case_id="K-001"):
    """Insert a valid process event for testing."""
    connection.execute(
        """
        INSERT INTO process_events (
            case_id, activity, timestamp, resource,
            role, source, status, zaprosen_znesek,
            bonitetna_ocena, namen_kredita, pdf_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            "Izpolnitev in oddaja kreditne vloge",
            "2026-11-03T09:00:00",
            "miha.p",
            "stranka",
            "system",
            "oddana",
            "10000",
            None,
            "nakup_vozila",
            "uploads/document.pdf",
        ),
    )


def test_database_tables_exist(test_db):
    """Both required tables must be created."""
    with get_connection(test_db) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "credit_applications" in tables
    assert "process_events" in tables


def test_application_and_event_can_be_saved(test_db):
    """A credit application and its event must persist."""
    with get_connection(test_db) as connection:
        insert_application(connection)
        insert_event(connection)

    with get_connection(test_db) as connection:
        application = connection.execute(
            "SELECT * FROM credit_applications WHERE case_id = ?",
            ("K-001",),
        ).fetchone()

        events = connection.execute(
            "SELECT * FROM process_events WHERE case_id = ?",
            ("K-001",),
        ).fetchall()

    assert application is not None
    assert application["status"] == "oddana"
    assert len(events) == 1
    assert events[0]["resource"] == "miha.p"


def test_foreign_key_prevents_orphan_events(test_db):
    """An event cannot reference a nonexistent application."""
    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(test_db) as connection:
            insert_event(connection, case_id="K-999")

    with get_connection(test_db) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM process_events"
        ).fetchone()[0]

    assert count == 0


def test_event_log_is_append_only(test_db):
    """Existing events must not be updated or deleted."""
    with get_connection(test_db) as connection:
        insert_application(connection)
        insert_event(connection)

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(test_db) as connection:
            connection.execute(
                """
                UPDATE process_events
                SET activity = ?
                WHERE case_id = ?
                """,
                ("Spremenjena aktivnost", "K-001"),
            )

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(test_db) as connection:
            connection.execute(
                "DELETE FROM process_events WHERE case_id = ?",
                ("K-001",),
            )

    with get_connection(test_db) as connection:
        events = connection.execute(
            "SELECT * FROM process_events"
        ).fetchall()

    assert len(events) == 1
    assert events[0]["activity"] == (
        "Izpolnitev in oddaja kreditne vloge"
    )


def test_transaction_rolls_back_on_error(test_db):
    """An error must roll back all changes in the transaction."""
    with pytest.raises(RuntimeError):
        with get_connection(test_db) as connection:
            insert_application(connection)
            insert_event(connection)

            # Simulate an unexpected failure.
            raise RuntimeError("Simulated transaction failure")

    with get_connection(test_db) as connection:
        applications = connection.execute(
            "SELECT COUNT(*) FROM credit_applications"
        ).fetchone()[0]

        events = connection.execute(
            "SELECT COUNT(*) FROM process_events"
        ).fetchone()[0]

    assert applications == 0
    assert events == 0


def test_database_initialization_is_idempotent(test_db):
    """Initializing an existing database must preserve its data."""
    with get_connection(test_db) as connection:
        insert_application(connection)

    initialize_database(test_db)

    with get_connection(test_db) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM credit_applications"
        ).fetchone()[0]

    assert count == 1