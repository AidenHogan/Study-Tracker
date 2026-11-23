"""Redraws happen only where needed, widgets are reused, and slow work stays off the UI thread."""
import threading
import time
from datetime import datetime, date, timedelta

import pandas as pd
import pytest

from core import database_manager as db
from core import plot_manager as pm
import main_app
from ui import ui_components


def pump(app, until, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def open_tab(app, name):
    app.tab_view._segmented_button.set(name)
    app.tab_view._segmented_button_callback(name)
    end = time.time() + 0.2
    while time.time() < end:
        app.update()
        time.sleep(0.01)


@pytest.fixture
def tracker(app):
    """The app on its Tracker tab, showing today; sessions added by a test are removed again."""
    open_tab(app, "Tracker")
    tab = app.tracker_tab
    tab.selected_date, tab.current_calendar_date = date.today(), datetime.now()
    app.update_all_displays()
    yield tab
    for (sid,) in db.fetch_all("SELECT id FROM sessions"):
        db.delete_session(sid)
    open_tab(app, "Tracker")
    app.update_all_displays()


@pytest.fixture
def dialogs(monkeypatch):
    shown = []
    for name in ("showinfo", "showerror", "showwarning", "askyesno"):
        monkeypatch.setattr(main_app.messagebox, name,
                            lambda title, text="", _n=name, **k: shown.append((_n, title, text)) and False)
    return shown


def add_session(minutes, notes="", hour=9):
    start = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=hour)
    return db.add_session("General", start, start + timedelta(minutes=minutes), minutes * 60, notes)


# --- only the visible tab is redrawn ------------------------------------------------------

def test_hidden_tabs_wait_until_opened(app, tracker, monkeypatch):
    drawn = []
    monkeypatch.setattr(app.health_tab, "update_charts", lambda: drawn.append("health"))
    monkeypatch.setattr(app.analytics_tab, "update_charts", lambda: drawn.append("analytics"))
    monkeypatch.setattr(app.pomodoro_tab, "update_pomodoro_log", lambda: drawn.append("pomodoro"))

    app.update_all_displays()
    app.update_all_displays()
    assert drawn == []
    open_tab(app, "Health & Wellness")
    open_tab(app, "Tracker")
    open_tab(app, "Health & Wellness")      # unchanged since: not redrawn
    assert drawn == ["health"]
    app.update_health_charts()              # visible: redrawn at once
    assert drawn == ["health", "health"]
    open_tab(app, "Pomodoro")
    assert drawn == ["health", "health", "pomodoro"]


def test_failed_refresh_is_retried_on_next_open(app, tracker, monkeypatch):
    def fail():
        raise RuntimeError("boom")
    open_tab(app, "Health & Wellness")
    monkeypatch.setattr(app.health_tab, "update_charts", fail)
    with pytest.raises(RuntimeError):
        app.update_health_charts()
    assert "Health & Wellness" in app._stale_tabs


def test_opening_tracker_keeps_the_pomodoro_tag(app, tracker):
    db.add_tag("Zoology")
    open_tab(app, "Pomodoro")
    app.update_all_displays()
    app.pomodoro_tab.pomo_tag_combobox.set("Zoology")
    open_tab(app, "Tracker")                # refreshes because it is stale
    assert app.pomodoro_tab.pomo_tag_combobox.get() == "Zoology"


def test_pomodoro_keeps_its_subject_after_a_work_session(app, tracker, monkeypatch):
    db.add_tag("Zoology")
    app.update_all_displays()
    pomo = app.pomodoro_tab
    monkeypatch.setattr(pomo, "_send_notification", lambda *a: None)
    tracker.tag_combobox.set("General")
    pomo.pomo_tag_combobox.set("Zoology")
    pomo.pomo_state, pomo.pomo_start_time = "Work", datetime.now() - timedelta(minutes=25)
    try:
        pomo._finish_pomodoro_session()
    finally:
        pomo.reset_pomodoro_timer()
    assert db.fetch_all("SELECT tag FROM sessions") == [("Zoology",)]
    assert pomo.pomo_tag_combobox.get() == "Zoology"
    assert tracker.tag_combobox.get() == "General"


def test_pomodoro_falls_back_when_its_tag_is_gone(app, tracker):
    tags = ["General", "Other"]
    app.pomodoro_tab.pomo_tag_combobox.set("Deleted")
    app.pomodoro_tab.update_pomo_tag_combobox(tags, "Other")
    assert app.pomodoro_tab.pomo_tag_combobox.get() == "Other"
    app.refresh_tag_lists()


def test_manual_sleep_entry_saves_and_closes(app, tracker, monkeypatch):
    monkeypatch.setattr(app.health_tab, "update_charts", lambda: None)
    win = ui_components.ManualHealthEntryWindow(app)
    win.sleep_duration_entry.insert(0, "07:30")
    win.save_health_data()
    app.update()
    assert not win.winfo_exists()
    assert {"Analytics", "Health & Wellness"} <= app._stale_tabs


# --- tracker widgets are updated in place -------------------------------------------------

def test_session_rows_are_reused(app, tracker, monkeypatch):
    opened, notes = [], []
    monkeypatch.setattr(app, "edit_session_popup", opened.append)
    add_session(30, notes="chapter 3", hour=9)
    add_session(60, hour=11)
    app.update_all_displays()
    visible = [r for r in tracker._session_rows if r['visible']]
    assert [r['label'].cget("text") for r in visible] == ["General: 1:00:00", "General: 0:30:00 📝"]
    widgets = [r['frame'] for r in tracker._session_rows]

    db.delete_session(visible[0]['data'][0])
    app.update_all_displays()
    assert [r['frame'] for r in tracker._session_rows] == widgets
    visible = [r for r in tracker._session_rows if r['visible']]
    assert [r['label'].cget("text") for r in visible] == ["General: 0:30:00 📝"]
    # The reused row acts on the session it shows now.
    edit = visible[0]['frame'].winfo_children()[-1].winfo_children()[0]
    edit.invoke()
    assert opened == [visible[0]['data'][0]]
    assert visible[0]['data'][4] == "chapter 3"

    db.delete_session(visible[0]['data'][0])
    app.update_all_displays()
    assert not any(r['visible'] for r in tracker._session_rows)
    assert tracker.no_sessions_label.winfo_manager() == "pack"


def test_calendar_only_touches_days_that_changed(app, tracker, monkeypatch):
    add_session(30)
    app.update_all_displays()
    slot = next(s for s in tracker.day_widgets if s['date_obj'] == date.today())
    assert len([b for b in slot['bars'] if b.winfo_manager()]) == 1 and slot['lbl_frame'].cget("fg_color") == "#345e37"

    touched = []
    for s in tracker.day_widgets:
        for part in ('lbl_frame', 'day_label'):
            monkeypatch.setattr(s[part], "configure", lambda _s=s, **k: touched.append(_s['date_obj']))
    tracker.update_calendar_display()
    assert touched == []
    monkeypatch.undo()

    bar = slot['bars'][0]
    add_session(30, hour=11)
    app.update_all_displays()
    assert slot['bars'][0] is bar and len([b for b in slot['bars'] if b.winfo_manager()]) == 2
    tracker.prev_month(); tracker.next_month()
    slot = next(s for s in tracker.day_widgets if s['date_obj'] == date.today())
    assert len([b for b in slot['bars'] if b.winfo_manager()]) == 2


# --- charts reuse their canvas -------------------------------------------------------------

def test_chart_canvas_is_reused_and_hidden_when_empty(app, tracker):
    import tkinter as tk
    frame = tk.Frame(app)
    frame.place(x=0, y=0, width=300, height=200)
    app.update()
    df = pd.DataFrame({'hour': ['09', '10'], 'minutes': [10, 20]})
    try:
        pm.embed_figure_in_frame(pm.create_hourly_bar_chart(df, "Week"), frame)
        pump(app, lambda: getattr(frame._canvas_widget, '_drawn_once', False))
        canvas = frame._canvas_widget

        pm.clear_frame(frame)
        tk.Label(frame, text="text page").pack()
        app.update()
        assert not canvas.get_tk_widget().winfo_manager()

        fig = pm.create_hourly_bar_chart(df, "Month")
        pm.embed_figure_in_frame(fig, frame)
        assert frame._canvas_widget is canvas and canvas.figure is fig
        assert frame.winfo_children() == [canvas.get_tk_widget()]   # the label is gone
        pump(app, lambda: canvas._drawn_once)

        frame.place(width=420, height=260)                          # resizing follows the frame
        pump(app, lambda: (canvas._tkphoto.width(), canvas._tkphoto.height()) == (414, 254))

        pm.embed_figure_in_frame(None, frame)                       # nothing to plot
        assert not canvas.get_tk_widget().winfo_manager()
    finally:
        frame.destroy()
        app.update()


def test_window_drag_redraws_once(app, tracker, monkeypatch):
    import tkinter as tk
    frame = tk.Frame(app)
    frame.place(x=0, y=0, width=300, height=200)
    app.update()
    df = pd.DataFrame({'hour': ['09'], 'minutes': [10]})
    try:
        pm.embed_figure_in_frame(pm.create_hourly_bar_chart(df, "Week"), frame)
        canvas = frame._canvas_widget
        pump(app, lambda: getattr(canvas, '_drawn_once', False))
        draws = []
        monkeypatch.setattr(canvas, "draw", lambda: draws.append(1))
        for i in range(10):
            frame.place(width=300 + 5 * i, height=200)
            app.update()
        pump(app, lambda: canvas.get_tk_widget().winfo_width() == 339)
        app.update()
        assert len(draws) <= 2
    finally:
        frame.destroy()
        app.update()


# --- background work -----------------------------------------------------------------------

def test_analytics_runs_one_worker_and_shows_only_the_latest(app, tracker):
    tab = app.analytics_tab
    gate, started, shown = threading.Event(), [], []

    def request(n):
        def compute():
            started.append(n)
            gate.wait(5)
            return n
        tab._pending_job = (compute, shown.append)
        tab._start_pending_job()

    for n in (1, 2, 3):
        request(n)
    pump(app, lambda: started == [1])
    time.sleep(0.1)
    assert started == [1]
    gate.set()
    pump(app, lambda: shown)
    assert started == [1, 3] and shown == [3]


def test_analytics_recovers_when_a_worker_dies(app, tracker, monkeypatch):
    monkeypatch.setattr(threading, "excepthook", lambda a: None)
    tab, shown = app.analytics_tab, []

    def compute():
        raise SystemError("crash")
    tab._pending_job = (compute, shown.append)
    tab._start_pending_job()
    pump(app, lambda: shown)
    assert 'error' in shown[0] and tab._running_job is None


SUMMARY = {"days_updated": 2, "summaries": 5, "backfill_requested": 0, "skipped": [], "csv_path": None}


def test_garmin_sync_keeps_the_window_responsive(app, tracker, dialogs, monkeypatch):
    gate, threads, days_seen = threading.Event(), [], []

    def fake_sync(days=None):
        threads.append(threading.current_thread())
        days_seen.append(days)
        gate.wait(5)
        return SUMMARY
    monkeypatch.setattr(main_app.garmin_downloader, "sync_health_data", fake_sync)

    app._run_garmin_sync(7)
    ticks = []
    app.after(50, lambda: ticks.append(1))
    pump(app, lambda: ticks and threads)          # the UI loop runs while the sync waits
    assert threads[0] is not threading.main_thread() and days_seen == [7]
    app.sync_and_import_garmin_data()             # a second sync is ignored
    app.disconnect_garmin()                       # and the connection can't be pulled away
    assert [d[0] for d in dialogs] == ["showinfo"] and "running" in dialogs[0][2]

    app._stale_tabs.clear()
    gate.set()
    pump(app, lambda: not app._garmin_syncing)
    assert "Updated 2 day(s)" in dialogs[-1][2]
    assert "Health & Wellness" in app._stale_tabs
    assert app.health_tab.sync_button.cget("state") == "normal"


@pytest.mark.parametrize("error, kind, title", [
    (main_app.garmin_downloader.GarminConfigError("x"), "askyesno", "Garmin API Not Configured"),
    (main_app.garmin_downloader.GarminAPIError("x"), "showerror", "Sync Error"),
    (main_app.garmin_downloader.GarminAuthError("x"), "askyesno", None),
    (OSError("offline"), "showerror", "Sync Error"),
])
def test_garmin_sync_errors_are_reported_and_reset_the_button(app, tracker, dialogs, monkeypatch, error, kind, title):
    def fake_sync(days=None):
        raise error
    monkeypatch.setattr(main_app.garmin_downloader, "sync_health_data", fake_sync)
    app._run_garmin_sync(None)
    pump(app, lambda: dialogs)
    assert dialogs[0][0] == kind and (title is None or dialogs[0][1] == title)
    assert not app._garmin_syncing and app.health_tab.sync_button.cget("state") == "normal"
