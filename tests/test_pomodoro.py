"""Pomodoro timer: pauses split a session into separate entries, and breaks can be skipped."""
from datetime import datetime, timedelta

import pytest

from core import database_manager as db
import ui.pomodoro_tab as pomodoro_tab


@pytest.fixture
def pomo(app, monkeypatch):
    """The real Pomodoro tab on a clock the test controls (nothing ticks by itself)."""
    tab = app.pomodoro_tab
    tab.reset_pomodoro_timer()
    clock = [datetime(2026, 11, 24, 20, 2, 0)]

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    def run(seconds):
        for _ in range(seconds):
            clock[0] += timedelta(seconds=1)
            tab._cancel_timer()
            tab.update_pomodoro_display()

    def wait(minutes):
        clock[0] += timedelta(minutes=minutes)

    monkeypatch.setattr(pomodoro_tab, "datetime", FakeDatetime)
    monkeypatch.setattr(tab, "_send_notification", lambda *a: None)
    tab.pomo_tag_combobox.set("General")
    tab.run, tab.wait = run, wait
    yield tab
    tab.reset_pomodoro_timer()
    tab.skip_breaks.set(False)
    del tab.run, tab.wait
    db.execute_query("DELETE FROM pomodoro_sessions")
    db.execute_query("DELETE FROM sessions")
    app.update_all_displays()


def log():
    return db.fetch_all("SELECT session_type, substr(start_time, 12, 8), substr(end_time, 12, 8) "
                        "FROM pomodoro_sessions ORDER BY id")


def studied():
    return db.fetch_all("SELECT substr(start_time, 12, 8), substr(end_time, 12, 8), duration_seconds "
                        "FROM sessions ORDER BY id")


def test_each_stretch_between_pauses_is_its_own_entry(pomo):
    pomo.toggle_pomodoro_timer()
    pomo.run(360)
    pomo.toggle_pomodoro_timer()                # pause after 6 min ...
    assert studied() == [("20:02:00", "20:08:00", 360)]
    pomo.wait(71)                               # ... for longer than a whole session
    pomo.toggle_pomodoro_timer()
    pomo.run(60)
    pomo.toggle_pomodoro_timer()                # and once more
    pomo.wait(1)
    pomo.toggle_pomodoro_timer()
    assert pomo.pomo_sessions_done == 0         # pieces don't count as finished sessions
    pomo.run(18 * 60 + 1)

    assert studied() == [("20:02:00", "20:08:00", 360), ("21:19:00", "21:20:00", 60),
                         ("21:21:00", "21:39:01", 1081)]
    assert pomo.pomo_sessions_done == 1 and pomo.pomo_state == "Break"
    hours = db.get_hourly_breakdown_for_day("2026-11-24", "WHERE date(s.start_time) = ?", ["2026-11-24"])
    assert round(hours["minutes"].sum()) == 25  # the pauses are not counted as study time


def test_task_is_kept_for_all_pieces_and_cleared_at_the_end(pomo):
    pomo.pomo_task_entry.insert(0, "Chapter 3")
    pomo.toggle_pomodoro_timer()
    pomo.run(100)
    pomo.toggle_pomodoro_timer()
    pomo.toggle_pomodoro_timer()
    pomo.run(1401)
    assert db.fetch_all("SELECT task_title FROM pomodoro_sessions") == [("Chapter 3",), ("Chapter 3",)]
    assert pomo.pomo_task_entry.get() == ""


def test_pausing_after_the_long_break_still_counts_as_work(pomo):
    pomo.pomo_sessions_done = 4
    pomo._start_work()
    pomo.run(300)
    pomo.toggle_pomodoro_timer()
    pomo.toggle_pomodoro_timer()
    pomo.run(1201)
    assert [r[0] for r in log()] == ["Work", "Work"] and pomo.pomo_sessions_done == 5


def test_failed_redraw_does_not_log_a_session_twice(pomo, app, monkeypatch):
    pomo.toggle_pomodoro_timer()
    pomo.run(1500)

    def fail():
        raise RuntimeError("redraw failed")
    monkeypatch.setattr(app, "update_all_displays", fail)
    with pytest.raises(RuntimeError):
        pomo.run(1)
    monkeypatch.setattr(app, "update_all_displays", lambda: None)
    assert pomo.pomo_state == "Break"
    pomo.toggle_pomodoro_timer()
    pomo.wait(30)
    pomo.toggle_pomodoro_timer()
    pomo.run(1)
    assert len(studied()) == 1


def test_failed_save_keeps_the_timer_running_and_can_be_retried(pomo, monkeypatch):
    pomo.toggle_pomodoro_timer()
    pomo.run(60)
    real = db.add_session

    def fail(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(db, "add_session", fail)
    with pytest.raises(RuntimeError):
        pomo.toggle_pomodoro_timer()
    assert pomo.pomo_state == "Work" and pomo.pomo_timer_job
    monkeypatch.setattr(db, "add_session", real)
    pomo.run(5)
    pomo.toggle_pomodoro_timer()
    assert studied() == [("20:02:00", "20:03:05", 65)]


def test_paused_break_is_split_and_resumes_as_a_break(pomo):
    pomo.toggle_pomodoro_timer()
    pomo.run(1501)
    pomo.run(60)
    pomo.toggle_pomodoro_timer()
    pomo.wait(45)
    pomo.toggle_pomodoro_timer()
    assert pomo.pomo_state == "Break"
    pomo.run(241)
    assert [r[0] for r in log()] == ["Work", "Short Break", "Short Break"]
    assert pomo.pomo_state == "Work" and len(studied()) == 1


def test_reset_keeps_logged_pieces_and_drops_the_running_one(pomo):
    pomo.toggle_pomodoro_timer()
    pomo.run(60)
    pomo.toggle_pomodoro_timer()
    pomo.toggle_pomodoro_timer()
    pomo.run(30)
    pomo.reset_pomodoro_timer()
    assert [s[2] for s in studied()] == [60]
    assert pomo.pomo_state == "Stopped" and pomo.pomo_timer_job is None


def test_skip_breaks_setting_goes_straight_to_the_next_session(pomo):
    pomo.skip_breaks.set(True)
    pomo.toggle_pomodoro_timer()
    for done in range(1, 6):                    # past the long break too
        pomo.run(1501)
        assert pomo.pomo_state == "Work" and pomo.pomo_sessions_done == done
    assert [r[0] for r in log()] == ["Work"] * 5


@pytest.mark.parametrize("paused", [False, True])
def test_skip_break_button(pomo, paused):
    assert not pomo.pomo_skip_button.winfo_manager()
    pomo.skip_break()                           # nothing to skip yet
    assert pomo.pomo_state == "Stopped"
    pomo.toggle_pomodoro_timer()
    pomo.run(1501)
    assert pomo.pomo_skip_button.winfo_manager() == "grid"
    pomo.run(90)
    if paused:
        pomo.toggle_pomodoro_timer()
        pomo.wait(20)
    pomo.skip_break()
    assert pomo.pomo_state == "Work" and pomo.pomo_seconds_left == 1500
    assert pomo.pomo_toggle_button.cget("text") == "Pause"
    assert not pomo.pomo_skip_button.winfo_manager()
    assert [r[0] for r in log()] == ["Work", "Short Break"]
    pomo.run(1501)
    assert len(studied()) == 2


def test_fourth_session_is_followed_by_a_long_break(pomo):
    pomo.pomo_sessions_done = 3
    pomo._start_work()
    pomo.run(1501)
    assert pomo.pomo_break_type == "Long Break" and pomo.pomo_seconds_left == 15 * 60


def test_bad_settings_do_not_stop_the_timer(pomo):
    for entry in (pomo.pomo_sessions_goal, pomo.pomo_work_min):
        entry.delete(0, "end")
        entry.insert(0, "0")
    try:
        pomo.toggle_pomodoro_timer()
        pomo.run(1501)                          # fell back to 25 minutes, goal 4
        assert pomo.pomo_break_type == "Short Break"
    finally:
        for entry, value in ((pomo.pomo_sessions_goal, "4"), (pomo.pomo_work_min, "25")):
            entry.delete(0, "end")
            entry.insert(0, value)
