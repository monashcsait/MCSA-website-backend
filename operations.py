"""Offline operations for private SQLite/account/media backups.

Run ``python operations.py backup`` from a systemd timer. Restore creates a new
instance directory, so the service must be stopped before switching to it.
"""

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone


MEDIA_NAME = re.compile(r"media/[a-f0-9]{32}\.(png|jpg|gif|webp)\Z")
ARCHIVE_NAME = re.compile(r"MCSA-full-\d{8}T\d{12}Z\.zip\Z")


def instance_path():
    return Path(os.environ.get("MCSA_INSTANCE", Path(__file__).resolve().parent / "instance"))


def backup_dir(instance):
    return Path(os.environ.get("MCSA_BACKUP_DIR", instance.parent / "mcsa-backups"))


def check_database(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        if not db.execute("SELECT 1 FROM site WHERE id=1").fetchone():
            raise ValueError("Website content is missing")
        if not db.execute("SELECT 1 FROM users WHERE role='super_admin' AND active=1").fetchone():
            raise ValueError("No active super administrator exists")


def verify_archive(path):
    """Check archive shape, CRC, credentials, and a restored SQLite snapshot."""
    with TemporaryDirectory() as directory, zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not {"site.sqlite3", "credentials.json"}.issubset(names):
            raise ValueError("Missing or duplicate backup entries")
        if any(name not in {"site.sqlite3", "credentials.json"} and not MEDIA_NAME.fullmatch(name) for name in names):
            raise ValueError("Unexpected backup entry")
        if archive.testzip() is not None:
            raise ValueError("Damaged backup entry")
        credentials = json.loads(archive.read("credentials.json"))
        if (not isinstance(credentials.get("secret"), str) or not credentials["secret"]
                or not isinstance(credentials.get("password_hash"), str)):
            raise ValueError("Session credentials are missing")
        database = Path(directory) / "site.sqlite3"
        database.write_bytes(archive.read("site.sqlite3"))
        check_database(database)
        return len(names) - 2


def create_backup(instance, destination, keep=14):
    """Take a consistent SQLite snapshot and copy immutable uploaded media."""
    instance, destination = Path(instance), Path(destination)
    database = instance / "site.sqlite3"
    credentials = instance / "credentials.json"
    if not database.is_file() or not credentials.is_file():
        raise FileNotFoundError("Initialize the instance before backing it up")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = destination / f"MCSA-full-{stamp}.zip"
    temporary = None
    try:
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "site.sqlite3"
            with closing(sqlite3.connect(database, timeout=15)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            check_database(snapshot)
            with tempfile.NamedTemporaryFile(dir=destination, prefix=".MCSA-full-", delete=False) as file:
                temporary = Path(file.name)
            temporary.chmod(0o600)
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, "site.sqlite3")
                archive.write(credentials, "credentials.json")
                for media in sorted((instance / "media").glob("*")):
                    if media.is_file() and not media.is_symlink() and MEDIA_NAME.fullmatch("media/" + media.name):
                        archive.write(media, "media/" + media.name)
            verify_archive(temporary)
            temporary.replace(output)
            temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    archives = sorted((p for p in destination.iterdir() if ARCHIVE_NAME.fullmatch(p.name)), reverse=True)
    for old in archives[keep:]:
        old.unlink()
    return output


def restore_to_new_directory(archive_path, target):
    """Restore only into an empty, newly created directory; never overwrite live data."""
    archive_path, target = Path(archive_path), Path(target)
    verify_archive(archive_path)
    if target.exists():
        raise FileExistsError("Restore destination must not exist")
    target.mkdir(mode=0o700)
    try:
        (target / "media").mkdir(mode=0o700)
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                path = target / name
                path.write_bytes(archive.read(name))
                path.chmod(0o600)
        check_database(target / "site.sqlite3")
    except Exception:
        import shutil
        shutil.rmtree(target)
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    check = commands.add_parser("verify")
    check.add_argument("archive", type=Path)
    restore = commands.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("new_directory", type=Path)
    args = parser.parse_args()
    if args.command == "backup":
        print(create_backup(instance_path(), backup_dir(instance_path())))
    elif args.command == "verify":
        print(f"Backup valid; {verify_archive(args.archive)} media files")
    else:
        print(restore_to_new_directory(args.archive, args.new_directory))


if __name__ == "__main__":
    main()
