# file: tracker_tab.py

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta, date
import calendar

from core import database_manager as db


class TrackerTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance  # Reference to the main StudyTrackerApp instance

        # --- State Variables ---
        self.timer_running = False
        self.start_time = None
        self.current_calendar_date = datetime.now()
        self.struggle_timer_job = None
        self.struggle_seconds_left = 0

        # --- UI Setup ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._create_widgets()
        # self.update_displays() # The main app will call this after initialization

    def _create_widgets(self):
        # --- Left Frame ---
        left_frame = ctk.CTkFrame(self, width=400)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.grid_propagate(False)
        ctk.CTkLabel(left_frame, text="Timer", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        self.time_display = ctk.CTkLabel(left_frame, text="00:00:00", font=ctk.CTkFont(size=48, family="monospace"))
        self.time_display.pack(pady=10, padx=20)

        tag_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        tag_frame.pack(fill="x", padx=20, pady=10)
        tag_frame.columnconfigure(0, weight=1)
        self.tag_combobox = ctk.CTkComboBox(tag_frame, values=[])
        self.tag_combobox.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(tag_frame, text="Manage", width=70, command=self.app.open_tag_manager).grid(row=0, column=1,
                                                                                                  padx=(5, 0))

        self.toggle_button = ctk.CTkButton(left_frame, text="Start", command=self.toggle_timer, height=40)
        self.toggle_button.pack(pady=10, padx=20, fill="x")
        ctk.CTkButton(left_frame, text="Manual Session Entry", command=self.app.add_session_popup).pack(pady=5, padx=20,
                                                                                                        fill="x")

        self.struggle_frame = ctk.CTkFrame(left_frame)
        self.struggle_frame.pack(pady=10, padx=20, fill="x")
        self.struggle_frame.columnconfigure(0, weight=1)
        self.struggle_timer_button = ctk.CTkButton(self.struggle_frame, text="Start Struggle Timer (20 min)",
                                                   fg_color="#524bdb", hover_color="#423db0",
                                                   command=self.toggle_struggle_timer)
        self.struggle_timer_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.struggle_time_label = ctk.CTkLabel(self.struggle_frame, text="")
        self.struggle_time_label.grid(row=0, column=1, padx=(5, 0))

        ctk.CTkLabel(left_frame, text="Today's Sessions", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.sessions_frame = ctk.CTkScrollableFrame(left_frame, label_text="")
        self.sessions_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # --- Right Frame ---
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)  # Note: Changed row 2 to 1 for stats+calendar

        stats_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        stats_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.today_focus_label = ctk.CTkLabel(stats_frame, text="Today's Focus\n--")
        self.today_focus_label.grid(row=0, column=0, padx=5, pady=5)
        self.week_focus_label = ctk.CTkLabel(stats_frame, text="This Week\n--")
        self.week_focus_label.grid(row=0, column=1, padx=5, pady=5)
        self.daily_avg_label = ctk.CTkLabel(stats_frame, text="Daily Average\n--")
        self.daily_avg_label.grid(row=0, column=2, padx=5, pady=5)
        self.total_focus_label = ctk.CTkLabel(stats_frame, text="Lifetime Focus\n--")
        self.total_focus_label.grid(row=0, column=3, padx=5, pady=5)
        self.current_streak_label = ctk.CTkLabel(stats_frame, text="Current Streak\n-- days")
        self.current_streak_label.grid(row=1, column=0, columnspan=2, padx=5, pady=5)
        self.best_streak_label = ctk.CTkLabel(stats_frame, text="Best Streak\n-- days")
        self.best_streak_label.grid(row=1, column=2, columnspan=2, padx=5, pady=5)

        calendar_frame = ctk.CTkFrame(right_frame)
        calendar_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        calendar_frame.grid_columnconfigure(0, weight=1)
        calendar_frame.grid_rowconfigure(1, weight=1)
        calendar_header = ctk.CTkFrame(calendar_frame, fg_color="transparent")
        calendar_header.pack(fill="x", pady=10, padx=10)
        calendar_header.columnconfigure(1, weight=1)
        ctk.CTkButton(calendar_header, text="<", width=30, command=self.prev_month).grid(row=0, column=0)
        self.month_year_label = ctk.CTkLabel(calendar_header, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.month_year_label.grid(row=0, column=1)
        ctk.CTkButton(calendar_header, text=">", width=30, command=self.next_month).grid(row=0, column=2)
        self.calendar_grid = ctk.CTkFrame(calendar_frame, fg_color="transparent")
        self.calendar_grid.pack(fill="both", expand=True, padx=10, pady=10)

    def update_displays(self):
        self.update_tag_combobox()
        self.update_stats_display()
        self.update_session_list()
        self.update_calendar_display()

    def update_tag_combobox(self):
        tags = [row[0] for row in db.get_tags()]
        current_tag = self.tag_combobox.get()
        self.tag_combobox.configure(values=tags)

        if current_tag not in tags:
            current_tag = tags[0] if tags else ""
        self.tag_combobox.set(current_tag)

        # Pass the updated tags list to the main app so it can inform the pomodoro tab
        self.app.update_pomodoro_tags(tags, current_tag)

    def update_session_list(self):
        for widget in self.sessions_frame.winfo_children(): widget.destroy()
        today_str = datetime.now().strftime('%Y-%m-%d')
        query = "SELECT s.id, s.tag, s.duration_seconds, t.color, s.notes FROM sessions s JOIN tags t ON s.tag = t.name WHERE date(s.start_time) = ? ORDER BY s.start_time DESC"
        sessions = db.fetch_all(query, (today_str,))

        if not sessions:
            ctk.CTkLabel(self.sessions_frame, text="No sessions logged today.").pack()
        else:
            for session_id, tag, duration, color, notes in sessions:
                f = ctk.CTkFrame(self.sessions_frame)
                f.pack(fill="x", pady=2)
                f.columnconfigure(1, weight=1)
                ctk.CTkFrame(f, width=5, fg_color=color).grid(row=0, rowspan=2, column=0, sticky="ns", padx=(5, 0),
                                                              pady=5)
                text = f"{tag}: {str(timedelta(seconds=int(duration)))}" + (" 📝" if notes else "")
                lbl = ctk.CTkLabel(f, text=text, anchor="w", cursor="hand2" if notes else "")
                lbl.grid(row=0, column=1, sticky="ew", padx=5)
                if notes: lbl.bind("<Button-1>", lambda e, n=notes, t=tag: messagebox.showinfo(f"Note for: {t}", n))

                btn_frame = ctk.CTkFrame(f, fg_color="transparent")
                btn_frame.grid(row=0, column=2, padx=5)
                ctk.CTkButton(btn_frame, text="Edit", width=50,
                              command=lambda sid=session_id: self.app.edit_session_popup(sid)).pack(side="left")
                ctk.CTkButton(btn_frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                              command=lambda sid=session_id: self.delete_session(sid)).pack(side="left", padx=(5, 0))

    def update_stats_display(self):
        today = datetime.now()
        today_str = today.strftime('%Y-%m-%d')
        start_of_week = today - timedelta(days=today.weekday())  # Monday as start of week

        q1 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) = ?", (today_str,))
        q2 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) >= ?",
                          (start_of_week.strftime('%Y-%m-%d'),))
        q3 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions")
        q4 = db.fetch_one("SELECT COUNT(DISTINCT date(start_time)) FROM sessions")
        dates_q = db.fetch_all("SELECT DISTINCT date(start_time) FROM sessions ORDER BY date(start_time) DESC")

        today_total = q1[0] or 0
        week_total = q2[0] or 0
        total_s = q3[0] or 0
        total_d = q4[0] or 1  # Avoid division by zero

        self.today_focus_label.configure(text=f"Today's Focus\n{str(timedelta(seconds=int(today_total)))}")
        self.week_focus_label.configure(text=f"This Week\n{str(timedelta(seconds=int(week_total)))}")
        self.total_focus_label.configure(text=f"Lifetime Focus\n{str(timedelta(seconds=int(total_s)))}")
        self.daily_avg_label.configure(text=f"Daily Average\n{str(timedelta(seconds=int(total_s / total_d)))}")

        # Streak calculation
        dates = {datetime.strptime(row[0], '%Y-%m-%d').date() for row in dates_q}
        current_streak, best_streak = 0, 0
        if dates:
            today_date = date.today()
            d = today_date if today_date in dates else today_date - timedelta(days=1)
            temp_streak = 0
            while d in dates:
                temp_streak += 1
                d -= timedelta(days=1)
            if today_date in dates or (today_date - timedelta(days=1)) in dates:
                current_streak = temp_streak

            sorted_dates = sorted(list(dates))
            if sorted_dates:
                longest, current = 0, 0
                for i in range(len(sorted_dates)):
                    if i > 0 and (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
                        current += 1
                    else:
                        current = 1
                    longest = max(longest, current)
                best_streak = longest

        self.current_streak_label.configure(text=f"Current Streak\n{current_streak} days")
        self.best_streak_label.configure(text=f"Best Streak\n{best_streak} days")

    def update_calendar_display(self):
        for widget in self.calendar_grid.winfo_children(): widget.destroy()
        year, month = self.current_calendar_date.year, self.current_calendar_date.month
        self.month_year_label.configure(text=f"{self.current_calendar_date.strftime('%B %Y')}")

        query = "SELECT strftime('%d', s.start_time), s.duration_seconds, t.color FROM sessions s JOIN tags t ON s.tag = t.name WHERE strftime('%Y-%m', s.start_time) = ?"
        sessions_data = db.fetch_all(query, (f"{year}-{month:02d}",))
        sessions_by_day = {}
        for day, duration, color in sessions_data:
            day_int = int(day)
            if day_int not in sessions_by_day: sessions_by_day[day_int] = []
            sessions_by_day[day_int].append({'duration': duration, 'color': color})

        for i, day_name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(self.calendar_grid, text=day_name, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0,
                                                                                                           column=i,
                                                                                                           sticky="nsew")
            self.calendar_grid.columnconfigure(i, weight=1)

        for r, week in enumerate(calendar.monthcalendar(year, month), start=1):
            self.calendar_grid.rowconfigure(r, weight=1)
            for c, day in enumerate(week):
                if day == 0: continue
                day_frame = ctk.CTkFrame(self.calendar_grid, fg_color="transparent")
                day_frame.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                day_frame.rowconfigure(0, weight=1)
                day_frame.columnconfigure(0, weight=1)

                is_today = (date.today() == date(year, month, day))
                lbl_frame = ctk.CTkFrame(day_frame, corner_radius=5, border_width=2 if is_today else 0,
                                         border_color="#3b8ed0")
                lbl_frame.grid(row=0, column=0, sticky="nsew")
                ctk.CTkLabel(lbl_frame, text=str(day)).pack(expand=True)

                if day in sessions_by_day:
                    lbl_frame.configure(fg_color="#345e37")  # Green for days with sessions
                    bar_frame = ctk.CTkFrame(day_frame, height=5, fg_color="transparent")
                    bar_frame.grid(row=1, column=0, sticky="ew", pady=(2, 0))
                    total_dur = sum(s['duration'] for s in sessions_by_day[day])
                    if total_dur > 0:
                        relx = 0
                        for s in sessions_by_day[day]:
                            relw = s['duration'] / total_dur
                            ctk.CTkFrame(bar_frame, fg_color=s['color'], height=5, corner_radius=0).place(relx=relx,
                                                                                                          rely=0,
                                                                                                          relwidth=relw,
                                                                                                          relheight=1)
                            relx += relw

    def delete_session(self, session_id):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this session?"):
            db.delete_session(session_id)
            self.app.update_all_displays()

    def toggle_timer(self):
        if self.timer_running:
            self.timer_running = False
            self.toggle_button.configure(text="Start", **ctk.ThemeManager.theme["CTkButton"])
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds()
            db.add_session(self.tag_combobox.get(), self.start_time, end_time, duration, notes="")
            self.app.update_all_displays()
        else:
            if not self.tag_combobox.get():
                messagebox.showwarning("No Tag", "Please select or create a tag before starting.");
                return
            self.timer_running = True
            self.toggle_button.configure(text="Stop", fg_color="#db524b", hover_color="#b0423d")
            self.start_time = datetime.now()
            self.update_timer()

    def update_timer(self):
        if self.timer_running:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            self.time_display.configure(text=str(timedelta(seconds=int(elapsed))))
            self.after(1000, self.update_timer)

    def toggle_struggle_timer(self):
        if self.struggle_timer_job:
            self.after_cancel(self.struggle_timer_job)
            self.struggle_timer_job = None
            self.struggle_time_label.configure(text="")
            self.struggle_timer_button.configure(text="Start Struggle Timer (20 min)", fg_color="#524bdb",
                                                 hover_color="#423db0")
        else:
            self.struggle_seconds_left = 20 * 60
            self.update_struggle_timer()
            self.struggle_timer_button.configure(text="Cancel Timer", fg_color="#db524b", hover_color="#b0423d")

    def update_struggle_timer(self):
        if self.struggle_seconds_left > 0:
            m, s = divmod(self.struggle_seconds_left, 60)
            self.struggle_time_label.configure(text=f"{m:02d}:{s:02d}")
            self.struggle_seconds_left -= 1
            self.struggle_timer_job = self.after(1000, self.update_struggle_timer)
        else:
            self.toggle_struggle_timer()
            messagebox.showinfo("Time's Up!", "20 minutes of productive struggle is complete!")

    def prev_month(self):
        self.current_calendar_date = (self.current_calendar_date.replace(day=1) - timedelta(days=1))
        self.update_calendar_display()

    def next_month(self):
        days_in_month = calendar.monthrange(self.current_calendar_date.year, self.current_calendar_date.month)[1]
        self.current_calendar_date = self.current_calendar_date.replace(day=1) + timedelta(days=days_in_month)
        self.update_calendar_display()