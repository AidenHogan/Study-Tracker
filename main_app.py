# file: main_app.py

import customtkinter as ctk
import pandas as pd
from tkinter import messagebox, filedialog
from datetime import datetime, timedelta, date
import os
import calendar

# Import from our new modules
import database_manager as db
import plot_manager as pm
import data_importer
from ui_components import SessionEditWindow, TagManagementWindow, ManualHealthEntryWindow


class StudyTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Focus & Wellness Tracker")
        self.geometry("1200x850")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- State Variables ---
        self.timer_running = False
        self.start_time = None
        self.current_calendar_date = datetime.now()
        self.analytics_time_range = ctk.StringVar(value="30 Days")
        self.health_time_range = ctk.StringVar(value="30 Days")
        self.struggle_timer_job = None
        self.struggle_seconds_left = 0

        # --- UI Setup ---
        self._setup_tabs()
        self._create_tracker_tab()
        self._create_analytics_tab()
        self._create_health_tab()
        self.update_all_displays()

    def _setup_tabs(self):
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)
        self.tracker_tab = self.tab_view.add("Tracker")
        self.analytics_tab = self.tab_view.add("Analytics")
        self.health_tab = self.tab_view.add("Health & Wellness")

    def _create_tracker_tab(self):
        self.tracker_tab.grid_columnconfigure(1, weight=1)
        self.tracker_tab.grid_rowconfigure(0, weight=1)
        # Left Frame (Timer and Sessions)
        left_frame = ctk.CTkFrame(self.tracker_tab, width=400)
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
        ctk.CTkButton(tag_frame, text="Manage", width=70, command=self.open_tag_manager).grid(row=0, column=1, padx=(5,0))
        self.toggle_button = ctk.CTkButton(left_frame, text="Start", command=self.toggle_timer, height=40)
        self.toggle_button.pack(pady=10, padx=20, fill="x")
        ctk.CTkButton(left_frame, text="Manual Session Entry", command=self.add_session_popup).pack(pady=5, padx=20, fill="x")
        # Struggle Timer
        self.struggle_frame = ctk.CTkFrame(left_frame)
        self.struggle_frame.pack(pady=10, padx=20, fill="x")
        self.struggle_frame.columnconfigure(0, weight=1)
        self.struggle_timer_button = ctk.CTkButton(self.struggle_frame, text="Start Struggle Timer (20 min)", fg_color="#524bdb", hover_color="#423db0", command=self.toggle_struggle_timer)
        self.struggle_timer_button.grid(row=0, column=0, sticky="ew", padx=(0,5))
        self.struggle_time_label = ctk.CTkLabel(self.struggle_frame, text="")
        self.struggle_time_label.grid(row=0, column=1, padx=(5,0))
        # Session List
        ctk.CTkLabel(left_frame, text="Today's Sessions", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        self.sessions_frame = ctk.CTkScrollableFrame(left_frame, label_text="")
        self.sessions_frame.pack(pady=10, padx=20, fill="both", expand=True)

        # Right Frame (Stats and Calendar)
        right_frame = ctk.CTkFrame(self.tracker_tab)
        right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(2, weight=1)
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
        # Calendar
        calendar_frame = ctk.CTkFrame(right_frame)
        calendar_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        calendar_frame.grid_columnconfigure(0, weight=1); calendar_frame.grid_rowconfigure(1, weight=1)
        calendar_header = ctk.CTkFrame(calendar_frame, fg_color="transparent")
        calendar_header.pack(fill="x", pady=10, padx=10)
        calendar_header.columnconfigure(1, weight=1)
        ctk.CTkButton(calendar_header, text="<", width=30, command=self.prev_month).grid(row=0, column=0)
        self.month_year_label = ctk.CTkLabel(calendar_header, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.month_year_label.grid(row=0, column=1)
        ctk.CTkButton(calendar_header, text=">", width=30, command=self.next_month).grid(row=0, column=2)
        self.calendar_grid = ctk.CTkFrame(calendar_frame, fg_color="transparent")
        self.calendar_grid.pack(fill="both", expand=True, padx=10, pady=10)

    def _create_analytics_tab(self):
        self.analytics_tab.grid_columnconfigure(0, weight=1); self.analytics_tab.grid_rowconfigure(1, weight=1)
        header_frame = ctk.CTkFrame(self.analytics_tab, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(header_frame, text="Study Analytics", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        time_range_button = ctk.CTkSegmentedButton(header_frame, values=["Today", "7 Days", "30 Days", "Year"], variable=self.analytics_time_range, command=lambda v: self.update_analytics_charts())
        time_range_button.grid(row=0, column=1, padx=20, pady=5)
        ctk.CTkButton(header_frame, text="Export Data", command=self.export_data).grid(row=0, column=2, padx=(0,10))
        self.charts_frame = ctk.CTkFrame(self.analytics_tab)
        self.charts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.charts_frame.grid_columnconfigure((0, 1), weight=1); self.charts_frame.grid_rowconfigure((0, 1), weight=1)
        self.pie_chart_frame = ctk.CTkFrame(self.charts_frame)
        self.pie_chart_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.daily_bar_chart_frame = ctk.CTkFrame(self.charts_frame)
        self.daily_bar_chart_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.hourly_bar_chart_frame = ctk.CTkFrame(self.charts_frame)
        self.hourly_bar_chart_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.weekly_bar_chart_frame = ctk.CTkFrame(self.charts_frame)
        self.weekly_bar_chart_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

    def _create_health_tab(self):
        self.health_tab.grid_columnconfigure(0, weight=1); self.health_tab.grid_rowconfigure(1, weight=1)
        header_frame = ctk.CTkFrame(self.health_tab, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.columnconfigure(3, weight=1)
        ctk.CTkLabel(header_frame, text="Health & Study Correlation", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header_frame, text="Import Garmin CSV", command=self.import_garmin_data).grid(row=0, column=1, padx=(20, 5))
        ctk.CTkButton(header_frame, text="Manual Sleep Entry", command=self.open_manual_health_entry).grid(row=0, column=2, padx=(0, 20))
        time_range_button = ctk.CTkSegmentedButton(header_frame, values=["7 Days", "30 Days", "90 Days", "Year"], variable=self.health_time_range, command=lambda v: self.update_health_charts())
        time_range_button.grid(row=0, column=3, padx=20, pady=5)
        self.health_charts_frame = ctk.CTkFrame(self.health_tab)
        self.health_charts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.health_charts_frame.grid_columnconfigure((0, 1), weight=1); self.health_charts_frame.grid_rowconfigure((0, 1), weight=1)
        self.sleep_score_chart = ctk.CTkFrame(self.health_charts_frame)
        self.sleep_score_chart.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.sleep_duration_chart = ctk.CTkFrame(self.health_charts_frame)
        self.sleep_duration_chart.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.body_battery_chart = ctk.CTkFrame(self.health_charts_frame)
        self.body_battery_chart.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.trends_chart = ctk.CTkFrame(self.health_charts_frame)
        self.trends_chart.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

    # --- Methods to open popup windows ---
    def open_tag_manager(self): TagManagementWindow(self)
    def add_session_popup(self): SessionEditWindow(self, session_id=None)
    def edit_session_popup(self, session_id): SessionEditWindow(self, session_id=session_id)
    def open_manual_health_entry(self): ManualHealthEntryWindow(self)

    # --- Update Methods ---
    def update_all_displays(self):
        """Refreshes all data-driven parts of the UI."""
        self.update_tag_combobox()
        self.update_stats_display()
        self.update_session_list()
        self.update_calendar_display()
        self.update_analytics_charts()
        self.update_health_charts()

    def update_tag_combobox(self):
        tags = [row[0] for row in db.get_tags()]
        self.tag_combobox.configure(values=tags)
        if not self.tag_combobox.get() and tags:
            self.tag_combobox.set(tags[0])

    def update_session_list(self):
        for widget in self.sessions_frame.winfo_children(): widget.destroy()
        today_str = datetime.now().strftime('%Y-%m-%d')
        query = """SELECT s.id, s.tag, s.duration_seconds, t.color, s.notes
                   FROM sessions s JOIN tags t ON s.tag = t.name
                   WHERE date(s.start_time) = ? ORDER BY s.start_time DESC"""
        sessions = db.fetch_all(query, (today_str,))
        if not sessions:
            ctk.CTkLabel(self.sessions_frame, text="No sessions logged today.").pack()
        else:
            for session_id, tag, duration, color, notes in sessions:
                f = ctk.CTkFrame(self.sessions_frame); f.pack(fill="x", pady=2); f.columnconfigure(1, weight=1)
                ctk.CTkFrame(f, width=5, fg_color=color).grid(row=0, column=0, sticky="ns", padx=(5,0), pady=5)
                text = f"{tag}: {str(timedelta(seconds=duration))}" + (" (note)" if notes else "")
                lbl = ctk.CTkLabel(f, text=text, anchor="w", cursor="hand2" if notes else "")
                lbl.grid(row=0, column=1, sticky="ew", padx=5)
                if notes: lbl.bind("<Button-1>", lambda e, n=notes, t=tag: messagebox.showinfo(f"Note for: {t}", n))
                ctk.CTkButton(f, text="Edit", width=50, command=lambda sid=session_id: self.edit_session_popup(sid)).grid(row=0, column=2, padx=5)
                ctk.CTkButton(f, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d", command=lambda sid=session_id: self.delete_session(sid)).grid(row=0, column=3, padx=5)

    def update_stats_display(self):
        today = datetime.now(); today_str = today.strftime('%Y-%m-%d')
        start_of_week = today - timedelta(days=(today.weekday() + 1) % 7)
        q1 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) = ?", (today_str,))
        q2 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) >= ?", (start_of_week.strftime('%Y-%m-%d'),))
        q3 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions")
        q4 = db.fetch_one("SELECT COUNT(DISTINCT date(start_time)) FROM sessions")
        dates_q = db.fetch_all("SELECT DISTINCT date(start_time) FROM sessions ORDER BY date(start_time) DESC")
        today_total, week_total, total_s = q1[0] or 0, q2[0] or 0, q3[0] or 0
        total_d = q4[0] or 1
        self.today_focus_label.configure(text=f"Today's Focus\n{str(timedelta(seconds=today_total))}")
        self.week_focus_label.configure(text=f"This Week\n{str(timedelta(seconds=week_total))}")
        self.total_focus_label.configure(text=f"Lifetime Focus\n{str(timedelta(seconds=total_s))}")
        self.daily_avg_label.configure(text=f"Daily Average\n{str(timedelta(seconds=int(total_s / total_d)))}")
        # Streak calculation
        dates = {datetime.strptime(row[0], '%Y-%m-%d').date() for row in dates_q}
        current_streak, best_streak = 0, 0
        if dates:
            d, today_date = (date.today(), date.today())
            if today_date not in dates:
                d -= timedelta(days=1)
            temp_streak = 0
            while d in dates:
                temp_streak += 1; d -= timedelta(days=1)
            if today_date in dates or (today_date-timedelta(days=1)) in dates:
                current_streak = temp_streak
            sorted_dates = sorted(list(dates))
            if sorted_dates:
                longest, current = 1, 1
                for i in range(1, len(sorted_dates)):
                    if (sorted_dates[i] - sorted_dates[i-1]).days == 1: current += 1
                    else: longest = max(longest, current); current = 1
                best_streak = max(longest, current)
        self.current_streak_label.configure(text=f"Current Streak\n{current_streak} days")
        self.best_streak_label.configure(text=f"Best Streak\n{best_streak} days")

    def update_calendar_display(self):
        for widget in self.calendar_grid.winfo_children(): widget.destroy()
        year, month = self.current_calendar_date.year, self.current_calendar_date.month
        self.month_year_label.configure(text=f"{self.current_calendar_date.strftime('%B %Y')}")
        query = """SELECT strftime('%d', s.start_time), s.duration_seconds, t.color
                   FROM sessions s JOIN tags t ON s.tag = t.name WHERE strftime('%Y-%m', s.start_time) = ?"""
        sessions_data = db.fetch_all(query, (self.current_calendar_date.strftime('%Y-%m'),))
        sessions_by_day = {}
        for day, duration, color in sessions_data:
            day = int(day)
            if day not in sessions_by_day: sessions_by_day[day] = []
            sessions_by_day[day].append({'duration': duration, 'color': color})
        for i, day_name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(self.calendar_grid, text=day_name, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, sticky="nsew")
            self.calendar_grid.columnconfigure(i, weight=1)
        for r, week in enumerate(calendar.monthcalendar(year, month), start=1):
            self.calendar_grid.rowconfigure(r, weight=1)
            for c, day in enumerate(week):
                if day == 0: continue
                day_frame = ctk.CTkFrame(self.calendar_grid, fg_color="transparent")
                day_frame.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                day_frame.rowconfigure(0, weight=1); day_frame.columnconfigure(0, weight=1)
                is_today = (date.today() == date(year, month, day))
                lbl_frame = ctk.CTkFrame(day_frame, corner_radius=5, border_width=2 if is_today else 0, border_color="#3b8ed0")
                lbl_frame.grid(row=0, column=0, sticky="nsew")
                ctk.CTkLabel(lbl_frame, text=str(day)).pack(expand=True)
                if day in sessions_by_day:
                    lbl_frame.configure(fg_color="#345e37")
                    bar_frame = ctk.CTkFrame(day_frame, height=5, fg_color="transparent")
                    bar_frame.grid(row=1, column=0, sticky="ew", pady=(2,0))
                    total_dur = sum(s['duration'] for s in sessions_by_day[day])
                    if total_dur > 0:
                        relx = 0
                        for s in sessions_by_day[day]:
                            relw = s['duration'] / total_dur
                            ctk.CTkFrame(bar_frame, fg_color=s['color'], height=5, corner_radius=0).place(relx=relx, rely=0, relwidth=relw, relheight=1)
                            relx += relw

    def update_analytics_charts(self):
        time_range = self.analytics_time_range.get()
        today = datetime.now()
        params = []
        if time_range == "Today": start_date = today.strftime('%Y-%m-%d'); where = "WHERE date(s.start_time) = ?"
        elif time_range == "7 Days": start_date = (today - timedelta(days=6)).strftime('%Y-%m-%d'); where = "WHERE date(s.start_time) >= ?"
        elif time_range == "30 Days": start_date = (today - timedelta(days=29)).strftime('%Y-%m-%d'); where = "WHERE date(s.start_time) >= ?"
        elif time_range == "Year": start_date = (today - timedelta(days=364)).strftime('%Y-%m-%d'); where = "WHERE date(s.start_time) >= ?"
        else: where = ""
        if where != "": params = [start_date]

        # Pie Chart
        query1 = f"SELECT s.tag, SUM(s.duration_seconds), t.color FROM sessions s JOIN tags t ON s.tag = t.name {where} GROUP BY s.tag"
        pie_data = db.fetch_all(query1, params)
        fig1 = pm.create_pie_chart(pie_data, time_range)
        pm.embed_figure_in_frame(fig1, self.pie_chart_frame)

        # Daily Bar Chart
        if time_range != "Today":
            query2 = f"SELECT strftime('%Y-%m-%d', s.start_time) as day, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s {where} GROUP BY day ORDER BY day"
            daily_df = pd.DataFrame(db.fetch_all(query2, params), columns=['day', 'minutes'])
            fig2 = pm.create_daily_bar_chart(daily_df, time_range)
            pm.embed_figure_in_frame(fig2, self.daily_bar_chart_frame)
        else:
             for w in self.daily_bar_chart_frame.winfo_children(): w.destroy() # Clear frame for 'Today'

        # Hourly Bar Chart
        query3 = f"SELECT strftime('%H', s.start_time) as hour, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s {where} GROUP BY hour ORDER BY hour"
        hourly_df = pd.DataFrame(db.fetch_all(query3, params), columns=['hour', 'minutes'])
        fig3 = pm.create_hourly_bar_chart(hourly_df, time_range)
        pm.embed_figure_in_frame(fig3, self.hourly_bar_chart_frame)

        # Weekly Bar Chart
        query4 = f"SELECT strftime('%w', s.start_time) as dow, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s {where} GROUP BY dow"
        weekly_map = {int(r[0]): r[1] for r in db.fetch_all(query4, params)}
        weekly_df = pd.DataFrame({'dow': range(7), 'minutes': [weekly_map.get(i, 0) for i in range(7)]})
        fig4 = pm.create_weekly_bar_chart(weekly_df, time_range)
        pm.embed_figure_in_frame(fig4, self.weekly_bar_chart_frame)

    def update_health_charts(self):
        time_range = self.health_time_range.get()
        days = {'7 Days': 6, '30 Days': 29, '90 Days': 89, 'Year': 364}.get(time_range, 29)
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        query = """SELECT h.date, h.sleep_score, h.body_battery, h.sleep_duration_seconds,
                   IFNULL(SUM(s.duration_seconds) / 60.0, 0) AS total_study_minutes
                   FROM health_metrics h LEFT JOIN sessions s ON h.date = date(s.start_time)
                   WHERE h.date >= ? GROUP BY h.date ORDER BY h.date"""
        with db.db_connection() as conn:
            df = pd.read_sql_query(query, conn, params=[start_date])

        if df.empty:
            for frame in [self.sleep_score_chart, self.sleep_duration_chart, self.body_battery_chart, self.trends_chart]:
                 for w in frame.winfo_children(): w.destroy()
            return

        # Convert columns to numeric types to prevent plotting errors
        df['sleep_score'] = pd.to_numeric(df['sleep_score'], errors='coerce')
        df['total_study_minutes'] = pd.to_numeric(df['total_study_minutes'], errors='coerce')
        df['sleep_duration_seconds'] = pd.to_numeric(df['sleep_duration_seconds'], errors='coerce')
        df['body_battery'] = pd.to_numeric(df['body_battery'], errors='coerce')

        df['sleep_duration_hours'] = df['sleep_duration_seconds'] / 3600.0
        fig1 = pm.create_correlation_scatter_plot(df, 'sleep_score', 'total_study_minutes', f"Study vs. Sleep Score ({time_range})", "Sleep Score", "Study Minutes")
        pm.embed_figure_in_frame(fig1, self.sleep_score_chart)
        fig2 = pm.create_correlation_scatter_plot(df, 'sleep_duration_hours', 'total_study_minutes', f"Study vs. Sleep Duration ({time_range})", "Sleep Duration (Hours)", "Study Minutes")
        pm.embed_figure_in_frame(fig2, self.sleep_duration_chart)
        fig3 = pm.create_correlation_scatter_plot(df, 'body_battery', 'total_study_minutes', f"Study vs. Body Battery ({time_range})", "Body Battery", "Study Minutes")
        pm.embed_figure_in_frame(fig3, self.body_battery_chart)
        fig4 = pm.create_trends_chart(df, time_range)
        pm.embed_figure_in_frame(fig4, self.trends_chart)

    # --- Data I/O ---
    def import_garmin_data(self):
        filepath = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not filepath: return
        try:
            count, message = data_importer.import_garmin_csv(filepath)
            if count > 0:
                messagebox.showinfo("Success", f"Successfully imported {count} health record(s).")
                self.update_health_charts()
            else:
                messagebox.showwarning("No Data Imported", message)
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not process the file.\n\nError: {e}")

    def export_data(self):
        folder = filedialog.askdirectory()
        if not folder: return
        try:
            with db.db_connection() as conn:
                sessions_df = pd.read_sql_query("SELECT * FROM sessions", conn)
                health_df = pd.read_sql_query("SELECT * FROM health_metrics", conn)
            sessions_df.to_csv(os.path.join(folder, "sessions_export.csv"), index=False)
            health_df.to_csv(os.path.join(folder, "health_data_export.csv"), index=False)
            messagebox.showinfo("Success", f"Data exported to {folder}")
        except Exception as e:
            messagebox.showerror("Export Error", f"An error occurred: {e}")

    # --- Session & Timer Logic ---
    def delete_session(self, session_id):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this session?"):
            db.delete_session(session_id)
            self.update_all_displays()

    def toggle_timer(self):
        if self.timer_running:
            self.timer_running = False
            self.toggle_button.configure(text="Start", **ctk.ThemeManager.theme["CTkButton"])
            end_time = datetime.now()
            duration = (end_time - self.start_time).total_seconds()
            db.add_session(self.tag_combobox.get(), self.start_time, end_time, duration, notes="")
            self.update_all_displays()
        else:
            if not self.tag_combobox.get():
                messagebox.showwarning("No Tag", "Please select or create a tag before starting."); return
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
            self.after_cancel(self.struggle_timer_job); self.struggle_timer_job = None
            self.struggle_time_label.configure(text="")
            self.struggle_timer_button.configure(text="Start Struggle Timer (20 min)", fg_color="#524bdb", hover_color="#423db0")
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
            self.toggle_struggle_timer() # Reset button state
            messagebox.showinfo("Time's Up!", "20 minutes of productive struggle is complete!")

    # --- Calendar Navigation ---
    def prev_month(self):
        self.current_calendar_date = self.current_calendar_date.replace(day=1) - timedelta(days=1)
        self.update_calendar_display()

    def next_month(self):
        days_in_month = calendar.monthrange(self.current_calendar_date.year, self.current_calendar_date.month)[1]
        self.current_calendar_date = self.current_calendar_date.replace(day=1) + timedelta(days=days_in_month)
        self.update_calendar_display()


if __name__ == "__main__":
    db.setup_database()
    app = StudyTrackerApp()
    if not db.get_tags():
        db.add_tag('General')
        app.update_tag_combobox()
    app.mainloop()