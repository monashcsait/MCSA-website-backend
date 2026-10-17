"""Persistent, loopback-only conference demo. No production configuration changes."""

from contextlib import closing
from pathlib import Path
import argparse
import getpass
import json
import os
import socket
import sqlite3

ROOT = Path(__file__).resolve().parent
DEFAULT_INSTANCE = ROOT / "instance-demo"
DEFAULT_FRONTEND = ROOT.parent / "MCSA-offical-website"
DEFAULT_BACKUPS = ROOT / "demo-backups"


def prepare_content(instance):
    """Hide unconfirmed mini-program entries in a backed-up demo copy only."""
    from server import validate

    with closing(sqlite3.connect(instance / "site.sqlite3")) as db:
        revision, raw = db.execute("SELECT revision,data FROM site WHERE id=1").fetchone()
        content = json.loads(raw)
        changed = 0
        for item in content.get("socials", []):
            if "小程序" in item.get("name", {}).get("zh", "") and item.get("placement") != "hidden":
                item["placement"] = "hidden"
                changed += 1
        if changed:
            validate(content)
            with db:
                db.execute("UPDATE site SET revision=?,data=? WHERE id=1", (revision + 1, json.dumps(content, ensure_ascii=False)))
        return changed


def build_app(instance, frontend, port, *, initialize=False):
    # Override addresses in this process only. Serve both websites from one origin.
    origin = f"http://127.0.0.1:{port}"
    os.environ.update({
        "MCSA_FRONTEND_URL": origin + "/site/",
        "MCSA_PUBLIC_URL": origin,
        "MCSA_ALLOWED_ORIGINS": origin,
        "MCSA_HTTPS": "0",
        "AZURE_TRANSLATOR_KEY": "",  # Local demonstration requires no external service.
    })
    from flask import abort, redirect, send_from_directory
    from server import create_app

    if not initialize and not (instance / "credentials.json").is_file():
        raise ValueError("Initialize or import the demo instance first; see local_demo.py --help")
    app = create_app(instance)

    @app.get("/site")
    def site_redirect():
        return redirect("/site/")

    @app.get("/site/")
    @app.get("/site/<path:path>")
    def site_file(path="index.html"):
        if path == "assets/config.js":
            return app.response_class("window.MCSA_CONFIG=" + json.dumps({"apiBase": origin + "/api"}) + ";", mimetype="text/javascript")
        candidate = (frontend / path).resolve()
        extensions = {".html", ".js", ".css", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".mp4", ".webm"}
        if (not candidate.is_relative_to(frontend) or not candidate.is_file()
                or any(part.startswith(".") for part in Path(path).parts)
                or candidate.suffix.lower() not in extensions):
            abort(404)
        return send_from_directory(frontend, path)

    @app.after_request
    def demo_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND)
    parser.add_argument("--backups", type=Path, default=DEFAULT_BACKUPS)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize a new demo; enter a password locally")
    importer = commands.add_parser("import-instance", help="Back up and copy an existing instance; never overwrite")
    importer.add_argument("source", type=Path)
    starter = commands.add_parser("serve", help="Start the persistent demo on 127.0.0.1")
    starter.add_argument("--port", type=int, default=18091)
    commands.add_parser("backup", help="Create a private full backup; retain all prior archives")
    verifier = commands.add_parser("verify", help="Check a full archive")
    verifier.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="Restore to a NEW directory only")
    restore.add_argument("archive", type=Path)
    restore.add_argument("new_directory", type=Path)
    args = parser.parse_args()
    instance, frontend, backups = args.instance.resolve(), args.frontend.resolve(), args.backups.resolve()
    from operations import create_backup, restore_to_new_directory, verify_archive

    if args.command == "import-instance":
        if instance.exists():
            raise FileExistsError("Demo destination already exists; no files were replaced")
        source = args.source.resolve()
        if source == instance or instance.is_relative_to(source) or source.is_relative_to(instance):
            raise ValueError("Source and destination must be separate directories")
        archive = create_backup(source, backups, keep=1000000)
        restore_to_new_directory(archive, instance)
        print(f"Imported a backed-up COPY. Hidden mini-program entries: {prepare_content(instance)}. Source untouched.")
    elif args.command == "init":
        if instance.exists():
            raise FileExistsError("Initialization requires a new directory; existing accounts were not changed")
        password = getpass.getpass("New demo password (minimum 12 characters): ")
        if len(password) < 12 or password != getpass.getpass("Repeat password: "):
            raise ValueError("Passwords must match and contain at least 12 characters")
        os.environ["MCSA_ADMIN_PASSWORD"] = password
        build_app(instance, frontend, 18091, initialize=True)
        del os.environ["MCSA_ADMIN_PASSWORD"]
        prepare_content(instance)
        print("Persistent demo initialized. Username: admin. Password was not printed or saved as plain text.")
    elif args.command == "backup":
        print(create_backup(instance, backups, keep=1000000))
    elif args.command == "verify":
        print(f"Verified full backup; media files: {verify_archive(args.archive)}")
    elif args.command == "restore":
        print(restore_to_new_directory(args.archive, args.new_directory.resolve()))
    else:
        if not 1024 <= args.port <= 65535:
            raise ValueError("Use a port between 1024 and 65535")
        if not (frontend / "index.html").is_file():
            raise FileNotFoundError("Frontend checkout is missing; use --frontend with its directory")
        # Fail before opening the instance when a port is already in use. Never stop another process.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
        app = build_app(instance, frontend, args.port)
        from waitress import serve
        print(f"CMS: http://127.0.0.1:{args.port}/admin.html\nWebsite: http://127.0.0.1:{args.port}/site/\nPersistent demo data enabled. Ctrl+C stops this server; data remains.", flush=True)
        serve(app, host="127.0.0.1", port=args.port, threads=6, max_request_body_size=13 * 1024 * 1024)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as error:
        raise SystemExit(str(error)) from None
