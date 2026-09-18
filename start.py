from pathlib import Path
import os, json, secrets, getpass, sys
from werkzeug.security import generate_password_hash
from waitress import serve
from server import create_app

root = Path(__file__).resolve().parent
inst = Path(os.environ.get("MCSA_INSTANCE", str(root / "instance")))
inst.mkdir(parents=True, exist_ok=True)
f = inst / "credentials.json"
if "--reset-password" in sys.argv or not f.exists():
    print(
        "Create / reset MCSA administrator password. Username: admin. Minimum 12 characters."
    )
    while True:
        password = getpass.getpass("Password (typing is hidden): ")
        confirm = getpass.getpass("Repeat password: ")
        if len(password) >= 12 and password == confirm:
            break
        print("Passwords must match and contain at least 12 characters.")
    f.write_text(
        json.dumps(
            {
                "password_hash": generate_password_hash(password),
                "secret": secrets.token_hex(32),
            }
        )
    )
    f.chmod(0o600)
    print("Password saved. Existing website content is preserved.")
    if "--reset-password" in sys.argv or "--init" in sys.argv:
        raise SystemExit()
if "--init" in sys.argv:
    print("Administrator credentials already exist; nothing was changed.")
    raise SystemExit()
port = int(os.environ.get("PORT", "8000"))
host = os.environ.get("MCSA_HOST", "127.0.0.1")
print(
    f"Backend: http://127.0.0.1:{port}/\nAdmin: http://127.0.0.1:{port}/admin.html\nKeep this window open. Press Ctrl+C to stop.",
    flush=True,
)
serve(
    create_app(inst),
    host=host,
    port=port,
    threads=6,
    max_request_body_size=13 * 1024 * 1024,
)
