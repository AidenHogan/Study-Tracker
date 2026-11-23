"""
Tags/categories changed in the Manage Tags window must show up at once in every dropdown
that lists them (tracker, pomodoro, analytics category filter), without restarting the app.

Builds the real app window against a throwaway database, so it needs a display; it is
skipped where Tk cannot start.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import database_manager as db


def _open_tag_manager(app):
    from ui.ui_components import TagManagementWindow
    win = TagManagementWindow(app)
    app.update()
    return win


def _tracker_tags(app):
    return list(app.tracker_tab.tag_combobox.cget("values"))


def _pomo_tags(app):
    return list(app.pomodoro_tab.pomo_tag_combobox.cget("values"))


def test_added_tag_appears_in_tracker_and_pomodoro_dropdowns(app):
    win = _open_tag_manager(app)
    assert "Biology" not in _tracker_tags(app)

    win.new_tag_entry.insert(0, "Biology")
    win.add_tag()

    assert "Biology" in _tracker_tags(app)
    assert "Biology" in _pomo_tags(app)
    # The user's current selection is kept.
    assert app.tracker_tab.tag_combobox.get() == "General"
    win.destroy()


def test_archive_and_restore_update_dropdowns(app, monkeypatch):
    db.add_tag("Chemistry")
    app.tracker_tab.update_tag_combobox()
    win = _open_tag_manager(app)

    # 'no' in the delete dialog means Archive.
    monkeypatch.setattr("ui.ui_components.messagebox.askquestion", lambda *a, **k: "no")
    win.delete_tag("Chemistry")
    assert "Chemistry" not in _tracker_tags(app)
    assert "Chemistry" not in _pomo_tags(app)

    restore_win = type("W", (), {"destroy": lambda self: None})()
    win._restore_and_refresh(restore_win, "Chemistry")
    assert "Chemistry" in _tracker_tags(app)
    assert "Chemistry" in _pomo_tags(app)
    win.destroy()


def test_categories_update_analytics_filter(app):
    win = _open_tag_manager(app)
    combo = app.analytics_tab.category_combo

    win.new_cat_entry.insert(0, "Science")
    win.add_category()
    assert "Science" in combo.cget("values")

    app.analytics_tab.category_filter.set("Science")
    win.delete_category("Science")
    assert "Science" not in combo.cget("values")
    assert app.analytics_tab.category_filter.get() == "All Time"
    win.destroy()
