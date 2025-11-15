"""Quick test runner for ActivityWatch importer (does not require pytest)."""
import tempfile
import os
import json

import sys
import os
# Ensure project root is on sys.path when run from tests/ folder
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import activitywatch_importer as awi
from core import database_manager as db


def run():
    tmpdir = tempfile.TemporaryDirectory()
    try:
        temp_db = os.path.join(tmpdir.name, 'test_study.db')
        # Point DB to temp file
        db.DB_PATH = temp_db
        db.setup_database()

        # CSV test
        csv_path = os.path.join(tmpdir.name, 'sample_aw.csv')
        with open(csv_path, 'w', encoding='utf-8') as f:
            f.write('timestamp,duration,app\n2025-10-27T10:00:00Z,60,Code.exe\n2025-10-27T10:05:00Z,120,Code.exe\n2025-10-26T09:00:00Z,30,firefox.exe\n')

        count, msg = awi.import_aw_csv(csv_path)
        print('CSV import returned:', count, msg)
        rows = db.get_aw_daily()
        print('AW rows:', rows)

        # Tags JSON test
        json_path = os.path.join(tmpdir.name, 'cats.json')
        content = 'Make {\n  "categories": [\n    {"id": 0, "name": ["Work"], "name_pretty": "Work"},\n    {"id": 1, "name": ["Work","Programming"], "name_pretty": "Work>Programming"},\n    {"id": 2, "name": ["Work","Programming","ActivityWatch"], "name_pretty": "Work>Programming>ActivityWatch"}\n  ]\n}\n'
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(content)

        created, skipped, message = awi.import_aw_tags_json(json_path)
        print('Tags import created/skipped:', created, skipped, message)
        print('Tags in DB:', db.get_tags())

    finally:
        tmpdir.cleanup()


if __name__ == '__main__':
    run()
