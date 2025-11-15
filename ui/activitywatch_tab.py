"""UI tab to import and view ActivityWatch daily aggregates."""
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import timedelta
import json

from core import activitywatch_importer as awi
from core import database_manager as db


class ActivityWatchTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(header, text="ActivityWatch Import & Daily Summary", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e", padx=20, pady=10)
        ctk.CTkButton(btn_frame, text="Import AW CSV", command=self.import_csv).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Import AW JSON", command=self.import_json).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Import AW Tags (JSON)", command=self.import_tags_json).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Refresh", command=self.refresh).pack(side="left", padx=6)

        # Main scrollable list for daily aggregates
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0,20))
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()

    def import_csv(self):
        filepath = filedialog.askopenfilename(title="Select ActivityWatch CSV", filetypes=[("CSV files", "*.csv")])
        if not filepath: return
        try:
            count, message = awi.import_aw_csv(filepath)
            if count > 0:
                messagebox.showinfo("Imported", f"Imported {count} day(s) of ActivityWatch data.")
            else:
                messagebox.showwarning("Import Result", message)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not import file: {e}")

    def import_json(self):
        filepath = filedialog.askopenfilename(title="Select ActivityWatch JSON", filetypes=[("JSON files", "*.json")])
        if not filepath: return
        try:
            count, message = awi.import_aw_json(filepath)
            if count > 0:
                messagebox.showinfo("Imported", f"Imported {count} day(s) of ActivityWatch data.")
            else:
                messagebox.showwarning("Import Result", message)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not import file: {e}")

    def import_tags_json(self):
        filepath = filedialog.askopenfilename(title="Select AW categories JSON", filetypes=[("JSON files", "*.json")])
        if not filepath: return
        try:
            created, skipped, message = awi.import_aw_tags_json(filepath)
            msg = f"Created {created} tags. Skipped {skipped} entries." if not message else message
            messagebox.showinfo("Tags Import Result", msg)
            # If tags were created, refresh tag-dependent UI (tracker tab)
            try:
                self.app.tracker_tab.update_tag_combobox()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not import tags file: {e}")

    def refresh(self):
        # Clear list
        for w in self.list_frame.winfo_children():
            w.destroy()

        rows = db.get_aw_daily()
        if not rows:
            ctk.CTkLabel(self.list_frame, text="No ActivityWatch data imported.").grid(row=0, column=0, sticky="w", padx=10, pady=10)
            return

        # Header
        header = ctk.CTkFrame(self.list_frame, fg_color=("#EDEDED", "#1f1f1f"))
        header.grid(row=0, column=0, sticky="ew", padx=5, pady=(5,2))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Date", width=140).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ctk.CTkLabel(header, text="Active Time", anchor="w").grid(row=0, column=1, sticky="w", padx=8)

        for i, (date_str, seconds, app_json) in enumerate(rows, start=1):
            frame = ctk.CTkFrame(self.list_frame, fg_color=("#FFFFFF", "#2b2b2b"))
            frame.grid(row=i, column=0, sticky="ew", padx=5, pady=2)
            frame.grid_columnconfigure(1, weight=1)
            hrs = timedelta(seconds=int(seconds))
            ctk.CTkLabel(frame, text=date_str, width=140).grid(row=0, column=0, sticky="w", padx=8, pady=6)
            ctk.CTkLabel(frame, text=str(hrs)).grid(row=0, column=1, sticky="w", padx=8)
            # Small button to show app breakdown
            def make_show(json_txt):
                def _show():
                    try:
                        d = json.loads(json_txt) if json_txt else {}
                    except Exception:
                        d = {}
                    text = "\n".join([f"{k}: {v}s" for k, v in d.items()]) or "No per-app data."
                    messagebox.showinfo("App breakdown", text)
                return _show

            ctk.CTkButton(frame, text="Apps", width=60, command=make_show(app_json)).grid(row=0, column=2, padx=6)
