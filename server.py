"""网站后台入口：管理内容、账号、图片和备份，并向前端提供公开数据。"""

from pathlib import Path
from datetime import timedelta
from contextlib import closing
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
    g,
)
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, UnidentifiedImageError
from content_delivery import deployment_settings, published_content

# 项目目录和默认内容模板；首次建库以及旧数据迁移都会用到 SEED。
ROOT = Path(__file__).resolve().parent
SEED = json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))
# 普通管理员可被授予的权限；超级管理员始终拥有全部权限。
ACCOUNT_PERMISSIONS = frozenset({"site.read", "site.write", "media.upload", "backup.download"})


def account_input(body, *, creating=False):
    """检查账号表单，并整理成写入数据库所需的字段。"""
    if not isinstance(body, dict):
        raise ValueError("invalid_account")
    username = body.get("username")
    role = body.get("role")
    active = body.get("active", True)
    permissions = body.get("permissions", [])
    password = body.get("password", "")
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        raise ValueError("invalid_username")
    if not isinstance(role, str) or role not in {"super_admin", "admin"} or type(active) is not bool:
        raise ValueError("invalid_role")
    if (
        not isinstance(permissions, list)
        or any(not isinstance(item, str) or item not in ACCOUNT_PERMISSIONS for item in permissions)
    ):
        raise ValueError("invalid_permissions")
    if len(permissions) != len(set(permissions)):
        raise ValueError("invalid_permissions")
    # 编辑或上传时也必须能读取内容，否则后台无法正常使用这些功能。
    if role == "admin" and {"site.write", "media.upload"}.intersection(permissions) and "site.read" not in permissions:
        raise ValueError("invalid_permissions")
    if not isinstance(password, str) or len(password) > 1024 or (creating and len(password) < 12) or (password and len(password) < 12):
        raise ValueError("invalid_password")
    return username, role, active, [] if role == "super_admin" else sorted(permissions), password


def effective_permissions(role, stored):
    """计算账号实际权限；异常的权限数据按无权限处理。"""
    if role == "super_admin":
        return sorted(ACCOUNT_PERMISSIONS)
    try:
        permissions = json.loads(stored)
    except (TypeError, ValueError):
        return []
    if not isinstance(permissions, list) or any(
        not isinstance(item, str) or item not in ACCOUNT_PERMISSIONS for item in permissions
    ):
        return []
    return sorted(set(permissions))


def public_account(row):
    """生成可发给前端的账号信息，不包含密码哈希。"""
    return {
        "id": row[0],
        "username": row[1],
        "role": row[2],
        "permissions": effective_permissions(row[2], row[3]),
        "active": bool(row[4]),
        "createdAt": row[5],
    }


def valid_url(v, media=False):
    """只允许正常的网页链接，或符合规则的站内页面与图片路径。"""
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
    """保存内容前检查整份数据的结构、类型和取值范围。"""
    if not isinstance(content, dict) or set(content) != set(SEED):
        raise ValueError("invalid_content")

    def check(value, key=""):
        # 递归检查嵌套字段，包括多语言文字、图片裁剪参数和链接。
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
    # 每类内容至少需要哪些字段，以及列表条目的 ID 是否有效、重复。
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
    # 以下是各栏目的额外业务规则，不能只靠字段是否存在来判断。
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
    # 网站设置和版式参数会直接影响页面展示，需要单独限制。
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
    """把旧版内容补齐到当前结构，尽量保留已有文章和链接。"""
    if content.get("schemaVersion") == 4:
        return content
    # 先迁移多语言数据，再补入新版默认字段。
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
    # 这些静态页面按当前版本模板更新；其他编辑内容尽量沿用旧数据。
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


def reset_admin_account(instance_path, password_hash):
    """管理员重置密码时，同步更新数据库账号并使旧会话失效。"""
    db = Path(instance_path) / "site.sqlite3"
    if not db.exists():
        return
    with closing(sqlite3.connect(db, timeout=15)) as connection, connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not exists:
            return
        connection.execute(
            """INSERT INTO users (username, password_hash, role) VALUES ('admin', ?, 'super_admin')
            ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash,
                role='super_admin',
                active=1,
                auth_version=users.auth_version+1""",
            (password_hash,),
        )


def create_app(instance_path=None):
    """初始化本地数据、Flask 配置和所有网站接口。"""
    frontend_url, backend_url, allowed_origins = deployment_settings(ROOT)
    # instance 存运行数据；media 存上传的图片，凭据文件与源码分开保存。
    inst = Path(
        instance_path or os.environ.get("MCSA_INSTANCE", str(ROOT / "instance"))
    )
    inst.mkdir(parents=True, exist_ok=True)
    media = inst / "media"
    media.mkdir(exist_ok=True)
    credentials = inst / "credentials.json"
    if not credentials.exists():
        # 首次启动时生成管理员密码哈希和用于签名会话的密钥。
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
        """连接 SQLite，并开启适合同时读写的 WAL 模式。"""
        c = sqlite3.connect(db, timeout=15)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    # 首次运行时建内容表和账号表；已有数据库则保留其中的数据。
    with conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS site (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,data TEXT NOT NULL)"
        )
        c.execute(
            "INSERT OR IGNORE INTO site VALUES (1,0,?)",
            (json.dumps(SEED, ensure_ascii=False),),
        )
        users_table_exists = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone() is not None
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('super_admin', 'admin')),
                permissions TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                auth_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        # 只在首次创建账号表时迁入旧管理员，避免重建已被删除的账号。
        if not users_table_exists:
            c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", cred["password_hash"], "super_admin"),
            )
    # 旧内容升级到 v4 前，留一份原始 JSON 供人工恢复。
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
    # 会话 Cookie、上传大小等基础安全配置。
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
        """读取当前内容和修订号；旧格式会在返回前迁移。"""
        with conn() as c:
            r, d = c.execute("SELECT revision,data FROM site WHERE id=1").fetchone()
        return r, migrate(json.loads(d))

    def current_user():
        """按会话里的账号 ID 重新查库，确认账号仍启用且会话未过期。"""
        user_id = session.get("user_id")
        auth_version = session.get("auth_version")
        if type(user_id) is not int or type(auth_version) is not int:
            if session:
                session.clear()
            return None
        with closing(conn()) as c:
            row = c.execute(
                "SELECT id, username, role, permissions, active, auth_version FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        # 停用账号或修改账号时，数据库中的版本变化会让旧会话失效。
        if not row or row[4] != 1 or row[5] != auth_version:
            session.clear()
            return None
        return {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "permissions": effective_permissions(row[2], row[3]),
        }

    def guard(fn=None, *, require_super_admin=True, permission=None):
        """保护接口：先检查登录与权限，写请求还要验证 CSRF。"""
        if fn is None:
            return lambda protected: guard(
                protected, require_super_admin=require_super_admin, permission=permission
            )

        @wraps(fn)
        def wrap(*a, **kw):
            user = current_user()
            if user is None:
                return jsonify(error="login_required"), 401
            # 超级管理员直接通过；普通管理员按接口要求的权限判断。
            if user["role"] != "super_admin":
                allowed = (
                    permission in user["permissions"]
                    if permission is not None
                    else not require_super_admin
                )
                if not allowed:
                    return jsonify(error="forbidden"), 403
            # 防止别的网站借用浏览器里现有的登录状态发起修改请求。
            if request.method not in ["GET", "HEAD"]:
                csrf = session.get("csrf")
                if not isinstance(csrf, str) or not csrf or not secrets.compare_digest(
                    request.headers.get("X-CSRF-Token", ""), csrf
                ):
                    return jsonify(error="csrf_failed"), 403
            g.current_user = user
            return fn(*a, **kw)

        return wrap

    @app.after_request
    def headers(r):
        """为响应设置安全与缓存头，只允许公开内容接口跨域读取。"""
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
        # 只有公开内容可供指定的前端域名跨域读取，不开放后台接口。
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
        """把上传过大的异常转成前端可识别的错误。"""
        return jsonify(error="file_too_large"), 413

    @app.get("/api/translation-status")
    @guard(permission="site.read")
    def translation_status():
        """告诉后台当前是否配置了英文自动翻译服务。"""
        return jsonify(configured=bool(os.environ.get("AZURE_TRANSLATOR_KEY")))

    @app.get("/api/session")
    def session_info():
        """供后台刷新页面后恢复登录状态、角色和权限。"""
        user = current_user()
        return jsonify(
            authenticated=user is not None,
            csrf=session.get("csrf") if user else None,
            user=user,
        )

    @app.post("/api/login")
    def login():
        """验证账号密码，创建带 CSRF 令牌的登录会话。"""
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error="origin_rejected"), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            body = {}
        # 同一 IP 五分钟内最多尝试十次，减少密码猜测风险。
        ip = request.remote_addr
        now = time.monotonic()
        with lock:
            times = [x for x in attempts.get(ip, []) if now - x < 300]
            attempts[ip] = times
            if len(times) >= 10:
                return jsonify(error="too_many_attempts"), 429
            times.append(now)
        username = body.get("username")
        pwd = body.get("password")
        if not isinstance(username, str) or len(username) > 100 or not isinstance(pwd, str) or len(pwd) > 1024:
            return jsonify(error="invalid_login"), 401
        # 账号和密码哈希存放在 SQLite users 表中。
        with closing(conn()) as c:
            account = c.execute(
                "SELECT id, username, password_hash, role, permissions, active, auth_version FROM users WHERE username=?",
                (username,),
            ).fetchone()
        if not account or account[5] != 1 or not check_password_hash(account[2], pwd):
            return jsonify(error="invalid_login"), 401
        with lock:
            attempts.pop(ip, None)
        # 登录成功后重建会话，记录账号版本和写请求使用的 CSRF 令牌。
        session.clear()
        session["user_id"] = account[0]
        session["auth_version"] = account[6]
        session["csrf"] = secrets.token_hex(24)
        session.permanent = True
        return jsonify(
            authenticated=True,
            csrf=session["csrf"],
            user={
                "id": account[0],
                "username": account[1],
                "role": account[3],
                "permissions": effective_permissions(account[3], account[4]),
            },
        )

    @app.post("/api/logout")
    @guard(require_super_admin=False)
    def logout():
        """清除当前账号的登录会话。"""
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/admin/accounts")
    @guard
    def list_accounts():
        """仅超级管理员可查看账号列表。"""
        with closing(conn()) as c:
            rows = c.execute(
                "SELECT id, username, role, permissions, active, created_at FROM users ORDER BY username"
            ).fetchall()
        return jsonify(accounts=[public_account(row) for row in rows])

    @app.post("/api/admin/accounts")
    @guard
    def create_account():
        """仅超级管理员可创建账号，密码先哈希再写入数据库。"""
        try:
            username, role, active, permissions, password = account_input(
                request.get_json(silent=True), creating=True
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        try:
            with closing(conn()) as c, c:
                cursor = c.execute(
                    "INSERT INTO users (username, password_hash, role, permissions, active) VALUES (?, ?, ?, ?, ?)",
                    (username, generate_password_hash(password), role, json.dumps(permissions), int(active)),
                )
                row = c.execute(
                    "SELECT id, username, role, permissions, active, created_at FROM users WHERE id=?",
                    (cursor.lastrowid,),
                ).fetchone()
        except sqlite3.IntegrityError:
            return jsonify(error="username_taken"), 409
        return jsonify(account=public_account(row)), 201

    @app.put("/api/admin/accounts/<int:user_id>")
    @guard
    def update_account(user_id):
        """修改账号资料、权限或状态，并按需撤销旧会话。"""
        try:
            username, role, active, permissions, password = account_input(
                request.get_json(silent=True)
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        encoded_permissions = json.dumps(permissions)
        try:
            with closing(conn()) as c, c:
                # 在同一事务内检查和更新，避免并发修改时漏掉最后一位超级管理员。
                c.execute("BEGIN IMMEDIATE")
                previous = c.execute(
                    "SELECT username, role, permissions, active FROM users WHERE id=?",
                    (user_id,),
                ).fetchone()
                if previous is None:
                    return jsonify(error="account_not_found"), 404
                if previous[1] == "super_admin" and previous[3] == 1 and (
                    role != "super_admin" or not active
                ):
                    remaining = c.execute(
                        "SELECT COUNT(*) FROM users WHERE role='super_admin' AND active=1"
                    ).fetchone()[0]
                    if remaining <= 1:
                        return jsonify(error="last_super_admin"), 409
                # 资料、权限或密码有变化时递增版本，迫使该账号重新登录。
                changed = (
                    previous != (username, role, encoded_permissions, int(active))
                    or bool(password)
                )
                c.execute(
                    """UPDATE users SET username=?, role=?, permissions=?, active=?,
                        password_hash=COALESCE(?, password_hash),
                        auth_version=auth_version+? WHERE id=?""",
                    (
                        username, role, encoded_permissions, int(active),
                        generate_password_hash(password) if password else None,
                        int(changed), user_id,
                    ),
                )
                row = c.execute(
                    "SELECT id, username, role, permissions, active, created_at FROM users WHERE id=?",
                    (user_id,),
                ).fetchone()
        except sqlite3.IntegrityError:
            return jsonify(error="username_taken"), 409
        return jsonify(account=public_account(row))

    @app.get("/api/site")
    def public_site():
        """向官网返回可公开展示的内容，过滤未发布的信息。"""
        rev, d = load()
        return jsonify(revision=rev, data=published_content(d, backend_url))

    @app.get("/api/admin/site")
    @guard(permission="site.read")
    def admin_site():
        """向有查看权限的后台账号返回完整可编辑内容。"""
        rev, d = load()
        return jsonify(revision=rev, data=d)

    @app.put("/api/admin/site")
    @guard(permission="site.write")
    def save_site():
        """校验、翻译并保存整份内容；修订号不一致时拒绝覆盖。"""
        body = request.get_json(silent=True)
        try:
            if not isinstance(body, dict) or type(body.get("revision")) != int:
                raise ValueError()
            d = validate(body["data"])
        except (ValueError, KeyError, TypeError, AttributeError):
            return jsonify(error="invalid_content"), 400
        from translations import translate_changes

        # 先检查客户端基于哪个版本编辑，再翻译改动。
        current_revision, previous = load()
        if current_revision != body["revision"]:
            return jsonify(error="revision_conflict"), 409
        warnings = translate_changes(d, previous)
        # 写入前在事务中复查版本，防止两位管理员同时保存互相覆盖。
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
    @guard(permission="media.upload")
    def upload():
        """校验上传图片的大小、格式和尺寸后，保存到 media 目录。"""
        f = request.files.get("file")
        if not f:
            return jsonify(error="missing_file"), 400
        raw = f.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            return jsonify(error="file_too_large"), 413
        # 读取并验证真实图片内容，不能只相信上传时提供的文件名。
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
        # 用随机文件名保存，避免重名覆盖或暴露原始文件名。
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
        """按安全文件名读取已上传的公开图片。"""
        if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|gif|webp)", name):
            abort(404)
        return send_from_directory(media, name)

    @app.get("/api/backup")
    @guard(permission="backup.download")
    def backup():
        """下载内容 JSON 和上传图片组成的 ZIP 备份。"""
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
        """给后台页面提供 API 路径和官网地址。"""
        return app.response_class(
            "window.MCSA_CONFIG=" + json.dumps({"apiBase": "/api", "frontendUrl": frontend_url}).replace("<", "\\u003c") + ";", mimetype="text/javascript"
        )

    @app.get("/")
    def home():
        """访问后台根路径时跳转到登录页面。"""
        return redirect("/admin.html")

    @app.get("/<path:path>")
    def static(path):
        """提供后台静态文件，并阻止读取 web 目录之外的路径。"""
        p = (ROOT / "web" / path).resolve()
        if not p.is_relative_to((ROOT / "web").resolve()) or not p.is_file():
            abort(404)
        return send_from_directory(ROOT / "web", path)

    return app
