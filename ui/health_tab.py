# file: ui/health_tab.py

import customtkinter as ctk
import pandas as pd
from datetime import datetime, timedelta

from core import database_manager as db
from core import plot_manager as pm


class HealthTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance

        # --- State Variables ---
        self.time_range = ctk.StringVar(value="30 Days")

        # --- UI Setup ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.columnconfigure(5, weight=1)

        ctk.CTkLabel(header_frame, text="Health & Study Correlation", font=ctk.CTkFont(size=20, weight="bold")).grid(
            row=0, column=0, sticky="w")

        self.sync_button = ctk.CTkButton(header_frame, text="Sync from Garmin",
                                         command=self.app.sync_and_import_garmin_data)
        self.sync_button.grid(row=0, column=1, padx=(20, 5))

        ctk.CTkButton(header_frame, text="Import From File", command=self.app.import_garmin_data).grid(row=0, column=2,
                                                                                                       padx=(20, 5))
        ctk.CTkButton(header_frame, text="Import Activities CSV", command=self.app.import_activities_data).grid(row=0,
                                                                                                                column=3,
                                                                                                                padx=(0,
                                                                                                                      5))
        ctk.CTkButton(header_frame, text="Manual Sleep Entry", command=self.app.open_manual_health_entry).grid(row=0,
                                                                                                               column=4,
                                                                                                               padx=(0,
                                                                                                                     5))
        ctk.CTkButton(header_frame, text="Manage Factors", command=self.app.open_custom_factors_manager).grid(row=0,
                                                                                                              column=5,
                                                                                                              padx=(0,
                                                                                                                    20))

        ctk.CTkSegmentedButton(
            header_frame,
            values=["7 Days", "30 Days", "90 Days", "Year"],
            variable=self.time_range,
            command=lambda v: self.update_charts()
        ).grid(row=0, column=6, padx=20, pady=5)

        self.charts_frame = ctk.CTkFrame(self)
        self.charts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.charts_frame.grid_rowconfigure((0, 1), weight=1)

        self.sleep_score_chart = ctk.CTkFrame(self.charts_frame)
        self.sleep_score_chart.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.sleep_duration_chart = ctk.CTkFrame(self.charts_frame)
        self.sleep_duration_chart.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.body_battery_chart = ctk.CTkFrame(self.charts_frame)
        self.body_battery_chart.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.trends_chart = ctk.CTkFrame(self.charts_frame)
        self.trends_chart.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

    def update_charts(self):
        time_range_str = self.time_range.get()
        days = {'7 Days': 6, '30 Days': 29, '90 Days': 89, 'Year': 364}.get(time_range_str, 29)
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')

        # For the health tab, we always get all study data.
        where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
        params = [start_date, end_date]

        # *** BUG FIX: Removed .reset_index() as it's now handled in the database manager ***
        df = db.get_health_and_study_data(start_date, end_date, where_clause, params)

        if df.empty:
            for frame in [self.sleep_score_chart, self.sleep_duration_chart, self.body_battery_chart,
                          self.trends_chart]:
                for w in frame.winfo_children(): w.destroy()
            return

        # Safely convert columns to numeric types
        for col in ['sleep_score', 'total_study_minutes', 'sleep_duration_seconds', 'body_battery', 'avg_stress']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['sleep_duration_hours'] = df['sleep_duration_seconds'] / 3600.0

        # Create and embed plots
        fig1 = pm.create_correlation_scatter_plot(df, 'sleep_score', 'total_study_minutes',
                                                  f"Study vs. Sleep Score ({time_range_str})", "Sleep Score",
                                                  "Study Minutes")
        pm.embed_figure_in_frame(fig1, self.sleep_score_chart)

        fig2 = pm.create_correlation_scatter_plot(df, 'sleep_duration_hours', 'total_study_minutes',
                                                  f"Study vs. Sleep Duration ({time_range_str})",
                                                  "Sleep Duration (Hours)", "Study Minutes")
        pm.embed_figure_in_frame(fig2, self.sleep_duration_chart)

        fig3 = pm.create_correlation_scatter_plot(df, 'body_battery', 'total_study_minutes',
                                                  f"Study vs. Body Battery ({time_range_str})", "Body Battery",
                                                  "Study Minutes")
        pm.embed_figure_in_frame(fig3, self.body_battery_chart)

        fig4 = pm.create_trends_chart(df, time_range_str)
        pm.embed_figure_in_frame(fig4, self.trends_chart)

