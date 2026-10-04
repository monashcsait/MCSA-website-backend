"""Merchant-only RBAC and a complete offline backup/restore drill."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest

from PIL import Image
from operations import create_backup, restore_to_new_directory, verify_archive
from server import create_app


class MerchantOperationsTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict("os.environ", {
            "MCSA_ADMIN_PASSWORD": "local-super-password-123",
            "MCSA_FRONTEND_URL": "http://127.0.0.1:8080",
            "MCSA_PUBLIC_URL": "http://127.0.0.1:8000",
            "AZURE_TRANSLATOR_KEY": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.instance = Path(self.directory.name) / "instance"
        self.app = create_app(self.instance)
        self.owner = self.app.test_client()
        login = self.owner.post("/api/login", json={"username": "admin", "password": "local-super-password-123"})
        self.csrf = {"X-CSRF-Token": login.json["csrf"]}

    def test_merchant_admin_can_publish_only_merchants_and_revoke_session(self):
        created = self.owner.post("/api/admin/accounts", headers=self.csrf, json={
            "username": "merchant_editor", "password": "merchant-password-123",
            "role": "admin", "active": True,
            "permissions": ["merchant.read", "merchant.write", "media.upload"],
        })
        self.assertEqual(created.status_code, 201, created.json)
        client = self.app.test_client()
        login = client.post("/api/login", json={"username": "merchant_editor", "password": "merchant-password-123"})
        self.assertEqual(login.status_code, 200)
        headers = {"X-CSRF-Token": login.json["csrf"]}
        self.assertEqual(client.get("/api/admin/site").status_code, 403)
        self.assertEqual(client.get("/api/admin/accounts").status_code, 403)
        self.assertEqual(client.get("/api/backup").status_code, 403)
        merchant_data = client.get("/api/admin/merchants").json
        self.assertEqual(set(merchant_data["data"]), {"merchants", "regions", "categories"})
        self.assertEqual(client.put("/api/admin/merchants", json=merchant_data).status_code, 403)
        self.assertEqual(client.put("/api/admin/site", json=merchant_data, headers=headers).status_code, 403)

        unauthorized = deepcopy(merchant_data)
        unauthorized["data"]["settings"] = {"email": "attacker@example.org"}
        self.assertEqual(client.put("/api/admin/merchants", json=unauthorized, headers=headers).status_code, 400)

        merchant_data["data"]["merchants"] = [{
            "id": "first", "name": {"zh": "测试店", "en": "Test", "hant": "測試店"},
            "text": {"zh": "优惠", "en": "Offer", "hant": "優惠"},
            "image": "", "url": "", "region": merchant_data["data"]["regions"][0]["id"],
            "category": merchant_data["data"]["categories"][0]["id"],
            "address": "1 Example Street", "latitude": -37.9, "longitude": 145.1,
            "published": True,
        }]
        saved = client.put("/api/admin/merchants", json=merchant_data, headers=headers)
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(self.owner.get("/api/admin/site").json["data"]["merchants"][0]["name"]["zh"], "测试店")
        self.assertEqual(self.owner.get("/api/site").json["data"]["merchants"][0]["address"], "1 Example Street")
        self.assertEqual(client.put("/api/admin/merchants", json=merchant_data, headers=headers).status_code, 409)

        invalid = deepcopy(saved.json)
        invalid["data"]["merchants"][0]["latitude"] = 200
        self.assertEqual(client.put("/api/admin/merchants", json=invalid, headers=headers).json["error"], "invalid_merchant_coordinates")
        changed = self.owner.put(f"/api/admin/accounts/{created.json['account']['id']}", headers=self.csrf, json={
            "username": "merchant_editor", "role": "admin", "active": False,
            "permissions": ["merchant.read", "merchant.write", "media.upload"],
        })
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(client.get("/api/admin/merchants").status_code, 401)

    def test_full_backup_verify_and_restore_preserve_accounts_and_media(self):
        image = BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, "PNG")
        image.seek(0)
        uploaded = self.owner.post("/api/upload", headers=self.csrf, data={"file": (image, "pic.png")})
        self.assertEqual(uploaded.status_code, 201)
        created = self.owner.post("/api/admin/accounts", headers=self.csrf, json={
            "username": "backup_editor", "password": "backup-password-123",
            "role": "admin", "active": True, "permissions": ["site.read"],
        })
        self.assertEqual(created.status_code, 201)
        archive = create_backup(self.instance, Path(self.directory.name) / "archives")
        self.assertEqual(verify_archive(archive), 1)
        restored = restore_to_new_directory(archive, Path(self.directory.name) / "restored")
        self.assertEqual((restored / uploaded.json["url"]).read_bytes(), (self.instance / uploaded.json["url"]).read_bytes())
        self.assertEqual((restored / "credentials.json").read_bytes(), (self.instance / "credentials.json").read_bytes())
        with sqlite3.connect(restored / "site.sqlite3") as db:
            self.assertEqual(db.execute("SELECT username FROM users WHERE username='backup_editor'").fetchone()[0], "backup_editor")
        self.assertEqual(create_app(restored).test_client().get("/healthz").status_code, 200)
        with self.assertRaises(FileExistsError):
            restore_to_new_directory(archive, restored)


if __name__ == "__main__":
    unittest.main()
