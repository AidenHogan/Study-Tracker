# file: pomodoro_tab.py

import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
import os
from plyer import notification
from playsound import playsound
from core import database_manager as db
from .ui_components import PomodoroEditWindow  # Import the new window


class PomodoroTab(ctk.CTkFrame):
    def __init__(self, master, master_app):
        super().__init__(master)
        self.master_app = master_app  # Reference to the main StudyTrackerApp instance

        # --- Pomodoro State Variables ---
        self.pomo_timer_job = None
        self.pomo_state = "Stopped"  # Can be: Stopped, Work, Break, Paused
        self.pomo_seconds_left = 0
        self.pomo_sessions_done = 0
        self.pomo_start_time = None
        self.pomo_paused_seconds = 0
        self.enable_notifications = ctk.BooleanVar(value=True)

        # --- UI Setup ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left control panel
        left_frame = ctk.CTkFrame(self, width=450)
        left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_frame.grid_propagate(False)
        left_frame.grid_columnconfigure(0, weight=1)

        # -- Timer Display --
        ctk.CTkLabel(left_frame, text="Pomodoro Timer", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
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
        ctk.CTkSwitch(settings_frame, text="Enable Notifications", variable=self.enable_notifications).grid(row=2,
                                                                                                            column=0,
                                                                                                            columnspan=8,
                                                                                                            pady=10,
                                                                                                            padx=10,
                                                                                                            sticky="w")

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

    def toggle_pomodoro_timer(self):
        if self.pomo_state in ["Work", "Break"]:  # Pause the timer
            self.pomo_paused_seconds = self.pomo_seconds_left
            self.pomo_state = "Paused"
            if self.pomo_timer_job: self.after_cancel(self.pomo_timer_job)
            self.pomo_toggle_button.configure(text="Resume")
        elif self.pomo_state == "Paused":  # Resume the timer
            self.pomo_seconds_left = self.pomo_paused_seconds
            if self.pomo_sessions_done % int(self.pomo_sessions_goal.get() or 4) == 0 and self.pomo_sessions_done > 0:
                self.pomo_state = "Break"
            else:
                self.pomo_state = "Work" if self.pomo_status_label.cget('text').startswith("Work") else "Break"
            self.pomo_timer_job = self.after(1000, self.update_pomodoro_display)
            self.pomo_toggle_button.configure(text="Pause")
        elif self.pomo_state == "Stopped":  # Start the first session
            if not self.pomo_tag_combobox.get():
                messagebox.showwarning("No Tag", "Please select a subject tag before starting a work session.",
                                       parent=self)
                return
            self._start_next_pomo_session()

    def reset_pomodoro_timer(self):
        if self.pomo_timer_job: self.after_cancel(self.pomo_timer_job)
        self.pomo_timer_job = None
        self.pomo_state = "Stopped"
        self.pomo_sessions_done = 0
        try:
            work_mins = int(self.pomo_work_min.get())
        except ValueError:
            work_mins = 25
        self.pomo_time_display.configure(text=f"{work_mins:02d}:00")
        self.pomo_status_label.configure(text="Ready to start!")
        self.pomo_toggle_button.configure(text="Start", **ctk.ThemeManager.theme["CTkButton"])

    def update_pomodoro_display(self):
        if self.pomo_seconds_left > 0:
            self.pomo_seconds_left -= 1
            mins, secs = divmod(self.pomo_seconds_left, 60)
            self.pomo_time_display.configure(text=f"{mins:02d}:{secs:02d}")
            self.pomo_timer_job = self.after(1000, self.update_pomodoro_display)
        else:
            self._finish_pomodoro_session()

    def _finish_pomodoro_session(self):
        end_time = datetime.now()
        duration = (end_time - self.pomo_start_time).total_seconds()
        task_title = self.pomo_task_entry.get()
        task_desc = self.pomo_task_desc.get("1.0", "end-1c").strip()

        if self.pomo_state == "Work":
            main_session_id = db.add_session(
                self.pomo_tag_combobox.get(),
                self.pomo_start_time,
                end_time,
                duration,
                f"Pomodoro Task: {task_title}\n\n{task_desc}".strip()
            )
            db.add_pomodoro_session("Work", self.pomo_start_time, end_time, duration, task_title, task_desc,
                                    main_session_id)
            self.pomo_sessions_done += 1
            self.master_app.update_all_displays()
        else:
            prev_session_was_work_num = self.pomo_sessions_done
            sessions_goal = int(self.pomo_sessions_goal.get() or 4)
            break_type = "Long Break" if prev_session_was_work_num % sessions_goal == 0 and prev_session_was_work_num > 0 else "Short Break"
            db.add_pomodoro_session(break_type, self.pomo_start_time, end_time, duration, "Break", "")

        self.update_pomodoro_log()
        self._start_next_pomo_session()

    def _start_next_pomo_session(self):
        try:
            sessions_goal = int(self.pomo_sessions_goal.get())
            if sessions_goal <= 0: sessions_goal = 4
        except ValueError:
            sessions_goal = 4

        last_state_was_work = self.pomo_state == "Work"

        if last_state_was_work:
            if self.pomo_sessions_done > 0 and self.pomo_sessions_done % sessions_goal == 0:
                self.pomo_state = "Break"
                try:
                    duration_mins = int(self.pomo_long_brk_min.get())
                except ValueError:
                    duration_mins = 15
                self.pomo_status_label.configure(text="Time for a long break!")
                self._send_notification("Break Time!", f"Nicely done! Time for a {duration_mins}-minute break.")
            else:
                self.pomo_state = "Break"
                try:
                    duration_mins = int(self.pomo_short_brk_min.get())
                except ValueError:
                    duration_mins = 5
                self.pomo_status_label.configure(text="Time for a short break!")
                self._send_notification("Break Time!", f"Great work! Take a {duration_mins}-minute break.")
        else:
            self.pomo_state = "Work"
            try:
                duration_mins = int(self.pomo_work_min.get())
            except ValueError:
                duration_mins = 25
            self.pomo_status_label.configure(text=f"Work Session {self.pomo_sessions_done + 1} of {sessions_goal}")
            if self.pomo_sessions_done > 0 or not last_state_was_work:
                self._send_notification("Back to Work!", f"Time to focus for {duration_mins} minutes. You can do it!")
            self.pomo_task_entry.delete(0, 'end')
            self.pomo_task_desc.delete("1.0", 'end')

        self.pomo_seconds_left = duration_mins * 60
        mins, secs = divmod(self.pomo_seconds_left, 60)
        self.pomo_time_display.configure(text=f"{mins:02d}:{secs:02d}")
        self.pomo_start_time = datetime.now()
        self.pomo_toggle_button.configure(text="Pause", fg_color="#db524b", hover_color="#b0423d")
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

            sub_text = f"{start_time.strftime('%I:%M %p')} ({int(duration / 60)} min)"
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
        self.pomo_tag_combobox.configure(values=tags)
        if current_tag in tags:
            self.pomo_tag_combobox.set(current_tag)
        elif tags:
            self.pomo_tag_combobox.set(tags[0])