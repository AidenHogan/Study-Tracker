import pandas as pd
from . import database_manager as db

# --- Constants for Garmin CSV parsing ---
# These constants make it easy to update if the CSV column names change.
COL_DATE = 'Date'
COL_DURATION = 'Duration'
COL_SCORE = 'Score'
COL_RESTING_HR = 'Resting Heart Rate'
COL_BODY_BATTERY = 'Body Battery'
COL_BODY_BATTERY_ALT = 'Body Battery Change'
COL_PULSE_OX = 'Avg. SpO2'
COL_PULSE_OX_ALT = 'Pulse Ox'
COL_RESPIRATION = 'Avg. Respiration Rate'
COL_RESPIRATION_ALT = 'Respiration'
COL_AVG_STRESS = 'Avg. Stress'

# Sentinel values often found in Garmin data for missing entries.
GARMIN_NAN_VALUES = ['--', 'nan', 'None']


def _find_header_row(filepath):
    """Finds the correct header row in the Garmin CSV file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        # Check first to prevent parsing an unsupported file type
        if "Sleep Score 1 Day" in f.read(1024):
            return -1, "The '1 Day' summary CSV is not supported. Please export a '7 Day' or '4 Week' summary from Garmin Connect."

        f.seek(0)  # Reset file pointer to the beginning
        for i, line in enumerate(f):
            # The true header contains these key columns
            if COL_SCORE in line and COL_DURATION in line and "Bedtime" in line:
                return i, None
    return -1, "Could not find a valid Garmin data header in the file. Ensure the file contains 'Score', 'Duration', and 'Bedtime' columns."


def _parse_duration_to_seconds(duration_str):
    """Converts Garmin's duration format (e.g., '8h 15m') to total seconds."""
    s_val = str(duration_str).strip()
    if not s_val or s_val in GARMIN_NAN_VALUES:
        return 0

    h, m = 0, 0
    # Standardize format by removing 'min' and spaces
    s_val = s_val.replace('min', '').replace(' ', '')

    if 'h' in s_val:
        parts = s_val.split('h')
        h = int(parts[0]) if parts[0].isdigit() else 0
        m_str = parts[1].replace('m', '')
        m = int(m_str) if m_str.isdigit() else 0
    elif 'm' in s_val:
        m_str = s_val.replace('m', '')
        m = int(m_str) if m_str.isdigit() else 0

    return (h * 3600) + (m * 60)


def _to_int_or_none(value):
    """Safely converts a value to an integer, returning None on failure."""
    s_val = str(value).strip()
    if s_val in GARMIN_NAN_VALUES:
        return None
    try:
        return int(float(s_val))
    except (ValueError, TypeError):
        return None


def _to_float_or_none(value):
    """Safely converts a value to a float, returning None on failure."""
    s_val = str(value).replace('%', '').replace(' brpm', '').strip()
    if s_val in GARMIN_NAN_VALUES:
        return None
    try:
        return float(s_val)
    except (ValueError, TypeError):
        return None


def import_garmin_csv(filepath):
    """
    Processes a Garmin sleep data CSV file and imports the data into the database.
    Returns a tuple of (imported_count, message).
    """
    header_line_index, error_msg = _find_header_row(filepath)
    if error_msg:
        return 0, error_msg

    df = pd.read_csv(filepath, skiprows=header_line_index)
    df = df.rename(columns={df.columns[0]: COL_DATE})
    df.columns = df.columns.str.strip()

    required_cols = [COL_DATE, COL_DURATION, COL_SCORE]
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        return 0, f"CSV is missing required columns: {', '.join(missing)}."

    imported_count = 0
    for _, row in df.iterrows():
        # A row is only valid if it has a sleep score.
        sleep_score = row.get(COL_SCORE)
        if pd.isna(sleep_score) or str(sleep_score).strip() in GARMIN_NAN_VALUES:
            continue

        date_str = pd.to_datetime(row[COL_DATE]).strftime('%Y-%m-%d')
        duration_seconds = _parse_duration_to_seconds(row.get(COL_DURATION))

        # Use .get() to safely access columns that might not exist in all Garmin exports
        # and coalesce alternative column names (e.g., 'Body Battery' or 'Body Battery Change')
        db.add_or_replace_health_metric(
            date=date_str,
            score=_to_int_or_none(sleep_score),
            rhr=_to_int_or_none(row.get(COL_RESTING_HR)),
            bb=_to_int_or_none(row.get(COL_BODY_BATTERY) or row.get(COL_BODY_BATTERY_ALT)),
            spo2=_to_float_or_none(row.get(COL_PULSE_OX) or row.get(COL_PULSE_OX_ALT)),
            resp=_to_float_or_none(row.get(COL_RESPIRATION) or row.get(COL_RESPIRATION_ALT)),
            sleep_sec=duration_seconds,
            stress=_to_int_or_none(row.get(COL_AVG_STRESS))
        )
        imported_count += 1

    if imported_count == 0:
        return 0, "No valid sleep records with a 'Score' could be found and imported from the file."

    return imported_count, ""