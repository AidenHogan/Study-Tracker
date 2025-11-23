import pandas as pd
import json
from datetime import datetime
from collections import defaultdict

from . import database_manager as db


def _to_date_str(ts):
    # Accept either ISO timestamps or pandas Timestamp
    if isinstance(ts, str):
        try:
            return pd.to_datetime(ts).strftime('%Y-%m-%d')
        except Exception:
            return None
    try:
        return pd.to_datetime(ts).strftime('%Y-%m-%d')
    except Exception:
        return None


def import_aw_csv(filepath):
    """
    Import an ActivityWatch window watcher CSV export.
    Aggregates active (foreground) time per calendar date and stores a daily summary.

    Returns (imported_days_count, message)
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return 0, f"Could not read CSV: {e}"

    # Expecting at least 'timestamp' and 'duration' columns (see sample attachments)
    if 'timestamp' not in df.columns or 'duration' not in df.columns:
        return 0, "CSV missing required 'timestamp' or 'duration' columns."

    # Normalize timestamp -> date and ensure duration numeric (assume seconds)
    df['date'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.strftime('%Y-%m-%d')
    df['duration_seconds'] = pd.to_numeric(df['duration'], errors='coerce').fillna(0).astype(float)

    # Aggregate total active seconds per day
    daily = df.groupby('date')['duration_seconds'].sum().reset_index()

    # Also create a small per-app summary (top 10 by total seconds)
    app_summary_map = {}
    if 'app' in df.columns:
        grouped = df.groupby(['date', 'app'])['duration_seconds'].sum().reset_index()
        for d, group in grouped.groupby('date'):
            g = group.sort_values('duration_seconds', ascending=False).head(10)
            app_summary_map[d] = {row['app']: float(row['duration_seconds']) for _, row in g.iterrows()}

    imported = 0
    for _, row in daily.iterrows():
        date_str = row['date']
        if not date_str or pd.isna(date_str):
            continue
        secs = int(row['duration_seconds'])
        app_summary = app_summary_map.get(date_str, {})
        app_summary_json = json.dumps(app_summary)
        try:
            db.add_or_replace_aw_daily(date_str, secs, app_summary_json)
            imported += 1
        except Exception as e:
            # Continue on error but report later
            print(f"Failed to write AW daily for {date_str}: {e}")

    if imported == 0:
        return 0, "No valid AW daily aggregates were imported from the file."
    return imported, ""


def import_aw_json(filepath):
    """
    Import ActivityWatch bucket export JSON. Attempts to detect records and aggregate to daily.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, f"Could not read JSON: {e}"

    # ActivityWatch bucket export formats vary. We'll try a few heuristics.
    records = []

    # Case A: list of dicts with 'timestamp' and 'duration'
    if isinstance(data, list) and data and isinstance(data[0], dict) and 'timestamp' in data[0]:
        for r in data:
            ts = r.get('timestamp') or r.get('start')
            dur = r.get('duration') or r.get('delta') or r.get('end')
            # If there's an explicit end and start, compute duration
            if not dur and r.get('start') and r.get('end'):
                try:
                    start = pd.to_datetime(r['start'])
                    end = pd.to_datetime(r['end'])
                    dur = (end - start).total_seconds()
                except Exception:
                    dur = 0
            records.append({'timestamp': ts, 'duration': dur, 'app': r.get('data') or r.get('app')})

    # Case B: bucket object with nested 'events' list
    elif isinstance(data, dict):
        # Flatten any lists inside
        for key, val in data.items():
            if isinstance(val, list):
                for r in val:
                    if isinstance(r, dict):
                        ts = r.get('timestamp') or r.get('start')
                        dur = r.get('duration') or r.get('delta')
                        if not dur and r.get('start') and r.get('end'):
                            try:
                                dur = (pd.to_datetime(r['end']) - pd.to_datetime(r['start'])).total_seconds()
                            except Exception:
                                dur = 0
                        records.append({'timestamp': ts, 'duration': dur, 'app': r.get('data') or r.get('app')})

    if not records:
        return 0, "No recognizable AW records found in JSON file."

    # Convert into DataFrame and reuse CSV path
    df = pd.DataFrame(records)
    # Reuse CSV importer logic by writing a temp CSV in memory via DataFrame
    # Normalize and aggregate
    df['date'] = pd.to_datetime(df['timestamp'], errors='coerce').dt.strftime('%Y-%m-%d')
    df['duration_seconds'] = pd.to_numeric(df['duration'], errors='coerce').fillna(0).astype(float)

    daily = df.groupby('date')['duration_seconds'].sum().reset_index()

    app_summary_map = {}
    if 'app' in df.columns:
        grouped = df.groupby(['date', 'app'])['duration_seconds'].sum().reset_index()
        for d, group in grouped.groupby('date'):
            g = group.sort_values('duration_seconds', ascending=False).head(10)
            app_summary_map[d] = {row['app']: float(row['duration_seconds']) for _, row in g.iterrows()}

    imported = 0
    for _, row in daily.iterrows():
        date_str = row['date']
        if not date_str or pd.isna(date_str):
            continue
        secs = int(row['duration_seconds'])
        app_summary = app_summary_map.get(date_str, {})
        app_summary_json = json.dumps(app_summary)
        try:
            db.add_or_replace_aw_daily(date_str, secs, app_summary_json)
            imported += 1
        except Exception as e:
            print(f"Failed to write AW daily for {date_str}: {e}")

    if imported == 0:
        return 0, "No valid AW daily aggregates were imported from the JSON file."
    return imported, ""


def import_aw_tags_json(filepath):
    """
    Import ActivityWatch category/tag definitions (categories export) and create corresponding tags in app DB.

    Robustness notes:
    - Accepts objects with 'categories' list where entries may contain 'name_pretty', 'subname', or 'name' (list).
    - Falls back gracefully on missing fields.
    - Does not overwrite existing tags; skips duplicates.

    Returns (created_count, skipped_count, message)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
            # Some AW exports include a leading non-JSON token (like "Make {\n...") in attachments;
            # try to find the first '{' and parse from there.
            idx = raw.find('{')
            if idx > 0:
                raw = raw[idx:]
            data = json.loads(raw)
    except Exception as e:
        return 0, 0, f"Could not read/parse JSON: {e}"

    cats = data.get('categories') if isinstance(data, dict) else None
    if not cats or not isinstance(cats, list):
        return 0, 0, "JSON did not contain a 'categories' list."

    created = 0
    skipped = 0
    for entry in cats:
        # Prefer a human-friendly name if available
        name = entry.get('name_pretty') or entry.get('subname')
        if not name:
            raw_name = entry.get('name')
            if isinstance(raw_name, list):
                name = '>'.join(raw_name)
            elif isinstance(raw_name, str):
                name = raw_name
        # As a final fallback, use id-based name
        if not name:
            name = f"aw_cat_{entry.get('id', 'unknown')}"

        # Normalize whitespace
        name = str(name).strip()
        if not name:
            skipped += 1
            continue

        # Top-level category for categorization (if available)
        category_name = None
        raw_name = entry.get('name')
        if isinstance(raw_name, list) and len(raw_name) > 0:
            category_name = raw_name[0]

        try:
            # Mark ActivityWatch-imported tags as hidden so they don't flood user tag lists
            ok, msg = db.add_tag(name, is_hidden=1)
            if not ok:
                # duplicate likely
                skipped += 1
            else:
                created += 1
                # assign category if present
                if category_name:
                    try:
                        db.update_tag_category(name, category_name)
                    except Exception:
                        pass
        except Exception:
            skipped += 1

    return created, skipped, ""
