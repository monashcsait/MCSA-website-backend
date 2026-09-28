"""Existing installations gain an account record without losing the admin login."""

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from werkzeug.security import check_password_hash, generate_password_hash

from server import SEED, create_app


class AccountMigrationTests(unittest.TestCase):
    def test_existing_admin_is_seeded_once_without_replacing_credentials(self):
        with TemporaryDirectory() as directory:
            instance = Path(directory)
            old_hash = generate_password_hash("existing-admin-password")
            (instance / "credentials.json").write_text(
                json.dumps({"password_hash": old_hash, "secret": "existing-secret"}),
                encoding="utf-8",
            )
            # Model an installation created before the users table existed.
            with sqlite3.connect(instance / "site.sqlite3") as connection:
                connection.execute(
                    "CREATE TABLE site (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO site VALUES (1, 7, ?)",
                    (json.dumps(SEED, ensure_ascii=False),),
                )
            with patch.dict("os.environ", {"MCSA_HTTPS": "0"}):
                app = create_app(directory)
                with sqlite3.connect(instance / "site.sqlite3") as connection:
                    rows = connection.execute(
                        "SELECT username, password_hash, role, permissions, active FROM users"
                    ).fetchall()
                    self.assertEqual(
                        connection.execute("SELECT revision FROM site WHERE id=1").fetchone()[0],
                        7,
                    )
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0], ("admin", old_hash, "super_admin", "[]", 1))
                self.assertTrue(check_password_hash(rows[0][1], "existing-admin-password"))
                self.assertEqual(
                    app.test_client().post(
                        "/api/login",
                        json={"username": "admin", "password": "existing-admin-password"},
                    ).status_code,
                    200,
                )

                create_app(directory)
                with sqlite3.connect(instance / "site.sqlite3") as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT password_hash FROM users WHERE username='admin'"
                        ).fetchone()[0],
                        old_hash,
                    )

                with sqlite3.connect(instance / "site.sqlite3") as connection:
                    connection.execute("DELETE FROM users WHERE username='admin'")
                create_app(directory)
                with sqlite3.connect(instance / "site.sqlite3") as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0
                    )


if __name__ == "__main__":
    unittest.main()
