import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import database_manager as db


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """The real app window on a throwaway database; skipped where Tk cannot start.

    One app for the whole run: Tk does not reliably start a second root in one process.
    """
    mp = pytest.MonkeyPatch()
    mp.setattr(db, "DB_PATH", str(tmp_path_factory.mktemp("db") / "study_sessions.db"))
    db.setup_database()
    if not db.get_tags():
        db.add_tag("General")

    import main_app
    try:
        application = main_app.StudyTrackerApp()
    except Exception as e:  # no display / Tk unavailable
        mp.undo()
        pytest.skip(f"Tk app could not start: {e}")
    application.update()
    yield application
    application.destroy()
    mp.undo()
