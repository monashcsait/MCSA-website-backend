"""Existing installations gain an account record without losing the admin login."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from werkzeug.security import check_password_hash, generate_password_hash

from server import SEED, create_app, reset_admin_account


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


class AccountAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(
            "os.environ",
            {"MCSA_ADMIN_PASSWORD": "original-admin-password", "MCSA_HTTPS": "0"},
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_app(self.directory.name)
        self.client = self.app.test_client()

    def login(self, username="admin", password="original-admin-password"):
        return self.client.post(
            "/api/login", json={"username": username, "password": password}
        )

    def test_disabled_account_loses_access_and_cannot_log_in_again(self):
        result = self.login()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["user"]["role"], "super_admin")
        self.assertEqual(self.client.get("/api/admin/site").status_code, 200)
        with sqlite3.connect(Path(self.directory.name) / "site.sqlite3") as connection:
            connection.execute("UPDATE users SET active=0 WHERE username='admin'")
        self.assertFalse(self.client.get("/api/session").json["authenticated"])
        self.assertEqual(self.client.get("/api/admin/site").status_code, 401)
        self.assertEqual(self.login().status_code, 401)

    def test_password_reset_invalidates_existing_session(self):
        self.assertEqual(self.login().status_code, 200)
        reset_admin_account(
            self.directory.name, generate_password_hash("replacement-admin-password")
        )
        self.assertFalse(self.client.get("/api/session").json["authenticated"])
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(
            self.login(password="replacement-admin-password").status_code, 200
        )

    def test_reset_command_updates_account_and_legacy_credentials_together(self):
        instance = Path(self.directory.name)
        old_secret = json.loads((instance / "credentials.json").read_text())["secret"]
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "start.py"), "--reset-password"],
            input="replacement-admin-password\nreplacement-admin-password\n",
            text=True,
            capture_output=True,
            env={**os.environ, "MCSA_INSTANCE": self.directory.name},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        credentials = json.loads((instance / "credentials.json").read_text())
        self.assertNotEqual(credentials["secret"], old_secret)
        with sqlite3.connect(instance / "site.sqlite3") as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT password_hash FROM users WHERE username='admin'"
                ).fetchone()[0],
                credentials["password_hash"],
            )
        restarted = create_app(self.directory.name).test_client()
        self.assertEqual(
            restarted.post(
                "/api/login", json={"username": "admin", "password": "original-admin-password"}
            ).status_code,
            401,
        )
        self.assertEqual(
            restarted.post(
                "/api/login", json={"username": "admin", "password": "replacement-admin-password"}
            ).status_code,
            200,
        )

    def test_regular_admin_cannot_use_super_admin_routes(self):
        with sqlite3.connect(Path(self.directory.name) / "site.sqlite3") as connection:
            connection.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("editor", generate_password_hash("editor-password-123"), "admin"),
            )
        result = self.login("editor", "editor-password-123")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["user"]["role"], "admin")
        self.assertEqual(self.client.get("/api/admin/site").status_code, 403)
        self.assertEqual(self.client.get("/api/backup").status_code, 403)
        self.assertEqual(
            self.client.put(
                "/api/admin/site",
                json={},
                headers={"X-CSRF-Token": result.json["csrf"]},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/logout", headers={"X-CSRF-Token": result.json["csrf"]}
            ).status_code,
            200,
        )
        self.assertFalse(self.client.get("/api/session").json["authenticated"])


if __name__ == "__main__":
    unittest.main()
