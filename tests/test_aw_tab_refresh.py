"""
The ActivityWatch list is slow to build, so it is rebuilt only on import or when its tab is
opened with changed data -- not on every app-wide refresh.

Uses stand-ins for the widgets, so it needs no display (and no second Tk root).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import database_manager as db
import main_app
from ui.activitywatch_tab import ActivityWatchTab


class _Recorder:
    """Accepts any method call and records its name."""
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


@pytest.fixture
def tab(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.setup_database()
    t = ActivityWatchTab.__new__(ActivityWatchTab)   # skip widget creation
    t._shown_rows = None
    t.builds = []

    def fake_refresh(rows=None):
        t.builds.append(rows)
        t._shown_rows = rows

    t.refresh = fake_refresh
    return t


def test_list_rebuilds_only_when_data_changed(tab):
    tab.refresh_if_changed()                         # first open builds, even when empty
    tab.refresh_if_changed()
    assert len(tab.builds) == 1
    db.add_or_replace_aw_daily('2026-11-20', 3600, '{}')
    tab.refresh_if_changed()
    tab.refresh_if_changed()
    assert len(tab.builds) == 2
    db.add_or_replace_aw_daily('2026-11-20', 7200, '{}')   # same day, new value
    tab.refresh_if_changed()
    assert len(tab.builds) == 3


def _fake_app(current):
    app = _Recorder()
    for name in ('tracker_tab', 'pomodoro_tab', 'analytics_tab', 'health_tab', 'aw_tab'):
        setattr(app, name, _Recorder())
    app.tab_view = type('V', (), {'get': lambda self: current})()
    app.after = lambda ms, fn: fn()
    app._stale_tabs = set()
    for name in ('refresh_tabs', '_refresh_visible_tab'):
        setattr(app, name, getattr(main_app.StudyTrackerApp, name).__get__(app))
    return app


def test_global_refresh_skips_activitywatch():
    app = _fake_app('Tracker')
    main_app.StudyTrackerApp.update_all_displays(app)
    assert app.aw_tab.calls == []
    assert app.tracker_tab.calls == ['update_tag_combobox', 'update_views']


@pytest.mark.parametrize('current, expected', [('ActivityWatch', ['refresh_if_changed']), ('Tracker', [])])
def test_opening_the_tab_refreshes_it(current, expected):
    app = _fake_app(current)
    main_app.StudyTrackerApp._on_tab_changed(app)
    assert app.aw_tab.calls == expected
