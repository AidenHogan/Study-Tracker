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
- Garmin integration: The app supports an OAuth1 sign-in flow via the app menu (Garmin → Sign in to Garmin (OAuth)). The `core/garmin_downloader` module contains CLI helpers and sync logic — change here to add new Garmin endpoints.
- New daily health columns (e.g., `hydration_ml`, `intensity_minutes`) are prepared by the importer/db code. If you add automatic Garmin sync for these fields, also update the DB schema/migrations.
- UI fixes: avoid fragile CustomTkinter-only menu constructs — prefer `tkinter.Menu` where startup stability matters (this was the source of a prior crash).

Integration points and cross-component flows to inspect first:
- GUI → Controller → DB: `main_app.py` routes user interactions (timers, manual entry, tag management) into the persistence layer; follow these calls when modifying behavior.
- Importer → DB → Analytics: CSV/garmin import code normalizes rows into the SQLite schema; analytics code reads from the same DB and computes rolling/weekly aggregates.
- OAuth1 flow: menu action triggers the OAuth helper; after sign-in, the downloader can populate additional daily stats.

When editing or adding features, quickly check these files first:
- `main_app.py` — application entry, menu wiring, and the main window.
- `core/garmin_downloader` — Garmin auth and download helpers.
- Any `db`, `models`, or `importer` modules — schema, import mappings, and migration helpers.
- `requirements.txt` — pinned runtime libs (CustomTkinter, pandas, matplotlib, pyinstaller, etc.).

Notes for AI agents:
- Be explicit about where you change UI strings or menu entries (point to `main_app.py` lines) and keep UI changes backward compatible with the packaged release.
- When proposing DB schema changes, include a short migration plan: SQL ALTER steps or a new migration function, and update the importer to write to the new columns.
- Provide short, focused tests or a manual verification checklist for any fixing of importer or Garmin sync logic (e.g., example CSV snippet + expected DB row).