# file: ui/analytics_tab.py

import customtkinter as ctk
import pandas as pd
from tkinter import filedialog, messagebox
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
import os

from core import database_manager as db
from core import plot_manager as pm
from core import correlation_engine


class AnalyticsTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance

        # --- State Variables ---
        self.page = 0
        self.max_pages = 4
        self.view_mode = ctk.StringVar(value="Week")
        self.end_date = date.today()
        self.analysis_method = ctk.StringVar(value="Strict")
        self.model_type = ctk.StringVar(value="Lasso")
        self.category_filter = ctk.StringVar(value="All Time")

        # --- UI Setup ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._create_widgets()

    def _create_widgets(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.columnconfigure(3, weight=1)

        ctk.CTkLabel(header_frame, text="Study Analytics", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0,
                                                                                                          column=0,
                                                                                                          sticky="w")

        # Category Filter
        ctk.CTkLabel(header_frame, text="Filter by Category:").grid(row=0, column=1, padx=(20, 5), sticky="w")
        ctk.CTkSegmentedButton(header_frame, values=["All Time", "School Work"],
                               variable=self.category_filter,
                               command=lambda v: self.update_charts()).grid(row=0, column=2, sticky="w")

        ctk.CTkButton(header_frame, text="<", width=30, command=lambda: self._cycle_date_range(-1)).grid(row=0,
                                                                                                         column=4,
                                                                                                         padx=(20, 5))
        self.date_range_label = ctk.CTkLabel(header_frame, text="Date Range", font=ctk.CTkFont(size=14))
        self.date_range_label.grid(row=0, column=5, sticky="ew")  # Changed column
        ctk.CTkButton(header_frame, text=">", width=30, command=lambda: self._cycle_date_range(1)).grid(row=0, column=6,
                                                                                                        padx=(5, 20))
        ctk.CTkSegmentedButton(header_frame, values=["Day", "Week", "Month", "Year"], variable=self.view_mode,
                               command=self._on_view_mode_change).grid(row=0, column=7, padx=5)
        ctk.CTkButton(header_frame, text="Export Data", command=self.export_data).grid(row=0, column=8, padx=(20, 10))

        self.charts_frame = ctk.CTkFrame(self)
        self.charts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.charts_frame.grid_rowconfigure((0, 1), weight=1)
        self.chart_frame_tl = ctk.CTkFrame(self.charts_frame)
        self.chart_frame_tl.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.chart_frame_tr = ctk.CTkFrame(self.charts_frame)
        self.chart_frame_tr.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chart_frame_bl = ctk.CTkFrame(self.charts_frame)
        self.chart_frame_bl.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.chart_frame_br = ctk.CTkFrame(self.charts_frame)
        self.chart_frame_br.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        footer_frame.columnconfigure(1, weight=1)
        ctk.CTkButton(footer_frame, text="<", width=30, command=lambda: self._cycle_chart_page(-1)).grid(row=0,
                                                                                                         column=0,
                                                                                                         sticky="e")
        self.page_label = ctk.CTkLabel(footer_frame, text=f"Page {self.page + 1} / {self.max_pages}")
        self.page_label.grid(row=0, column=1)
        ctk.CTkButton(footer_frame, text=">", width=30, command=lambda: self._cycle_chart_page(1)).grid(row=0, column=2,
                                                                                                        sticky="w")

        self.analysis_controls_frame = ctk.CTkFrame(footer_frame, fg_color="transparent")
        self.analysis_controls_frame.grid(row=0, column=3, padx=(20, 0))
        ctk.CTkLabel(self.analysis_controls_frame, text="Model:").pack(side="left", padx=(0, 5))
        ctk.CTkSegmentedButton(self.analysis_controls_frame, values=["Lasso", "PCA", "Standard", "Weekly"],
                               variable=self.model_type, command=lambda v: self.update_charts()).pack(side="left")
        ctk.CTkLabel(self.analysis_controls_frame, text="Data:").pack(side="left", padx=(15, 5))
        ctk.CTkSegmentedButton(self.analysis_controls_frame, values=["Strict", "Imputed"],
                               variable=self.analysis_method, command=lambda v: self.update_charts()).pack(side="left")

    def _get_date_range(self):
        end = self.end_date
        mode = self.view_mode.get()
        if mode == "Day":
            start = end
        elif mode == "Week":
            start = end - timedelta(days=6)
        elif mode == "Month":
            start = end - relativedelta(months=1) + timedelta(days=1)
        elif mode == "Year":
            start = end - relativedelta(years=1) + timedelta(days=1)
        else:
            start = end - timedelta(days=6)
        return start, end

    def _cycle_date_range(self, direction):
        mode = self.view_mode.get()
        if mode == "Day":
            self.end_date += timedelta(days=direction)
        elif mode == "Week":
            self.end_date += timedelta(weeks=direction)
        elif mode == "Month":
            self.end_date += relativedelta(months=direction)
        elif mode == "Year":
            self.end_date += relativedelta(years=direction)
        self.update_charts()

    def _cycle_chart_page(self, direction):
        self.page = (self.page + direction) % self.max_pages
        self.update_charts()

    def _on_view_mode_change(self, value):
        self.end_date = date.today()
        self.update_charts()

    def _clear_chart_frames(self):
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]:
            for widget in frame.winfo_children(): widget.destroy()
        for widget in self.charts_frame.winfo_children():
            if not isinstance(widget, ctk.CTkFrame): widget.destroy()

    def update_charts(self):
        self._clear_chart_frames()
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]: frame.grid()

        start_date, end_date = self._get_date_range()
        if start_date == end_date:
            self.date_range_label.configure(text=start_date.strftime('%B %d, %Y'))
        else:
            self.date_range_label.configure(
                text=f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}")
        self.page_label.configure(text=f"Page {self.page + 1} / {self.max_pages}")

        if self.page == 3:
            self.analysis_controls_frame.grid()
        else:
            self.analysis_controls_frame.grid_remove()

        if self.category_filter.get() == "School Work":
            where_clause = "WHERE date(s.start_time) BETWEEN ? AND ? AND t.category_name = 'School Work'"
            params = [start_date.isoformat(), end_date.isoformat()]
        else:
            where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
            params = [start_date.isoformat(), end_date.isoformat()]

        page_renderers = {
            0: self._render_overview_page, 1: self._render_health_correlation_page,
            2: self._render_numerical_stats_page, 3: self._render_modeling_page
        }
        renderer = page_renderers.get(self.page)
        if renderer: renderer(start_date, end_date, where_clause, params)

    # In ui/analytics_tab.py, find the _render_overview_page function and replace it with this updated version.

    def _render_overview_page(self, start_date, end_date, where_clause, params):
        time_range_str = self.view_mode.get()

        # --- Special layout for "Day" view ---
        if time_range_str == "Day":
            # TOP LEFT: Time by Subject (Pie Chart)
            query1 = f"SELECT s.tag, SUM(s.duration_seconds), t.color FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY s.tag"
            pm.embed_figure_in_frame(pm.create_pie_chart(db.fetch_all(query1, params), time_range_str),
                                     self.chart_frame_tl)

            # TOP RIGHT: Detailed Session List (Replaces daily bar chart)
            self.chart_frame_tr.configure(fg_color=("#DBDBDB", "#2B2B2B"))
            ctk.CTkLabel(self.chart_frame_tr, text="Session Log", font=ctk.CTkFont(size=16, weight="bold")).pack(
                anchor="w", padx=10, pady=(10, 5))
            log_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent")
            log_frame.pack(fill="both", expand=True, padx=5)

            day_sessions_query = f"SELECT s.tag, s.start_time, s.end_time, s.duration_seconds FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} ORDER BY s.start_time"
            day_sessions = db.fetch_all(day_sessions_query, params)
            if not day_sessions:
                ctk.CTkLabel(log_frame, text="No sessions logged.").pack(anchor="w", padx=10)
            else:
                for tag, start, end, duration in day_sessions:
                    start_dt = datetime.fromisoformat(start)
                    end_dt = datetime.fromisoformat(end)
                    duration_str = str(timedelta(seconds=int(duration)))
                    log_text = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')} ({duration_str}) - {tag}"
                    ctk.CTkLabel(log_frame, text=log_text).pack(anchor="w", padx=10)

            # BOTTOM LEFT: Hourly breakdown (using new function)
            hourly_df = db.get_hourly_breakdown_for_day(start_date.isoformat(), where_clause, params)
            pm.embed_figure_in_frame(pm.create_hourly_bar_chart(hourly_df, time_range_str), self.chart_frame_bl)

            # BOTTOM RIGHT: Time by Category
            pm.embed_figure_in_frame(
                pm.create_category_pie_chart(db.get_time_by_category(where_clause, params), self.chart_frame_br),
                self.chart_frame_br)

        # --- Standard layout for all other views ---
        else:
            query1 = f"SELECT s.tag, SUM(s.duration_seconds), t.color FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY s.tag"
            pm.embed_figure_in_frame(pm.create_pie_chart(db.fetch_all(query1, params), time_range_str),
                                     self.chart_frame_tl)

            query2 = f"SELECT strftime('%Y-%m-%d', s.start_time) as day, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY day ORDER BY day"
            pm.embed_figure_in_frame(
                pm.create_daily_bar_chart(pd.DataFrame(db.fetch_all(query2, params), columns=['day', 'minutes']),
                                          time_range_str), self.chart_frame_tr)

            # NOTE: This still uses the old, less accurate query for broader ranges where precision is less critical.
            query3 = f"SELECT strftime('%H', s.start_time) as hour, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY hour ORDER BY hour"
            pm.embed_figure_in_frame(
                pm.create_hourly_bar_chart(pd.DataFrame(db.fetch_all(query3, params), columns=['hour', 'minutes']),
                                           time_range_str), self.chart_frame_bl)

            pm.embed_figure_in_frame(
                pm.create_category_pie_chart(db.get_time_by_category(where_clause, params), time_range_str),
                self.chart_frame_br)

    def _render_health_correlation_page(self, start_date, end_date, where_clause, params):
        # *** BUG FIX: Removed .reset_index() as it's now handled in the database manager ***
        df = db.get_health_and_study_data(start_date, end_date, where_clause, params)

        if not df.empty:
            for col in ['sleep_score', 'total_study_minutes', 'sleep_duration_seconds', 'body_battery', 'avg_stress']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['sleep_duration_hours'] = df['sleep_duration_seconds'] / 3600.0

        pm.embed_figure_in_frame(
            pm.create_correlation_scatter_plot(df, 'sleep_score', 'total_study_minutes', "Study vs. Sleep Score",
                                               "Sleep Score", "Study Minutes"), self.chart_frame_tl)
        pm.embed_figure_in_frame(pm.create_correlation_scatter_plot(df, 'sleep_duration_hours', 'total_study_minutes',
                                                                    "Study vs. Sleep Duration",
                                                                    "Sleep Duration (Hours)", "Study Minutes"),
                                 self.chart_frame_tr)
        pm.embed_figure_in_frame(
            pm.create_correlation_scatter_plot(df, 'avg_stress', 'total_study_minutes', "Study vs. Stress Level",
                                               "Average Stress Level", "Study Minutes"), self.chart_frame_bl)
        pm.embed_figure_in_frame(pm.create_trends_chart(df, self.view_mode.get()), self.chart_frame_br)

    def _render_numerical_stats_page(self, start_date, end_date, where_clause, params):
        stats_data = db.get_numerical_analytics(start_date, end_date, where_clause, params)
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl,
                      self.chart_frame_br]: frame.configure(fg_color=("#DBDBDB", "#2B2B2B"))

        ctk.CTkLabel(self.chart_frame_tl, text="Overall Stats", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(self.chart_frame_tl, text=f"Total Focus: {timedelta(seconds=int(stats_data['total_seconds']))}",
                     anchor="w").pack(anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_tl, text=f"Days Worked: {stats_data['num_days_worked']}", anchor="w").pack(
            anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_tl,
                     text=f"Daily Average: {timedelta(seconds=int(stats_data['daily_avg_seconds']))}", anchor="w").pack(
            anchor="w", padx=20)

        ctk.CTkLabel(self.chart_frame_tr, text="Category Breakdown", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        cat_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent")
        cat_frame.pack(fill="both", expand=True, padx=5)
        for category, seconds in sorted(stats_data['category_breakdown'].items(), key=lambda item: item[1],
                                        reverse=True):
            ctk.CTkLabel(cat_frame, text=f"{category}: {timedelta(seconds=int(seconds))}").pack(anchor="w", padx=10)

        ctk.CTkLabel(self.chart_frame_bl, text="Session Metrics", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(self.chart_frame_bl, text=f"Number of Sessions: {stats_data['num_sessions']}", anchor="w").pack(
            anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_bl,
                     text=f"Average Session: {timedelta(seconds=int(stats_data['avg_session_seconds']))}",
                     anchor="w").pack(anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_bl,
                     text=f"Longest Session: {timedelta(seconds=int(stats_data['longest_session_seconds']))}",
                     anchor="w").pack(anchor="w", padx=20)

        ctk.CTkLabel(self.chart_frame_br, text="Highlights", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=(10,
                                                                                                                  5))
        ctk.CTkLabel(self.chart_frame_br, text=f"Top Subject: {stats_data['top_tag']}", anchor="w").pack(anchor="w",
                                                                                                         padx=20)

        if stats_data['most_productive_day'] != "N/A":
            top_day_str = pd.to_datetime(stats_data['most_productive_day']).strftime('%B %d, %Y')
            ctk.CTkLabel(self.chart_frame_br, text=f"Most Productive Day: {top_day_str}", anchor="w",
                         wraplength=250).pack(anchor="w", padx=20)
            ctk.CTkLabel(self.chart_frame_br,
                         text=f"  - Focus Time: {timedelta(seconds=int(stats_data['most_productive_day_seconds']))}",
                         anchor="w").pack(anchor="w", padx=20)
        else:
            ctk.CTkLabel(self.chart_frame_br, text="Most Productive Day: N/A", anchor="w").pack(anchor="w", padx=20)

    def _render_modeling_page(self, start_date, end_date, where_clause, params):
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl,
                      self.chart_frame_br]: frame.configure(fg_color=("#DBDBDB", "#2B2B2B"))

        df = correlation_engine.prepare_daily_features(start_date, end_date, where_clause, params)
        model_type = self.model_type.get()

        if model_type == "Weekly":
            results = correlation_engine.run_weekly_efficiency_analysis(df)
        else:
            results = correlation_engine.run_analysis(start_date, end_date, data_method=self.analysis_method.get(),
                                                      model_type=model_type)

        if "error" in results:
            for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl,
                          self.chart_frame_br]: frame.grid_remove()
            error_label = ctk.CTkLabel(self.charts_frame, text=f"Analysis Error\n\n{results['error']}",
                                       font=ctk.CTkFont(size=16), justify="center", wraplength=500)
            error_label.grid(row=0, column=0, columnspan=2, rowspan=2, sticky="nsew")
            return

        display_map = {
            "Lasso": self._display_lasso_results, "PCA": self._display_pca_results,
            "Standard": self._display_standard_results, "Weekly Efficiency": self._display_weekly_results
        }
        display_func = display_map.get(results.get("model_type"))
        if display_func: display_func(results)

    def _display_standard_results(self, results):
        ctk.CTkLabel(self.chart_frame_tl, text="Significant Factors", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        sig_frame = ctk.CTkScrollableFrame(self.chart_frame_tl, fg_color="transparent");
        sig_frame.pack(fill="both", expand=True, padx=5)
        if not results["significant_factors"]: ctk.CTkLabel(sig_frame,
                                                            text="No statistically significant factors found.").pack(
            anchor="w", padx=10)
        for factor in results["significant_factors"]:
            color = "green" if factor["coefficient"] > 0 else "red"
            ctk.CTkLabel(sig_frame, text=f"• {factor['name']}", text_color=color, font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=10, pady=(5, 0))
            ctk.CTkLabel(sig_frame, text=factor['insight'], wraplength=220, justify="left").pack(anchor="w", padx=20,
                                                                                                 pady=(0, 5))

        ctk.CTkLabel(self.chart_frame_tr, text="Insignificant Factors", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        insig_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent");
        insig_frame.pack(fill="both", expand=True, padx=5)
        if not results["insignificant_factors"]: ctk.CTkLabel(insig_frame, text="All factors were significant.").pack(
            anchor="w", padx=10)
        for factor in results["insignificant_factors"]: ctk.CTkLabel(insig_frame, text=f"• {factor['name']}",
                                                                     text_color="gray").pack(anchor="w", padx=10)

        ctk.CTkLabel(self.chart_frame_bl, text="Model Details (Technical)",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        details_textbox = ctk.CTkTextbox(self.chart_frame_bl, wrap="none");
        details_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        details_textbox.insert("1.0", results["model_summary"]);
        details_textbox.configure(state="disabled")

        ctk.CTkLabel(self.chart_frame_br, text="How to Read This", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        explanation_frame = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent");
        explanation_frame.pack(fill="both", expand=True, padx=5)
        explanation = "This analysis uses a Multiple Linear Regression model.\n\nSignificant Factors (p < 0.05):\nThese have a clear, measurable effect.\n\nInsignificant Factors (p >= 0.05):\nNo reliable pattern could be found."
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(anchor="w",
                                                                                                            padx=10)

    def _display_lasso_results(self, results):
        ctk.CTkLabel(self.chart_frame_tl, text="Selected Factors", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        sig_frame = ctk.CTkScrollableFrame(self.chart_frame_tl, fg_color="transparent");
        sig_frame.pack(fill="both", expand=True, padx=5)
        if not results["selected_factors"]: ctk.CTkLabel(sig_frame, text="Lasso eliminated all factors.").pack(
            anchor="w", padx=10)
        for factor in results["selected_factors"]:
            color = "green" if factor["coefficient"] > 0 else "red"
            ctk.CTkLabel(sig_frame, text=f"• {factor['name']}", text_color=color, font=ctk.CTkFont(weight="bold")).pack(
                anchor="w", padx=10, pady=(5, 0))
            ctk.CTkLabel(sig_frame, text=factor['insight'], wraplength=220, justify="left").pack(anchor="w", padx=20,
                                                                                                 pady=(0, 5))

        ctk.CTkLabel(self.chart_frame_tr, text="Eliminated Factors", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        insig_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent");
        insig_frame.pack(fill="both", expand=True, padx=5)
        for factor in results["eliminated_factors"]: ctk.CTkLabel(insig_frame, text=f"• {factor['name']}",
                                                                  text_color="gray").pack(anchor="w", padx=10)

        ctk.CTkLabel(self.chart_frame_bl, text="Model Details", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(self.chart_frame_bl, text=f"Model: Lasso Regression (L1)", anchor="w").pack(anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_bl, text=f"Optimal Alpha (penalty): {results['alpha']:.4f}", anchor="w").pack(
            anchor="w", padx=20)

        ctk.CTkLabel(self.chart_frame_br, text="How to Read This", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        explanation_frame = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent");
        explanation_frame.pack(fill="both", expand=True, padx=5)
        explanation = "Lasso automatically selects the most important features.\n\nSelected Factors:\nThese have the strongest, most consistent impact on study time.\n\nEliminated Factors:\nTheir effect was too weak or redundant to be reliably measured."
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(anchor="w",
                                                                                                            padx=10)

    def _display_pca_results(self, results):
        ctk.CTkLabel(self.chart_frame_tl, text="Principal Component (PC) Significance",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        summary_box = ctk.CTkTextbox(self.chart_frame_tl, wrap="none");
        summary_box.pack(fill="both", expand=True, padx=10, pady=5)
        summary_box.insert("1.0", results["model_summary"]);
        summary_box.configure(state="disabled")

        ctk.CTkLabel(self.chart_frame_tr, text="Component Variance", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        var_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent");
        var_frame.pack(fill="both", expand=True, padx=5)
        total_variance = 0
        for i, variance in enumerate(results["explained_variance"]):
            total_variance += variance
            ctk.CTkLabel(var_frame, text=f"PC_{i + 1}: {variance:.2%} of variance", anchor="w").pack(anchor="w",
                                                                                                     padx=10)
        ctk.CTkLabel(var_frame, text=f"Total Explained: {total_variance:.2%}", anchor="w",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 0))

        ctk.CTkLabel(self.chart_frame_bl, text="Component Loadings", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        loadings_box = ctk.CTkTextbox(self.chart_frame_bl, wrap="none");
        loadings_box.pack(fill="both", expand=True, padx=10, pady=5)
        loadings_box.insert("1.0", results["component_loadings"]);
        loadings_box.configure(state="disabled")

        br_scroll_frame = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent");
        br_scroll_frame.pack(fill="both", expand=True, padx=5)
        ctk.CTkLabel(br_scroll_frame, text="Automated Analysis", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        analysis_text = results.get("automated_analysis", [])
        if not analysis_text:
            ctk.CTkLabel(br_scroll_frame,
                         text="No principal components had a statistically significant impact on study time.",
                         justify="left", wraplength=250).pack(anchor="w", padx=10, pady=(0, 15))
        else:
            for insight in analysis_text: ctk.CTkLabel(br_scroll_frame, text=insight, justify="left",
                                                       wraplength=250).pack(anchor="w", padx=10, pady=(0, 10))

        ctk.CTkLabel(br_scroll_frame, text="How to Read This", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(15, 5))
        explanation = "PCA combines your metrics into abstract 'Principal Components' that capture the most information.\n\nPC Significance:\nShows if these abstract components have a statistically significant effect on study time.\n\nComponent Loadings:\nShows which of your original factors (e.g., Sleep Score) are the main ingredients in each PC."
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(anchor="w",
                                                                                                            padx=10)

    def _display_weekly_results(self, results):
        ctk.CTkLabel(self.chart_frame_tl, text="Weekly Data Preview", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        preview_box = ctk.CTkTextbox(self.chart_frame_tl, wrap="none")
        preview_box.pack(fill="both", expand=True, padx=10, pady=5);
        preview_box.insert("1.0", results.get("weekly_data_preview", "No data."));
        preview_box.configure(state="disabled")

        ctk.CTkLabel(self.chart_frame_tr, text="Weekly Correlation Matrix",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        matrix_box = ctk.CTkTextbox(self.chart_frame_tr, wrap="none")
        matrix_box.pack(fill="both", expand=True, padx=10, pady=5);
        matrix_box.insert("1.0", results.get("correlation_matrix", "No data."));
        matrix_box.configure(state="disabled")

        ctk.CTkLabel(self.chart_frame_bl, text="Automated Insights", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        insights_frame = ctk.CTkScrollableFrame(self.chart_frame_bl, fg_color="transparent")
        insights_frame.pack(fill="both", expand=True, padx=5)
        for insight in results.get("insights", []): ctk.CTkLabel(insights_frame, text=insight, justify="left",
                                                                 wraplength=250).pack(anchor="w", padx=10, pady=(0, 10))

        ctk.CTkLabel(self.chart_frame_br, text="How to Read This", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        explanation_frame = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent")
        explanation_frame.pack(fill="both", expand=True, padx=5)
        explanation = "This analysis groups data by week to find broader trends in efficiency.\n\nCorrelation Matrix:\nShows the relationship between different weekly averages. Values range from -1 (perfect negative correlation) to +1 (perfect positive correlation). A value near 0 means no relationship.\n\nEfficiency Metrics:\n- study_per_sleep_hour: Measures how many minutes you studied for each hour you slept.\n- efficiency_score: An abstract score relating sleep quality to total study time."
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(anchor="w",
                                                                                                            padx=10)

    def export_data(self):
        start_date, end_date = self._get_date_range()
        folder = filedialog.askdirectory()
        if not folder: return
        try:
            if self.category_filter.get() == "School Work":
                where_clause = "WHERE date(s.start_time) BETWEEN ? AND ? AND t.category_name = 'School Work'"
                params = [start_date.isoformat(), end_date.isoformat()]
            else:
                where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
                params = [start_date.isoformat(), end_date.isoformat()]

            with db.db_connection() as conn:
                sessions_df = pd.read_sql_query(
                    f"SELECT s.*, t.category_name FROM sessions s JOIN tags t ON s.tag = t.name {where_clause}", conn,
                    params=params)
                health_df = pd.read_sql_query("SELECT * FROM health_metrics WHERE date BETWEEN ? AND ?", conn,
                                              params=[start_date.isoformat(), end_date.isoformat()])

            sessions_df.to_csv(
                os.path.join(folder, f"sessions_export_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"),
                index=False)
            health_df.to_csv(
                os.path.join(folder, f"health_data_export_{start_date.isoformat()}_to_{end_date.isoformat()}.csv"),
                index=False)
            messagebox.showinfo("Success", f"Data for the current view exported to {folder}")
        except Exception as e:
            messagebox.showerror("Export Error", f"An error occurred: {e}")

