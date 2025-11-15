import tempfile
import os
import json
import sqlite3

import pytest

from core import activitywatch_importer as awi
from core import database_manager as db


def _use_temp_db(monkeypatch, tmp_path):
    # Point the database manager to a temp DB for isolation
    temp_db = tmp_path / "test_study.db"
    monkeypatch.setattr(db, 'DB_PATH', str(temp_db))
    # Recreate tables
    db.setup_database()
    return str(temp_db)


def test_import_aw_csv_creates_daily_rows(monkeypatch, tmp_path):
    db_path = _use_temp_db(monkeypatch, tmp_path)

    csv_content = "timestamp,duration,app\n2025-10-27T10:00:00Z,60,Code.exe\n2025-10-27T10:05:00Z,120,Code.exe\n2025-10-26T09:00:00Z,30,firefox.exe\n"
    f = tmp_path / "sample_aw.csv"
    f.write_text(csv_content)

    count, msg = awi.import_aw_csv(str(f))
    assert count == 2

    rows = db.get_aw_daily()
    assert len(rows) == 2
    # check that totals sum properly for 2025-10-27 (60+120=180)
    dates = {r[0]: r[1] for r in rows}
    assert dates['2025-10-27'] == 180
    assert dates['2025-10-26'] == 30


def test_import_aw_tags_json(monkeypatch, tmp_path):
    db_path = _use_temp_db(monkeypatch, tmp_path)

    # Use a minimal category export resembling the provided file
    content = '''Make {
  "categories": [
    {"id": 0, "name": ["Work"], "name_pretty": "Work"},
    {"id": 1, "name": ["Work","Programming"], "name_pretty": "Work>Programming"},
    {"id": 2, "name": ["Work","Programming","ActivityWatch"], "name_pretty": "Work>Programming>ActivityWatch"}
  ]
}
'''
    f = tmp_path / "cats.json"
    f.write_text(content)

    created, skipped, message = awi.import_aw_tags_json(str(f))
    assert created >= 1
    tags = [r[0] for r in db.get_tags()]
    assert 'Work' in tags or 'Work>Programming' in tags
