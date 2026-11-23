# file: tracker_tab.py

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime, timedelta, date
import calendar

from core import database_manager as db

DEFAULT_TAG_COLOR = "#3b8ed0"  # same as the tags table's default


class TrackerTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance  # Reference to the main StudyTrackerApp instance

        # --- State Variables ---
        self.timer_running = False
        self.timer_job = None
        self.start_time = None
        self.current_calendar_date = datetime.now()
        self.selected_date = date.today()  # Date whose sessions are displayed/editable
        self.struggle_timer_job = None
        self.struggle_seconds_left = 0

        # --- UI Setup ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        # --- Left Frame ---
        left_frame = ctk.CTkFrame(self, width=400)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.grid_propagate(False)
        
        # Title with help button
        title_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        title_frame.pack(pady=(20, 10), fill="x", padx=20)
        ctk.CTkLabel(title_frame, text="Timer", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(title_frame, text="?", width=30, command=self._show_overview_help_modal).pack(side="right")
        
        self.time_display = ctk.CTkLabel(left_frame, text="00:00:00", font=ctk.CTkFont(size=48, family="monospace"))
        self.time_display.pack(pady=10, padx=20)

        # Tag Frame
        tag_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        tag_frame.pack(fill="x", padx=20, pady=10)
        tag_frame.columnconfigure(0, weight=1)
        self.tag_combobox = ctk.CTkComboBox(tag_frame, values=[])
        self.tag_combobox.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(tag_frame, text="Manage", width=70, command=self.app.open_tag_manager).grid(row=0, column=1, padx=(5, 0))

        # Timer Start
        self.toggle_button = ctk.CTkButton(left_frame, text="Start", command=self.toggle_timer, height=40)
        self.toggle_button.pack(pady=10, padx=20, fill="x")
        
        # Manual Entry
        ctk.CTkButton(left_frame, text="Manual Session Entry", command=self.app.add_session_popup).pack(pady=5, padx=20, fill="x")

        # --- Updated Struggle Frame (Custom Time) ---
        self.struggle_frame = ctk.CTkFrame(left_frame)
        self.struggle_frame.pack(pady=10, padx=20, fill="x")
        self.struggle_frame.columnconfigure(2, weight=1)  # Button takes remaining space

        # Input for custom minutes
        self.struggle_duration_entry = ctk.CTkEntry(self.struggle_frame, width=50, placeholder_text="20", justify="center")
        self.struggle_duration_entry.insert(0, "20")  # Default value
        self.struggle_duration_entry.grid(row=0, column=0, padx=(5, 2), pady=5)

        ctk.CTkLabel(self.struggle_frame, text="min").grid(row=0, column=1, padx=(0, 5))

        self.struggle_timer_button = ctk.CTkButton(self.struggle_frame, text="Start Struggle",
                                                   fg_color="#524bdb", hover_color="#423db0",
                                                   command=self.toggle_struggle_timer)
        self.struggle_timer_button.grid(row=0, column=2, sticky="ew", padx=(0, 5))
        
        self.struggle_time_label = ctk.CTkLabel(self.struggle_frame, text="", width=40)
        self.struggle_time_label.grid(row=0, column=3, padx=(0, 5))

        self.sessions_title_label = ctk.CTkLabel(left_frame, text="Sessions for Today", font=ctk.CTkFont(size=16, weight="bold"))
        self.sessions_title_label.pack(pady=(10, 5))
        self.sessions_frame = ctk.CTkScrollableFrame(left_frame, label_text="")
        self.sessions_frame.pack(pady=10, padx=20, fill="both", expand=True)
        self.no_sessions_label = ctk.CTkLabel(self.sessions_frame, text="No sessions logged today.")
        self._session_rows = []       # reusable row widgets
        self._shown_sessions = None   # (date, rows) currently listed

        # --- Right Frame (Stats & Calendar) ---
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)

        stats_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        stats_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # These are the labels causing the AttributeError
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
        
        #Builds a permanent 42-slot grid
        self._init_calendar_grid()

    def _init_calendar_grid(self):
        self.day_widgets = []
        
        # Create Day Headers (Sun - Sat)
        for i, day_name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(self.calendar_grid, text=day_name, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, sticky="nsew")
            self.calendar_grid.columnconfigure(i, weight=1)
            
        # Create a 6-row by 7-column grid of reusable day slots
        for r in range(1, 7):
            self.calendar_grid.rowconfigure(r, weight=1)
            for c in range(7):
                day_frame = ctk.CTkFrame(self.calendar_grid, fg_color="transparent")
                day_frame.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                day_frame.rowconfigure(0, weight=1)
                day_frame.columnconfigure(0, weight=1)
                
                lbl_frame = ctk.CTkFrame(day_frame, corner_radius=5, border_width=0)
                lbl_frame.grid(row=0, column=0, sticky="nsew")
                
                day_label = ctk.CTkLabel(lbl_frame, text="")
                day_label.pack(expand=True)
                
                bar_frame = ctk.CTkFrame(day_frame, height=5, fg_color="transparent")
                bar_frame.grid(row=1, column=0, sticky="ew", pady=(2, 0))
                
                # Store references in a dictionary
                widget_dict = {
                    'day_frame': day_frame,
                    'lbl_frame': lbl_frame,
                    'day_label': day_label,
                    'bar_frame': bar_frame,
                    'date_obj': None,
                    'bars': [],        # reusable duration-bar frames
                    'shown': {}        # what each part currently displays, to skip no-op updates
                }
                self.day_widgets.append(widget_dict)
                
                # Bind click events
                lbl_frame.bind("<Button-1>", lambda e, idx=len(self.day_widgets)-1: self._on_day_clicked(idx))
                day_label.bind("<Button-1>", lambda e, idx=len(self.day_widgets)-1: self._on_day_clicked(idx))

    def _on_day_clicked(self, widget_index):
        clicked_dict = self.day_widgets[widget_index]
        clicked_date = clicked_dict['date_obj']
        
        if not clicked_date: 
            return # Clicked an empty padding slot
        
        self.selected_date = clicked_date
        for d in self.day_widgets:
            self._style_day_border(d)

        self.update_session_list()

    @staticmethod
    def _changed(slot, part, value):
        """Remember what `part` of a calendar slot shows; True if that is different from before."""
        if slot['shown'].get(part, ()) == value:
            return False
        slot['shown'][part] = value
        return True

    def _style_day_border(self, slot):
        """Orange border on the selected day, blue on today, none elsewhere."""
        day = slot['date_obj']
        if day is None:
            return
        if day == self.selected_date:
            border = (2, "#db8e3b")
        elif day == date.today():
            border = (2, "#3b8ed0")
        else:
            border = (0, "#3b8ed0")
        if self._changed(slot, 'border', border):
            slot['lbl_frame'].configure(border_width=border[0], border_color=border[1])

    def update_displays(self):
        self.update_tag_combobox()
        self.update_views()

    def update_views(self):
        """Refresh everything except the tag dropdowns (which also set the Pomodoro tab's tag)."""
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
        target_str = self.selected_date.strftime('%Y-%m-%d')
        query = "SELECT s.id, s.tag, s.duration_seconds, t.color, s.notes FROM sessions s JOIN tags t ON s.tag = t.name WHERE date(s.start_time) = ? ORDER BY s.start_time DESC"
        sessions = db.fetch_all(query, (target_str,))

        if self._shown_sessions == (target_str, sessions):
            return
        self._shown_sessions = (target_str, sessions)
        self.sessions_title_label.configure(text=f"Sessions for {target_str}")

        # Rows are kept and refilled; only as many as the busiest day shown so far exist.
        while len(self._session_rows) < len(sessions):
            self._session_rows.append(self._create_session_row())
        for i, row in enumerate(self._session_rows):
            if i < len(sessions):
                self._fill_session_row(row, sessions[i])
                if not row['visible']:
                    row['frame'].pack(fill="x", pady=2)
                    row['visible'] = True
            elif row['visible']:
                row['frame'].pack_forget()
                row['visible'] = False

        if sessions:
            self.no_sessions_label.pack_forget()
        else:
            self.no_sessions_label.pack()

    def _create_session_row(self):
        f = ctk.CTkFrame(self.sessions_frame)
        f.columnconfigure(1, weight=1)
        row = {'frame': f, 'visible': False, 'data': None}

        row['color'] = ctk.CTkFrame(f, width=5)
        row['color'].grid(row=0, rowspan=2, column=0, sticky="ns", padx=(5, 0), pady=5)

        def show_note(_event):
            _, tag, _, _, notes = row['data']
            if notes:
                messagebox.showinfo(f"Note for: {tag}", notes)

        row['label'] = ctk.CTkLabel(f, text="", anchor="w")
        row['label'].grid(row=0, column=1, sticky="ew", padx=5)
        row['label'].bind("<Button-1>", show_note)

        btn_frame = ctk.CTkFrame(f, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=5)
        ctk.CTkButton(btn_frame, text="Edit", width=50,
                      command=lambda: self.app.edit_session_popup(row['data'][0])).pack(side="left")
        ctk.CTkButton(btn_frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                      command=lambda: self.delete_session(row['data'][0])).pack(side="left", padx=(5, 0))
        return row

    def _fill_session_row(self, row, data):
        old, row['data'] = row['data'], data
        if old == data:
            return
        _, tag, duration, color, notes = data
        if old is None or old[3] != color:
            row['color'].configure(fg_color=color or DEFAULT_TAG_COLOR)
        text = f"{tag}: {str(timedelta(seconds=int(duration)))}" + (" 📝" if notes else "")
        row['label'].configure(text=text, cursor="hand2" if notes else "")

    def update_stats_display(self):
        today = datetime.now()
        today_str = today.strftime('%Y-%m-%d')
        start_of_week = today - timedelta(days=today.weekday())  # Monday as start of week

        q1 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) = ?", (today_str,))
        q2 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions WHERE date(start_time) >= ?",
                          (start_of_week.strftime('%Y-%m-%d'),))
        q3 = db.fetch_one("SELECT SUM(duration_seconds) FROM sessions")
        earliest = db.get_earliest_session_date()
        q4 = db.fetch_one("SELECT COUNT(DISTINCT date(start_time)) FROM sessions")
        dates_q = db.fetch_all("SELECT DISTINCT date(start_time) FROM sessions ORDER BY date(start_time) DESC")

        today_total = (q1[0] or 0) if q1 else 0
        week_total = (q2[0] or 0) if q2 else 0
        total_s = (q3[0] or 0) if q3 else 0
        if earliest:
            total_days_span = (date.today() - earliest).days + 1
        else:
            total_days_span = (q4[0] or 1) if q4 else 1
        total_d = total_days_span or 1  # Avoid division by zero

        self.today_focus_label.configure(text=f"Today's Focus\n{str(timedelta(seconds=int(today_total)))}")
        self.week_focus_label.configure(text=f"This Week\n{str(timedelta(seconds=int(week_total)))}")
        self.total_focus_label.configure(text=f"Lifetime Focus\n{str(timedelta(seconds=int(total_s)))}")
        self.daily_avg_label.configure(text=f"Daily Average\n{str(timedelta(seconds=int(total_s / total_d)))}")

        # Streak calculation
        dates = {datetime.strptime(row[0], '%Y-%m-%d').date() for row in dates_q} if dates_q else set()
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
        year, month = self.current_calendar_date.year, self.current_calendar_date.month
        self.month_year_label.configure(text=f"{self.current_calendar_date.strftime('%B %Y')}")

        # Fetch data
        query = "SELECT strftime('%d', s.start_time), s.duration_seconds, t.color FROM sessions s JOIN tags t ON s.tag = t.name WHERE strftime('%Y-%m', s.start_time) = ?"
        sessions_data = db.fetch_all(query, (f"{year}-{month:02d}",))
        
        sessions_by_day = {}
        for day, duration, color in sessions_data:
            day_int = int(day)
            if day_int not in sessions_by_day: sessions_by_day[day_int] = []
            sessions_by_day[day_int].append({'duration': duration, 'color': color})

        # Calculate layout
        cal = calendar.Calendar(firstweekday=6)
        weeks = cal.monthdayscalendar(year, month)
        flat_days = [day for week in weeks for day in week]
        today_date = date.today()

        # Update existing widgets, touching only the parts that look different from before
        for i, slot in enumerate(self.day_widgets):
            day = flat_days[i] if i < len(flat_days) else 0
            if day == 0:
                # Padding day, hide the slot
                slot['date_obj'] = None
                if self._changed(slot, 'visible', False):
                    slot['day_frame'].grid_remove()
                continue

            slot['date_obj'] = date(year, month, day)
            if self._changed(slot, 'visible', True):
                slot['day_frame'].grid()
            if self._changed(slot, 'text', day):
                slot['day_label'].configure(text=str(day))
            self._style_day_border(slot)
            bg_color = "#345e37" if day in sessions_by_day else "transparent"
            if self._changed(slot, 'bg', bg_color):
                slot['lbl_frame'].configure(fg_color=bg_color)

            day_sessions = sessions_by_day.get(day, [])
            total_dur = sum(s['duration'] for s in day_sessions)
            bars = [(s['color'] or DEFAULT_TAG_COLOR, s['duration'] / total_dur) for s in day_sessions] if total_dur > 0 else []
            if self._changed(slot, 'bars', bars):
                self._update_day_bars(slot, bars)

    def _update_day_bars(self, slot, bars):
        """Show one colored segment per session, reusing the slot's existing segments."""
        frames = slot['bars']
        while len(frames) < len(bars):
            frames.append(ctk.CTkFrame(slot['bar_frame'], height=5, corner_radius=0))
        relx = 0
        for frame, (color, relw) in zip(frames, bars):
            frame.configure(fg_color=color)
            frame.place(relx=relx, rely=0, relwidth=relw, relheight=1)
            relx += relw
        for frame in frames[len(bars):]:
            frame.place_forget()

    def delete_session(self, session_id):
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this session?"):
            db.delete_session(session_id)
            self.app.update_all_displays()

    def toggle_timer(self):
        if self.timer_running:
            self.timer_running = False
            if self.timer_job:
                self.after_cancel(self.timer_job)
                self.timer_job = None
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
            self.timer_job = self.after(1000, self.update_timer)

    def toggle_struggle_timer(self):
        if self.struggle_timer_job:
            # Stop the timer
            self.after_cancel(self.struggle_timer_job)
            self.struggle_timer_job = None
            self.struggle_time_label.configure(text="")
            
            # Reset UI
            self.struggle_timer_button.configure(text="Start Struggle", fg_color="#524bdb", hover_color="#423db0")
            self.struggle_duration_entry.configure(state="normal") # Re-enable input
        else:
            # Start the timer
            try:
                minutes = int(self.struggle_duration_entry.get())
                if minutes <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid Time", "Please enter a valid number of minutes (integer > 0).")
                return

            self.struggle_seconds_left = minutes * 60
            self.update_struggle_timer()
            
            # Update UI
            self.struggle_timer_button.configure(text="Cancel", fg_color="#db524b", hover_color="#b0423d")
            self.struggle_duration_entry.configure(state="disabled") # Disable input while running

    def update_struggle_timer(self):
        if self.struggle_seconds_left > 0:
            m, s = divmod(self.struggle_seconds_left, 60)
            self.struggle_time_label.configure(text=f"{m:02d}:{s:02d}")
            self.struggle_seconds_left -= 1
            self.struggle_timer_job = self.after(1000, self.update_struggle_timer)
        else:
            # Timer Finished naturally
            self.toggle_struggle_timer() # This will reset the button text and re-enable the entry
            messagebox.showinfo("Time's Up!", "Struggle session complete!")

    def prev_month(self):
        self.current_calendar_date = (self.current_calendar_date.replace(day=1) - timedelta(days=1))
        self.update_calendar_display()

    def next_month(self):
        last_day = calendar.monthrange(self.current_calendar_date.year, self.current_calendar_date.month)[1]
        self.current_calendar_date = (self.current_calendar_date.replace(day=1) + timedelta(days=last_day))
        self.update_calendar_display()

    # Help modals
    def _show_overview_help_modal(self):
        help_text = (
            "TRACKER TAB - Study Time Tracking\n\n"
            "TIMER:\n"
            "• Click 'Start' to begin tracking a study session\n"
            "• Select a subject tag to categorize your work\n"
            "• Timer runs until you click 'Stop'\n"
            "• Sessions are automatically saved to your log\n\n"
            "STRUGGLE TIMER:\n"
            "• Use this for focused n-minute deep work sessions\n"
            "• Helps track productive struggle time\n"
            "• Separate from main timer - use for specific challenges\n\n"
            "MANUAL ENTRY:\n"
            "• Add sessions you forgot to track\n"
            "• Edit existing sessions to correct errors\n"
            "• Add notes to remember what you worked on\n\n"
            "STATS:\n"
            "• Today's Focus: Total time tracked today\n"
            "• This Week: Total for current week (Mon-Sun)\n"
            "• Daily Average: Your average across all days\n"
            "• Streaks: Consecutive days with study sessions\n\n"
            "CALENDAR:\n"
            "• Green days = study session logged\n"
            "• Gray days = no session\n"
            "• Click days to see session details"
        )
        messagebox.showinfo("Tracker Tab Help", help_text)
    
    def _show_manual_entry_help_modal(self):
        help_text = (
            "MANUAL ENTRY - Create Activities\n\n"
            "TIME:\n"
            "• Time is in the 24 format, so 0:01 is 12am, 12:00 is 12pm, 13:00 is 1pm, and so on until 23:59 is 11:59 pm\n"
            "• 0:00 and 24:00 are invalid start/end points\n\n"
            "USING TAGS:\n"
            "• Simply click the drop down menu and select a tag.  To create a tag, close this menu and hit the 'Manage' button"


        )
        messagebox.showinfo("Create Activities Manually", help_text)