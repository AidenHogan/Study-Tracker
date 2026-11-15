## Copilot / AI Agent Instructions for Study Tracker

Purpose: Help AI coding agents be productive quickly in this repository by describing the architecture, key files, run/debug workflows, and project-specific conventions.

- Entry point: `main_app.py` (desktop GUI built with CustomTkinter; a recent change replaced a fragile CustomTkinter menu with `tkinter.Menu` to fix startup crashes).
- UI layer: CustomTkinter + standard `tkinter` components. Look for UI wiring and menu entries in `main_app.py` and related `ui/` modules (if present).
- Core logic: Data processing and analytics uses Pandas + Matplotlib. Search for `core/` for the Garmin downloader and importer code (example: `core/garmin_downloader`).
- Persistence: SQLite local DB (small schema migrations are applied in code). Look for DB helper modules and the importer that accepts both `Date` and legacy `Bedtime` CSV headers.

Developer workflows (what to run & where):
- Run from source (Windows PowerShell): create a `.venv`, install `requirements.txt`, activate the venv and run `python main_app.py` from the project root.
- The shipped/compiled executable is `Focus_Tracker.exe` (built with PyInstaller). Packaging and release are performed outside the repo's runtime; see `README.md` for release notes.
- There are VS Code tasks in this workspace that run the packaged venv Python executable. If you use the tasks, note the full path to the `.venv` interpreter is used (example shown in workspace tasks).

Project-specific conventions and gotchas (concrete, discoverable patterns):
- CSV importer: accepts either `Date` or `Bedtime` headers from Garmin exports. When adding importer fixes, keep both header mappings.
- Garmin integration: two official modes, `garth` is no longer used. (1) Personal API key: key → `POST personal.connectapi.garmin.com/.../personal-api-key/token` with `Authorization: ApiKey <key>` (no Accept header; returns a text/plain 24h token) → date-based endpoints via `garmin_api.personal_get`, mapped by `garmin_downloader.build_personal_daily_metrics`. (2) Developer app: Health API with OAuth 2.0 PKCE browser sign-in. `core/garmin_api.py` holds auth/HTTP (endpoints, token refresh, pull/backfill); `core/garmin_downloader.py` maps summaries to daily rows (`build_daily_metrics`) and runs the sync. Menu: Garmin → Configure Garmin API / Sign in to Garmin / Disconnect Garmin.
- Health schema: legacy `health_metrics` columns keep their meaning; extra API metrics live in `database_manager.EXTENDED_HEALTH_COLUMNS` (added via ALTER TABLE on startup). To add a metric: add it there, map it in `build_daily_metrics`, and add it to the feature lists in `correlation_engine.py`. API sync uses `upsert_health_metrics` (never overwrites with NULL); raw summaries are kept in `garmin_api_raw`.
- UI fixes: avoid fragile CustomTkinter-only menu constructs — prefer `tkinter.Menu` where startup stability matters (this was the source of a prior crash).

Integration points and cross-component flows to inspect first:
- GUI → Controller → DB: `main_app.py` routes user interactions (timers, manual entry, tag management) into the persistence layer; follow these calls when modifying behavior.
- Importer → DB → Analytics: CSV/garmin import code normalizes rows into the SQLite schema; analytics code reads from the same DB and computes rolling/weekly aggregates.
- Garmin flow: Configure (client id/secret) → Sign in (browser, localhost redirect) → Sync (`sync_health_data`) writes directly to the DB and exports `~/garmin_auto_export.csv`.

When editing or adding features, quickly check these files first:
- `main_app.py` — application entry, menu wiring, and the main window.
- `core/garmin_api.py` / `core/garmin_downloader.py` — Garmin Health API client and sync/mapping.
- Any `db`, `models`, or `importer` modules — schema, import mappings, and migration helpers.
- `requirements.txt` — pinned runtime libs (CustomTkinter, pandas, matplotlib, pyinstaller, etc.).

Notes for AI agents:
- Be explicit about where you change UI strings or menu entries (point to `main_app.py` lines) and keep UI changes backward compatible with the packaged release.
- When proposing DB schema changes, include a short migration plan: SQL ALTER steps or a new migration function, and update the importer to write to the new columns.
- Provide short, focused tests or a manual verification checklist for any fixing of importer or Garmin sync logic (e.g., example CSV snippet + expected DB row).