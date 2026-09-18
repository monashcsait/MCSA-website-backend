"""Offline restore; stop the running website first. Credentials are preserved."""

from pathlib import Path
import sys, json, zipfile, sqlite3, os, re, shutil, datetime
from server import validate, migrate

root = Path(__file__).resolve().parent
inst = Path(os.environ.get("MCSA_INSTANCE", str(root / "instance")))
if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python restore-backup.py path/to/MCSA-content-backup.zip (stop server first)"
    )
with zipfile.ZipFile(sys.argv[1]) as z:
    payload = json.loads(z.read("content.json"))
    data = validate(migrate(payload["data"]))
    if not (inst / "site.sqlite3").exists():
        raise SystemExit(
            "Run start.py once to initialize this installation, then stop it before restoring."
        )
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = inst.parent / ("instance-before-restore-" + stamp)
    shutil.copytree(inst, backup)
    with sqlite3.connect(inst / "site.sqlite3") as c:
        c.execute(
            "UPDATE site SET data=?,revision=revision+1 WHERE id=1",
            (json.dumps(data, ensure_ascii=False),),
        )
    (inst / "media").mkdir(exist_ok=True)
    for name in z.namelist():
        if re.fullmatch(r"media/[a-f0-9]{32}\.(png|jpg|gif|webp)", name):
            (inst / name).write_bytes(z.read(name))
print(
    "Restore complete. Existing content was copied to "
    + str(backup)
    + ". Restart the website."
)
