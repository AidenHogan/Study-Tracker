# file: ui_components.py

import customtkinter as ctk
from tkinter import messagebox, colorchooser
from datetime import datetime, timedelta
import database_manager as db


class SessionEditWindow(ctk.CTkToplevel):
    def __init__(self, master, session_id=None):
        super().__init__(master)
        self.master_app = master
        self.session_id = session_id
        self.title("Edit Session" if self.session_id else "Add Manual Session")
        self.geometry("400x450")
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Tag:").grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        tag_values = [tag[0] for tag in db.get_tags()]
        self.tag_combobox = ctk.CTkComboBox(self, values=tag_values)
        self.tag_combobox.grid(row=0, column=1, padx=20, pady=(20, 5), sticky="ew")

        ctk.CTkLabel(self, text="Date (YYYY-MM-DD):").grid(row=1, column=0, padx=20, pady=5, sticky="w")
        self.date_entry = ctk.CTkEntry(self)
        self.date_entry.grid(row=1, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self, text="Start Time (HH:MM):").grid(row=2, column=0, padx=20, pady=5, sticky="w")
        self.start_time_entry = ctk.CTkEntry(self)
        self.start_time_entry.grid(row=2, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self, text="End Time (HH:MM):").grid(row=3, column=0, padx=20, pady=5, sticky="w")
        self.end_time_entry = ctk.CTkEntry(self)
        self.end_time_entry.grid(row=3, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self, text="Notes:").grid(row=4, column=0, padx=20, pady=5, sticky="nw")
        self.notes_textbox = ctk.CTkTextbox(self, height=150)
        self.notes_textbox.grid(row=4, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkButton(self, text="Save", command=self.save_session).grid(row=5, column=1, padx=20, pady=(20, 5), sticky="ew")

        if self.session_id: self.load_session_data()
        else: self.date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))

    def load_session_data(self):
        record = db.get_session_by_id(self.session_id)
        if not record: return

        tag, start_iso, end_iso, notes = record
        start_dt, end_dt = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)

        self.tag_combobox.set(tag)
        self.date_entry.insert(0, start_dt.strftime('%Y-%m-%d'))
        self.start_time_entry.insert(0, start_dt.strftime('%H:%M'))
        self.end_time_entry.insert(0, end_dt.strftime('%H:%M'))
        if notes: self.notes_textbox.insert("1.0", notes)

    def save_session(self):
        tag, date_str = self.tag_combobox.get(), self.date_entry.get()
        start_time_str, end_time_str = self.start_time_entry.get(), self.end_time_entry.get()
        notes = self.notes_textbox.get("1.0", "end-1c").strip()

        if not all([tag, date_str, start_time_str, end_time_str]):
            messagebox.showerror("Error", "Tag, Date, and Times are required.", parent=self)
            return
        try:
            start_datetime = datetime.strptime(f"{date_str} {start_time_str}", '%Y-%m-%d %H:%M')
            end_datetime = datetime.strptime(f"{date_str} {end_time_str}", '%Y-%m-%d %H:%M')
            if end_datetime <= start_datetime:
                messagebox.showerror("Error", "End time must be after start time.", parent=self)
                return

            duration_seconds = (end_datetime - start_datetime).total_seconds()

            if self.session_id: db.update_session(self.session_id, tag, start_datetime, end_datetime, duration_seconds, notes)
            else: db.add_session(tag, start_datetime, end_datetime, duration_seconds, notes)

            self.master_app.update_all_displays()
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid date or time format. Use YYYY-MM-DD and HH:MM.", parent=self)


class TagManagementWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Manage Tags")
        self.geometry("350x400")
        self.transient(master)
        self.grab_set()

        self.tag_list_frame = ctk.CTkScrollableFrame(self, label_text="Saved Tags")
        self.tag_list_frame.pack(fill="both", expand=True, padx=15, pady=15)

        self.entry_frame = ctk.CTkFrame(self)
        self.entry_frame.pack(fill="x", padx=15, pady=(0, 15))
        self.entry_frame.columnconfigure(0, weight=1)

        self.new_tag_entry = ctk.CTkEntry(self.entry_frame, placeholder_text="New tag name")
        self.new_tag_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(self.entry_frame, text="Add", width=50, command=self.add_tag).grid(row=0, column=1)
        self.load_tags()

    def load_tags(self):
        for widget in self.tag_list_frame.winfo_children(): widget.destroy()
        for tag, color in db.get_tags_with_colors():
            frame = ctk.CTkFrame(self.tag_list_frame)
            frame.pack(fill="x", pady=2);
            frame.columnconfigure(1, weight=1)
            color_swatch = ctk.CTkButton(frame, text="", fg_color=color, width=30, height=30,
                                         command=lambda t=tag, c=color: self.change_color(t, c))
            color_swatch.grid(row=0, column=0, padx=5, pady=5)
            ctk.CTkLabel(frame, text=tag).grid(row=0, column=1, padx=5, sticky="w")
            ctk.CTkButton(frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                          command=lambda t=tag: self.delete_tag(t)).grid(row=0, column=2, padx=5, pady=5)

    def change_color(self, tag_name, old_color):
        new_color = colorchooser.askcolor(initialcolor=old_color, title=f"Select color for {tag_name}")
        if new_color and new_color[1]:
            db.update_tag_color(tag_name, new_color[1])
            self.load_tags();
            self.master_app.update_all_displays()

    def add_tag(self):
        new_tag = self.new_tag_entry.get()
        if not new_tag: return
        success, message = db.add_tag(new_tag)
        if success:
            self.new_tag_entry.delete(0, 'end');
            self.load_tags();
            self.master_app.update_tag_combobox()
        else:
            messagebox.showwarning("Duplicate", message, parent=self)

    def delete_tag(self, tag_name):
        db.delete_tag(tag_name);
        self.load_tags();
        self.master_app.update_tag_combobox()


class ManualHealthEntryWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Manual Sleep Entry")
        self.geometry("350x200")
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Date (YYYY-MM-DD):").grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        self.date_entry = ctk.CTkEntry(self)
        self.date_entry.grid(row=0, column=1, padx=20, pady=(20, 5), sticky="ew")
        self.date_entry.insert(0, (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))

        ctk.CTkLabel(self, text="Sleep Duration (HH:MM):").grid(row=1, column=0, padx=20, pady=5, sticky="w")
        self.sleep_duration_entry = ctk.CTkEntry(self, placeholder_text="e.g., 07:30")
        self.sleep_duration_entry.grid(row=1, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkButton(self, text="Save", command=self.save_health_data).grid(row=2, column=1, padx=20, pady=(20, 5),
                                                                             sticky="ew")

    def save_health_data(self):
        date_str, duration_str = self.date_entry.get(), self.sleep_duration_entry.get()
        if not all([date_str, duration_str]):
            messagebox.showerror("Error", "Both fields are required.", parent=self);
            return
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            parts = duration_str.split(':')
            if len(parts) != 2: raise ValueError("Invalid time format")
            hours, minutes = int(parts[0]), int(parts[1])
            db.add_manual_sleep_entry(date_str, (hours * 3600) + (minutes * 60))
            self.master_app.update_health_charts();
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid format.\nDate: YYYY-MM-DD\nDuration: HH:MM", parent=self)