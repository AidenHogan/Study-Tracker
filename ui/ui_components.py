# file: ui_components.py

import customtkinter as ctk
from tkinter import messagebox, colorchooser
from datetime import datetime, timedelta
from core import database_manager as db


class PomodoroEditWindow(ctk.CTkToplevel):
    def __init__(self, master, pomo_id):
        super().__init__(master)
        self.master_app = master
        self.pomo_id = pomo_id

        self.title("Edit Pomodoro Log")
        self.geometry("400x400")
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(1, weight=1)

        # --- Widgets ---
        ctk.CTkLabel(self, text="Subject Tag:").grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")
        tag_values = [tag[0] for tag in db.get_tags()]
        self.tag_combobox = ctk.CTkComboBox(self, values=tag_values)
        self.tag_combobox.grid(row=0, column=1, padx=20, pady=(20, 5), sticky="ew")

        ctk.CTkLabel(self, text="Task Title:").grid(row=1, column=0, padx=20, pady=5, sticky="w")
        self.title_entry = ctk.CTkEntry(self)
        self.title_entry.grid(row=1, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self, text="Description:").grid(row=2, column=0, padx=20, pady=5, sticky="nw")
        self.desc_textbox = ctk.CTkTextbox(self, height=150)
        self.desc_textbox.grid(row=2, column=1, padx=20, pady=5, sticky="ew")

        ctk.CTkButton(self, text="Save Changes", command=self.save_data).grid(row=3, column=1, padx=20, pady=(20, 5),
                                                                              sticky="ew")

        self.load_data()

    def load_data(self):
        record = db.get_pomodoro_session_by_id(self.pomo_id)
        if not record:
            messagebox.showerror("Error", "Could not find session data.", parent=self)
            self.destroy()
            return

        title, desc, main_session_id, tag = record
        self.title_entry.insert(0, title or "")
        if desc:
            self.desc_textbox.insert("1.0", desc)
        if tag:
            self.tag_combobox.set(tag)

    def save_data(self):
        new_tag = self.tag_combobox.get()
        new_title = self.title_entry.get()
        new_desc = self.desc_textbox.get("1.0", "end-1c").strip()

        if not all([new_tag, new_title]):
            messagebox.showerror("Error", "Tag and Title are required.", parent=self)
            return

        db.update_pomodoro_session(self.pomo_id, new_title, new_desc, new_tag)
        self.master_app.update_all_displays()
        self.destroy()


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

        ctk.CTkButton(self, text="Save", command=self.save_session).grid(row=5, column=1, padx=20, pady=(20, 5),
                                                                         sticky="ew")

        if self.session_id:
            self.load_session_data()
        else:
            self.date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))

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

            if self.session_id:
                db.update_session(self.session_id, tag, start_datetime, end_datetime, duration_seconds, notes)
            else:
                db.add_session(tag, start_datetime, end_datetime, duration_seconds, notes)

            self.master_app.update_all_displays()
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Invalid date or time format. Use YYYY-MM-DD and HH:MM.", parent=self)


class TagManagementWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Manage Tags & Categories")
        self.geometry("700x500")  # Increased size
        self.transient(master)
        self.grab_set()
        self.grid_columnconfigure(1, weight=1)  # Two main columns
        self.grid_rowconfigure(0, weight=1)

        # --- Categories Panel (Left) ---
        category_panel = ctk.CTkFrame(self)
        category_panel.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        category_panel.grid_rowconfigure(0, weight=1)
        category_panel.grid_columnconfigure(0, weight=1)

        self.category_list_frame = ctk.CTkScrollableFrame(category_panel, label_text="Categories")
        self.category_list_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        cat_entry_frame = ctk.CTkFrame(category_panel)
        cat_entry_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        cat_entry_frame.columnconfigure(0, weight=1)
        self.new_cat_entry = ctk.CTkEntry(cat_entry_frame, placeholder_text="New category name")
        self.new_cat_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(cat_entry_frame, text="Add", width=50, command=self.add_category).grid(row=0, column=1)

        # --- Tags Panel (Right) ---
        tags_panel = ctk.CTkFrame(self)
        tags_panel.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        tags_panel.grid_rowconfigure(0, weight=1)
        tags_panel.grid_columnconfigure(0, weight=1)

        self.tag_list_frame = ctk.CTkScrollableFrame(tags_panel, label_text="Tags")
        self.tag_list_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        tag_entry_frame = ctk.CTkFrame(tags_panel)
        tag_entry_frame.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        tag_entry_frame.columnconfigure(0, weight=1)
        self.new_tag_entry = ctk.CTkEntry(tag_entry_frame, placeholder_text="New tag name")
        self.new_tag_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(tag_entry_frame, text="Add", width=50, command=self.add_tag).grid(row=0, column=1)

        self.refresh_all()

    def refresh_all(self):
        self.load_categories()
        self.load_tags()
        self.master_app.update_all_displays()

    def load_categories(self):
        for widget in self.category_list_frame.winfo_children(): widget.destroy()
        self.categories = [row[0] for row in db.get_categories()]
        for cat_name in self.categories:
            frame = ctk.CTkFrame(self.category_list_frame)
            frame.pack(fill="x", pady=2)
            frame.columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=cat_name).grid(row=0, column=0, padx=5, sticky="w")
            ctk.CTkButton(frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                          command=lambda n=cat_name: self.delete_category(n)).grid(row=0, column=1, padx=5, pady=5)

    def load_tags(self):
        for widget in self.tag_list_frame.winfo_children(): widget.destroy()
        category_options = ["None"] + self.categories

        for tag, color, category in db.get_tags_with_colors_and_categories():
            frame = ctk.CTkFrame(self.tag_list_frame)
            frame.pack(fill="x", pady=2)
            frame.columnconfigure(1, weight=1)

            color_swatch = ctk.CTkButton(frame, text="", fg_color=color, width=30, height=30,
                                         command=lambda t=tag, c=color: self.change_color(t, c))
            color_swatch.grid(row=0, column=0, padx=5, pady=5)

            ctk.CTkLabel(frame, text=tag).grid(row=0, column=1, padx=5, sticky="w")

            cat_combo = ctk.CTkComboBox(frame, values=category_options, width=120,
                                        command=lambda cat, t=tag: self.assign_category(t, cat))
            cat_combo.set(category if category else "None")
            cat_combo.grid(row=0, column=2, padx=5, pady=5)

            ctk.CTkButton(frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                          command=lambda t=tag: self.delete_tag(t)).grid(row=0, column=3, padx=5, pady=5)

    def add_category(self):
        cat_name = self.new_cat_entry.get()
        if not cat_name: return
        success, message = db.add_category(cat_name)
        if success:
            self.new_cat_entry.delete(0, 'end')
            self.refresh_all()
        else:
            messagebox.showwarning("Duplicate", message, parent=self)

    def delete_category(self, name):
        db.delete_category(name)
        self.refresh_all()

    def assign_category(self, tag_name, category_name):
        db.update_tag_category(tag_name, category_name)
        self.refresh_all()  # Refresh to ensure data consistency

    def add_tag(self):
        new_tag = self.new_tag_entry.get()
        if not new_tag: return
        success, message = db.add_tag(new_tag)
        if success:
            self.new_tag_entry.delete(0, 'end')
            self.refresh_all()
        else:
            messagebox.showwarning("Duplicate", message, parent=self)

    def delete_tag(self, tag_name):
        # Confirmation modal offering Archive vs Full Delete
        msg = ("Delete Tag Options:\n\n" 
               "Archive: Hide this tag from future selection, KEEP all past session data.\n" 
               "Full Delete: Remove the tag AND all sessions that used it (cannot be undone).\n\n" 
               f"Tag: {tag_name}\n\nChoose an option:")
        dialog = messagebox.askquestion("Delete Tag", msg + "\n\nClick 'Yes' for Full Delete, 'No' to Archive.")
        try:
            if dialog == 'yes':
                db.delete_tag(tag_name)
            else:
                db.archive_tag(tag_name)
        except Exception as e:
            messagebox.showerror("Tag Deletion Error", f"Operation failed: {e}", parent=self)
            return

        # Lightweight, immediate UI update to avoid freezing the whole app.
        # Update the tag list in-place and inform dependent widgets.
        try:
            self.load_tags()
        except Exception:
            pass

        try:
            # Update tracker and pomodoro comboboxes without doing the full analytics/health refresh.
            tags = [row[0] for row in db.get_tags()]
            current_tag = tags[0] if tags else ""
            try:
                self.master_app.tracker_tab.tag_combobox.configure(values=tags)
                self.master_app.tracker_tab.tag_combobox.set(current_tag)
            except Exception:
                pass
            try:
                self.master_app.update_pomodoro_tags(tags, current_tag)
            except Exception:
                pass
        except Exception:
            pass

        # Schedule a full refresh shortly after so heavy computations happen after UI becomes responsive.
        try:
            # Use a small delay so the UI updates first and avoids the OS marking the window as not-responding.
            self.after(600, lambda: self.master_app.update_all_displays())
        except Exception:
            # Fallback to immediate refresh if scheduling fails
            try:
                self.master_app.update_all_displays()
            except Exception:
                pass

    def restore_archived_tags(self):
        # Simple picker window listing archived tags to restore
        archived = [row[0] for row in db.get_tags(include_hidden=True) if row[0] not in [t[0] for t in db.get_tags()]]
        if not archived:
            messagebox.showinfo("Restore Tags", "No archived tags to restore.", parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title("Restore Archived Tags")
        win.geometry("300x400")
        list_frame = ctk.CTkScrollableFrame(win)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        for t in archived:
            row = ctk.CTkFrame(list_frame)
            row.pack(fill='x', pady=2)
            ctk.CTkLabel(row, text=t).pack(side='left', padx=5)
            ctk.CTkButton(row, text="Restore", width=70, command=lambda name=t: self._restore_and_refresh(win, name)).pack(side='right', padx=5)

    def _restore_and_refresh(self, window, tag_name):
        try:
            db.restore_tag(tag_name)
        except Exception as e:
            messagebox.showerror("Restore Error", f"Could not restore {tag_name}: {e}", parent=window)
        self.refresh_all()
        window.destroy()

    def change_color(self, tag_name, old_color):
        new_color = colorchooser.askcolor(initialcolor=old_color, title=f"Select color for {tag_name}")
        if new_color and new_color[1]:
            db.update_tag_color(tag_name, new_color[1])
            self.refresh_all()


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