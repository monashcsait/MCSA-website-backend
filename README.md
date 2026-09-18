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

`MCSA_INSTANCE` selects the data directory. Default: local `instance/`. The supplied systemd service uses `/var/lib/mcsa-backend`. Keep credentials, SQLite and `media/` outside Git. Do not replace this directory when updating code.

`seed.json` is used only for a new database. Existing fifth-version content can be retained by copying the complete stopped `instance` contents into the selected data directory.

## Deployment

Templates are in `deploy/`. Use HTTPS with Nginx proxying to Waitress on `127.0.0.1:8000`. Apply the supplied proxy fragment to the correct site's HTTPS server block, not to the entire Nginx configuration. Configure TLS and DNS separately.

Optional environment overrides: `MCSA_FRONTEND_URL`, `MCSA_PUBLIC_URL`, `MCSA_ALLOWED_ORIGINS` (comma-separated origins), `MCSA_INSTANCE`, `MCSA_HOST`, `PORT`. Translation keys stay on the server; `.env.example` is a template, not automatically loaded by Python.

## Checks

```bash
python -m unittest discover -s tests -v
```

The current account model is one administrator. Supabase authentication and multiple roles are not implemented in this package.
