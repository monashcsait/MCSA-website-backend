"""Account management and authorization across the existing CMS endpoints."""

from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from server import create_app


class AccountPermissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(
            "os.environ",
            {"MCSA_ADMIN_PASSWORD": "super-admin-password", "MCSA_HTTPS": "0"},
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_app(self.directory.name)
        self.owner = self.app.test_client()
        login = self.owner.post(
            "/api/login", json={"username": "admin", "password": "super-admin-password"}
        )
        self.assertEqual(login.status_code, 200)
        self.owner_headers = {"X-CSRF-Token": login.json["csrf"]}

    def create_account(self, **changes):
        body = {
            "username": "editor",
            "password": "editor-password-123",
            "role": "admin",
            "active": True,
            "permissions": ["site.read"],
            **changes,
        }
        return self.owner.post(
            "/api/admin/accounts", json=body, headers=self.owner_headers
        )

    def test_account_creation_listing_and_private_fields(self):
        created = self.create_account()
        self.assertEqual(created.status_code, 201, created.json)
        account = created.json["account"]
        self.assertEqual(account["username"], "editor")
        self.assertEqual(account["permissions"], ["site.read"])
        self.assertNotIn("password_hash", str(created.json))
        listed = self.owner.get("/api/admin/accounts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json["accounts"]), 2)
        self.assertNotIn("password_hash", str(listed.json))
        duplicate = self.create_account(username="EDITOR")
        self.assertEqual(duplicate.status_code, 409)

    def test_granted_permissions_apply_on_backend_and_changes_revoke_sessions(self):
        account = self.create_account().json["account"]
        editor = self.app.test_client()
        login = editor.post(
            "/api/login", json={"username": "editor", "password": "editor-password-123"}
        )
        self.assertEqual(login.status_code, 200)
        csrf = {"X-CSRF-Token": login.json["csrf"]}
        snapshot = editor.get("/api/admin/site")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(editor.get("/api/admin/accounts").status_code, 403)
        self.assertEqual(editor.get("/api/backup").status_code, 403)
        self.assertEqual(editor.post("/api/upload", headers=csrf).status_code, 403)
        self.assertEqual(
            editor.put("/api/admin/site", json=snapshot.json, headers=csrf).status_code,
            403,
        )

        update = self.owner.put(
            f"/api/admin/accounts/{account['id']}",
            headers=self.owner_headers,
            json={
                "username": "editor",
                "role": "admin",
                "active": True,
                "permissions": ["site.read", "site.write", "media.upload"],
            },
        )
        self.assertEqual(update.status_code, 200, update.json)
        self.assertFalse(editor.get("/api/session").json["authenticated"])
        fresh_login = editor.post(
            "/api/login", json={"username": "editor", "password": "editor-password-123"}
        )
        self.assertEqual(fresh_login.status_code, 200)
        save = editor.put(
            "/api/admin/site",
            headers={"X-CSRF-Token": fresh_login.json["csrf"]},
            json=snapshot.json,
        )
        self.assertEqual(save.status_code, 200, save.json)
        self.assertEqual(
            editor.post(
                "/api/upload", headers={"X-CSRF-Token": fresh_login.json["csrf"]}
            ).status_code,
            400,
        )
        self.assertEqual(editor.get("/api/backup").status_code, 403)

        disabled = self.owner.put(
            f"/api/admin/accounts/{account['id']}",
            headers=self.owner_headers,
            json={
                "username": "editor",
                "role": "admin",
                "active": False,
                "permissions": ["site.read", "site.write", "media.upload"],
            },
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(editor.get("/api/admin/site").status_code, 401)
        self.assertEqual(
            editor.post(
                "/api/login", json={"username": "editor", "password": "editor-password-123"}
            ).status_code,
            401,
        )

    def test_cannot_remove_last_active_super_admin(self):
        owner = self.owner.get("/api/admin/accounts").json["accounts"][0]
        response = self.owner.put(
            f"/api/admin/accounts/{owner['id']}",
            headers=self.owner_headers,
            json={"username": "admin", "role": "admin", "active": True, "permissions": []},
        )
        self.assertEqual(response.status_code, 409)
        response = self.owner.put(
            f"/api/admin/accounts/{owner['id']}",
            headers=self.owner_headers,
            json={"username": "admin", "role": "super_admin", "active": False},
        )
        self.assertEqual(response.status_code, 409)

    def test_backup_permission_can_be_granted_without_content_editor(self):
        created = self.create_account(permissions=["backup.download"])
        self.assertEqual(created.status_code, 201)
        editor = self.app.test_client()
        login = editor.post(
            "/api/login", json={"username": "editor", "password": "editor-password-123"}
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(editor.get("/api/admin/site").status_code, 403)
        backup = editor.get("/api/backup")
        self.assertEqual(backup.status_code, 200)
        self.assertEqual(backup.mimetype, "application/zip")

    def test_rejects_invalid_account_payloads(self):
        self.assertEqual(
            self.owner.post(
                "/api/admin/accounts",
                json={"username": "no_csrf", "password": "long-enough-password", "role": "admin"},
            ).status_code,
            403,
        )
        for body in [
            {"username": "x", "password": "long-enough-password", "role": "admin"},
            {"username": "valid", "password": "short", "role": "admin"},
            {"username": "valid", "password": "long-enough-password", "role": "admin", "permissions": ["site.write"]},
            {"username": "valid", "password": "long-enough-password", "role": "admin", "permissions": ["media.upload"]},
            {"username": "valid", "password": "long-enough-password", "role": "admin", "permissions": [{"bad": 1}]},
            {"username": "valid", "password": "long-enough-password", "role": ["admin"]},
        ]:
            response = self.owner.post(
                "/api/admin/accounts", json=body, headers=self.owner_headers
            )
            self.assertEqual(response.status_code, 400, body)


if __name__ == "__main__":
    unittest.main()
