# file: pomodoro_tab.py

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
import os
from plyer import notification
from playsound3 import playsound
from core import database_manager as db
from .ui_components import PomodoroEditWindow  # Import the new window


class PomodoroTab(ctk.CTkFrame):
    def __init__(self, master, master_app):
        super().__init__(master)
        self.master_app = master_app  # Reference to the main StudyTrackerApp instance

        # --- Pomodoro State Variables ---
        self.pomo_timer_job = None
        self.pomo_state = "Stopped"  # Can be: Stopped, Work, Break, Paused
        self.pomo_paused_state = None  # what is paused while pomo_state is Paused: Work or Break
        self.pomo_break_type = "Short Break"
        self.pomo_seconds_left = 0
        self.pomo_sessions_done = 0
        self.pomo_start_time = None  # start of the stretch running now (since the last start/resume)
        self.enable_notifications = ctk.BooleanVar(value=True)
        self.skip_breaks = ctk.BooleanVar(value=False)

        # --- UI Setup ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left control panel
        left_frame = ctk.CTkFrame(self, width=450)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.grid_propagate(False)
        left_frame.grid_columnconfigure(0, weight=1)

        # -- Timer Display --
        title_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        title_frame.pack(pady=(20, 10), fill="x", padx=20)
        ctk.CTkLabel(title_frame, text="Pomodoro Timer", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(title_frame, text="?", width=30, command=self._show_help_modal).pack(side="right")
        
        self.pomo_time_display = ctk.CTkLabel(left_frame, text="25:00", font=ctk.CTkFont(size=60, family="monospace"))
        self.pomo_time_display.pack(pady=10, padx=20)
        self.pomo_status_label = ctk.CTkLabel(left_frame, text="Ready to start!", font=ctk.CTkFont(size=14))
        self.pomo_status_label.pack(pady=(0, 20))

        # -- Controls --
        controls_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20)
        controls_frame.grid_columnconfigure((0, 1), weight=1)
        self.pomo_toggle_button = ctk.CTkButton(controls_frame, text="Start", height=40,
                                                command=self.toggle_pomodoro_timer)
        self.pomo_toggle_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.pomo_reset_button = ctk.CTkButton(controls_frame, text="Reset", height=40,
                                               command=self.reset_pomodoro_timer)
        self.pomo_reset_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        # Only shown during a break
        self.pomo_skip_button = ctk.CTkButton(controls_frame, text="Skip Break", height=32,
                                              command=self.skip_break)
        self.pomo_skip_button.grid(row=1, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        self.pomo_skip_button.grid_remove()

        # -- Task Entry --
        task_frame = ctk.CTkFrame(left_frame)
        task_frame.pack(pady=20, padx=20, fill="both", expand=True)
        task_frame.grid_columnconfigure(0, weight=1)
        task_frame.grid_rowconfigure(5, weight=1)
        ctk.CTkLabel(task_frame, text="Task for this Session", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0,
                                                                                                              column=0,
                                                                                                              sticky="w",
                                                                                                              padx=10,
                                                                                                              pady=(10,
                                                                                                                    0))
        self.pomo_task_entry = ctk.CTkEntry(task_frame, placeholder_text="e.g., Chapter 3 Reading")
        self.pomo_task_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(task_frame, text="Subject Tag", font=ctk.CTkFont(size=14, weight="bold")).grid(row=2, column=0,
                                                                                                    sticky="w", padx=10,
                                                                                                    pady=(10, 0))
        self.pomo_tag_combobox = ctk.CTkComboBox(task_frame, values=[])
        self.pomo_tag_combobox.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        ctk.CTkLabel(task_frame, text="Description (Optional)", font=ctk.CTkFont(size=14, weight="bold")).grid(row=4,
                                                                                                               column=0,
                                                                                                               sticky="w",
                                                                                                               padx=10,
                                                                                                               pady=(10,
                                                                                                                     0))
        self.pomo_task_desc = ctk.CTkTextbox(task_frame)
        self.pomo_task_desc.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")

        # Right panel for settings and log
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # -- Settings --
        settings_frame = ctk.CTkFrame(right_frame)
        settings_frame.grid(row=0, column=0, padx=10, pady=10, sticky="new")
        settings_frame.grid_columnconfigure((1, 3, 5, 7), weight=1)
        ctk.CTkLabel(settings_frame, text="Settings (minutes)").grid(row=0, column=0, columnspan=8, pady=(5, 10))
        ctk.CTkLabel(settings_frame, text="Work:").grid(row=1, column=0, padx=(10, 5), pady=5)
        self.pomo_work_min = ctk.CTkEntry(settings_frame, width=50);
        self.pomo_work_min.grid(row=1, column=1);
        self.pomo_work_min.insert(0, "25")
        ctk.CTkLabel(settings_frame, text="Short Brk:").grid(row=1, column=2, padx=(10, 5), pady=5)
        self.pomo_short_brk_min = ctk.CTkEntry(settings_frame, width=50);
        self.pomo_short_brk_min.grid(row=1, column=3);
        self.pomo_short_brk_min.insert(0, "5")
        ctk.CTkLabel(settings_frame, text="Long Brk:").grid(row=1, column=4, padx=(10, 5), pady=5)
        self.pomo_long_brk_min = ctk.CTkEntry(settings_frame, width=50);
        self.pomo_long_brk_min.grid(row=1, column=5);
        self.pomo_long_brk_min.insert(0, "15")
        ctk.CTkLabel(settings_frame, text="Cycles:").grid(row=1, column=6, padx=(10, 5), pady=5)
        self.pomo_sessions_goal = ctk.CTkEntry(settings_frame, width=50);
        self.pomo_sessions_goal.grid(row=1, column=7, padx=(0, 10));
        self.pomo_sessions_goal.insert(0, "4")
        ctk.CTkSwitch(settings_frame, text="Enable Notifications", variable=self.enable_notifications).grid(
            row=2, column=0, columnspan=4, pady=10, padx=10, sticky="w")
        ctk.CTkSwitch(settings_frame, text="Skip Breaks", variable=self.skip_breaks).grid(
            row=2, column=4, columnspan=4, pady=10, padx=10, sticky="w")

        # -- Log --
        self.pomo_log_frame = ctk.CTkScrollableFrame(right_frame, label_text="Today's Pomodoro Log")
        self.pomo_log_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

    # --- Pomodoro Logic ---
    def _send_notification(self, title, message):
        if not self.enable_notifications.get():
            return
        try:
            notification.notify(
                title=title,
                message=message,
                app_name='Focus & Wellness Tracker',
                timeout=10
            )
            sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notification.wav')
            if os.path.exists(sound_path):
                playsound(sound_path, block=False)
        except Exception as e:
            print(f"Notification Error: {e}")

    @staticmethod
    def _read_int(entry, default, minimum=0):
        try:
            value = int(entry.get())
        except ValueError:
            return default
        return value if value >= minimum else default

    def _cancel_timer(self):
        if self.pomo_timer_job:
            self.after_cancel(self.pomo_timer_job)
            self.pomo_timer_job = None

    def toggle_pomodoro_timer(self):
        if self.pomo_state in ["Work", "Break"]:  # Pause the timer
            # Log the stretch up to now, so the time spent paused is never part of any entry.
            self._save_stretch(self.pomo_state)
            self._cancel_timer()
            self.pomo_paused_state, self.pomo_state = self.pomo_state, "Paused"
            self.pomo_toggle_button.configure(text="Resume")
            self._refresh_displays(self.pomo_paused_state)
        elif self.pomo_state == "Paused":  # Resume: a new stretch starts now
            self.pomo_state, self.pomo_paused_state = self.pomo_paused_state, None
            self.pomo_start_time = datetime.now()
            self.pomo_timer_job = self.after(1000, self.update_pomodoro_display)
            self.pomo_toggle_button.configure(text="Pause")
        elif self.pomo_state == "Stopped":  # Start the first session
            if not self.pomo_tag_combobox.get():
                messagebox.showwarning("No Tag", "Please select a subject tag before starting a work session.",
                                       parent=self)
                return
            self._start_work()

    def reset_pomodoro_timer(self):
        self._cancel_timer()
        self.pomo_state = "Stopped"
        self.pomo_paused_state = None
        self.pomo_start_time = None
        self.pomo_sessions_done = 0
        work_mins = self._read_int(self.pomo_work_min, 25)
        self.pomo_time_display.configure(text=f"{work_mins:02d}:00")
        self.pomo_status_label.configure(text="Ready to start!")
        self.pomo_toggle_button.configure(text="Start", **ctk.ThemeManager.theme["CTkButton"])
        self.pomo_skip_button.grid_remove()

    def update_pomodoro_display(self):
        if self.pomo_seconds_left > 0:
            self.pomo_seconds_left -= 1
            mins, secs = divmod(self.pomo_seconds_left, 60)
            self.pomo_time_display.configure(text=f"{mins:02d}:{secs:02d}")
            self.pomo_timer_job = self.after(1000, self.update_pomodoro_display)
        else:
            self._finish_pomodoro_session()

    def _save_stretch(self, kind):
        """Log the uninterrupted stretch of `kind` (Work or Break) that is ending now, once."""
        start, end = self.pomo_start_time, datetime.now()
        if start is None:
            return
        duration = (end - start).total_seconds()
        if duration < 1:
            self.pomo_start_time = None
            return
        # pomo_start_time is cleared as soon as the stretch is stored: never logged twice, and
        # kept for another try if storing it fails.
        if kind == "Work":
            task_title = self.pomo_task_entry.get()
            task_desc = self.pomo_task_desc.get("1.0", "end-1c").strip()
            main_session_id = db.add_session(self.pomo_tag_combobox.get(), start, end, duration,
                                             f"Pomodoro Task: {task_title}\n\n{task_desc}".strip())
            self.pomo_start_time = None
            db.add_pomodoro_session("Work", start, end, duration, task_title, task_desc, main_session_id)
        else:
            db.add_pomodoro_session(self.pomo_break_type, start, end, duration, "Break", "")
            self.pomo_start_time = None

    def _refresh_displays(self, kind):
        if kind == "Work":
            self.master_app.update_all_displays()
        else:
            self.master_app.refresh_tabs("Pomodoro")  # breaks only appear in the log here

    def _finish_pomodoro_session(self):
        finished = self.pomo_state
        self._save_stretch(finished)
        # Move on before redrawing anything: if a redraw fails, the finished session must not
        # stay current, or resuming it would log it a second time.
        if finished == "Work":
            self.pomo_sessions_done += 1
            self.pomo_task_entry.delete(0, 'end')
            self.pomo_task_desc.delete("1.0", 'end')
            if self.skip_breaks.get():
                self._start_work()
            else:
                self._start_break()
        else:
            self._start_work()
        self._refresh_displays(finished)

    def skip_break(self):
        """End the current (running or paused) break and start the next work session."""
        if "Break" not in (self.pomo_state, self.pomo_paused_state):
            return
        self._save_stretch("Break")
        self._start_work()
        self._refresh_displays("Break")

    def _sessions_goal(self):
        return self._read_int(self.pomo_sessions_goal, 4, minimum=1)

    def _start_work(self):
        duration_mins = self._read_int(self.pomo_work_min, 25, minimum=1)
        self.pomo_status_label.configure(
            text=f"Work Session {self.pomo_sessions_done + 1} of {self._sessions_goal()}")
        self._begin("Work", duration_mins)
        self._send_notification("Back to Work!", f"Time to focus for {duration_mins} minutes. You can do it!")

    def _start_break(self):
        if self.pomo_sessions_done % self._sessions_goal() == 0:
            self.pomo_break_type = "Long Break"
            duration_mins = self._read_int(self.pomo_long_brk_min, 15)
            status, message = "Time for a long break!", f"Nicely done! Time for a {duration_mins}-minute break."
        else:
            self.pomo_break_type = "Short Break"
            duration_mins = self._read_int(self.pomo_short_brk_min, 5)
            status, message = "Time for a short break!", f"Great work! Take a {duration_mins}-minute break."
        self.pomo_status_label.configure(text=status)
        self._begin("Break", duration_mins)
        self._send_notification("Break Time!", message)

    def _begin(self, state, duration_mins):
        """Start the countdown of a new work session or break."""
        self._cancel_timer()
        self.pomo_state, self.pomo_paused_state = state, None
        self.pomo_seconds_left = duration_mins * 60
        self.pomo_time_display.configure(text=f"{duration_mins:02d}:00")
        self.pomo_toggle_button.configure(text="Pause", fg_color="#db524b", hover_color="#b0423d")
        if state == "Break":
            self.pomo_skip_button.grid()
        else:
            self.pomo_skip_button.grid_remove()
        self.pomo_start_time = datetime.now()
        self.pomo_timer_job = self.after(1000, self.update_pomodoro_display)

    def open_edit_popup(self, pomo_id):
        PomodoroEditWindow(master=self.master_app, pomo_id=pomo_id)

    def delete_pomo_entry(self, pomo_id):
        if messagebox.askyesno("Confirm Delete",
                               "Are you sure you want to delete this log entry?\nThis will also remove it from the main tracker.",
                               parent=self.master_app):
            db.delete_pomodoro_session(pomo_id)
            self.master_app.update_all_displays()

    def update_pomodoro_log(self):
        for widget in self.pomo_log_frame.winfo_children(): widget.destroy()
        sessions = db.get_todays_pomodoro_sessions()
        if not sessions:
            ctk.CTkLabel(self.pomo_log_frame, text="No pomodoro sessions logged today.").pack(pady=10)

        for pomo_id, session_type, duration, title, start_time_iso, desc, tag_color in sessions:
            start_time = datetime.fromisoformat(start_time_iso)
            f = ctk.CTkFrame(self.pomo_log_frame, fg_color="#3a3a3a")
            f.pack(fill="x", pady=3, padx=3)
            f.columnconfigure(1, weight=1)

            # Determine the color for the side bar
            if session_type == 'Work' and tag_color:
                color = tag_color
            elif session_type == 'Work':
                color = "#4CAF50"  # Default Green for Work
            else:
                color = "#2196F3"  # Blue for Breaks

            ctk.CTkFrame(f, width=5, fg_color=color).grid(row=0, rowspan=2, column=0, sticky="ns", padx=5, pady=5)

            info_frame = ctk.CTkFrame(f, fg_color="transparent")
            info_frame.grid(row=0, rowspan=2, column=1, sticky="nsew")
            info_frame.columnconfigure(0, weight=1)

            main_text = f"{session_type}: {title or 'Untitled'}"
            lbl_main = ctk.CTkLabel(info_frame, text=main_text, anchor="w", font=ctk.CTkFont(weight="bold"))
            lbl_main.grid(row=0, column=0, sticky="ew", padx=5)

            length = f"{int(duration / 60)} min" if duration >= 60 else f"{int(duration)} sec"
            sub_text = f"{start_time.strftime('%I:%M %p')} ({length})"
            lbl_sub = ctk.CTkLabel(info_frame, text=sub_text, anchor="w", text_color="gray")
            lbl_sub.grid(row=1, column=0, sticky="ew", padx=5)

            if desc:
                lbl_main.configure(cursor="hand2")
                lbl_main.bind("<Button-1>", lambda e, d=desc, t=title: messagebox.showinfo(f"Description for: {t}", d))

            buttons_frame = ctk.CTkFrame(f, fg_color="transparent")
            buttons_frame.grid(row=0, rowspan=2, column=2, padx=5, pady=5)

            if session_type == 'Work':
                ctk.CTkButton(buttons_frame, text="Edit", width=50,
                              command=lambda p_id=pomo_id: self.open_edit_popup(p_id)).pack(pady=(0, 2))

            ctk.CTkButton(buttons_frame, text="Del", width=50, fg_color="#db524b", hover_color="#b0423d",
                          command=lambda p_id=pomo_id: self.delete_pomo_entry(p_id)).pack()

    def update_pomo_tag_combobox(self, tags, current_tag):
        """Update the tag choices, keeping this tab's selection; `current_tag` (the Tracker's) is
        only used when nothing valid is selected, e.g. at startup or after a tag was deleted."""
        selected = self.pomo_tag_combobox.get()
        self.pomo_tag_combobox.configure(values=tags)
        if selected in tags:
            return
        if current_tag in tags:
            self.pomo_tag_combobox.set(current_tag)
        elif tags:
            self.pomo_tag_combobox.set(tags[0])

    def _show_help_modal(self):
        help_text = (
            "POMODORO TAB - Structured Study Sessions\n\n"
            "WHAT IS POMODORO?\n"
            "• Work for a set time (default: 25 min)\n"
            "• Take a short break (default: 5 min)\n"
            "• After 4 work sessions, take a long break (default: 15 min)\n"
            "• Helps maintain focus and prevent burnout\n\n"
            "HOW TO USE:\n"
            "1. Enter a task name (e.g., 'Chapter 3 Reading')\n"
            "2. Select a subject tag\n"
            "3. Optionally add a description\n"
            "4. Click 'Start' to begin your first work session\n"
            "5. When the timer ends, you'll get a notification\n"
            "6. Break time starts automatically\n"
            "7. After the break, start the next work session\n\n"
            "SETTINGS:\n"
            "• Work: Length of focus sessions (minutes)\n"
            "• Short Break: Length of short breaks (minutes)\n"
            "• Long Break: Length of long breaks (minutes)\n"
            "• Cycles: How many work sessions before a long break\n"
            "• Skip Breaks: Go straight from one work session to the next\n\n"
            "CONTROLS:\n"
            "• Start/Pause: Begin or pause the current timer\n"
            "• Pause: Keeps your place. The time so far is logged as its own entry, and resuming\n"
            "  starts a new one, so time spent paused is never counted\n"
            "• Skip Break: End the current break early (only shown during a break)\n"
            "• Reset: Stop and drop the time since you last started or resumed\n\n"
            "NOTIFICATIONS:\n"
            "• Toggle notifications on/off\n"
            "• Get alerts when work/break sessions end\n\n"
            "LOG:\n"
            "• View today's work sessions and breaks (one entry per stretch between pauses)\n"
            "• Edit work session details\n"
            "• Delete sessions if needed\n"
            "• Click on task name to see description"
        )
        messagebox.showinfo("Pomodoro Tab Help", help_text)