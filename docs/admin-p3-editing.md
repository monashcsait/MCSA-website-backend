# Admin P3 editing handoff

Date: 2026-10-12 (Australia/Sydney).

## Scope and baseline

`admin-p3-editing` starts from team `main` commit `06add5b`, including the account, scoped merchant, location and publication APIs. It integrates the existing P2 visual interface and collapsible mobile navigation with that backend, then improves the editing workflow.

Files: `web/admin.html`, `web/assets/admin.css`, `admin.js`, `admin-runtime.js`, `admin-editing.js`, `admin-navigation.js`, and the two handoff documents in `docs/`.

The earlier `docs/admin-phase1-audit.md` staging entry is excluded from this delivery. Runtime databases, credentials, uploaded files, test fixtures and local automation scripts are excluded. Server implementation, translations, seed content and public website source are unchanged in this delivery.

## Changes

- Chinese field guidance and validation for URLs, email, dates, text, layout values, published titles, merchant names and coordinates; save errors link to the relevant editor.
- Search for interface text entries.
- Image upload, replacement, clearing and thumbnail feedback; client checks format and 12 MiB size before the existing server verification. Changed images reset crop metadata.
- Upload/save busy state prevents overlapping edits and saves.
- Preview current unsaved content using the existing public frontend iframe/message protocol; choose a page, department or article. Article drafts are shown using a preview copy without saving or publishing them.
- Network, session, revision-conflict and malformed-response handling preserves browser editing state. Unsaved content can be downloaded as JSON containing content and revision, without account credentials.
- Named deletion confirmation, disabled boundary reorder controls, safer logout handling and retained account/merchant permission logic.
- Existing P2 styling and mobile navigation retained alongside current account UI.

## Running and integration

Use the repository README and `START-WINDOWS.bat` for the backend. Open the running backend's `/admin.html`.

Public frontend configuration must point `window.MCSA_CONFIG.apiBase` to the backend URL ending in `/api`. Backend `frontendUrl` must point to the separately running website for preview; `backendUrl` must match the backend origin. See README deployment/environment configuration. Check directory assumptions before using an external `connect.py` helper.

The current developer demonstration uses backend `127.0.0.1:18081` and website `127.0.0.1:18082`. Its launcher is outside this repository and overrides the frontend configuration response. These ports and this launcher are not production defaults and are not supplied by this commit.

The developer demonstration uses a temporary instance; restarting its launcher creates a fresh database. For the conference, use an independent persistent instance containing SQLite and media, prepare example content, and rehearse startup/restart and the edit-to-website flow. Preserve any existing instance during updates. The user has confirmed that the conference presentation is local only; server deployment is outside that presentation's acceptance scope.

## Validation evidence

2026-10-09: isolated Windows/Chrome 155 instance, 25 browser check groups PASS, no unhandled page errors. Coverage includes upload/replace/clear persistence, invalid uploads and URLs, list operations, long content, unsaved preview, publication/public website refresh, network/server/malformed-response errors, real 409 and 401 responses, draft export, account scopes and mobile flows.

Viewports: 320x740, 390x844, 430x932, 844x390, 768x1024, 1024x768 and 1280x900. The complete edit/preview/save/public-website flow passed at 390px. This is Chrome viewport simulation, not physical-device Safari verification.

2026-10-12: current demonstration health, admin page, public homepage, frontend API configuration and public content endpoint returned HTTP 200. Current draft article preview rendered successfully and closed back to editing. Public revision remained 4 and published article count remained 0. Existing user content was preserved; upload/save/publication were not repeated in that check.

Evidence JSON and screenshots are stored in the developer workspace's Shared document; no database or fixture credentials are included here.

Existing backend suite: 18 tests ran, 14 passed, 4 errored during Windows temporary SQLite cleanup (WinError 32). One historically blocking interactive password-reset subprocess test was not run. The whole backend suite is not reported as passing; server/test files were not modified by this work.

## Remaining scope

- Confirm obsolete-field disposition and department history/former minister fields with content and backend owners. Preserve current compatibility data until confirmed.
- Coordinate the final multilingual branch and English/manual translation rules; the requested Traditional Chinese editor scope is unresolved. Live external English translation was not verified in the isolated demonstration.
- Merchant-only users currently cannot use full-site preview. A separate merchant preview needs a scope decision.
- Multi-image merchant details and map/navigation frontend integration are not delivered here.
- Physical-device/Safari validation, conference data persistence/restart/backup rehearsal and complete user acceptance remain pending.

Status: implemented and locally verified for the documented core workflow; full P3 scope and acceptance remain incomplete. A branch push is code delivery, not a merge, deployment or database publication.
