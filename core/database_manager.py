# file: core/database_manager.py

import sqlite3
import os
import sys
from contextlib import contextmanager
from datetime import datetime
import pandas as pd


def get_db_path():
    """Gets the correct path to the database file for bundled executables."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, 'study_sessions.db')


DB_PATH = get_db_path()


@contextmanager
def db_connection():
    """Provides a database connection as a context manager to ensure it's always closed."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        yield conn
    finally:
        if conn:
            conn.close()


def setup_database():
    """Initializes the database and creates/updates tables if they don't exist."""
    with db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS sessions
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           tag
                           TEXT
                           NOT
                           NULL,
                           start_time
                           TEXT
                           NOT
                           NULL,
                           end_time
                           TEXT
                           NOT
                           NULL,
                           duration_seconds
                           INTEGER
                           NOT
                           NULL,
                           notes
                           TEXT
                       )''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS tags
                       (
                           name
                           TEXT
                           PRIMARY
                           KEY
                           NOT
                           NULL,
                           color
                           TEXT
                           DEFAULT
                           '#3b8ed0',
                           category_name
                           TEXT,
                           FOREIGN
                           KEY
                       (
                           category_name
                       ) REFERENCES categories
                       (
                           name
                       ))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS categories
                          (
                              name
                              TEXT
                              PRIMARY
                              KEY
                              NOT
                              NULL
                          )''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS health_metrics
                       (
                           date
                           TEXT
                           PRIMARY
                           KEY,
                           sleep_score
                           INTEGER,
                           resting_hr
                           INTEGER,
                           body_battery
                           INTEGER,
                           pulse_ox
                           REAL,
                           respiration
                           REAL,
                           sleep_duration_seconds
                           INTEGER,
                           avg_stress
                           INTEGER
                       )''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS activities
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           activity_type
                           TEXT
                           NOT
                           NULL,
                           start_time
                           TEXT
                           NOT
                           NULL
                           UNIQUE,
                           duration_seconds
                           INTEGER
                           NOT
                           NULL,
                           distance
                           REAL,
                           calories
                           INTEGER
                       )''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS pomodoro_sessions
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           session_type
                           TEXT
                           NOT
                           NULL,
                           start_time
                           TEXT
                           NOT
                           NULL,
                           end_time
                           TEXT
                           NOT
                           NULL,
                           duration_seconds
                           INTEGER
                           NOT
                           NULL,
                           task_title
                           TEXT,
                           task_description
                           TEXT,
                           main_session_id
                           INTEGER,
                           FOREIGN
                           KEY
                       (
                           main_session_id
                       ) REFERENCES sessions
                       (
                           id
                       ))''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS custom_factors
                       (
                           name
                           TEXT
                           PRIMARY
                           KEY,
                           start_date
                           TEXT
                           NOT
                           NULL
                       )''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS custom_factor_log
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           factor_name
                           TEXT
                           NOT
                           NULL,
                           date
                           TEXT
                           NOT
                           NULL,
                           value
                           INTEGER
                           NOT
                           NULL,
                           FOREIGN
                           KEY
                       (
                           factor_name
                       ) REFERENCES custom_factors
                       (
                           name
                       ) ON DELETE CASCADE,
                           UNIQUE
                       (
                           factor_name,
                           date
                       ))''')

        _add_column_if_not_exists(cursor, 'sessions', 'notes', 'TEXT')
        _add_column_if_not_exists(cursor, 'tags', 'color', "TEXT DEFAULT '#3b8ed0'")
        _add_column_if_not_exists(cursor, 'pomodoro_sessions', 'main_session_id', 'INTEGER')
        _add_column_if_not_exists(cursor, 'tags', 'category_name', 'TEXT')
        _add_column_if_not_exists(cursor, 'health_metrics', 'avg_stress', 'INTEGER')

        conn.commit()


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def fetch_all(query, params=()):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def fetch_one(query, params=()):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()


def execute_query(query, params=(), fetch_last_id=False):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        if fetch_last_id:
            return cursor.lastrowid


def get_categories():
    return fetch_all("SELECT name FROM categories ORDER BY name")


def add_category(name):
    try:
        execute_query("INSERT INTO categories (name) VALUES (?)", (name,))
        return True, ""
    except sqlite3.IntegrityError:
        return False, f"Category '{name}' already exists."


def delete_category(name):
    execute_query("UPDATE tags SET category_name = NULL WHERE category_name = ?", (name,))
    execute_query("DELETE FROM categories WHERE name = ?", (name,))


def update_tag_category(tag_name, category_name):
    cat_name_or_null = category_name if category_name and category_name != "None" else None
    execute_query("UPDATE tags SET category_name = ? WHERE name = ?", (cat_name_or_null, tag_name))


def get_tags_with_colors_and_categories():
    return fetch_all("SELECT name, color, category_name FROM tags ORDER BY name")


def get_tags():
    return fetch_all("SELECT name FROM tags ORDER BY name")


def add_tag(tag_name):
    try:
        execute_query("INSERT INTO tags (name) VALUES (?)", (tag_name,))
        return True, ""
    except sqlite3.IntegrityError:
        return False, f"Tag '{tag_name}' already exists."


def delete_tag(tag_name):
    execute_query("DELETE FROM tags WHERE name = ?", (tag_name,))


def update_tag_color(tag_name, color):
    execute_query("UPDATE tags SET color = ? WHERE name = ?", (color, tag_name))


def get_session_by_id(session_id):
    return fetch_one("SELECT tag, start_time, end_time, notes FROM sessions WHERE id = ?", (session_id,))


def update_session(session_id, tag, start, end, duration, notes):
    params = (tag, start.isoformat(), end.isoformat(), int(duration), notes, session_id)
    execute_query("UPDATE sessions SET tag=?, start_time=?, end_time=?, duration_seconds=?, notes=? WHERE id=?", params)


def add_session(tag, start, end, duration, notes):
    params = (tag, start.isoformat(), end.isoformat(), int(duration), notes)
    query = "INSERT INTO sessions (tag, start_time, end_time, duration_seconds, notes) VALUES (?, ?, ?, ?, ?)"
    return execute_query(query, params, fetch_last_id=True)


def delete_session(session_id):
    execute_query("DELETE FROM pomodoro_sessions WHERE main_session_id = ?", (session_id,))
    execute_query("DELETE FROM sessions WHERE id = ?", (session_id,))


def get_pomodoro_session_by_id(pomo_id):
    query = "SELECT p.task_title, p.task_description, p.main_session_id, s.tag FROM pomodoro_sessions p LEFT JOIN sessions s ON p.main_session_id = s.id WHERE p.id = ?"
    return fetch_one(query, (pomo_id,))


def update_pomodoro_session(pomo_id, title, desc, tag):
    execute_query("UPDATE pomodoro_sessions SET task_title=?, task_description=? WHERE id=?", (title, desc, pomo_id))
    session_data = fetch_one("SELECT main_session_id FROM pomodoro_sessions WHERE id=?", (pomo_id,))
    if session_data and session_data[0] is not None:
        main_session_id = session_data[0]
        execute_query("UPDATE sessions SET tag=? WHERE id=?", (tag, main_session_id))


def delete_pomodoro_session(pomo_id):
    session_data = fetch_one("SELECT main_session_id FROM pomodoro_sessions WHERE id=?", (pomo_id,))
    if session_data and session_data[0] is not None:
        main_session_id = session_data[0]
        execute_query("DELETE FROM sessions WHERE id=?", (main_session_id,))
    execute_query("DELETE FROM pomodoro_sessions WHERE id=?", (pomo_id,))


def add_pomodoro_session(session_type, start, end, duration, task_title, task_description, main_session_id=None):
    params = (session_type, start.isoformat(), end.isoformat(), int(duration), task_title, task_description,
              main_session_id)
    execute_query(
        "INSERT INTO pomodoro_sessions (session_type, start_time, end_time, duration_seconds, task_title, task_description, main_session_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        params)


def get_todays_pomodoro_sessions():
    today_str = datetime.now().strftime('%Y-%m-%d')
    query = "SELECT p.id, p.session_type, p.duration_seconds, p.task_title, p.start_time, p.task_description, t.color FROM pomodoro_sessions p LEFT JOIN sessions s ON p.main_session_id = s.id LEFT JOIN tags t ON s.tag = t.name WHERE date(p.start_time) = ? ORDER BY p.start_time DESC"
    return fetch_all(query, (today_str,))


def get_time_by_category(where_clause, params):
    query = f"SELECT IFNULL(t.category_name, 'Uncategorized'), SUM(s.duration_seconds) FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY IFNULL(t.category_name, 'Uncategorized')"
    return fetch_all(query, params)


def get_health_and_study_data(start_date, end_date, where_clause, params):
    health_query = "SELECT date, sleep_score, body_battery, sleep_duration_seconds, avg_stress FROM health_metrics WHERE date BETWEEN ? AND ?"
    health_params = [start_date, end_date]

    study_query = f"SELECT date(s.start_time) as date, SUM(s.duration_seconds) / 60.0 AS total_study_minutes FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY date(s.start_time)"
    study_params = params

    with db_connection() as conn:
        health_df = pd.read_sql_query(health_query, conn, params=health_params, index_col='date')
        study_df = pd.read_sql_query(study_query, conn, params=study_params, index_col='date')

    # *** BUG FIX: Use an 'outer' join to keep all dates from both datasets ***
    df = health_df.join(study_df, how='outer')
    df['total_study_minutes'] = df['total_study_minutes'].fillna(0)

    # Turn the date index into a column for plotting
    df = df.reset_index()
    df = df.rename(columns={'index': 'date'})
    return df


def get_numerical_analytics(start_date, end_date, where_clause, params):
    query = f"SELECT s.duration_seconds, date(s.start_time) as session_date, s.tag, IFNULL(t.category_name, 'Uncategorized') as category FROM sessions s JOIN tags t ON s.tag = t.name {where_clause}"

    with db_connection() as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        return {
            "total_seconds": 0, "daily_avg_seconds": 0, "num_sessions": 0,
            "num_days_worked": 0, "avg_session_seconds": 0,
            "longest_session_seconds": 0, "category_breakdown": {},
            "top_tag": "N/A", "most_productive_day": "N/A",
            "most_productive_day_seconds": 0
        }

    total_seconds = df['duration_seconds'].sum()
    num_sessions = len(df)
    num_days_worked = df['session_date'].nunique()
    daily_avg_seconds = total_seconds / num_days_worked if num_days_worked > 0 else 0
    avg_session_seconds = df['duration_seconds'].mean()
    longest_session_seconds = df['duration_seconds'].max()
    category_breakdown = df.groupby('category')['duration_seconds'].sum().to_dict()
    top_tag = df.groupby('tag')['duration_seconds'].sum().idxmax()
    daily_totals = df.groupby('session_date')['duration_seconds'].sum()
    most_productive_day = daily_totals.idxmax()
    most_productive_day_seconds = daily_totals.max()

    return {"total_seconds": total_seconds, "daily_avg_seconds": daily_avg_seconds, "num_sessions": num_sessions,
            "num_days_worked": num_days_worked, "avg_session_seconds": avg_session_seconds,
            "longest_session_seconds": longest_session_seconds, "category_breakdown": category_breakdown,
            "top_tag": top_tag, "most_productive_day": most_productive_day,
            "most_productive_day_seconds": most_productive_day_seconds}


def add_or_replace_health_metric(date, score, rhr, bb, spo2, resp, sleep_sec, stress):
    params = (date, score, rhr, bb, spo2, resp, sleep_sec, stress)
    execute_query(
        "INSERT OR REPLACE INTO health_metrics (date, sleep_score, resting_hr, body_battery, pulse_ox, respiration, sleep_duration_seconds, avg_stress) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        params)


def add_manual_sleep_entry(date_str, duration_seconds):
    existing = fetch_one("SELECT sleep_score FROM health_metrics WHERE date = ?", (date_str,))
    if existing:
        execute_query("UPDATE health_metrics SET sleep_duration_seconds = ? WHERE date = ?",
                      (duration_seconds, date_str))
    else:
        execute_query("INSERT INTO health_metrics (date, sleep_duration_seconds) VALUES (?, ?)",
                      (date_str, duration_seconds))


def add_activity(activity_type, start_time, duration_seconds, distance, calories):
    params = (activity_type, start_time.isoformat(), duration_seconds, distance, calories)
    execute_query(
        "INSERT OR IGNORE INTO activities (activity_type, start_time, duration_seconds, distance, calories) VALUES (?, ?, ?, ?, ?)",
        params)


def get_custom_factors():
    return fetch_all("SELECT name FROM custom_factors ORDER BY name")


def add_custom_factor(name, start_date):
    try:
        execute_query("INSERT INTO custom_factors (name, start_date) VALUES (?, ?)", (name, start_date.isoformat()))
        set_factor_override(name, start_date, 1)
        return True, ""
    except sqlite3.IntegrityError:
        return False, f"Factor '{name}' already exists."


def delete_custom_factor(name):
    execute_query("DELETE FROM custom_factors WHERE name = ?", (name,))


def set_factor_override(factor_name, date_obj, value):
    params = (factor_name, date_obj.isoformat(), value)
    execute_query("INSERT OR REPLACE INTO custom_factor_log (factor_name, date, value) VALUES (?, ?, ?)", params)


def get_factor_overrides_for_month(factor_name, year, month):
    month_str = f"{year}-{month:02d}"
    query = "SELECT date, value FROM custom_factor_log WHERE factor_name = ? AND strftime('%Y-%m', date) = ?"
    return fetch_all(query, (factor_name, month_str))


def get_factor_status_for_date(factor_name, date_obj):
    factor_info = fetch_one("SELECT start_date FROM custom_factors WHERE name = ?", (factor_name,))
    if not factor_info or date_obj < datetime.fromisoformat(factor_info[0]).date():
        return None

    query = "SELECT value FROM custom_factor_log WHERE factor_name = ? AND date <= ? ORDER BY date DESC LIMIT 1"
    last_status = fetch_one(query, (factor_name, date_obj.isoformat()))

    return last_status[0] if last_status is not None else None


def get_hourly_breakdown_for_day(day_iso_str, where_clause, params):
    """
    Calculates the total study minutes for each hour of a given day,
    correctly handling sessions that span multiple hours.
    """
    query = f"SELECT start_time, end_time FROM sessions s JOIN tags t ON s.tag = t.name {where_clause}"

    with db_connection() as conn:
        sessions = pd.read_sql_query(query, conn, params=params, parse_dates=['start_time', 'end_time'])

    hourly_totals = {f"{h:02d}": 0 for h in range(24)}
    if sessions.empty:
        return pd.DataFrame(list(hourly_totals.items()), columns=['hour', 'minutes'])

    for _, session in sessions.iterrows():
        start = session['start_time']
        end = session['end_time']

        current = start
        while current < end:
            hour_start = current.replace(minute=0, second=0, microsecond=0)
            next_hour_start = hour_start + timedelta(hours=1)

            overlap_end = min(end, next_hour_start)
            duration_in_hour = (overlap_end - current).total_seconds()

            hourly_totals[current.strftime('%H')] += duration_in_hour / 60.0

            current = next_hour_start

    return pd.DataFrame(list(hourly_totals.items()), columns=['hour', 'minutes'])