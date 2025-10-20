# file: custom_factors_manager.py

import customtkinter as ctk
from tkinter import messagebox
from tkcalendar import DateEntry
from datetime import timedelta
from datetime import date
import calendar
from core import database_manager as db


class CustomFactorsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Manage Custom Factors")
        self.geometry("800x600")
        self.transient(master)
        self.grab_set()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.selected_factor = None
        self.current_calendar_date = date.today()

        # --- Left Panel: Factor List ---
        left_panel = ctk.CTkFrame(self, width=250)
        left_panel.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        left_panel.grid_rowconfigure(0, weight=1)

        self.factor_list_frame = ctk.CTkScrollableFrame(left_panel, label_text="Factors")
        self.factor_list_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        add_frame = ctk.CTkFrame(left_panel)
        add_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        add_frame.grid_columnconfigure(0, weight=1)
        self.new_factor_entry = ctk.CTkEntry(add_frame, placeholder_text="New Factor Name")
        self.new_factor_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ctk.CTkButton(add_frame, text="Add", width=50, command=self.add_factor).grid(row=0, column=1)
        ctk.CTkLabel(add_frame, text="Start Date:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.start_date_entry = DateEntry(add_frame, date_pattern='y-mm-dd', width=12)
        self.start_date_entry.grid(row=1, column=1, sticky="e", pady=(5, 0))

        # --- Right Panel: Calendar Editor ---
        right_panel = ctk.CTkFrame(self)
        right_panel.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        calendar_header = ctk.CTkFrame(right_panel, fg_color="transparent")
        calendar_header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        calendar_header.columnconfigure(1, weight=1)

        ctk.CTkButton(calendar_header, text="<", width=30, command=self.prev_month).grid(row=0, column=0)
        self.month_year_label = ctk.CTkLabel(calendar_header, text="Select a factor",
                                             font=ctk.CTkFont(size=16, weight="bold"))
        self.month_year_label.grid(row=0, column=1)
        ctk.CTkButton(calendar_header, text=">", width=30, command=self.next_month).grid(row=0, column=2)

        self.calendar_grid = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.calendar_grid.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        self.load_factors()
        self.update_calendar_display()

    def add_factor(self):
        name = self.new_factor_entry.get()
        start_date = self.start_date_entry.get_date()
        if not name:
            messagebox.showwarning("Input Error", "Please enter a factor name.", parent=self)
            return

        success, msg = db.add_custom_factor(name, start_date)
        if success:
            self.new_factor_entry.delete(0, 'end')
            self.load_factors()
            self.select_factor(name)
        else:
            messagebox.showerror("Database Error", msg, parent=self)

    def delete_factor(self, name):
        if messagebox.askyesno("Confirm Delete",
                               f"Are you sure you want to delete the factor '{name}' and all its data?", parent=self):
            db.delete_custom_factor(name)
            self.selected_factor = None
            self.load_factors()
            self.update_calendar_display()

    def edit_factor(self, name):
        """Open a dialog to edit the factor name and start date."""
        factor_details = db.get_custom_factor_details(name)
        if not factor_details:
            messagebox.showerror("Error", f"Factor '{name}' not found.", parent=self)
            return
        
        # Create edit dialog
        edit_dialog = ctk.CTkToplevel(self)
        edit_dialog.title(f"Edit Factor: {name}")
        edit_dialog.geometry("400x200")
        edit_dialog.transient(self)
        edit_dialog.grab_set()
        
        # Name entry
        ctk.CTkLabel(edit_dialog, text="Factor Name:").pack(pady=(20, 5))
        name_entry = ctk.CTkEntry(edit_dialog, width=300)
        name_entry.pack(pady=5)
        name_entry.insert(0, factor_details['name'])
        
        # Start date entry
        ctk.CTkLabel(edit_dialog, text="Start Date:").pack(pady=(10, 5))
        from datetime import datetime
        from tkcalendar import DateEntry
        start_date = datetime.fromisoformat(factor_details['start_date']).date()
        date_entry = DateEntry(edit_dialog, date_pattern='y-mm-dd', width=20)
        date_entry.set_date(start_date)
        date_entry.pack(pady=5)
        
        def save_changes():
            new_name = name_entry.get().strip()
            new_start_date = date_entry.get_date()
            
            if not new_name:
                messagebox.showwarning("Input Error", "Please enter a factor name.", parent=edit_dialog)
                return
            
            success, msg = db.update_custom_factor(name, new_name, new_start_date)
            if success:
                edit_dialog.destroy()
                if self.selected_factor == name:
                    self.selected_factor = new_name
                self.load_factors()
                self.update_calendar_display()
            else:
                messagebox.showerror("Database Error", msg, parent=edit_dialog)
        
        # Buttons
        button_frame = ctk.CTkFrame(edit_dialog, fg_color="transparent")
        button_frame.pack(pady=20)
        ctk.CTkButton(button_frame, text="Save", command=save_changes).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Cancel", command=edit_dialog.destroy).pack(side="left", padx=5)

    def load_factors(self):
        for widget in self.factor_list_frame.winfo_children():
            widget.destroy()

        factors = db.get_custom_factors()
        for factor_name, in factors:
            frame = ctk.CTkFrame(self.factor_list_frame)
            frame.pack(fill="x", pady=2)
            frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(frame, text=factor_name, anchor="w").grid(row=0, column=0, sticky="ew", padx=5)
            frame.bind("<Button-1>", lambda e, n=factor_name: self.select_factor(n))
            frame.winfo_children()[0].bind("<Button-1>", lambda e, n=factor_name: self.select_factor(n))

            ctk.CTkButton(frame, text="Edit", width=40, fg_color="#3b7dd6", hover_color="#2e63ab",
                          command=lambda n=factor_name: self.edit_factor(n)).grid(row=0, column=1, padx=2, pady=5)
            ctk.CTkButton(frame, text="Del", width=40, fg_color="#db524b", hover_color="#b0423d",
                          command=lambda n=factor_name: self.delete_factor(n)).grid(row=0, column=2, padx=2, pady=5)

    def select_factor(self, name):
        self.selected_factor = name
        self.current_calendar_date = date.today()
        self.update_calendar_display()

    def toggle_day_override(self, day_date):
        if not self.selected_factor: return

        current_status = db.get_factor_status_for_date(self.selected_factor, day_date)
        # If toggling a "Taken" day to "Missed", value is 0.
        # If toggling a "Missed" day back to "Taken", value is 1.
        new_value = 0 if current_status == 1 else 1

        db.set_factor_override(self.selected_factor, day_date, new_value)
        self.update_calendar_display()

    def update_calendar_display(self):
        for widget in self.calendar_grid.winfo_children(): widget.destroy()

        if not self.selected_factor:
            self.month_year_label.configure(text="Select a factor")
            ctk.CTkLabel(self.calendar_grid, text="Select a factor from the list to manage its dates.").pack(
                expand=True)
            return

        year, month = self.current_calendar_date.year, self.current_calendar_date.month
        self.month_year_label.configure(text=f"{self.selected_factor}: {self.current_calendar_date.strftime('%B %Y')}")

        monthly_overrides = db.get_factor_overrides_for_month(self.selected_factor, year, month)

        for i, day_name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(self.calendar_grid, text=day_name, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0,
                                                                                                           column=i,
                                                                                                           sticky="nsew")
            self.calendar_grid.columnconfigure(i, weight=1)

        for r, week in enumerate(calendar.monthcalendar(year, month), start=1):
            self.calendar_grid.rowconfigure(r, weight=1)
            for c, day in enumerate(week):
                if day == 0: continue

                day_date = date(year, month, day)
                status = db.get_factor_status_for_date(self.selected_factor, day_date)

                color = "transparent"
                if status == 1:
                    color = "#345e37"  # Green for "Taken"
                elif status == 0:
                    color = "#8B0000"  # Dark Red for "Missed"

                day_frame = ctk.CTkFrame(self.calendar_grid, fg_color=color, border_width=1, border_color="gray")
                day_frame.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                day_frame.bind("<Button-1>", lambda e, d=day_date: self.toggle_day_override(d))

                lbl = ctk.CTkLabel(day_frame, text=str(day))
                lbl.pack(expand=True)
                lbl.bind("<Button-1>", lambda e, d=day_date: self.toggle_day_override(d))

    def prev_month(self):
        if not self.selected_factor: return
        self.current_calendar_date = (self.current_calendar_date.replace(day=1) - timedelta(days=1))
        self.update_calendar_display()

    def next_month(self):
        if not self.selected_factor: return
        last_day = calendar.monthrange(self.current_calendar_date.year, self.current_calendar_date.month)[1]
        self.current_calendar_date = (self.current_calendar_date.replace(day=1) + timedelta(days=last_day))
        self.update_calendar_display()