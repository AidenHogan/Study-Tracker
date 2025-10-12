# file: activity_importer.py

import pandas as pd
from datetime import timedelta
import database_manager as db

# --- Constants for Garmin Activities CSV parsing ---
COL_ACTIVITY_TYPE = 'Activity Type'
COL_DATE = 'Date'
COL_START_TIME = 'Start Time'
COL_TIME = 'Time' # Note: Garmin uses "Time" for the duration
COL_DISTANCE = 'Distance'
COL_CALORIES = 'Calories'

# Sentinel values for missing data
GARMIN_NAN_VALUES = ['--', 'nan', 'None']


def _parse_duration_to_seconds(duration_str):
    """
    Robustly converts various time duration formats (HH:MM:SS, MM:SS) to seconds.
    Handles potential floating point seconds from Garmin exports.
    """
    s_val = str(duration_str).strip()
    if not s_val or s_val in GARMIN_NAN_VALUES:
        return 0

    parts = s_val.split(':')
    try:
        if len(parts) == 3:  # HH:MM:SS
            td = timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=float(parts[2]))
        elif len(parts) == 2:  # MM:SS
            td = timedelta(minutes=int(parts[0]), seconds=float(parts[1]))
        elif len(parts) == 1 and s_val.replace('.', '', 1).isdigit(): # Just seconds
             td = timedelta(seconds=float(s_val))
        else:
            return 0 # Unsupported format
        return td.total_seconds()
    except (ValueError, IndexError):
        # Return 0 if conversion fails for any reason (e.g., non-numeric parts)
        return 0


def _to_float_or_zero(value):
    """Safely converts a value to a float, returning 0.0 on failure."""
    s_val = str(value).strip()
    if s_val in GARMIN_NAN_VALUES:
        return 0.0
    # Check if the string can be a number (handles cases like "1,234.56")
    if str(s_val).replace(',', '').replace('.', '', 1).isdigit():
        return float(str(s_val).replace(',', ''))
    return 0.0


def import_activities_csv(filepath):
    """
    Processes a Garmin Activities CSV file and imports the data into the database.
    Returns a tuple of (imported_count, message).
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return 0, f"Could not read the CSV file. Error: {e}"

    # Use constants for required columns
    required_cols = [COL_ACTIVITY_TYPE, COL_DATE, COL_TIME]
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        return 0, f"CSV is missing required columns: {', '.join(missing)}"

    imported_count = 0
    skipped_count = 0
    for _, row in df.iterrows():
        try:
            # Use the helper to parse duration from the "Time" column
            duration_seconds = _parse_duration_to_seconds(row.get(COL_TIME))

            # Skip records with no valid duration
            if duration_seconds <= 0:
                skipped_count += 1
                continue

            # Combine date and start time (if available, otherwise default to midnight)
            start_time_str = row.get(COL_START_TIME, '00:00:00')
            start_datetime = pd.to_datetime(f"{row[COL_DATE]} {start_time_str}")

            # Use helpers to safely convert numeric types
            distance = _to_float_or_zero(row.get(COL_DISTANCE))
            calories = int(_to_float_or_zero(row.get(COL_CALORIES)))

            db.add_activity(
                activity_type=row[COL_ACTIVITY_TYPE],
                start_time=start_datetime,
                duration_seconds=duration_seconds,
                distance=distance,
                calories=calories
            )
            imported_count += 1
        except (ValueError, KeyError) as e:
            print(f"Skipping a row due to data format error: {e} | Row data: {row.to_dict()}")
            skipped_count += 1
            continue

    if imported_count == 0:
        return 0, "No valid activity records with a duration could be imported from the file."

    return imported_count, ""