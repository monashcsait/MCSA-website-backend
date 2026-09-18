"""Run from the backend repository: python -m unittest discover -s tests -v."""

from copy import deepcopy
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from PIL import Image
from server import create_app


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict("os.environ", {
            "MCSA_ADMIN_PASSWORD": "test-password-for-local-checks",
            "MCSA_FRONTEND_URL": "https://club.github.io/mcsa-frontend/",
            "MCSA_PUBLIC_URL": "https://admin.example.org",
            "MCSA_ALLOWED_ORIGINS": "",
            "MCSA_HTTPS": "0",
            "AZURE_TRANSLATOR_KEY": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.app = create_app(self.directory.name)
        self.admin = self.app.test_client()
        self.visitor = self.app.test_client()
        login = self.admin.post("/api/login", json={"username": "admin", "password": "test-password-for-local-checks"})
        self.assertEqual(login.status_code, 200)
        self.csrf = {"X-CSRF-Token": login.json["csrf"]}
        self.current = self.admin.get("/api/admin/site").json

    def save(self, data):
        response = self.admin.put("/api/admin/site", headers=self.csrf, json={"revision": self.current["revision"], "data": data})
        self.assertEqual(response.status_code, 200, response.json)
        self.current = {"revision": response.json["revision"], "data": response.json["data"]}
        return response

    def test_publish_change_unpublish_and_reopen(self):
        image = BytesIO()
        Image.new("RGB", (16, 16), "white").save(image, "PNG")
        image.seek(0)
        uploaded = self.admin.post("/api/upload", headers=self.csrf, data={"file": (image, "cover.png")})
        self.assertEqual(uploaded.status_code, 201)
        data = deepcopy(self.current["data"])
        post = data["posts"][0]
        post["title"]["zh"] = "发布后首次内容"
        post["published"] = True
        post["image"] = uploaded.json["url"]
        data["departments"][0]["url"] = "https://example.org/dept-first"
        data["posts"][1]["title"]["zh"] = "绝不能出现在公开接口的草稿"
        self.save(data)
        first = self.visitor.get("/api/site", headers={"Origin": "https://club.github.io"})
        self.assertEqual(first.json["data"]["posts"][0]["title"]["zh"], "发布后首次内容")
        self.assertNotIn("绝不能出现在公开接口的草稿", str(first.json))
        expected_image = "https://admin.example.org/" + uploaded.json["url"]
        self.assertEqual(first.json["data"]["posts"][0]["image"], expected_image)
        with self.visitor.get("/" + uploaded.json["url"]) as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(first.json["data"]["settings"]["heroLogo"], "https://admin.example.org/images/hero-logo.png")
        # Editing has no public effect until the authenticated save succeeds.
        data = deepcopy(self.current["data"])
        data["posts"][0]["title"]["zh"] = "刷新后第二次内容"
        data["departments"][0]["url"] = "https://example.org/dept-second"
        self.assertEqual(self.visitor.get("/api/site").json["revision"], first.json["revision"])
        self.save(data)
        second = self.visitor.get("/api/site")
        self.assertGreater(second.json["revision"], first.json["revision"])
        self.assertEqual(second.json["data"]["posts"][0]["title"]["zh"], "刷新后第二次内容")
        self.assertEqual(second.json["data"]["departments"][0]["url"], "https://example.org/dept-second")
        # A service restart reads the same persistent database.
        reopened = create_app(self.directory.name).test_client().get("/api/site")
        self.assertEqual(reopened.json, second.json)
        data = deepcopy(self.current["data"])
        data["posts"][0]["published"] = False
        self.save(data)
        self.assertNotIn("刷新后第二次内容", str(self.visitor.get("/api/site").json))

    def test_only_public_feed_has_cors_and_never_uses_cookies(self):
        allowed = self.visitor.get("/api/site", headers={"Origin": "https://club.github.io"})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], "https://club.github.io")
        self.assertIn("Origin", allowed.headers["Vary"])
        self.assertIn("no-store", allowed.headers["Cache-Control"])
        self.assertNotIn("Access-Control-Allow-Credentials", allowed.headers)
        for origin in ["https://club.github.io.evil.example", "null", "https://other.example"]:
            result = self.visitor.get("/api/site", headers={"Origin": origin})
            self.assertNotIn("Access-Control-Allow-Origin", result.headers)
        admin = self.visitor.get("/api/admin/site", headers={"Origin": "https://club.github.io"})
        self.assertEqual(admin.status_code, 401)
        self.assertNotIn("Access-Control-Allow-Origin", admin.headers)
        preflight = self.visitor.options("/api/site", headers={"Origin": "https://club.github.io", "Access-Control-Request-Method": "GET"})
        self.assertEqual(preflight.headers["Access-Control-Allow-Methods"], "GET, HEAD, OPTIONS")
        bad_preflight = self.visitor.options("/api/site", headers={"Origin": "https://club.github.io", "Access-Control-Request-Method": "PUT"})
        self.assertNotIn("Access-Control-Allow-Origin", bad_preflight.headers)

    def test_anonymous_and_csrf_writes_cannot_publish(self):
        data = deepcopy(self.current)
        before = self.visitor.get("/api/site").json
        self.assertEqual(self.visitor.put("/api/admin/site", json=data).status_code, 401)
        self.assertEqual(self.admin.put("/api/admin/site", json=data).status_code, 403)
        self.assertEqual(self.visitor.put("/api/site", json=data).status_code, 405)
        self.assertEqual(self.visitor.get("/api/site").json, before)
        for private in ["/seed.json", "/data/site.js", "/instance/credentials.json", "/server.py", "/deployment.json", "/api/export"]:
            self.assertEqual(self.visitor.get(private).status_code, 404, private)

    def test_concurrent_edits_require_current_revision(self):
        stale = deepcopy(self.current)
        self.save(self.current["data"])
        response = self.admin.put("/api/admin/site", headers=self.csrf, json=stale)
        self.assertEqual(response.status_code, 409)

    def test_new_admin_shell_and_preview_target(self):
        self.assertEqual(self.visitor.get("/").location, "/admin.html")
        with self.visitor.get("/admin.html") as response:
            shell = response.text
        self.assertIn("admin-runtime.js", shell)
        self.assertNotIn("data/site.js", shell)
        config = self.visitor.get("/assets/config.js")
        self.assertIn("https://club.github.io/mcsa-frontend/", config.text)
        self.assertEqual(config.headers["Cache-Control"], "no-store")
        self.assertIn('href="', shell)


if __name__ == "__main__":
    unittest.main()
