# file: data_importer.py

import pandas as pd
import database_manager as db


def import_garmin_csv(filepath):
    """
    Processes a Garmin sleep data CSV file and imports the data into the database.
    Returns a tuple of (imported_count, message).
    """

    # --- Step 1: Preliminary File Checks ---
    with open(filepath, 'r', encoding='utf-8') as f:
        header_content = f.read(1024)

    if "Sleep Score 1 Day" in header_content:
        return 0, "The '1 Day' summary CSV is not supported. Please export a '7 Day' or '4 Week' summary from Garmin Connect."

    header_line_index = -1
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if "Score" in line and "Duration" in line and "Bedtime" in line:
                header_line_index = i
                break

    if header_line_index == -1:
        raise ValueError("Could not find a valid Garmin data header in the file.")

    # --- Step 2: Load and Clean with Pandas ---
    df = pd.read_csv(filepath, skiprows=header_line_index)
    df = df.rename(columns={df.columns[0]: 'Date'})
    df.columns = df.columns.str.strip()

    required_cols = ['Date', 'Duration', 'Score']
    if not all(col in df.columns for col in required_cols):
        raise ValueError(f"CSV is missing required columns. Found: {df.columns.to_list()}.")

    # --- Step 3: Define Helper Functions for Data Conversion ---
    def to_int(val):
        try: return int(float(val))
        except (ValueError, TypeError): return None

    def to_float(val):
        s_val = str(val).replace('%', '').replace(' brpm', '').strip()
        try: return float(s_val)
        except (ValueError, TypeError): return None

    def duration_to_seconds(duration_str):
        duration_str = str(duration_str)
        if not duration_str or duration_str in ['--', 'nan']: return 0
        h, m = 0, 0
        if 'h' in duration_str:
            parts = duration_str.split('h')
            h = to_int(parts[0]) or 0
            if len(parts) > 1:
                m_str = parts[1].replace('min', '').replace('m', '').strip()
                m = to_int(m_str) or 0
        elif 'm' in duration_str:
            m = to_int(duration_str.replace('m', '').strip()) or 0
        return (h * 3600) + (m * 60)

    # --- Step 4: Iterate and Import Data ---
    imported_count = 0
    for _, row in df.iterrows():
        sleep_score = row.get('Score')
        if pd.isna(sleep_score) or str(sleep_score).strip() == '--':
            continue

        date_str = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
        duration_seconds = duration_to_seconds(row.get('Duration'))

        # Get various possible column names from different Garmin export versions
        resting_hr = row.get('Resting Heart Rate')
        body_battery = row.get('Body Battery') or row.get('Body Battery Change')
        pulse_ox = row.get('Avg. SpO2') or row.get('Pulse Ox')
        respiration = row.get('Avg. Respiration Rate') or row.get('Respiration')

        db.add_or_replace_health_metric(
            date_str, to_int(sleep_score), to_int(resting_hr),
            to_int(body_battery), to_float(pulse_ox), to_float(respiration),
            duration_seconds
        )
        imported_count += 1

    if imported_count == 0:
        return 0, "Could not find any valid sleep records to import from the file."

    return imported_count, ""