# file: main_app.py

import customtkinter as ctk
from tkinter import messagebox, filedialog

# --- Local Module Imports ---
# Import the database manager first as it's a core dependency
import database_manager as db

# Import data handling modules
import data_importer
import activity_importer

# Import UI component modules for pop-up windows
from ui_components import SessionEditWindow, TagManagementWindow, ManualHealthEntryWindow
from custom_factors_manager import CustomFactorsWindow

# Import the new, self-contained tab modules
from tracker_tab import TrackerTab
from pomodoro_tab import PomodoroTab
from analytics_tab import AnalyticsTab
from health_tab import HealthTab

# --- Application Constants ---
APP_WIDTH = 1200
APP_HEIGHT = 850


class StudyTrackerApp(ctk.CTk):
    """
    The main application window.
    This class is responsible for building the main UI structure (the tab view)
    and coordinating actions that affect the entire application, such as
    opening pop-up windows and triggering data imports.
    """

    def __init__(self):
        super().__init__()
        self.title("Focus & Wellness Tracker")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Initialize UI ---
        self._setup_tabs()
        self.update_all_displays()

    def _setup_tabs(self):
        """Creates the main tab view and populates it with the tab modules."""
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        # Create the container frames for each tab within the tab view
        tracker_frame = self.tab_view.add("Tracker")
        pomodoro_frame = self.tab_view.add("Pomodoro")
        analytics_frame = self.tab_view.add("Analytics")
        health_frame = self.tab_view.add("Health & Wellness")

        # Instantiate each tab class, passing the appropriate frame and a
        # reference to this main app instance (`self`) for callbacks.
        self.tracker_tab = TrackerTab(tracker_frame, self)
        self.tracker_tab.pack(fill="both", expand=True)

        self.pomodoro_tab = PomodoroTab(pomodoro_frame, self)
        self.pomodoro_tab.pack(fill="both", expand=True)

        self.analytics_tab = AnalyticsTab(analytics_frame, self)
        self.analytics_tab.pack(fill="both", expand=True)

        self.health_tab = HealthTab(health_frame, self)
        self.health_tab.pack(fill="both", expand=True)

    # --- Pop-up Window Management ---
    # These methods remain in the main app as they are global actions.
    def open_tag_manager(self):
        TagManagementWindow(self)

    def open_custom_factors_manager(self):
        CustomFactorsWindow(self)

    def add_session_popup(self):
        SessionEditWindow(self, session_id=None)

    def edit_session_popup(self, session_id):
        SessionEditWindow(self, session_id=session_id)

    def open_manual_health_entry(self):
        ManualHealthEntryWindow(self)

    # --- Data Import Management ---
    # These methods handle file dialogs and call the appropriate importers.
    # They stay in the main app to coordinate a full UI refresh upon completion.
    def import_garmin_data(self):
        filepath = filedialog.askopenfilename(title="Select Garmin Sleep CSV", filetypes=[("CSV files", "*.csv")])
        if not filepath: return
        try:
            count, message = data_importer.import_garmin_csv(filepath)
            if count > 0:
                messagebox.showinfo("Success", f"Successfully imported {count} health record(s).")
            else:
                messagebox.showwarning("No Data Imported", message)
            self.update_all_displays()
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not process the file.\n\nError: {e}")

    def import_activities_data(self):
        filepath = filedialog.askopenfilename(title="Select Garmin Activities CSV", filetypes=[("CSV files", "*.csv")])
        if not filepath: return
        try:
            count, message = activity_importer.import_activities_csv(filepath)
            if count > 0:
                messagebox.showinfo("Success", f"Successfully imported {count} activity record(s).")
            else:
                messagebox.showwarning("No Data Imported", message)
            self.update_all_displays()
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not process the file.\n\nError: {e}")

    # --- Global Update Coordination ---
    def update_all_displays(self):
        """Delegates update calls to each individual tab object."""
        self.tracker_tab.update_displays()
        self.pomodoro_tab.update_pomodoro_log()
        self.analytics_tab.update_charts()
        self.health_tab.update_charts()

    def update_pomodoro_tags(self, tags, current_tag):
        """
        Specialized method to pass tag information from the TrackerTab
        to the PomodoroTab, ensuring they stay in sync.
        """
        self.pomodoro_tab.update_pomo_tag_combobox(tags, current_tag)


if __name__ == "__main__":
    # Ensure the database and its tables are created before the app starts
    db.setup_database()

    # Check for required packages to provide a helpful error message on launch
    try:
        from dateutil.relativedelta import relativedelta
        import statsmodels
        import sklearn
    except ImportError:
        messagebox.showerror("Missing Packages",
                             "This application requires 'python-dateutil', 'statsmodels', and 'scikit-learn'. "
                             "Please install them by running:\n\n"
                             "pip install -r requirements.txt")
    else:
        app = StudyTrackerApp()
        # On first run, create a default tag to ensure the app is usable
        if not db.get_tags():
            db.add_tag('General')
            app.tracker_tab.update_tag_combobox()

        app.mainloop()