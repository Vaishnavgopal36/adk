"""Standalone SQLite schema initialization; no agents, tools, or CRUD operations.

Run ``python my_agent/database.py`` to initialize the local task database.
Future repositories should use ``connect_database`` so foreign keys are enabled
on every connection. Re-running initialization preserves existing records; this
is not a migration system for changing an existing table's definition.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent / "data" / "tasks.db"

# Unset priority is '' (or NULL); archiving preserves the original task row.
# Canonical UUID spelling is checked without requiring a SQLite extension.
SCHEMA_SQL = """
BEGIN;

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT NOT NULL PRIMARY KEY
        CHECK (
            length(id) = 36
            AND substr(id, 9, 1) = '-'
            AND substr(id, 14, 1) = '-'
            AND substr(id, 19, 1) = '-'
            AND substr(id, 24, 1) = '-'
            AND length(replace(id, '-', '')) = 32
            AND replace(id, '-', '') NOT GLOB '*[^0-9a-fA-F]*'
        ),
    title TEXT NOT NULL
        CHECK (length(trim(title, ' ' || char(9) || char(10) || char(13))) > 0),
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Not Started'
        CHECK (status IN ('Not Started', 'In Progress', 'Done')),
    priority TEXT NOT NULL DEFAULT 'Low'
        CHECK (priority IN ('Low', 'Medium', 'High')),
    due_date TEXT
        CHECK (
            due_date IS NULL OR (
                length(due_date) = 10
                AND due_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                AND date(due_date, '+0 days') IS NOT NULL
                AND date(due_date, '+0 days') = due_date
            )
        ),
    created_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            substr(created_at, 11, 1) = 'T'
            AND (substr(created_at, -1) = 'Z' OR substr(created_at, -6) = '+00:00')
            AND datetime(created_at) IS NOT NULL
            AND date(substr(created_at, 1, 10), '+0 days') = substr(created_at, 1, 10)
        ),
    updated_at TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        CHECK (
            substr(updated_at, 11, 1) = 'T'
            AND (substr(updated_at, -1) = 'Z' OR substr(updated_at, -6) = '+00:00')
            AND datetime(updated_at) IS NOT NULL
            AND date(substr(updated_at, 1, 10), '+0 days') = substr(updated_at, 1, 10)
        ),
    archived INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(archived) = 'integer' AND archived IN (0, 1))
);

-- Each index supports archive filtering through its leftmost column.
CREATE INDEX IF NOT EXISTS idx_tasks_archived_status ON tasks (archived, status);
CREATE INDEX IF NOT EXISTS idx_tasks_archived_priority ON tasks (archived, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_archived_due_date ON tasks (archived, due_date);

COMMIT;
"""


def connect_database(database_path: str | Path = DATABASE_PATH) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled; the caller must close it.

    Creates missing parent directories and the file, but not the tables.
    No foreign key columns are needed for the current single-table design.
    """
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10.0)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error:
        connection.close()
        raise


def initialize_database(database_path: str | Path = DATABASE_PATH) -> Path:
    """Create the database, table, and indexes if missing, without inserting tasks."""
    path = Path(database_path)
    with closing(connect_database(path)) as connection, connection:
        connection.executescript(SCHEMA_SQL)
    return path


if __name__ == "__main__":
    print(f"Initialized task database: {initialize_database()}")
