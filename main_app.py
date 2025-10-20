# file: main_app.py

import os
import customtkinter as ctk
from tkinter import messagebox, filedialog

# --- Local Module Imports ---
# Import the database manager first as it's a core dependency
from core import database_manager as db, data_importer, activity_importer
from core import garmin_downloader

# Import data handling modules

# Import UI component modules for pop-up windows
from ui.ui_components import SessionEditWindow, TagManagementWindow, ManualHealthEntryWindow
from ui.custom_factors_manager import CustomFactorsWindow

# Import the new, self-contained tab modules
from ui.tracker_tab import TrackerTab
from ui.pomodoro_tab import PomodoroTab
from ui.analytics_tab import AnalyticsTab
from ui.health_tab import HealthTab


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
        self._setup_menu()
        self._setup_tabs()
        self.update_all_displays()

    def _setup_menu(self):
        """Create a simple menu bar with an option to sign in to Garmin for full metrics."""
        # Use the standard tkinter Menu API (safer and more compatible than CTkMenu)
        import tkinter as tk
        menubar = tk.Menu(self)

        # Create an "Auth" cascade for Garmin sign-in
        auth_menu = tk.Menu(menubar, tearoff=0)
        auth_menu.add_command(label="Sign in to Garmin (OAuth)", command=self.sign_in_garmin)
        auth_menu.add_command(label="Update Garmin Credentials", command=self.update_garmin_credentials)
        menubar.add_cascade(label="Garmin", menu=auth_menu)

        # Attach the menu to the root window. If this fails in some packaged
        # environments it's non-fatal and we continue without a menu bar.
        try:
            self.config(menu=menubar)
        except Exception:
            pass

    def _setup_tabs(self):
        """Creates the main tab view and populates it with the tab modules."""
        # Use grid for the main tab view to ensure proper expansion
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Create the container frames for each tab within the tab view
        tracker_frame = self.tab_view.add("Tracker")
        pomodoro_frame = self.tab_view.add("Pomodoro")
        analytics_frame = self.tab_view.add("Analytics")
        health_frame = self.tab_view.add("Health & Wellness")

        # Instantiate each tab class, passing the appropriate frame and a
        # reference to this main app instance (`self`) for callbacks.
        # Ensure each tab frame expands fully
        tracker_frame.grid_rowconfigure(0, weight=1)
        tracker_frame.grid_columnconfigure(0, weight=1)
        self.tracker_tab = TrackerTab(tracker_frame, self)
        self.tracker_tab.grid(row=0, column=0, sticky="nsew")

        pomodoro_frame.grid_rowconfigure(0, weight=1)
        pomodoro_frame.grid_columnconfigure(0, weight=1)
        self.pomodoro_tab = PomodoroTab(pomodoro_frame, self)
        self.pomodoro_tab.grid(row=0, column=0, sticky="nsew")

        analytics_frame.grid_rowconfigure(0, weight=1)
        analytics_frame.grid_columnconfigure(0, weight=1)
        self.analytics_tab = AnalyticsTab(analytics_frame, self)
        self.analytics_tab.grid(row=0, column=0, sticky="nsew")

        health_frame.grid_rowconfigure(0, weight=1)
        health_frame.grid_columnconfigure(0, weight=1)
        self.health_tab = HealthTab(health_frame, self)
        self.health_tab.grid(row=0, column=0, sticky="nsew")

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

    def sync_and_import_garmin_data(self):
        """Downloads latest data from Garmin and then imports it."""
        # Show a dialog to select sync time frame
        import tkinter as tk
        from tkinter import simpledialog
        
        # Create a custom dialog for time frame selection
        dialog = tk.Toplevel(self)
        dialog.title("Select Sync Time Frame")
        dialog.geometry("450x250")
        dialog.transient(self)
        dialog.grab_set()
        
        selected_option = tk.StringVar(value="smart")
        
        tk.Label(dialog, text="Choose how much data to sync:", font=("Arial", 12, "bold")).pack(pady=10)
        
        tk.Radiobutton(dialog, text="Smart sync (recommended - only fetch missing data)", 
                      variable=selected_option, value="smart", font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        tk.Radiobutton(dialog, text="Last 7 days", 
                      variable=selected_option, value="7", font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        tk.Radiobutton(dialog, text="Last 30 days", 
                      variable=selected_option, value="30", font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        tk.Radiobutton(dialog, text="Last 90 days (full sync - slower)", 
                      variable=selected_option, value="90", font=("Arial", 10)).pack(anchor="w", padx=20, pady=5)
        
        result = {"confirmed": False}
        
        def on_ok():
            result["confirmed"] = True
            result["option"] = selected_option.get()
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=5)
        tk.Button(button_frame, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=5)
        
        self.wait_window(dialog)
        
        if not result.get("confirmed"):
            return
        
        try:
            self.health_tab.sync_button.configure(text="Syncing...", state="disabled")
            self.update()
        
            # Determine days parameter based on user selection
            option = result["option"]
            if option == "smart":
                filepath = garmin_downloader.download_health_stats()  # Smart sync (no days param)
            else:
                filepath = garmin_downloader.download_health_stats(days=int(option))

            if not filepath or not os.path.exists(filepath):
                messagebox.showwarning("Download Failed", "Could not retrieve the data file from Garmin.")
                return

            count, message = data_importer.import_garmin_csv(filepath)
            if count > 0:
                messagebox.showinfo("Success", f"Successfully synced and imported {count} health record(s).")
            else:
                messagebox.showwarning("No New Data",
                                       message or "No new health records were found.")
            self.update_all_displays()
        except garmin_downloader.GarthException as e:
            # Check if it's an authentication error
            error_msg = str(e)
            if "credentials" in error_msg.lower() or "password" in error_msg.lower() or "auth" in error_msg.lower():
                # Offer to update credentials
                if messagebox.askyesno("Authentication Failed", 
                                      f"{error_msg}\n\nWould you like to update your Garmin credentials?"):
                    self.update_garmin_credentials()
            else:
                messagebox.showerror("Sync Error", f"Garmin sync error:\n\n{e}")
        except Exception as e:
            messagebox.showerror("Sync Error",
                                 f"Could not sync data from Garmin Connect.\nPlease ensure you are connected to the internet.\n\nError: {e}")
        finally:
            self.health_tab.sync_button.configure(text="Sync from Garmin", state="normal")

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

    def sign_in_garmin(self):
        """Trigger an interactive Garmin OAuth1 login to obtain full metric access."""
        try:
            ok = garmin_downloader.ensure_oauth_session()
            if ok:
                messagebox.showinfo("Garmin Login", "Successfully signed in to Garmin. Full metrics should now be available on the next sync.")
            else:
                messagebox.showwarning("Garmin Login", "Could not sign in to Garmin. Please check credentials and try again.")
        except Exception as e:
            messagebox.showerror("Garmin Login Error", f"An error occurred during Garmin sign-in: {e}")

    def update_garmin_credentials(self):
        """Open a dialog to update Garmin credentials."""
        import tkinter as tk
        
        dialog = tk.Toplevel(self)
        dialog.title("Update Garmin Credentials")
        dialog.geometry("400x250")
        dialog.transient(self)
        dialog.grab_set()
        
        tk.Label(dialog, text="Update Your Garmin Connect Credentials", 
                font=("Arial", 12, "bold")).pack(pady=20)
        
        tk.Label(dialog, text="These credentials will be saved as environment variables\nand used for future syncs.", 
                justify="center").pack(pady=5)
        
        # Email
        tk.Label(dialog, text="Garmin Email:").pack(pady=(10, 0))
        email_entry = tk.Entry(dialog, width=40)
        email_entry.pack(pady=5)
        
        # Pre-fill with current value if exists
        current_email = os.getenv("GARMIN_EMAIL", "")
        if current_email:
            email_entry.insert(0, current_email)
        
        # Password
        tk.Label(dialog, text="Garmin Password:").pack(pady=(10, 0))
        password_entry = tk.Entry(dialog, width=40, show="*")
        password_entry.pack(pady=5)
        
        def save_credentials():
            email = email_entry.get().strip()
            password = password_entry.get().strip()
            
            if not email or not password:
                messagebox.showwarning("Input Error", "Please enter both email and password.", parent=dialog)
                return
            
            # Set environment variables for this session
            os.environ["GARMIN_EMAIL"] = email
            os.environ["GARMIN_PASSWORD"] = password
            
            # Try to authenticate with the new credentials
            try:
                import garth
                garth.login(email, password)
                garth.save("~/.garth")
                messagebox.showinfo("Success", 
                                  "Credentials updated and authenticated successfully!\n\n"
                                  "Note: These are stored for this session only.\n"
                                  "To persist across restarts, add them to your system environment variables:\n"
                                  "GARMIN_EMAIL and GARMIN_PASSWORD", 
                                  parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Authentication Failed", 
                                   f"Could not authenticate with the provided credentials.\n\nError: {e}", 
                                   parent=dialog)
        
        # Buttons
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)
        tk.Button(button_frame, text="Save & Test", command=save_credentials, width=15).pack(side="left", padx=5)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy, width=15).pack(side="left", padx=5)


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