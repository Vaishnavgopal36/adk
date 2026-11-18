"""Verify initialization and constraints using disposable SQLite databases."""

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from my_agent.database import DATABASE_PATH, connect_database, initialize_database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data" / "tasks.db"
        initialize_database(self.path)
        self.connection = connect_database(self.path)
        self.addCleanup(self.connection.close)

    def test_file_table_columns_and_foreign_keys(self):
        self.assertTrue(self.path.is_file())
        row = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name = ?",
            ("table", "tasks"),
        ).fetchone()
        self.assertIsNotNone(row)
        columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(tasks)")
        }
        self.assertEqual(
            columns,
            {
                "id",
                "title",
                "description",
                "status",
                "priority",
                "due_date",
                "created_at",
                "updated_at",
                "archived",
            },
        )
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
        )
        self.assertEqual(
            self.connection.execute("SELECT count(*) FROM tasks").fetchone()[0], 0
        )
        self.assertEqual(
            DATABASE_PATH,
            Path(__file__).resolve().parents[1] / "my_agent/data/tasks.db",
        )

    def test_initialization_is_idempotent_and_preserves_rows(self):
        task_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO tasks (id, title) VALUES (?, ?)", (task_id, "Keep this task")
        )
        self.connection.commit()
        initialize_database(self.path)
        with closing(connect_database(self.path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT title FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()[0],
                "Keep this task",
            )
            indexes = {
                row["name"] for row in connection.execute("PRAGMA index_list(tasks)")
            }
            self.assertEqual(
                indexes - {"sqlite_autoindex_tasks_1"},
                {
                    "idx_tasks_archived_status",
                    "idx_tasks_archived_priority",
                    "idx_tasks_archived_due_date",
                },
            )

    def test_defaults_and_allowed_values(self):
        for status in ["Not Started", "In Progress", "Done"]:
            for priority in ["", "Low", "Medium", "High", None]:
                self.connection.execute(
                    "INSERT INTO tasks (id, title, status, priority) VALUES (?, ?, ?, ?)",
                    (str(uuid4()), "Valid task", status, priority),
                )
        task_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO tasks (id, title) VALUES (?, ?)", (task_id, "Defaults")
        )
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        self.assertEqual(
            (
                row["description"],
                row["status"],
                row["priority"],
                row["due_date"],
                row["archived"],
            ),
            ("", "Not Started", "", None, 0),
        )
        for name in ["created_at", "updated_at"]:
            self.assertIn("T", row[name])
            self.assertTrue(row[name].endswith("Z"))

    def test_invalid_status_and_priority(self):
        for status, priority in [("Pending", "Low"), ("Done", "Urgent")]:
            with (
                self.subTest(status=status, priority=priority),
                self.assertRaises(sqlite3.IntegrityError),
            ):
                self.connection.execute(
                    "INSERT INTO tasks (id, title, status, priority) VALUES (?, ?, ?, ?)",
                    (str(uuid4()), "Invalid task", status, priority),
                )

    def test_invalid_title_archived_uuid_date_and_timestamps(self):
        statement = """INSERT INTO tasks
            (id, title, archived, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)"""
        valid: list[object] = [
            str(uuid4()),
            "Task",
            0,
            "2028-02-29",
            "2026-11-18T12:00:00Z",
            "2026-11-18T12:00:00+00:00",
        ]
        self.connection.execute(statement, valid)
        invalid_values = [
            (0, "not-a-uuid"),
            (0, None),
            (1, ""),
            (1, " \t\n"),
            (1, None),
            (2, 2),
            (2, -1),
            (2, 0.5),
            (3, "2026-02-30"),
            (3, "2026-13-01"),
            (3, "tomorrow"),
            (3, ""),
            (4, "2026-11-18T12:00:00+05:30"),
            (5, "not-a-timestamp"),
        ]
        for position, value in invalid_values:
            values = valid.copy()
            values[0] = str(uuid4())
            values[position] = value
            with (
                self.subTest(position=position, value=value),
                self.assertRaises(sqlite3.IntegrityError),
            ):
                self.connection.execute(statement, values)


if __name__ == "__main__":
    unittest.main()
