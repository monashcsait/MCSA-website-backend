"""MCSA multi-page website and visual CMS. Serve with Waitress via start.py."""

from pathlib import Path
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit
import copy
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import zipfile
from flask import (
    Flask,
    request,
    session,
    jsonify,
    send_from_directory,
    send_file,
    abort,
    redirect,
)
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, UnidentifiedImageError
from content_delivery import deployment_settings, published_content

ROOT = Path(__file__).resolve().parent
SEED = json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))


def valid_url(v, media=False):
    if not isinstance(v, str) or len(v) > 4000 or re.search(r"[\x00-\x20\\]", v):
        return False
    if not v:
        return True
    try:
        u = urlsplit(v)
        if u.scheme:
            return (
                u.scheme in ["https", "http"]
                and bool(u.hostname)
                and not u.username
                and not u.password
            )
    except ValueError:
        return False
    if ".." in v:
        return False
    return (
        bool(
            re.fullmatch(
                r"(?:images|media)/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|gif|webp)", v
            )
        )
        if media
        else bool(
            re.fullmatch(r"[a-zA-Z0-9_-]+\.html(?:#[a-zA-Z0-9_-]+)?|#[a-zA-Z0-9_-]+", v)
        )
    )


def validate(content):
    """Validate the editable tree before writing a new database revision."""
    if not isinstance(content, dict) or set(content) != set(SEED):
        raise ValueError("invalid_content")

    def check(value, key=""):
        if isinstance(value, dict):
            if "zh" in value:
                if set(value) != {"zh", "en", "hant"}:
                    raise ValueError("invalid_translation")
                if not all(
                    isinstance(text, str) and len(text) <= 12000
                    for text in value.values()
                ):
                    raise ValueError("invalid_text")
            else:
                for name, child in value.items():
                    check(child, name)
        elif isinstance(value, list):
            if key == "crop":
                if len(value) != 6 or not all(
                    type(number) in (int, float) and 0 <= number <= 30000
                    for number in value
                ):
                    raise ValueError("invalid_crop")
                x, y, width, height, image_width, image_height = value
                if (
                    width <= 0
                    or height <= 0
                    or x + width > image_width
                    or y + height > image_height
                ):
                    raise ValueError("invalid_crop")
            if len(value) > 1000:
                raise ValueError("too_many_entries")
            for child in value:
                check(child)
        elif isinstance(value, str):
            if len(value) > 12000:
                raise ValueError("text_too_long")
            if key == "url" and not valid_url(value):
                raise ValueError("invalid_url")
            if key in ["image", "logo", "heroLogo", "opening"] and not valid_url(
                value, True
            ):
                raise ValueError("invalid_image")
        elif value is not None and type(value) not in (int, float, bool):
            raise ValueError("invalid_value")

    check(content)
    if content["schemaVersion"] != 4 or set(content["pages"]) != set(SEED["pages"]):
        raise ValueError("invalid_schema")
    for page in content["pages"].values():
        if (
            not isinstance(page, dict)
            or set(page) != {"title", "paragraphs"}
            or not isinstance(page["paragraphs"], list)
        ):
            raise ValueError("invalid_page")
    requirements = {
        "departments": {"id", "name", "intro", "recruitment", "url", "image"},
        "team": {"name", "role", "description", "image", "tags", "url"},
        "terms": {"id", "name", "year", "members"},
        "posts": {
            "id",
            "page",
            "title",
            "text",
            "image",
            "url",
            "published",
            "date",
            "crop",
        },
        "merchants": {"id", "name", "text", "image", "url", "region", "category"},
        "sponsors": {"id", "name", "image", "url"},
        "regions": {"id", "name"},
        "categories": {"id", "name"},
        "footerLinks": {"id", "name", "url"},
        "socials": {"id", "name", "account", "url", "image", "crop"},
    }
    for collection, fields in requirements.items():
        entries = content[collection]
        if not isinstance(entries, list):
            raise ValueError("invalid_collection")
        ids = []
        for entry in entries:
            if not isinstance(entry, dict) or not fields.issubset(entry):
                raise ValueError("missing_fields")
            if "id" in fields:
                if not isinstance(entry["id"], str) or not re.fullmatch(
                    r"[a-zA-Z0-9_-]{1,100}", entry["id"]
                ):
                    raise ValueError("invalid_id")
                ids.append(entry["id"])
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_id")
    if not content["team"]:
        raise ValueError("current_team_required")
    for term in content["terms"]:
        if type(term["year"]) != int or not isinstance(term["members"], list):
            raise ValueError("invalid_term")
        for member in term["members"]:
            if not {"name", "role", "image", "url"}.issubset(member):
                raise ValueError("invalid_member")
    for post in content["posts"]:
        if post["published"] and not post["title"]["zh"].strip():
            raise ValueError("title_required")
        if post["page"] not in content["pages"] or type(post["published"]) != bool:
            raise ValueError("invalid_post")
        if post["date"] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", post["date"]):
            raise ValueError("invalid_date")
    settings = content["settings"]
    if (
        not set(SEED["settings"]).issubset(settings)
        or type(settings["openingDuration"]) != int
        or not 100 <= settings["openingDuration"] <= 30000
    ):
        raise ValueError("invalid_settings")
    if not re.fullmatch(r'[^\s<>"@]+@[^\s<>"@]+\.[^\s<>"@]+', settings["email"]):
        raise ValueError("invalid_email")
    layout = content["layout"]
    ranges = {
        "contentWidth": (960, 1600),
        "baseFontSize": (14, 20),
        "sectionSpacing": (30, 110),
        "cardRadius": (12, 48),
        "heroCardWidth": (300, 520),
        "heroSlope": (15, 80),
        "presidentImageShare": (35, 55),
        "presidentHeight": (420, 680),
        "departmentHeight": (360, 680),
        "departmentSpeed": (5, 50),
        "contactQrSize": (80, 160),
        "contactColumns": (2, 4),
        "carouselSeconds": (4, 20),
    }
    if set(layout) != set(SEED["layout"]):
        raise ValueError("invalid_layout")
    for name, (minimum, maximum) in ranges.items():
        if (
            type(layout[name]) not in (int, float)
            or not minimum <= layout[name] <= maximum
        ):
            raise ValueError("invalid_layout_range")
    for name in ["primaryColor", "backgroundColor"]:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", layout[name]):
            raise ValueError("invalid_color")
    if (
        layout["departmentDirection"] not in ["up", "down"]
        or type(layout["departmentAutoplay"]) != bool
    ):
        raise ValueError("invalid_motion")
    sections = content["homeSections"]
    if not isinstance(sections, list) or sorted(
        item["id"] for item in sections
    ) != sorted(item["id"] for item in SEED["homeSections"]):
        raise ValueError("invalid_sections")
    if any(type(item["visible"]) != bool for item in sections):
        raise ValueError("invalid_visibility")
    for social in content["socials"]:
        if social.get("placement") not in ["qr", "account", "hidden"]:
            raise ValueError("invalid_social_placement")
    return content


def migrate(content):
    """Add new defaults, retaining the site's existing editorial content and links."""
    if content.get("schemaVersion") == 4:
        return content
    from translations import convert_legacy_languages

    convert_legacy_languages(content)
    for key, value in SEED.items():
        content.setdefault(key, copy.deepcopy(value))
    for key, value in SEED["settings"].items():
        content["settings"].setdefault(key, copy.deepcopy(value))
    for key, value in SEED["pages"].items():
        content["pages"].setdefault(key, copy.deepcopy(value))
    for post in content["posts"]:
        post.setdefault("date", "")
        post.setdefault("crop", None)
        if post["page"].startswith("department-"):
            post["page"] = "recruitment"
    for member in content["team"]:
        member.setdefault("url", "")
    defaults = {item["id"]: item for item in SEED["departments"]}
    for department in content["departments"]:
        department.setdefault(
            "keywords",
            copy.deepcopy(
                defaults.get(department["id"], {}).get(
                    "keywords", {"zh": "", "en": "", "hant": ""}
                )
            ),
        )
    for social in content["socials"]:
        identifier = social["id"]
        placement = (
            "qr"
            if identifier in ["wechat", "mini", "xhs", "instagram"]
            else "account" if identifier == "facebook" else "hidden"
        )
        social.setdefault("placement", placement)
        if (
            identifier == "instagram"
            and not social["image"]
            and social["url"] == "https://www.instagram.com/monashcsa/"
        ):
            social["image"] = "images/instagram-qr.png"
            social["crop"] = None
    # These sections are explicitly replaced by the requested homepage revision.
    for page_key in [
        "about",
        "disclaimer",
        "privacy",
        "accessibility",
        "feedback",
        "privacy-settings",
    ]:
        content["pages"][page_key] = copy.deepcopy(SEED["pages"][page_key])
    social_order = {"wechat": 0, "mini": 1, "xhs": 2, "instagram": 3, "facebook": 4}
    content["socials"].sort(key=lambda item: social_order.get(item["id"], 5))
    role_order = {"主席": 0, "对外副主席": 1, "对内副主席": 2}
    content["team"].sort(key=lambda item: role_order.get(item["role"]["zh"], 3))
    content["schemaVersion"] = 4
    return content


def create_app(instance_path=None):
    frontend_url, backend_url, allowed_origins = deployment_settings(ROOT)
    inst = Path(
        instance_path or os.environ.get("MCSA_INSTANCE", str(ROOT / "instance"))
    )
    inst.mkdir(parents=True, exist_ok=True)
    media = inst / "media"
    media.mkdir(exist_ok=True)
    credentials = inst / "credentials.json"
    if not credentials.exists():
        pwd = os.environ.get("MCSA_ADMIN_PASSWORD", "")
        if len(pwd) < 12:
            raise RuntimeError(
                "Run python start.py to set an admin password of at least 12 characters."
            )
        credentials.write_text(
            json.dumps(
                {
                    "password_hash": generate_password_hash(pwd),
                    "secret": secrets.token_hex(32),
                }
            )
        )
        credentials.chmod(0o600)
    cred = json.loads(credentials.read_text())
    db = inst / "site.sqlite3"

    def conn():
        c = sqlite3.connect(db, timeout=15)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    with conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS site (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,data TEXT NOT NULL)"
        )
        c.execute(
            "INSERT OR IGNORE INTO site VALUES (1,0,?)",
            (json.dumps(SEED, ensure_ascii=False),),
        )
    with conn() as connection:
        old_revision, old_json = connection.execute(
            "SELECT revision,data FROM site WHERE id=1"
        ).fetchone()
        if json.loads(old_json).get("schemaVersion") != 4:
            backup_path = inst / "content-before-v4.json"
            if not backup_path.exists():
                backup_path.write_text(
                    json.dumps(
                        {"revision": old_revision, "data": json.loads(old_json)},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    app = Flask(__name__, static_folder=None)
    app.secret_key = cred["secret"]
    app.config.update(
        MAX_CONTENT_LENGTH=13 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("MCSA_HTTPS", "1" if backend_url.startswith("https://") else "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    app.config["MCSA_INSTANCE"] = str(inst)
    attempts = {}
    lock = threading.Lock()

    def load():
        with conn() as c:
            r, d = c.execute("SELECT revision,data FROM site WHERE id=1").fetchone()
        return r, migrate(json.loads(d))

    def guard(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            if not session.get("admin"):
                return jsonify(error="login_required"), 401
            if request.method not in ["GET", "HEAD"] and not secrets.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session.get("csrf", "-")
            ):
                return jsonify(error="csrf_failed"), 403
            return fn(*a, **kw)

        return wrap

    @app.after_request
    def headers(r):
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        r.headers["X-Frame-Options"] = "SAMEORIGIN"
        r.headers["Cache-Control"] = (
            "no-store"
            if request.path.startswith("/api/")
            or request.path.endswith(".html")
            or request.path in ["/", "/data/site.js", "/assets/config.js"]
            else "public, max-age=3600"
        )
        # Only the published feed is readable cross-origin, without admin cookies.
        if request.path == "/api/site":
            r.vary.add("Origin")
            origin = request.headers.get("Origin")
            method = request.headers.get("Access-Control-Request-Method", "GET")
            if origin in allowed_origins and request.method in {"GET", "HEAD", "OPTIONS"} and method in {"GET", "HEAD"}:
                r.headers["Access-Control-Allow-Origin"] = origin
                r.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
            r.headers["Cache-Control"] = "no-store, max-age=0"
        return r

    @app.errorhandler(413)
    def large(e):
        return jsonify(error="file_too_large"), 413

    @app.get("/api/translation-status")
    @guard
    def translation_status():
        return jsonify(configured=bool(os.environ.get("AZURE_TRANSLATOR_KEY")))

    @app.get("/api/session")
    def session_info():
        return jsonify(
            authenticated=bool(session.get("admin")),
            csrf=session.get("csrf") if session.get("admin") else None,
        )

    @app.post("/api/login")
    def login():
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error="origin_rejected"), 403
        body = request.get_json(silent=True) or {}
        ip = request.remote_addr
        now = time.monotonic()
        with lock:
            times = [x for x in attempts.get(ip, []) if now - x < 300]
            attempts[ip] = times
            if len(times) >= 10:
                return jsonify(error="too_many_attempts"), 429
            times.append(now)
        pwd = body.get("password", "")
        if (
            body.get("username") != "admin"
            or not isinstance(pwd, str)
            or len(pwd) > 1024
            or not check_password_hash(cred["password_hash"], pwd)
        ):
            return jsonify(error="invalid_login"), 401
        with lock:
            attempts.pop(ip, None)
        session.clear()
        session["admin"] = True
        session["csrf"] = secrets.token_hex(24)
        session.permanent = True
        return jsonify(authenticated=True, csrf=session["csrf"])

    @app.post("/api/logout")
    @guard
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/site")
    def public_site():
        rev, d = load()
        return jsonify(revision=rev, data=published_content(d, backend_url))

    @app.get("/api/admin/site")
    @guard
    def admin_site():
        rev, d = load()
        return jsonify(revision=rev, data=d)

    @app.put("/api/admin/site")
    @guard
    def save_site():
        body = request.get_json(silent=True)
        try:
            if not isinstance(body, dict) or type(body.get("revision")) != int:
                raise ValueError()
            d = validate(body["data"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return jsonify(error="invalid_content"), 400
        from translations import translate_changes

        current_revision, previous = load()
        if current_revision != body["revision"]:
            return jsonify(error="revision_conflict"), 409
        warnings = translate_changes(d, previous)
        with conn() as c:
            c.execute("BEGIN IMMEDIATE")
            rev = c.execute("SELECT revision FROM site WHERE id=1").fetchone()[0]
            if rev != body["revision"]:
                return jsonify(error="revision_conflict"), 409
            c.execute(
                "UPDATE site SET data=?,revision=revision+1 WHERE id=1",
                (json.dumps(d, ensure_ascii=False),),
            )
        return jsonify(saved=True, revision=rev + 1, data=d, warnings=warnings)

    @app.post("/api/upload")
    @guard
    def upload():
        f = request.files.get("file")
        if not f:
            return jsonify(error="missing_file"), 400
        raw = f.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            return jsonify(error="file_too_large"), 413
        try:
            im = Image.open(io.BytesIO(raw))
            fmt = im.format
            if (
                fmt not in ["PNG", "JPEG", "GIF", "WEBP"]
                or im.width * im.height > 24000000
            ):
                raise ValueError()
            im.verify()
            duration = 0
            if fmt == "GIF":
                im = Image.open(io.BytesIO(raw))
                if im.n_frames > 1000:
                    raise ValueError()
                for i in range(im.n_frames):
                    im.seek(i)
                    duration += im.info.get("duration", 100)
            ext = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}[fmt]
        except (
            ValueError,
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
        ):
            return jsonify(error="invalid_image"), 400
        filename = secrets.token_hex(16) + "." + ext
        (media / filename).write_bytes(raw)
        return (
            jsonify(
                url="media/" + filename,
                duration=min(max(duration, 100), 30000) if duration else None,
            ),
            201,
        )

    @app.get("/media/<name>")
    def get_media(name):
        if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|gif|webp)", name):
            abort(404)
        return send_from_directory(media, name)

    @app.get("/api/backup")
    @guard
    def backup():
        out = io.BytesIO()
        rev, d = load()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "content.json",
                json.dumps({"revision": rev, "data": d}, ensure_ascii=False, indent=2),
            )
            for p in media.glob("*"):
                if p.is_file():
                    z.write(p, "media/" + p.name)
        out.seek(0)
        return send_file(
            out,
            mimetype="application/zip",
            as_attachment=True,
            download_name="MCSA-content-backup.zip",
        )

    @app.get("/assets/config.js")
    def config():
        return app.response_class(
            "window.MCSA_CONFIG=" + json.dumps({"apiBase": "/api", "frontendUrl": frontend_url}).replace("<", "\\u003c") + ";", mimetype="text/javascript"
        )

    @app.get("/")
    def home():
        return redirect("/admin.html")

    @app.get("/<path:path>")
    def static(path):
        p = (ROOT / "web" / path).resolve()
        if not p.is_relative_to((ROOT / "web").resolve()) or not p.is_file():
            abort(404)
        return send_from_directory(ROOT / "web", path)

    return app
