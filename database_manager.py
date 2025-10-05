# file: database_manager.py

import sqlite3
import os
import sys
from contextlib import contextmanager


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
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           tag TEXT NOT NULL,
                           start_time TEXT NOT NULL,
                           end_time TEXT NOT NULL,
                           duration_seconds INTEGER NOT NULL,
                           notes TEXT
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS tags
                       (
                           name TEXT PRIMARY KEY NOT NULL,
                           color TEXT DEFAULT '#3b8ed0'
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS health_metrics
                       (
                           date TEXT PRIMARY KEY,
                           sleep_score INTEGER,
                           resting_hr INTEGER,
                           body_battery INTEGER,
                           pulse_ox REAL,
                           respiration REAL,
                           sleep_duration_seconds INTEGER
                       )
                       ''')

        _add_column_if_not_exists(cursor, 'sessions', 'notes', 'TEXT')
        _add_column_if_not_exists(cursor, 'tags', 'color', "TEXT DEFAULT '#3b8ed0'")

        conn.commit()


def _add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Helper function to add a column to a table if it doesn't exist."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


# --- Generic Helper Functions ---
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

def execute_query(query, params=()):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


# --- Tag Management ---
def get_tags():
    return fetch_all("SELECT name FROM tags ORDER BY name")

def get_tags_with_colors():
    return fetch_all("SELECT name, color FROM tags ORDER BY name")

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


# --- Session Management ---
def get_session_by_id(session_id):
    return fetch_one("SELECT tag, start_time, end_time, notes FROM sessions WHERE id = ?", (session_id,))

def update_session(session_id, tag, start, end, duration, notes):
    params = (tag, start.isoformat(), end.isoformat(), int(duration), notes, session_id)
    execute_query("UPDATE sessions SET tag=?, start_time=?, end_time=?, duration_seconds=?, notes=? WHERE id=?", params)

def add_session(tag, start, end, duration, notes):
    params = (tag, start.isoformat(), end.isoformat(), int(duration), notes)
    execute_query("INSERT INTO sessions (tag, start_time, end_time, duration_seconds, notes) VALUES (?, ?, ?, ?, ?)",
                  params)

def delete_session(session_id):
    execute_query("DELETE FROM sessions WHERE id = ?", (session_id,))


# --- Health Data Management ---
def add_or_replace_health_metric(date, score, rhr, bb, spo2, resp, sleep_sec):
    params = (date, score, rhr, bb, spo2, resp, sleep_sec)
    execute_query("""
        INSERT OR REPLACE INTO health_metrics
        (date, sleep_score, resting_hr, body_battery, pulse_ox, respiration, sleep_duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, params)

def add_manual_sleep_entry(date_str, duration_seconds):
     execute_query("""
        INSERT OR REPLACE INTO health_metrics (date, sleep_duration_seconds)
        VALUES (?, ?)
    """, (date_str, duration_seconds))