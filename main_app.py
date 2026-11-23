# file: main_app.py

import os
import queue
import threading
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
from ui.activitywatch_tab import ActivityWatchTab


# Application Constants TODO: set these to be more adjustable
#APP_WIDTH = 1200
#APP_HEIGHT = 850


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
        
        # Dynamic Window Sizing & Centering
        # Get the user's actual screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        # Calculate 80% of their screen (capped at 1400x900 for huge monitors)
        app_width = min(int(screen_width * 0.8), 1400)
        app_height = min(int(screen_height * 0.8), 900)

        # Calculate the x and y coordinates to perfectly center the window
        x_position = int((screen_width / 2) - (app_width / 2))
        y_position = int((screen_height / 2) - (app_height / 2))

        # Apply the geometry (size + position)
        self.geometry(f"{app_width}x{app_height}+{x_position}+{y_position}")

        # Set a minimum size so the charts and UI never get squished
        self.minsize(720, 480)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Tabs whose data changed while they were hidden; refreshed when next opened
        self._stale_tabs = set()
        self._garmin_syncing = False

        # Initialize UI
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
        auth_menu.add_command(label="Sign in to Garmin", command=self.sign_in_garmin)
        auth_menu.add_command(label="Configure Garmin API", command=self.update_garmin_credentials)
        auth_menu.add_separator()
        auth_menu.add_command(label="Disconnect Garmin", command=self.disconnect_garmin)
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
        self.tab_view = ctk.CTkTabview(self, command=self._on_tab_changed)
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
        # ActivityWatch tab (5th main page)
        aw_frame = self.tab_view.add("ActivityWatch")
        aw_frame.grid_rowconfigure(0, weight=1)
        aw_frame.grid_columnconfigure(0, weight=1)
        self.aw_tab = ActivityWatchTab(aw_frame, self)
        self.aw_tab.grid(row=0, column=0, sticky="nsew")

    def _on_tab_changed(self):
        """Called when the user switches tabs."""
        if self.tab_view.get() == "ActivityWatch":
            # Let the tab paint first; building the list takes a moment the first time.
            self.after(10, self.aw_tab.refresh_if_changed)
        else:
            self.after(10, self._refresh_visible_tab)

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
        if self._garmin_syncing:
            return
        # Show a dialog to select sync time frame
        import tkinter as tk
        from tkinter import simpledialog
        
        # Create a custom dialog for time frame selection
        dialog = tk.Toplevel(self)
        dialog.title("Select Sync Time Frame")
        dialog.geometry("450x250")
        dialog.transient(self)
        dialog.after(200, dialog.grab_set)
        
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

            # Make sure we are configured and authorized before syncing.
            if not garmin_downloader.garmin_api.is_configured():
                raise garmin_downloader.GarminConfigError("Garmin API is not configured yet.")
            if not garmin_downloader.garmin_api.has_token():
                if not messagebox.askyesno("Garmin Sign-in",
                                           "You are not signed in to Garmin yet.\n\n"
                                           "Open the Garmin sign-in page in your browser now?"):
                    self._reset_sync_button()
                    return
                garmin_downloader.garmin_api.authorize_interactive(on_tick=self.update)

            # Determine days parameter based on user selection
            option = result["option"]
            days = None if option == "smart" else int(option)
        except Exception as e:
            self._finish_garmin_sync(error=e)
            return
        self._run_garmin_sync(days)

    def _run_garmin_sync(self, days):
        """Download in a background thread so the window stays usable meanwhile."""
        self._garmin_syncing = True
        outcome = queue.Queue()

        def worker():
            try:
                outcome.put({"summary": garmin_downloader.sync_health_data(days=days)})
            except Exception as e:
                outcome.put({"error": e})

        # Poll from the main thread: dialogs and widgets may only be touched there.
        def poll():
            try:
                done = outcome.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            self._finish_garmin_sync(**done)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _reset_sync_button(self):
        self._garmin_syncing = False
        self.health_tab.sync_button.configure(text="Sync from Garmin", state="normal")

    def _finish_garmin_sync(self, summary=None, error=None):
        """Report a sync's result (on the main thread) and refresh the displays."""
        self._reset_sync_button()
        api = garmin_downloader.garmin_api
        if error is None:
            if summary["days_updated"]:
                self.update_all_displays()
            parts = []
            if summary["days_updated"]:
                parts.append(f"Updated {summary['days_updated']} day(s) of health data "
                             f"from {summary['summaries']} Garmin summaries.")
            else:
                parts.append("No new health data was available from Garmin for this period.")
            if summary["backfill_requested"]:
                parts.append("Older history was requested from Garmin. It is delivered in the "
                             "background; sync again in a few minutes to import it.")
            if summary["skipped"]:
                parts.append("Not shared / not enabled: " + ", ".join(summary["skipped"]))
            messagebox.showinfo("Garmin Sync", "\n\n".join(parts))
        elif isinstance(error, garmin_downloader.GarminConfigError):
            if messagebox.askyesno("Garmin API Not Configured",
                                   f"{error}\n\nWould you like to enter your Garmin API credentials now?"):
                self.update_garmin_credentials()
        elif isinstance(error, garmin_downloader.GarminAuthError):
            if api.uses_api_key():
                if messagebox.askyesno("Garmin API Key Rejected",
                                       f"{error}\n\nWould you like to update your API key now?"):
                    self.update_garmin_credentials()
            elif messagebox.askyesno("Garmin Authorization Needed",
                                     f"{error}\n\nWould you like to sign in to Garmin again now?"):
                self.sign_in_garmin()
        elif isinstance(error, garmin_downloader.GarminAPIError):
            messagebox.showerror("Sync Error", f"Garmin sync error:\n\n{error}")
        else:
            messagebox.showerror("Sync Error",
                                 f"Could not sync data from Garmin Connect.\nPlease ensure you are connected to the internet.\n\nError: {error}")

    def _garmin_busy(self):
        """True (after telling the user) while a sync is using the Garmin connection."""
        if self._garmin_syncing:
            messagebox.showinfo("Garmin Sync", "A Garmin sync is running. Please wait until it finishes.")
        return self._garmin_syncing

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
        """Call after study or health data changed: updates every tab that shows it.

        Only the visible tab is redrawn now; the others are redrawn when opened. The
        ActivityWatch tab is left out: its data only changes through its own import buttons,
        and rebuilding its list is slow. It refreshes on import and when opened.
        """
        # The dropdowns are cheap and the timers read them even while their tab is hidden.
        self.tracker_tab.update_tag_combobox()
        self.refresh_tabs("Tracker", "Pomodoro", "Analytics", "Health & Wellness")

    def update_health_charts(self):
        """Call after only health data changed."""
        self.refresh_tabs("Analytics", "Health & Wellness")

    def refresh_tabs(self, *names):
        """Refresh the named tabs: now if visible, otherwise when they are next opened."""
        self._stale_tabs.update(names)
        self._refresh_visible_tab()

    def _refresh_visible_tab(self):
        name = self.tab_view.get()
        if name not in self._stale_tabs:
            return
        self.update_idletasks()  # a newly opened tab needs its size before charts are drawn
        self._stale_tabs.discard(name)
        refresh = {
            "Tracker": self.tracker_tab.update_views,
            "Pomodoro": self.pomodoro_tab.update_pomodoro_log,
            "Analytics": self.analytics_tab.update_charts,
            "Health & Wellness": self.health_tab.update_charts,
        }[name]
        try:
            refresh()
        except Exception:
            self._stale_tabs.add(name)  # try again when the tab is next opened
            raise

    def update_pomodoro_tags(self, tags, current_tag):
        """
        Specialized method to pass tag information from the TrackerTab
        to the PomodoroTab, ensuring they stay in sync.
        """
        self.pomodoro_tab.update_pomo_tag_combobox(tags, current_tag)

    def refresh_tag_lists(self):
        """
        Lightweight refresh of every dropdown that lists tags or categories, for use after
        the tag manager changes them. Avoids the full chart refresh of update_all_displays.
        """
        self.tracker_tab.update_tag_combobox()  # also syncs the pomodoro tab's combobox
        self.analytics_tab.refresh_category_combobox()

    def sign_in_garmin(self):
        """Authorize this app with Garmin via OAuth 2.0 (PKCE) in the user's browser."""
        if self._garmin_busy():
            return
        api = garmin_downloader.garmin_api
        if not api.is_configured():
            if messagebox.askyesno("Garmin API Not Configured",
                                   "Enter your Garmin API key or developer app credentials first?"):
                self.update_garmin_credentials()
            return
        if api.uses_api_key():
            # No browser sign-in with a personal key: just check that Garmin accepts it.
            try:
                msg = api.verify_credentials()
                messagebox.showinfo("Garmin API Key", f"{msg} You can sync now.")
            except garmin_downloader.GarminAPIError as e:
                messagebox.showerror("Garmin API Key", f"Could not verify the API key:\n\n{e}")
            return
        messagebox.showinfo("Garmin Sign-in",
                            "Your browser will open Garmin Connect.\n\n"
                            "Sign in there and allow access. This window will continue automatically "
                            "once you are done (times out after 5 minutes).")
        try:
            api.authorize_interactive(on_tick=self.update)
            perms = []
            try:
                perms = api.get_user_permissions()
            except garmin_downloader.GarminAPIError:
                pass
            extra = f"\n\nGranted permissions: {', '.join(perms)}" if perms else ""
            messagebox.showinfo("Garmin Sign-in", "Successfully connected to Garmin." + extra)
        except garmin_downloader.GarminAPIError as e:
            messagebox.showerror("Garmin Sign-in Failed", str(e))
        except Exception as e:
            messagebox.showerror("Garmin Sign-in Error", f"An error occurred during Garmin sign-in: {e}")

    def disconnect_garmin(self):
        """Revoke this app's Garmin access and delete the stored tokens."""
        if self._garmin_busy():
            return
        if garmin_downloader.garmin_api.uses_api_key():
            question = ("Remove the saved Garmin API key from this computer? (The key itself stays valid "
                        "until you revoke it on Garmin's site.) Health data already imported stays in the database.")
        else:
            question = ("Revoke Study Tracker's access to your Garmin data and delete the saved sign-in? "
                        "Health data already imported stays in the database.")
        if not messagebox.askyesno("Disconnect Garmin", question):
            return
        garmin_downloader.garmin_api.deregister_user()
        messagebox.showinfo("Disconnect Garmin", "Garmin has been disconnected.")

    def update_garmin_credentials(self):
        """Dialog to choose how the app authenticates with the Garmin Health API:
        a personal API key (used directly) or a developer app's Client ID/Secret (browser sign-in)."""
        if self._garmin_busy():
            return
        import tkinter as tk
        api = garmin_downloader.garmin_api
        cfg = api.load_config()

        dialog = tk.Toplevel(self)
        dialog.title("Configure Garmin API")
        dialog.geometry("500x500")
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(dialog, text="Garmin Health API Credentials", font=("Arial", 12, "bold")).pack(pady=(15, 5))

        mode = tk.StringVar(value=cfg.get("auth_mode", api.AUTH_MODE_OAUTH))
        tk.Radiobutton(dialog, text="Personal API key (no browser sign-in)", variable=mode,
                       value=api.AUTH_MODE_API_KEY).pack(anchor="w", padx=20)
        tk.Radiobutton(dialog, text="Developer app: Client ID / Secret (sign in through browser)", variable=mode,
                       value=api.AUTH_MODE_OAUTH).pack(anchor="w", padx=20)

        def labeled_entry(parent, label, value, show=None):
            tk.Label(parent, text=label).pack(pady=(6, 0))
            entry = tk.Entry(parent, width=52, show=show)
            entry.pack(pady=2)
            if value:
                entry.insert(0, value)
            return entry

        key_frame = tk.LabelFrame(dialog, text="Personal API key", padx=10, pady=5)
        key_frame.pack(fill="x", padx=15, pady=(10, 5))
        key_entry = labeled_entry(key_frame, "API key:", cfg.get("api_key", ""), show="*")

        oauth_frame = tk.LabelFrame(dialog, text="Developer app (OAuth)", padx=10, pady=5)
        oauth_frame.pack(fill="x", padx=15, pady=5)
        id_entry = labeled_entry(oauth_frame, "Client ID:", cfg.get("client_id", ""))
        secret_entry = labeled_entry(oauth_frame, "Client Secret:", cfg.get("client_secret", ""), show="*")
        redirect_entry = labeled_entry(oauth_frame, "Redirect URI (register it on your app):",
                                       cfg.get("redirect_uri", api.DEFAULT_REDIRECT_URI))

        tk.Label(dialog, justify="center", wraplength=460, fg="gray",
                 text="Saved in ~/.studytracker on this computer. Your Garmin password is never "
                      "stored by Study Tracker.").pack(pady=5)

        def refresh_state(*_):
            key_on = mode.get() == api.AUTH_MODE_API_KEY
            key_entry.configure(state="normal" if key_on else "disabled")
            for e in (id_entry, secret_entry, redirect_entry):
                e.configure(state="disabled" if key_on else "normal")

        mode.trace_add("write", refresh_state)
        refresh_state()

        def save_config():
            if mode.get() == api.AUTH_MODE_API_KEY:
                api_key = key_entry.get().strip()
                if not api_key:
                    messagebox.showwarning("Input Error", "Please enter your API key.", parent=dialog)
                    return
                api.save_api_key(api_key)
                dialog.destroy()
                self.sign_in_garmin()  # verifies the key
                return
            client_id = id_entry.get().strip()
            client_secret = secret_entry.get().strip()
            redirect_uri = redirect_entry.get().strip() or api.DEFAULT_REDIRECT_URI
            if not client_id or not client_secret:
                messagebox.showwarning("Input Error", "Please enter both Client ID and Client Secret.", parent=dialog)
                return
            api.save_config(client_id, client_secret, redirect_uri)
            dialog.destroy()
            if messagebox.askyesno("Garmin API", "Saved. Sign in to Garmin now?"):
                self.sign_in_garmin()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Save", command=save_config, width=15).pack(side="left", padx=5)
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