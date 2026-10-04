# MCSA content backend

Python / Flask / Waitress with an independent Chinese CMS, persistent SQLite content and media uploads. This repository runs on a server such as an Alibaba Cloud instance; GitHub Pages does not run it.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python start.py
```

Windows users can run `START-WINDOWS.bat`. First launch asks for the administrator password. Open `/admin.html`; username is `admin`.

## Connect the public website

Set `deployment.json`:

- `frontendUrl`: complete website URL, including the GitHub Pages repository path.
- `backendUrl`: this backend's HTTPS origin, without `/api` or `/admin.html`.

The parent package's `connect.py` writes both this file and the frontend configuration.

Only the public `GET /api/site` endpoint supports cross-origin reads. It returns current published content and absolute CMS image URLs. Admin writes require login and CSRF. Upload URLs are publicly retrievable when known; do not upload confidential material.

## Persistent data

`MCSA_INSTANCE` selects the data directory. Default: local `instance/`. The supplied systemd service uses `/var/lib/mcsa-backend`. SQLite stores content and accounts; `credentials.json` retains the session secret and legacy administrator password hash. Keep credentials, SQLite and `media/` outside Git. Do not replace this directory when updating code. Use `python start.py --reset-password` to reset the local super administrator password; it updates the account record and invalidates existing sessions.

`seed.json` is used only for a new database. Existing data can be retained by copying the complete stopped `instance` contents into the selected data directory.

## Deployment

Templates are in `deploy/`. Use HTTPS with Nginx proxying to Waitress on `127.0.0.1:8000`. Apply the supplied proxy fragment to the correct site's HTTPS server block, not to the entire Nginx configuration. Configure TLS and DNS separately.

Optional environment overrides: `MCSA_FRONTEND_URL`, `MCSA_PUBLIC_URL`, `MCSA_ALLOWED_ORIGINS` (comma-separated origins), `MCSA_INSTANCE`, `MCSA_HOST`, `PORT`. Translation keys stay on the server; `.env.example` is a template, not automatically loaded by Python.

## Checks

```bash
python -m unittest discover -s tests -v
```

`GET /healthz` returns HTTP 200 when SQLite passes an integrity check and the media directory exists; otherwise it returns 503. It does not expose private paths or account details. Unexpected server errors are logged by Flask and returned to API clients as `server_error` without traceback details.

## Full backups and recovery

The CMS **下载内容备份** button exports content and media for editors; it does not contain accounts or session credentials. A full server backup includes a consistent SQLite snapshot, `credentials.json`, and uploads:

```bash
.venv/bin/python operations.py backup
.venv/bin/python operations.py verify /path/to/MCSA-full-YYYYMMDDTHHMMSSffffffZ.zip
```

`MCSA_BACKUP_DIR` defaults to a private sibling directory of `MCSA_INSTANCE`. Full archives contain password hashes and the session signing secret, so restrict their access and copy them to separate storage. The backup command writes atomically, verifies each archive, and retains the newest 14 full archives. `deploy/mcsa-backup.service` and `deploy/mcsa-backup.timer` run a daily backup at 03:15 on a systemd server. Adjust the service's `/opt/mcsa-backend` path to the actual checkout, install both unit files, then run `sudo systemctl daemon-reload && sudo systemctl enable --now mcsa-backup.timer`. Run `sudo systemctl start mcsa-backup.service` once and inspect `systemctl status` and `journalctl -u mcsa-backup.service` to verify the schedule works. The service uses systemd's private `/var/lib/mcsa-backups` directory.

For a recovery drill, restore into a **new path** and start a test instance against that directory:

```bash
.venv/bin/python operations.py restore /path/to/MCSA-full-YYYYMMDDTHHMMSSffffffZ.zip /path/to/new-instance
```

The restore command refuses an existing destination and verifies SQLite, accounts, credentials, and media. For production recovery, stop the backend service, move the old instance aside, restore to the configured instance path, then restart the service and check `/healthz`, login, content, and uploaded pictures. The older `restore-backup.py` only imports a content-only ZIP into an existing installation; it does not restore accounts. Schedule an off-server copy and monitor backup failures separately from this repository.

## Accounts and permissions

Login and sessions use the SQLite `users` table. The existing administrator is migrated as a super administrator. In the CMS, only super administrators can open **账号与权限** to create, edit, or disable accounts and assign permissions. The same restriction applies to `GET/POST /api/admin/accounts` and `PUT /api/admin/accounts/<id>`; all writes require CSRF. Password hashes are never returned by these APIs.

Ordinary administrators can be assigned `site.read`, `site.write`, `merchant.read`, `merchant.write`, `media.upload`, and `backup.download`. `site.write` edits the full CMS and requires `site.read`. `merchant.write` edits only merchants, regions, and categories, requires `merchant.read`, and uses the separate `/api/admin/merchants` endpoint. Image upload requires either website or merchant read access. These permissions are checked on the backend for every request and again against the database for existing sessions. Changing an account revokes its current sessions. At least one active super administrator must remain. Supabase authentication is not used.

## Merchant location and publication

Merchant records now accept `address` (text), `latitude` (-90 to 90), `longitude` (-180 to 180), and `published` (boolean). Coordinates must be supplied together or both left empty; the map should omit merchants without coordinates. New merchants start unpublished. Existing merchants without these fields are read with empty location fields and remain published. `GET /api/admin/site` includes drafts; public `GET /api/site` includes only published merchants. The current public website still needs map rendering and navigation; this backend change only supplies the data contract.

Author：Guo Yu
