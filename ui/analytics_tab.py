# file: ui/analytics_tab.py

import customtkinter as ctk
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta
import os

from core import database_manager as db
from core import plot_manager as pm
from core import correlation_engine
from core.plot_manager import BG_COLOR
import json
from collections import Counter
import threading


class AnalyticsTab(ctk.CTkFrame):
    def __init__(self, master, app_instance):
        super().__init__(master, fg_color="transparent")
        self.app = app_instance

        # --- State Variables ---
        self.page = 0
        # Increase to 5 pages: Overview, Health Correlation, Numerical Stats, Modeling, ActivityWatch
        self.max_pages = 5
        self.view_mode = ctk.StringVar(value="Week")
        self.end_date = date.today()
        self.analysis_method = ctk.StringVar(value="Strict")
        self.model_type = ctk.StringVar(value="Lasso")
        self.analysis_type = ctk.StringVar(value="Overview")  # New: selects special analyses
        self.event_feature = ctk.StringVar(value="sleep_score")
        self.event_kind = ctk.StringVar(value="drop")
        self.event_threshold = ctk.IntVar(value=10)
        self.event_window = ctk.IntVar(value=2)
        self.ccf_max_lag = ctk.IntVar(value=7)
        self.category_filter = ctk.StringVar(value="All Time")

        # --- UI Setup ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._create_widgets()
        # Rendering guards to avoid drawing before layout is ready
        self._first_update_done = False
        self._second_pass_scheduled = False

    def _create_widgets(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        header_frame.columnconfigure(3, weight=1)

        ctk.CTkLabel(header_frame, text="Study Analytics", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0,
                                                                                                          column=0,
                                                                                                          sticky="w")

        # Category Filter
        ctk.CTkLabel(header_frame, text="Filter by Category:").grid(row=0, column=1, padx=(20, 5), sticky="w")
        
        # Fetch categories from DB for robust filtering
        try:
            db_cats = [row[0] for row in db.get_categories()]
            # Ensure "School Work" is present if not in DB (legacy support) or just rely on DB
            if "School Work" not in db_cats and "School Work" in ["School Work"]: # Keep existing behavior if needed
                 pass 
            categories = ["All Time"] + db_cats
        except Exception:
            categories = ["All Time", "School Work"]

        self.category_combo = ctk.CTkComboBox(header_frame, values=categories,
                                              variable=self.category_filter,
                                              command=lambda v: self.update_charts(),
                                              width=150)
        self.category_combo.grid(row=0, column=2, sticky="w")

        ctk.CTkButton(header_frame, text="<", width=30, command=lambda: self._cycle_date_range(-1)).grid(row=0,
                                                                                                         column=4,
                                                                                                         padx=(20, 5))
        self.date_range_label = ctk.CTkLabel(header_frame, text="Date Range", font=ctk.CTkFont(size=14))
        self.date_range_label.grid(row=0, column=5, sticky="ew")  # Changed column
        
        # Confidence Label (below date range or next to it)
        self.confidence_label = ctk.CTkLabel(header_frame, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.confidence_label.grid(row=1, column=5, sticky="ew")

        ctk.CTkButton(header_frame, text=">", width=30, command=lambda: self._cycle_date_range(1)).grid(row=0, column=6,
                                                                                                        padx=(5, 20))
        ctk.CTkSegmentedButton(header_frame, values=["Day", "Week", "Month", "Year"], variable=self.view_mode,
                               command=self._on_view_mode_change).grid(row=0, column=7, padx=5)
        ctk.CTkButton(header_frame, text="Export Data", command=self.export_data).grid(row=0, column=8, padx=(20, 10))

        self.charts_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.charts_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.charts_frame.grid_columnconfigure((0, 1), weight=1)
        self.charts_frame.grid_rowconfigure((0, 1), weight=1)

        # Use plain tk.Frame for matplotlib containers to avoid CTk rounded-corner clipping
        self.chart_frame_tl = tk.Frame(self.charts_frame, bg=BG_COLOR)
        self.chart_frame_tl.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=(5, 2))
        self.chart_frame_tl.grid_columnconfigure(0, weight=1)
        self.chart_frame_tl.grid_rowconfigure(0, weight=1)

        self.chart_frame_tr = tk.Frame(self.charts_frame, bg=BG_COLOR)
        self.chart_frame_tr.grid(row=0, column=1, sticky="nsew", padx=(8, 5), pady=(5, 2))
        self.chart_frame_tr.grid_columnconfigure(0, weight=1)
        self.chart_frame_tr.grid_rowconfigure(0, weight=1)

        self.chart_frame_bl = tk.Frame(self.charts_frame, bg=BG_COLOR)
        self.chart_frame_bl.grid(row=1, column=0, sticky="nsew", padx=(5, 2), pady=(2, 5))
        self.chart_frame_bl.grid_columnconfigure(0, weight=1)
        self.chart_frame_bl.grid_rowconfigure(0, weight=1)

        self.chart_frame_br = tk.Frame(self.charts_frame, bg=BG_COLOR)
        self.chart_frame_br.grid(row=1, column=1, sticky="nsew", padx=(8, 5), pady=(2, 5))
        self.chart_frame_br.grid_columnconfigure(0, weight=1)
        self.chart_frame_br.grid_rowconfigure(0, weight=1)

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
        # Dropdowns for analysis organization
        model_menu = ctk.CTkOptionMenu(self.analysis_controls_frame, values=["Lasso", "PCA", "Standard", "Weekly", "PLS", "IRF", "HMM"],
                                       variable=self.model_type, command=lambda v: self.update_charts())
        model_menu.pack(side="left")
        ctk.CTkLabel(self.analysis_controls_frame, text="Data:").pack(side="left", padx=(15, 5))
        ctk.CTkSegmentedButton(self.analysis_controls_frame, values=["Strict", "Imputed"],
                               variable=self.analysis_method, command=lambda v: self.update_charts()).pack(side="left")
        ctk.CTkLabel(self.analysis_controls_frame, text="Exploratory:").pack(side="left", padx=(15, 5))
        analysis_menu = ctk.CTkOptionMenu(self.analysis_controls_frame, values=["Overview", "CCF", "Event Study", "Quantile"],
                                          variable=self.analysis_type, command=lambda v: self.update_charts())
        analysis_menu.pack(side="left")
        # Help button and note
        ctk.CTkButton(self.analysis_controls_frame, text="?", width=26, command=self._show_help_modal).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(self.analysis_controls_frame, text="Exploratory analyses are model-agnostic.", text_color="gray").pack(side="left", padx=(10, 0))
        # Hide by default; only show on page 4 (index 3)
        self.analysis_controls_frame.grid_remove()

        # --- Dynamic controls for Exploratory analyses ---
        self.exploratory_controls = ctk.CTkFrame(footer_frame, fg_color="transparent")
        self.exploratory_controls.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8,0))
        # Hide by default; only show on page 4 (index 3)
        self.exploratory_controls.grid_remove()

    def _safe_set_frame_bg(self, frame, color):
        """Safely set background on a frame whether it's a CTkFrame or a plain tk.Frame.
        Tries CTkFrame-specific option first, falls back to tk 'bg'."""
        try:
            # Prefer CTk-style option when available
            frame.configure(fg_color=color)
            return
        except Exception:
            pass
        try:
            frame.configure(bg=color)
        except Exception:
            # give up silently
            pass

    def _build_exploratory_controls(self):
        for w in self.exploratory_controls.winfo_children():
            w.destroy()
        atype = self.analysis_type.get()
        if atype == "Event Study":
            # Feature selector
            ctk.CTkLabel(self.exploratory_controls, text="Feature:").pack(side="left", padx=(0,5))
            ctk.CTkOptionMenu(self.exploratory_controls, values=[
                "sleep_score","avg_stress","sleep_duration_hours","body_battery",
                "resting_hr","respiration","intensity_minutes","hydration_ml"
            ], variable=self.event_feature, command=lambda v: self.update_charts()).pack(side="left")
            # Shock type
            ctk.CTkLabel(self.exploratory_controls, text="Shock:").pack(side="left", padx=(10,5))
            ctk.CTkOptionMenu(self.exploratory_controls, values=["drop","spike"],
                              variable=self.event_kind, command=lambda v: self.update_charts()).pack(side="left")
            # Threshold
            ctk.CTkLabel(self.exploratory_controls, text="Threshold:").pack(side="left", padx=(10,5))
            thr_entry = ctk.CTkEntry(self.exploratory_controls, textvariable=self.event_threshold, width=60)
            thr_entry.pack(side="left")
            thr_entry.bind("<Return>", lambda e: self.update_charts())
            thr_entry.bind("<FocusOut>", lambda e: self.update_charts())
            # Window
            ctk.CTkLabel(self.exploratory_controls, text="Window ±days:").pack(side="left", padx=(10,5))
            win_entry = ctk.CTkEntry(self.exploratory_controls, textvariable=self.event_window, width=60)
            win_entry.pack(side="left")
            win_entry.bind("<Return>", lambda e: self.update_charts())
            win_entry.bind("<FocusOut>", lambda e: self.update_charts())
        elif atype == "CCF":
            ctk.CTkLabel(self.exploratory_controls, text="Max Lag (days):").pack(side="left", padx=(0,5))
            lag_entry = ctk.CTkEntry(self.exploratory_controls, textvariable=self.ccf_max_lag, width=60)
            lag_entry.pack(side="left")
            lag_entry.bind("<Return>", lambda e: self.update_charts())
            lag_entry.bind("<FocusOut>", lambda e: self.update_charts())

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
        # Clear children of each chart container if the container still exists
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]:
            try:
                if getattr(frame, 'winfo_exists', lambda: False)() and frame.winfo_exists():
                    for widget in frame.winfo_children():
                        try:
                            widget.destroy()
                        except Exception:
                            pass
            except Exception:
                pass
        # Destroy any auxiliary widgets in charts_frame except the four chart containers
        protected = {self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br}
        for widget in list(self.charts_frame.winfo_children()):
            try:
                if widget not in protected:
                    widget.destroy()
            except Exception:
                pass

    def update_charts(self):
        # Delay the first update until the widget is properly sized
        if not self._first_update_done:
            self.update_idletasks()
            if self.charts_frame.winfo_width() > 150 and self.charts_frame.winfo_height() > 150:
                self._first_update_done = True
            else:
                self.after(120, self.update_charts)
                return

        # Ensure main layout
        try:
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
            self.grid_rowconfigure(2, weight=0)
        except Exception: pass
        
        self._clear_chart_frames()
        
        # Reset chart frames to default 2x2 grid
        self.chart_frame_tl.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=(5, 2), rowspan=1, columnspan=1)
        self.chart_frame_tr.grid(row=0, column=1, sticky="nsew", padx=(8, 5), pady=(5, 2), rowspan=1, columnspan=1)
        self.chart_frame_bl.grid(row=1, column=0, sticky="nsew", padx=(5, 2), pady=(2, 5), rowspan=1, columnspan=1)
        self.chart_frame_br.grid(row=1, column=1, sticky="nsew", padx=(8, 5), pady=(2, 5), rowspan=1, columnspan=1)

        self.charts_frame.grid_rowconfigure(0, weight=1)
        self.charts_frame.grid_rowconfigure(1, weight=1)
        self.charts_frame.update_idletasks()

        start_date, end_date = self._get_date_range()
        self._current_range = (start_date, end_date)
        
        # Update labels
        if start_date == end_date:
            self.date_range_label.configure(text=start_date.strftime('%B %d, %Y'))
        else:
            self.date_range_label.configure(text=f"{start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}")
        self.page_label.configure(text=f"Page {self.page + 1} / {self.max_pages}")

        # Controls
        if self.page == 3:
            self.analysis_controls_frame.grid()
            self._build_exploratory_controls()
            self.exploratory_controls.grid()
        else:
            self.analysis_controls_frame.grid_remove()
            self.exploratory_controls.grid_remove()

        # Build SQL Params
        selected_category = self.category_filter.get()
        if selected_category and selected_category != "All Time":
            where_clause = "WHERE date(s.start_time) BETWEEN ? AND ? AND t.category_name = ?"
            params = [start_date.isoformat(), end_date.isoformat(), selected_category]
        else:
            where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
            params = [start_date.isoformat(), end_date.isoformat()]

        # Unified Thread dispatch
        self._bg_compute_token = getattr(self, '_bg_compute_token', 0) + 1
        token = self._bg_compute_token
        self._show_loading(True)

        # Capture variables for thread
        page = self.page
        view_mode = self.view_mode.get()
        # Modeling params
        an_type = self.analysis_type.get()
        mod_type = self.model_type.get()
        evt_feat = self.event_feature.get()
        evt_kind = self.event_kind.get()
        evt_thresh = self.event_threshold.get()
        evt_win = self.event_window.get()
        ccf_lag = self.ccf_max_lag.get()
        an_method = self.analysis_method.get()
        
        def bg_worker():
            result = {'payload': None, 'kind': 'error', 'conf': None}
            try:
                # Compute confidence safely
                try: 
                     conf = correlation_engine.compute_data_confidence(start_date, end_date, where_clause, params)
                     result['conf'] = f"Data Confidence: {conf['percent']}%"
                except: pass

                if page == 0:
                    result['kind'] = 'overview'
                    result['payload'] = self._prepare_overview_page(start_date, end_date, where_clause, params, view_mode)
                elif page == 1:
                    result['kind'] = 'health'
                    result['payload'] = self._prepare_health_page(start_date, end_date, where_clause, params)
                elif page == 2:
                    result['kind'] = 'stats'
                    result['payload'] = db.get_numerical_analytics(start_date, end_date, where_clause, params)
                elif page == 3:
                    result['kind'] = 'modeling'
                    if an_type == 'CCF':
                        result['payload'] = correlation_engine.compute_ccf_heatmap_df(start_date, end_date, where_clause, params, lags=range(-ccf_lag, ccf_lag+1))
                        result['subkind'] = 'ccf'
                    elif an_type == 'Event Study':
                        result['payload'] = correlation_engine.compute_event_study_df(start_date, end_date, where_clause, params, feature=evt_feat, shock=evt_kind, threshold=evt_thresh, window=evt_win)
                        result['subkind'] = 'event'
                    elif an_type == 'Quantile':
                        result['payload'] = correlation_engine.run_quantile_regression(start_date, end_date, where_clause, params)
                        result['subkind'] = 'quantile'
                    elif mod_type == 'Weekly':
                        # Weekly requires special preparation and a different engine function
                        df = correlation_engine.prepare_daily_features(start_date, end_date, where_clause, params)
                        result['payload'] = correlation_engine.run_weekly_efficiency_analysis(df)
                        result['subkind'] = 'model'
                        result['model_type'] = 'Weekly'
                    else:
                        result['payload'] = correlation_engine.run_analysis(start_date, end_date, data_method=an_method, model_type=mod_type, where_clause=where_clause, params=params)
                        result['subkind'] = 'model'
                        result['model_type'] = mod_type
                elif page == 4:
                    result['kind'] = 'aw'
                    result['payload'] = self._prepare_aw_page(start_date, end_date, where_clause, params)
                    
            except Exception as e:
                result['error'] = str(e)
            return result

        def finish(result):
             if getattr(self, '_bg_compute_token', None) != token: return
             self._show_loading(False)
             if result.get('conf'): self.confidence_label.configure(text=result['conf'])
             else: self.confidence_label.configure(text="")

             if result.get('error'):
                 self._show_error(result['error'])
                 return
                 
             kind = result.get('kind')
             payload = result.get('payload')
             
             try:
                 if kind == 'overview': self._display_overview(payload)
                 elif kind == 'health': self._display_health(payload)
                 elif kind == 'stats': self._display_stats(payload)
                 elif kind == 'aw': self._display_aw(payload)
                 elif kind == 'modeling':
                     subkind = result.get('subkind')
                     if subkind == 'ccf':
                         if payload is None: self._show_error('Not enough data.')
                         else: 
                              pm.embed_figure_in_frame(pm.create_ccf_heatmap(payload), self.chart_frame_tl)
                              ctk.CTkLabel(self.chart_frame_tr, text='Cross-Correlation', font=ctk.CTkFont(size=16, weight='bold')).pack(anchor='w', padx=10, pady=10)
                     elif subkind == 'event':
                         if payload is None: self._show_error('No events found.')
                         else:
                              pm.embed_figure_in_frame(pm.create_event_study_plot(payload, title=f"Study Time around {evt_feat}"), self.chart_frame_tl)
                              ctk.CTkLabel(self.chart_frame_tr, text='Event Study', font=ctk.CTkFont(size=16, weight='bold')).pack(anchor='w', padx=10, pady=10)
                     elif subkind == 'quantile':
                         if isinstance(payload, dict) and 'error' in payload: self._show_error(payload['error'])
                         else:
                              pm.embed_figure_in_frame(pm.create_quantile_coeff_plot(payload.get('coeff_df')), self.chart_frame_tl)
                              ctk.CTkLabel(self.chart_frame_tr, text='Quantile Reg', font=ctk.CTkFont(size=16, weight='bold')).pack(anchor='w', padx=10, pady=10)
                     elif subkind == 'model':
                         if not payload or 'error' in payload: self._show_error(payload.get('error', 'Model error') if payload else 'No results')
                         else:
                             mtype = result.get('model_type')
                             display_map = {'Lasso': self._display_lasso_results, 'PCA': self._display_pca_results, 'Standard': self._display_standard_results, 'Weekly': self._display_weekly_results, 'PLS': self._display_pls_results, 'IRF': self._display_irf_results, 'HMM': self._display_hmm_results}
                             if mtype in display_map: display_map[mtype](payload)
             except Exception as e:
                 self._show_error(f"Render error: {e}")

        threading.Thread(target=lambda: self.after(0, lambda: finish(bg_worker())), daemon=True).start()

    def _retry_modeling(self, where_clause, params):
        # Simply re-trigger update if needed
        self.update_charts()

    # In ui/analytics_tab.py, find the _render_overview_page function and replace it with this updated version.

    def _prepare_overview_page(self, start_date, end_date, where_clause, params, time_range_str):
        if not isinstance(time_range_str, str) or "ctk" in str(time_range_str).lower():
            time_range_str = "Day"
            
        results = {'figs': {}, 'data': {}, 'time_range': time_range_str}
        
        if time_range_str == "Day":
            query1 = f"SELECT s.tag, SUM(s.duration_seconds), t.color FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY s.tag"
            results['figs']['tl'] = pm.create_pie_chart(db.fetch_all(query1, params), time_range_str)
            
            day_sessions_query = f"SELECT s.tag, s.start_time, s.end_time, s.duration_seconds FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} ORDER BY s.start_time"
            results['data']['sessions'] = db.fetch_all(day_sessions_query, params)
            
            hourly_df = db.get_hourly_breakdown_for_day(start_date.isoformat(), where_clause, params)
            results['figs']['bl'] = pm.create_hourly_bar_chart(hourly_df, time_range_str)
            results['figs']['br'] = pm.create_category_pie_chart(db.get_time_by_category(where_clause, params), time_range_str)
        else:
            query1 = f"SELECT s.tag, SUM(s.duration_seconds), t.color FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY s.tag"
            results['figs']['tl'] = pm.create_pie_chart(db.fetch_all(query1, params), time_range_str)

            query2 = f"SELECT strftime('%Y-%m-%d', s.start_time) as day, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY day ORDER BY day"
            results['figs']['tr'] = pm.create_daily_bar_chart(pd.DataFrame(db.fetch_all(query2, params), columns=['day', 'minutes']), time_range_str)

            query3 = f"SELECT strftime('%H', s.start_time) as hour, SUM(s.duration_seconds)/60.0 as minutes FROM sessions s JOIN tags t ON s.tag = t.name {where_clause} GROUP BY hour ORDER BY hour"
            results['figs']['bl'] = pm.create_hourly_bar_chart(pd.DataFrame(db.fetch_all(query3, params), columns=['hour', 'minutes']), time_range_str)
            
            results['figs']['br'] = pm.create_category_pie_chart(db.get_time_by_category(where_clause, params), time_range_str)
        return results

    def _display_overview(self, results):
        figs = results.get('figs', {})
        time_range = results.get('time_range', 'Day')
        
        pm.embed_figure_in_frame(figs.get('tl'), self.chart_frame_tl)
        pm.embed_figure_in_frame(figs.get('bl'), self.chart_frame_bl)
        pm.embed_figure_in_frame(figs.get('br'), self.chart_frame_br)
        
        if time_range == "Day":
            self._safe_set_frame_bg(self.chart_frame_tr, ("#DBDBDB", "#2B2B2B"))
            for w in self.chart_frame_tr.winfo_children(): w.destroy()
            ctk.CTkLabel(self.chart_frame_tr, text="Session Log", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
            log_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent")
            log_frame.pack(fill="both", expand=True, padx=5)
            
            sessions = results['data'].get('sessions', [])
            if not sessions:
                ctk.CTkLabel(log_frame, text="No sessions logged.").pack(anchor="w", padx=10)
            else:
                for tag, start, end, duration in sessions:
                    try:
                        start_dt = datetime.fromisoformat(start)
                        end_dt = datetime.fromisoformat(end)
                        duration_str = str(timedelta(seconds=int(duration)))
                        log_text = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')} ({duration_str}) - {tag}"
                        ctk.CTkLabel(log_frame, text=log_text).pack(anchor="w", padx=10)
                    except: pass
        else:
             pm.embed_figure_in_frame(figs.get('tr'), self.chart_frame_tr)

    def _prepare_health_page(self, start_date, end_date, where_clause, params):
        df = db.get_health_and_study_data(start_date, end_date, where_clause, params)
        if not df.empty:
            for col in ['sleep_score', 'total_study_minutes', 'sleep_duration_seconds', 'body_battery', 'avg_stress']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['sleep_duration_hours'] = df['sleep_duration_seconds'] / 3600.0
            
        figs = {}
        figs['tl'] = pm.create_correlation_scatter_plot(df, 'sleep_score', 'total_study_minutes', "Study vs. Sleep Score", "Sleep Score", "Study Minutes")
        figs['tr'] = pm.create_correlation_scatter_plot(df, 'sleep_duration_hours', 'total_study_minutes', "Study vs. Sleep Duration", "Sleep Duration (Hours)", "Study Minutes")
        figs['bl'] = pm.create_correlation_scatter_plot(df, 'avg_stress', 'total_study_minutes', "Study vs. Stress Level", "Average Stress Level", "Study Minutes")
        figs['br'] = pm.create_trends_chart(df, self.view_mode.get())
        return {'figs': figs}

    def _display_health(self, results):
        figs = results.get('figs', {})
        pm.embed_figure_in_frame(figs.get('tl'), self.chart_frame_tl)
        pm.embed_figure_in_frame(figs.get('tr'), self.chart_frame_tr)
        pm.embed_figure_in_frame(figs.get('bl'), self.chart_frame_bl)
        pm.embed_figure_in_frame(figs.get('br'), self.chart_frame_br)

    # Legacy wrapper removed (overwritten above)
    def _render_health_correlation_page_legacy_removed(self): pass

    def _display_stats(self, stats_data):
        # Safely set background on the four chart containers. Some of these
        # widgets may have been replaced or destroyed during prior updates
        # (CTk wrappers create internal tk widgets which can be torn down),
        # so guard each configure call.
        for frame in (self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br):
            try:
                if getattr(frame, 'winfo_exists', lambda: False)() and frame.winfo_exists():
                    try:
                        frame.configure(bg=BG_COLOR)
                    except Exception:
                        try:
                            frame.configure(fg_color=BG_COLOR)
                        except Exception:
                            pass
            except Exception:
                pass

        ctk.CTkLabel(self.chart_frame_tl, text="Overall Stats", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        ctk.CTkLabel(self.chart_frame_tl, text=f"Total Focus: {timedelta(seconds=int(stats_data['total_seconds']))}",
                     anchor="w").pack(anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_tl, text=f"Days Worked: {stats_data['num_days_worked']}", anchor="w").pack(
            anchor="w", padx=20)
        ctk.CTkLabel(self.chart_frame_tl,
                     text=f"Daily Average: {timedelta(seconds=int(stats_data['daily_avg_seconds']))}", anchor="w").pack(
            anchor="w", padx=20)

        ctk.CTkLabel(self.chart_frame_tr, text="Category & Tag Breakdown", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 5))
        cat_frame = ctk.CTkScrollableFrame(self.chart_frame_tr, fg_color="transparent")
        cat_frame.pack(fill="both", expand=True, padx=5)
        
        ctk.CTkLabel(cat_frame, text="Categories:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(0,2))
        for category, seconds in sorted(stats_data['category_breakdown'].items(), key=lambda item: item[1],
                                        reverse=True):
            ctk.CTkLabel(cat_frame, text=f"{category}: {timedelta(seconds=int(seconds))}").pack(anchor="w", padx=20)
            
        ctk.CTkLabel(cat_frame, text="\nTags:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,2))
        tag_bd = stats_data.get('tag_breakdown', {})
        for tag, seconds in sorted(tag_bd.items(), key=lambda item: item[1], reverse=True):
             ctk.CTkLabel(cat_frame, text=f"{tag}: {timedelta(seconds=int(seconds))}").pack(anchor="w", padx=20)

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

    def _prepare_aw_page(self, start_date, end_date, where_clause, params):
        df = db.get_health_and_study_data(start_date, end_date, where_clause, params)
        if not df.empty:
            for col in ['sleep_score', 'total_study_minutes', 'sleep_duration_seconds', 'body_battery', 'avg_stress']:
                df[col] = pd.to_numeric(df.get(col, pd.Series()), errors='coerce')
            df['sleep_duration_hours'] = df.get('sleep_duration_seconds', 0) / 3600.0

        aw_rows = db.get_aw_daily(start_date.isoformat(), end_date.isoformat())
        figs = {}
        aw_stats = None
        
        if aw_rows:
            aw_df = pd.DataFrame(aw_rows, columns=['date', 'active_seconds', 'app_summary'])
            aw_df['date'] = pd.to_datetime(aw_df['date'])
            aw_df['active_hours'] = aw_df['active_seconds'] / 3600.0

            merged = df.copy()
            if not merged.empty: merged['date'] = pd.to_datetime(merged['date'])
            merged = merged.merge(aw_df[['date', 'active_hours']], on='date', how='left')

            figs['tl'] = pm.create_correlation_scatter_plot(merged, 'active_hours', 'sleep_score', "AW Active Hours vs Sleep Score", "Active Hours (AW)", "Sleep Score")
            figs['tr'] = pm.create_correlation_scatter_plot(merged, 'active_hours', 'sleep_duration_hours', "AW Active Hours vs Sleep Duration", "Active Hours (AW)", "Sleep Duration (Hours)")
            figs['bl'] = pm.create_correlation_scatter_plot(merged, 'active_hours', 'avg_stress', "AW Active Hours vs Avg Stress", "Active Hours (AW)", "Avg Stress")
            
            # Aggregate stats for bottom right
            app_totals = Counter()
            for _, r in aw_df.iterrows():
                try:
                    app_map = json.loads(r['app_summary']) if r['app_summary'] else {}
                except Exception:
                    app_map = {}
                for app_name, secs in app_map.items():
                    try: app_totals[app_name] += float(secs)
                    except: pass
            
            aw_daily_df = aw_df[['date', 'active_hours']].sort_values('date')
            aw_stats = {'app_totals': app_totals, 'daily': aw_daily_df}
            
            # Prepare BR charts in BG
            # Note: BR contains multiple charts in a scroll frame. We can create figures here and embed them later,
            # but using pm.create...
            # The original code created them on the fly. We'll generate a list of figures.
            
            top_apps = app_totals.most_common(10)
            figs['br_top_apps'] = pm.create_aw_top_apps_bar(top_apps)
            figs['br_timeline'] = pm.create_aw_daily_bar_chart(aw_daily_df)
            
        return {'figs': figs, 'has_data': bool(aw_rows)}

    def _display_aw(self, results):
        if not results.get('has_data'):
             return # Original code didn't handle no data explicitly well, but we can just do nothing
             
        figs = results.get('figs', {})
        pm.embed_figure_in_frame(figs.get('tl'), self.chart_frame_tl)
        pm.embed_figure_in_frame(figs.get('tr'), self.chart_frame_tr)
        pm.embed_figure_in_frame(figs.get('bl'), self.chart_frame_bl)
        
        for w in self.chart_frame_br.winfo_children(): w.destroy()
        scroll = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=6)
        
        # We need a frame helper since scrollable frame doesn't support embedding directly easily or pm expects frame info
        # Actually pm.embed_figure_in_frame clears children. We want multiple charts.
        # So we manually create frames inside scroll
        
        f1 = tk.Frame(scroll, bg=BG_COLOR, height=250)
        f1.pack(fill="x", expand=False, pady=5)
        pm.embed_figure_in_frame(figs.get('br_top_apps'), f1)
        
        f2 = tk.Frame(scroll, bg=BG_COLOR, height=250)
        f2.pack(fill="x", expand=False, pady=5)
        pm.embed_figure_in_frame(figs.get('br_timeline'), f2)

    def _render_modeling_page(self, start_date, end_date, where_clause, params):
        # Robustly attempt to set background on the four chart containers. We've seen sporadic
        # Tk "invalid command name" errors when a prior update destroyed an internal tk.Label
        # belonging to a CustomTkinter widget; guard each call so a stale reference doesn't
        # abort the entire rendering path.
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]:
            try:
                # Some are plain tk.Frame (use 'bg'), some could be CTkFrame (use 'fg_color').
                try:
                    frame.configure(bg=BG_COLOR)
                except Exception:
                    try:
                        frame.configure(fg_color=BG_COLOR)
                    except Exception:
                        pass
            except Exception:
                pass
        # DEBUG: log widget classes to help diagnose blank page issues.
        try:
            debug_log_path = os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log')
            with open(debug_log_path, 'a', encoding='utf-8') as lf:
                for idx, frame in enumerate([self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]):
                    try:
                        lf.write(f"[MODEL_DEBUG] Frame {idx} class={getattr(frame, 'winfo_class', lambda: 'N/A')()} exists={getattr(frame, 'winfo_exists', lambda: False)()} children={len(frame.winfo_children())}\n")
                    except Exception:
                        lf.write(f"[MODEL_DEBUG] Frame {idx} inaccessible\n")
        except Exception:
            pass
        model_type = self.model_type.get()
        analysis_type = self.analysis_type.get()

        # Analysis-type specific rendering
        if analysis_type == "CCF":
            # Hide bottom row for single-row layouts and clear them
            for widget in self.chart_frame_bl.winfo_children(): widget.destroy()
            for widget in self.chart_frame_br.winfo_children(): widget.destroy()
            self.chart_frame_bl.grid_remove()
            self.chart_frame_br.grid_remove()
            
            # Run CCF
            ccf_df = correlation_engine.compute_ccf_heatmap_df(start_date, end_date, where_clause, params, lags=range(-self.ccf_max_lag.get(), self.ccf_max_lag.get()+1))
            if ccf_df is None:
                self._show_error("Not enough data for CCF analysis.")
                return
            
            # Display CCF
            # We'll use the top two frames merged or just top-left large
            # For simplicity, let's put the heatmap in TL and explanation in TR
            pm.embed_figure_in_frame(pm.create_ccf_heatmap(ccf_df), self.chart_frame_tl)
            
            ctk.CTkLabel(self.chart_frame_tr, text="Cross-Correlation Function (CCF)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=10)
            self._show_explanation(self.chart_frame_tr, 
                "Shows correlation between study time and health metrics at different day lags.\n\n"
                "• Lag 0: Same day correlation.\n"
                "• Lag -k: Health metric k days ago vs Study today.\n"
                "• Red: Positive correlation (High metric -> High study).\n"
                "• Blue: Negative correlation (High metric -> Low study).")
            return

        elif analysis_type == "Event Study":
            # Hide bottom row
            for widget in self.chart_frame_bl.winfo_children(): widget.destroy()
            for widget in self.chart_frame_br.winfo_children(): widget.destroy()
            self.chart_frame_bl.grid_remove()
            self.chart_frame_br.grid_remove()
            
            feature = self.event_feature.get()
            shock = self.event_kind.get()
            threshold = self.event_threshold.get()
            window = self.event_window.get()
            
            event_df = correlation_engine.compute_event_study_df(start_date, end_date, where_clause, params,
                                                                 feature=feature, shock=shock, 
                                                                 threshold=threshold, window=window)
            if event_df is None:
                self._show_error(f"No events found for {feature} ({shock} >= {threshold}) or insufficient data.")
                return
                
            pm.embed_figure_in_frame(pm.create_event_study_plot(event_df, title=f"Study Time around {feature} {shock}"), self.chart_frame_tl)
            
            ctk.CTkLabel(self.chart_frame_tr, text="Event Study Analysis", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=10)
            self._show_explanation(self.chart_frame_tr,
                f"Analyzes how study time changes before and after a significant '{shock}' in {feature}.\n\n"
                f"• Day 0: The day the {shock} occurred.\n"
                f"• Negative days: Days leading up to the event.\n"
                f"• Positive days: Days following the event.\n"
                "• Error bars show the standard error of the mean.")
            return

        elif analysis_type == "Quantile":
            # Hide bottom row
            for widget in self.chart_frame_bl.winfo_children(): widget.destroy()
            for widget in self.chart_frame_br.winfo_children(): widget.destroy()
            self.chart_frame_bl.grid_remove()
            self.chart_frame_br.grid_remove()
            
            results = correlation_engine.run_quantile_regression(start_date, end_date, where_clause, params)
            if "error" in results:
                self._show_error(results['error'])
                return
                
            pm.embed_figure_in_frame(pm.create_quantile_coeff_plot(results['coeff_df']), self.chart_frame_tl)
            
            ctk.CTkLabel(self.chart_frame_tr, text="Quantile Regression", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=10)
            self._show_explanation(self.chart_frame_tr,
                "Shows how the impact of health metrics changes for different levels of productivity (quantiles).\n\n"
                "• 0.25: Low productivity days.\n"
                "• 0.50: Median productivity days.\n"
                "• 0.75: High productivity days.\n"
                "If a line slopes up, that factor helps you more on your best days than your worst days.")
            return

        # Ensure bottom frames are visible (may have been hidden for single-row analyses)
        self.chart_frame_bl.grid()
        self.chart_frame_br.grid()

        # Model selection path (uses all 4 quadrants)
        if model_type == "Weekly":
            print("[DEBUG] Running Weekly Efficiency analysis")
            try:
                with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                    lf.write("[DEBUG] Running Weekly Efficiency analysis\n")
            except Exception:
                pass
            df = correlation_engine.prepare_daily_features(start_date, end_date, where_clause, params)
            results = correlation_engine.run_weekly_efficiency_analysis(df)
        elif model_type == "PLS":
            print("[DEBUG] Running PLS analysis")
            try:
                with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                    lf.write("[DEBUG] Running PLS analysis\n")
            except Exception:
                pass
            results = correlation_engine.run_pls_analysis_full(start_date, end_date, where_clause, params,
                                                               data_method=self.analysis_method.get())
        elif model_type == "IRF":
            print("[DEBUG] Running IRF analysis")
            try:
                with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                    lf.write("[DEBUG] Running IRF analysis\n")
            except Exception:
                pass
            results = correlation_engine.run_var_irf(start_date, end_date, where_clause, params)
        elif model_type == "HMM":
            print("[DEBUG] Running HMM analysis")
            try:
                with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                    lf.write("[DEBUG] Running HMM analysis\n")
            except Exception:
                pass
            results = correlation_engine.run_hmm_states(start_date, end_date, where_clause, params)
        else:
            print(f"[DEBUG] Running standard analysis type={model_type}")
            try:
                with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"[DEBUG] Running standard analysis type={model_type}\n")
            except Exception:
                pass
            results = correlation_engine.run_analysis(start_date, end_date, data_method=self.analysis_method.get(),
                                                      model_type=model_type)

        # DEBUG: inspect results
        try:
            if results is None:
                print("[DEBUG] correlation_engine returned None for results")
                try:
                    with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                        lf.write("[DEBUG] correlation_engine returned None for results\n")
                except Exception:
                    pass
            else:
                k = list(results.keys()) if isinstance(results, dict) else type(results)
                print(f"[DEBUG] results keys: {k}")
                try:
                    with open(os.path.join(os.path.dirname(__file__), '..', '.analytics_debug.log'), 'a', encoding='utf-8') as lf:
                        lf.write(f"[DEBUG] results keys: {k}\n")
                except Exception:
                    pass
        except Exception:
            pass

        if "error" in (results or {}):
            self._show_error(results['error'])
            return

        display_map = {
            "Lasso": self._display_lasso_results, "PCA": self._display_pca_results,
            "Standard": self._display_standard_results, "Weekly Efficiency": self._display_weekly_results,
            "PLS": self._display_pls_results, "IRF": self._display_irf_results, "HMM": self._display_hmm_results
        }
        display_func = display_map.get(results.get("model_type"))
        if display_func:
            display_func(results)
        else:
            self._show_error("Unknown result type")

    def _render_aw_page(self, start_date, end_date, where_clause, params):
        """Render ActivityWatch comparison charts.

        - Top-left: AW active hours vs sleep score
        - Top-right: AW active hours vs sleep duration (hours)
        - Bottom-left: AW active hours vs avg_stress
        - Bottom-right: Trends chart (study vs AW) if available
        """
        # Get base health and study df
        df = db.get_health_and_study_data(start_date, end_date, where_clause, params)

        # Ensure numeric types
        if not df.empty:
            for col in ['sleep_score', 'total_study_minutes', 'sleep_duration_seconds', 'body_battery', 'avg_stress']:
                df[col] = pd.to_numeric(df.get(col, pd.Series()), errors='coerce')
            df['sleep_duration_hours'] = df.get('sleep_duration_seconds', 0) / 3600.0

        # Get AW daily data
        try:
            aw_rows = db.get_aw_daily(start_date.isoformat(), end_date.isoformat())
            if aw_rows:
                aw_df = pd.DataFrame(aw_rows, columns=['date', 'active_seconds', 'app_summary'])
                aw_df['date'] = pd.to_datetime(aw_df['date'])
                aw_df['active_hours'] = aw_df['active_seconds'] / 3600.0

                # Merge on date
                merged = df.copy()
                if not merged.empty:
                    merged['date'] = pd.to_datetime(merged['date'])
                merged = merged.merge(aw_df[['date', 'active_hours']], on='date', how='left')

                pm.embed_figure_in_frame(
                    pm.create_correlation_scatter_plot(merged, 'active_hours', 'sleep_score',
                                                       "AW Active Hours vs Sleep Score",
                                                       "Active Hours (AW)", "Sleep Score"),
                    self.chart_frame_tl)

                pm.embed_figure_in_frame(
                    pm.create_correlation_scatter_plot(merged, 'active_hours', 'sleep_duration_hours',
                                                       "AW Active Hours vs Sleep Duration",
                                                       "Active Hours (AW)", "Sleep Duration (Hours)"),
                    self.chart_frame_tr)

                pm.embed_figure_in_frame(
                    pm.create_correlation_scatter_plot(merged, 'active_hours', 'avg_stress',
                                                       "AW Active Hours vs Avg Stress",
                                                       "Active Hours (AW)", "Avg Stress"),
                    self.chart_frame_bl)

                # Bottom-right: vertically scrollable area with multiple AW charts
                for w in self.chart_frame_br.winfo_children():
                    w.destroy()
                scroll = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent")
                scroll.pack(fill="both", expand=True, padx=6, pady=6)

                # Aggregate apps across the selected range
                app_totals = Counter()
                for _, r in aw_df.iterrows():
                    try:
                        app_map = json.loads(r['app_summary']) if r['app_summary'] else {}
                    except Exception:
                        app_map = {}
                    for app_name, secs in app_map.items():
                        try:
                            app_totals[app_name] += float(secs)
                        except Exception:
                            pass

                # Build a DataFrame for daily AW totals for timeline
                aw_daily_df = aw_df[['date', 'active_hours']].sort_values('date')

                # Top Applications chart
                top_apps = app_totals.most_common(10)
                apps_frame = ctk.CTkFrame(scroll, fg_color=BG_COLOR)
                apps_frame.pack(fill="both", expand=True, padx=6, pady=(6, 4))
                if top_apps:
                    pm.embed_figure_in_frame(pm.create_aw_top_apps_bar(top_apps, title="Top Applications"), apps_frame)
                else:
                    ctk.CTkLabel(apps_frame, text="No per-app data available.").pack(anchor="w", padx=12, pady=8)

                # Top Window Titles (fallback to same as apps if window-level not available)
                top_windows = top_apps
                win_frame = ctk.CTkFrame(scroll, fg_color=BG_COLOR)
                win_frame.pack(fill="both", expand=True, padx=6, pady=(4, 4))
                if top_windows:
                    pm.embed_figure_in_frame(pm.create_aw_top_windows_bar(top_windows, title="Top Window Titles"), win_frame)

                # AW Daily timeline (active hours per day)
                timeline_frame = ctk.CTkFrame(scroll, fg_color=BG_COLOR)
                timeline_frame.pack(fill="both", expand=True, padx=6, pady=(4, 4))
                pm.embed_figure_in_frame(pm.create_aw_daily_bar_chart(aw_daily_df, title="AW Active Hours by Day"), timeline_frame)

                # Category sunburst / donut (use inferred tags as categories)
                tags = [t[0] for t in db.get_tags()]
                tag_totals = Counter()
                tag_map = [(t, t.split('>')[-1].strip().lower()) for t in tags]
                for app, secs in app_totals.items():
                    app_l = app.lower()
                    for full, short in tag_map:
                        if short and short in app_l:
                            tag_totals[full] += secs

                cat_items = tag_totals.most_common(12)
                cat_frame = ctk.CTkFrame(scroll, fg_color=BG_COLOR)
                cat_frame.pack(fill="both", expand=True, padx=6, pady=(4, 6))
                if cat_items:
                    pm.embed_figure_in_frame(pm.create_aw_category_sunburst(cat_items, title="Top Categories (inferred)"), cat_frame)
                else:
                    ctk.CTkLabel(cat_frame, text="No inferred categories to display.", text_color="gray").pack(anchor="w", padx=12, pady=8)

                # Small legend / hint
                ctk.CTkLabel(scroll, text="\nTip: Import AW categories (Tags) via the ActivityWatch tab to improve category mapping.", text_color="gray").pack(anchor="w", pady=(8,4), padx=8)
                return
        except Exception:
            # If anything fails, fall through to fallback
            pass

        # No AW data available for the selected range: show a friendly message
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]:
            for widget in frame.winfo_children():
                widget.destroy()
        ctk.CTkLabel(self.chart_frame_tl, text="No ActivityWatch data available for this date range.", font=ctk.CTkFont(size=14)).pack(anchor="center", pady=20)
        ctk.CTkLabel(self.chart_frame_tr, text="Use the ActivityWatch tab to import data or adjust the date range.", text_color="gray").pack(anchor="center", pady=10)
        return

        

    def _show_error(self, msg):
        for frame in [self.chart_frame_tl, self.chart_frame_tr, self.chart_frame_bl, self.chart_frame_br]:
            frame.grid_remove()
        error_label = ctk.CTkLabel(self.charts_frame, text=f"Analysis Error\n\n{msg}",
                                   font=ctk.CTkFont(size=16), justify="center", wraplength=500)
        error_label.grid(row=0, column=0, columnspan=2, rowspan=2, sticky="nsew")

    def _show_loading(self, show=True):
        """Show or hide a lightweight loading overlay in the charts area.

        This is safe to call from the main thread only; callers from background
        threads should schedule via `after(0, ...)`.
        """
        try:
            if show:
                # If already present, don't recreate
                if getattr(self, '_loading_overlay', None) and getattr(self._loading_overlay, 'winfo_exists', lambda: False)():
                    return
                lbl = ctk.CTkLabel(self.charts_frame, text="Computing…", font=ctk.CTkFont(size=14), text_color="#888888")
                lbl.grid(row=0, column=0, columnspan=2, rowspan=2, sticky="nsew")
                self._loading_overlay = lbl
            else:
                if getattr(self, '_loading_overlay', None):
                    try:
                        self._loading_overlay.destroy()
                    except Exception:
                        pass
                    self._loading_overlay = None
        except Exception:
            # Never raise UI errors from this helper
            pass

    def _display_pls_results(self, results):
        # Top-left: Coefficients
        ctk.CTkLabel(self.chart_frame_tl, text="PLS Coefficients", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,5))
        txt = ctk.CTkTextbox(self.chart_frame_tl, wrap="none"); txt.pack(fill="both", expand=True, padx=10, pady=5)
        coef_series = results.get('coefficients', pd.Series(dtype=float))
        if isinstance(coef_series, pd.Series) and not coef_series.empty:
            txt.insert("1.0", coef_series.to_string())
        else:
            txt.insert("1.0", "No coefficient data available.")
        txt.configure(state="disabled")
        
        # Top-right: VIP Scores
        ctk.CTkLabel(self.chart_frame_tr, text="PLS VIP Scores", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,5))
        txt2 = ctk.CTkTextbox(self.chart_frame_tr, wrap="none"); txt2.pack(fill="both", expand=True, padx=10, pady=5)
        vip_series = results.get('vip', pd.Series(dtype=float))
        if isinstance(vip_series, pd.Series) and not vip_series.empty:
            txt2.insert("1.0", vip_series.to_string())
        else:
            txt2.insert("1.0", "No VIP data available.")
        txt2.configure(state="disabled")
        
        # Bottom-right: Data Diagnostics
        ctk.CTkLabel(self.chart_frame_br, text="Data Diagnostics", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,5))
        diag_frame = ctk.CTkScrollableFrame(self.chart_frame_br, fg_color="transparent")
        diag_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Show diagnostic info
        n_comp = results.get('n_components', 'N/A')
        ctk.CTkLabel(diag_frame, text=f"Components used: {n_comp}", anchor="w").pack(anchor="w", padx=10, pady=2)
        
        if 'diagnostics' in results:
            diag = results['diagnostics']
            ctk.CTkLabel(diag_frame, text=f"Total rows after preprocessing: {diag.get('n_rows', 'N/A')}", anchor="w").pack(anchor="w", padx=10, pady=2)
            ctk.CTkLabel(diag_frame, text=f"Features available: {diag.get('n_features', 'N/A')}", anchor="w").pack(anchor="w", padx=10, pady=2)
            if 'feature_list' in diag:
                ctk.CTkLabel(diag_frame, text=f"Features used:", anchor="w", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(5,2))
                for feat in diag['feature_list']:
                    ctk.CTkLabel(diag_frame, text=f"  • {feat}", anchor="w", text_color="gray").pack(anchor="w", padx=20, pady=1)
        
        # Bottom-left: Explanation
        self._show_explanation(self.chart_frame_bl, "PLS (Partial Least Squares): Supervised dimensionality reduction—components are chosen to best predict study time. Coefficients show the direction/strength; VIP scores rank overall importance.")

    def _display_irf_results(self, results):
        # Special layout for IRF: Plot takes full left column (row 0+1) to avoid squishing
        self.chart_frame_tl.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(5, 2), pady=5)
        self.chart_frame_bl.grid_remove() # Hidden, as TL takes its place
        
        # Right column remains split
        self.chart_frame_tr.grid(row=0, column=1, sticky="nsew", padx=(8, 5), pady=(5, 2))
        self.chart_frame_br.grid(row=1, column=1, sticky="nsew", padx=(8, 5), pady=(2, 5))

        # Give row 0 (plot top) more weight, row 1 (explanation) less
        self.charts_frame.grid_rowconfigure(0, weight=1)
        self.charts_frame.grid_rowconfigure(1, weight=0)

        fig = pm.create_irf_plot(results.get('irf'))
        pm.embed_figure_in_frame(fig, self.chart_frame_tl)
        
        ctk.CTkLabel(self.chart_frame_tr, text=f"VAR Lag Order: {results.get('lag_order')}").pack(anchor="w", padx=10, pady=10)
        
        # Use BR for explanation since BL is covered by TL
        self._show_explanation(self.chart_frame_br, "IRF (Impulse Response): Shows how a one-time change in a health metric is followed by changes in study minutes over the next days. Shaded bands indicate uncertainty when available.")

    def _display_hmm_results(self, results):
        # Give more space to the textboxes (row 0)
        self.charts_frame.grid_rowconfigure(0, weight=3)
        self.charts_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.chart_frame_tl, text="HMM State Means", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,5))
        txt = ctk.CTkTextbox(self.chart_frame_tl, wrap="none"); txt.pack(fill="both", expand=True, padx=10, pady=5)
        txt.insert("1.0", results.get('state_means', '')); txt.configure(state="disabled")
        
        ctk.CTkLabel(self.chart_frame_tr, text="HMM State Counts").pack(anchor="w", padx=10, pady=10)
        txt2 = ctk.CTkTextbox(self.chart_frame_tr, wrap="none"); txt2.pack(fill="both", expand=True, padx=10, pady=5)
        txt2.insert("1.0", str(results.get('state_counts', {}))); txt2.configure(state="disabled")
        
        self._show_explanation(self.chart_frame_bl, "HMM (Hidden Markov Model): Groups days into latent states (e.g., high/neutral/low productivity) based on patterns in study and health; shows typical values and how often each state occurs.")

    def _show_explanation(self, frame, text):
        # Place a wrapped label with gray text below the main chart/text
        lbl = ctk.CTkLabel(frame, text=text, wraplength=300, justify="left", text_color="gray")
        lbl.pack(anchor="w", padx=10, pady=10)
        # Append data confidence if we have current range context
        try:
            if hasattr(self, '_current_range'):
                start_date, end_date = self._current_range
                # Reuse last where clause/params from latest update; recompute for safety
                if self.category_filter.get() == "School Work":
                    where_clause = "WHERE date(s.start_time) BETWEEN ? AND ? AND t.category_name = 'School Work'"
                else:
                    where_clause = "WHERE date(s.start_time) BETWEEN ? AND ?"
                params = [start_date.isoformat(), end_date.isoformat()]
                conf = correlation_engine.compute_data_confidence(start_date, end_date, where_clause, params)
                conf_text = f"Data Confidence: {conf['percent']}%\n{conf['rationale']}"
                ctk.CTkLabel(frame, text=conf_text, wraplength=300, justify="left", text_color="#999999").pack(anchor="w", padx=10, pady=(0,10))
        except Exception:
            pass

    def _show_help_modal(self):
        help_text = (
            "Exploratory (model-agnostic):\n"
            "• CCF: Correlation between each health metric and study minutes across day lags.\n"
            "• Event Study: Average study around sudden changes in a health metric.\n"
            "• Quantile Regression: Effects at different percentiles of study time.\n\n"
            "Models:\n"
            "• Standard: Ordinary Least Squares regression.\n"
            "• Lasso: Feature selection via L1 regularization.\n"
            "• PCA: Unsupervised components (variance in features).\n"
            "• PLS: Supervised components that best predict study time.\n"
            "• Weekly: Aggregates to weeks before modeling.\n"
            "• IRF: Dynamic responses from a VAR model (needs more data).\n"
            "• HMM: Latent productivity states (requires hmmlearn).\n\n"
            "Notes:\n"
            "• Exploratory analyses do not depend on the selected model.\n"
            "• Pre-first-session days are excluded from plots (treated as inaccessible)."
        )
        messagebox.showinfo("Analytics Help", help_text)

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
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(
            anchor="w", padx=10)

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
        ctk.CTkLabel(explanation_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(
            anchor="w", padx=10)

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
        ctk.CTkLabel(br_scroll_frame, text=explanation, justify="left", wraplength=250, anchor="nw").pack(
            anchor="w", padx=10)

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

