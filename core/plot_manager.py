# file: plot_manager.py

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import os
import warnings
from matplotlib import rcParams

# --- Constants for Chart Styling ---
BG_COLOR = '#2B2B2B'
FACE_COLOR = '#333333'
TEXT_COLOR = 'white'
SKY_BLUE = 'skyblue'
SEA_GREEN = 'mediumseagreen'
GOLD = '#FFD700'


def _setup_base_chart(title, xlabel=None, ylabel=None):
    """Creates and styles a base Matplotlib figure and axis to avoid repeating code."""
    # Use constrained_layout instead of tight_layout for better automatic spacing
    fig, ax = plt.subplots(figsize=(6, 4), facecolor=BG_COLOR, 
                          constrained_layout=True)
    ax.set_title(title, color=TEXT_COLOR)
    if xlabel: ax.set_xlabel(xlabel, color=TEXT_COLOR)
    if ylabel: ax.set_ylabel(ylabel, color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelcolor=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(TEXT_COLOR)
    ax.set_facecolor(FACE_COLOR)
    return fig, ax


def embed_figure_in_frame(fig, frame):
    """Clears a frame and embeds a Matplotlib figure in it, resizing with the frame."""
    for widget in frame.winfo_children():
        widget.destroy()
    if not fig:
        return

    debug = os.environ.get("ST_DEBUG_LAYOUT") == "1"
    # Try to set the figure DPI to match the screen for accurate pixel sizing
    try:
        screen_dpi = frame.winfo_fpixels('1i')
        fig.set_dpi(screen_dpi)
    except Exception:
        screen_dpi = fig.get_dpi() or 100

    canvas = FigureCanvasTkAgg(fig, master=frame)
    widget = canvas.get_tk_widget()
    # Widget visual tweaks
    try:
        widget.configure(background=BG_COLOR)
    except Exception:
        try:
            widget.configure(bg=BG_COLOR)
        except Exception:
            pass
    for opt in ("highlightthickness", "borderwidth", "bd", "highlightbackground"):
        try:
            if opt == "highlightbackground":
                widget.configure(**{opt: BG_COLOR})
            else:
                widget.configure(**{opt: 0})
        except Exception:
            pass

    # Place the canvas slightly inset inside the frame to avoid CTk frame masking
    # Use absolute placement so we control the exact pixel inset the canvas occupies.
    try:
        fw, fh = frame.winfo_width(), frame.winfo_height()
        widget.place(x=3, y=3, width=max(fw - 6, 50), height=max(fh - 6, 50))
    except Exception:
        # Fallback to pack if place is not available for some reason
        widget.pack(fill="both", expand=True, padx=3, pady=3)

    # Keep references to avoid premature GC (and invalid Tcl command names)
    try:
        widget._figure_canvas = canvas
        widget._mpl_fig = fig
        canvas._mpl_fig = fig
    except Exception:
        pass

    def _on_resize(event, canvas=canvas, fig=fig, frame=frame, widget=widget):
        try:
            # Use the containing frame's inner size as the authoritative target
            try:
                frame.update_idletasks()
            except Exception:
                pass
            widget_w = max(frame.winfo_width() - 6, 50)
            widget_h = max(frame.winfo_height() - 6, 50)
            dpi = fig.get_dpi() or 100
            # Resize the placed widget to exactly fit the available inner region
            try:
                widget.place_configure(width=widget_w, height=widget_h)
            except Exception:
                try:
                    widget.config(width=widget_w, height=widget_h)
                except Exception:
                    pass

            # Progressive fit: set figure size, draw, then check bounding box vs widget size.
            # If the figure is larger than the widget (due to rounding/constrained_layout),
            # shrink it slightly and retry a few times.
            max_iters = 6
            target_w_px = widget_w
            target_h_px = widget_h
            for _ in range(max_iters):
                fig.set_size_inches(target_w_px / dpi, target_h_px / dpi, forward=True)
                try:
                    # Ensure constrained_layout recalculates
                    if hasattr(fig, 'set_constrained_layout'):
                        fig.set_constrained_layout(True)
                except Exception:
                    pass
                try:
                    canvas.draw()
                except Exception:
                    try:
                        canvas.draw_idle()
                    except Exception:
                        pass

                # Get rendered figure bbox in pixels
                fig_bbox = fig.bbox
                fig_w_px = fig_bbox.width
                fig_h_px = fig_bbox.height

                # If the rendered fig is larger than widget, reduce target and retry
                over_w = fig_w_px - widget_w
                over_h = fig_h_px - widget_h
                if over_w <= 1 and over_h <= 1:
                    break
                # subtract the larger of the two overflows plus small margin
                reduce_w = max(int(np.ceil(over_w)) + 2, 0)
                reduce_h = max(int(np.ceil(over_h)) + 2, 0)
                if reduce_w == 0 and reduce_h == 0:
                    break
                target_w_px = max(target_w_px - reduce_w, 50)
                target_h_px = max(target_h_px - reduce_h, 50)

            if debug:
                print(f"[plot_manager] on_resize: widget size={event.width}x{event.height}, target fig px={target_w_px}x{target_h_px}, rendered fig px={fig_w_px}x{fig_h_px}, dpi={dpi}")
        except Exception:
            pass

    # Bind resize and trigger initial draw
    try:
        # Bind to the containing frame's resize so we can place the canvas exactly
        frame._on_resize_cb = _on_resize
        frame.bind("<Configure>", _on_resize)
    except Exception:
        try:
            frame.bind("<Configure>", _on_resize)
        except Exception:
            pass

    try:
        canvas.draw_idle()
    except Exception:
        try:
            warnings.filterwarnings("ignore", message="constrained_layout not applied")
            canvas.draw_idle()
        except Exception:
            pass

    # Keep the pyplot handle closed but ensure canvas retains the figure
    try:
        plt.close(fig)
    except Exception:
        pass


def create_pie_chart(data, time_range):
    """Creates a pie chart of time by subject."""
    if not data: return None
    labels, sizes, colors = zip(*data)
    fig, ax = _setup_base_chart(f"Time by Subject ({time_range})")
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90, textprops={'color': TEXT_COLOR})
    ax.axis('equal')
    try:
        ax.set_box_aspect(1)
    except Exception:
        pass
    return fig

def create_category_pie_chart(data, time_range):
    """Creates a pie chart of time by category."""
    if not data: return None
    labels, sizes = zip(*data)
    fig, ax = _setup_base_chart(f"Time by Category ({time_range})")
    # Generate colors for the categories
    colors = plt.cm.get_cmap('viridis', len(labels)).colors
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90, textprops={'color': TEXT_COLOR})
    ax.axis('equal')
    try:
        ax.set_box_aspect(1)
    except Exception:
        pass
    return fig

def create_daily_bar_chart(df, time_range):
    """Creates a bar chart of minutes studied per day."""
    if df.empty: return None
    fig, ax = _setup_base_chart(f"Minutes Studied Per Day ({time_range})", ylabel="Total Minutes")
    ax.bar(df['day'], df['minutes'])
    ax.tick_params(axis='x', labelrotation=90)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_hourly_bar_chart(df, time_range):
    if df.empty: return None
    fig, ax = _setup_base_chart(f"Productivity by Hour ({time_range})", ylabel="Total Minutes")
    ax.bar(df['hour'], df['minutes'], color=SKY_BLUE)
    ax.tick_params(axis='x', labelrotation=45)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_weekly_bar_chart(df, time_range):
    if df.empty: return None
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    fig, ax = _setup_base_chart(f"Productivity by Day of Week ({time_range})", ylabel="Total Minutes")
    ax.bar(day_names, df['minutes'], color=SEA_GREEN)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_correlation_scatter_plot(df, x_col, y_col, title, xlabel, ylabel):
    # If data is missing, create a chart with a text message instead of returning None
    if df.empty or x_col not in df.columns or y_col not in df.columns or df[x_col].isnull().all() or df[y_col].isnull().all():
        fig, ax = _setup_base_chart(title)
        ax.text(0.5, 0.5, "Not enough data to display plot",
                horizontalalignment='center', verticalalignment='center',
                transform=ax.transAxes, color=TEXT_COLOR)
        return fig
    # Drop any rows where either axis is NaN (e.g., pre-first-session days left as NaN)
    plot_df = df[[x_col, y_col]].dropna()

    if plot_df.empty:
        fig, ax = _setup_base_chart(title)
        ax.text(0.5, 0.5, "Not enough overlapping data to plot",
                horizontalalignment='center', verticalalignment='center',
                transform=ax.transAxes, color=TEXT_COLOR)
        return fig

    fig, ax = _setup_base_chart(title, xlabel=xlabel, ylabel=ylabel)
    # Plot using the cleaned and aligned data
    ax.scatter(plot_df[x_col], plot_df[y_col])
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_trends_chart(df, time_range):
    if df.empty: return None
    df_trends = df.sort_values('date')

    # Scale sleep duration for better visibility on the chart
    df_trends['sleep_duration_hours_scaled'] = df_trends['sleep_duration_hours'].fillna(0) * 10

    fig, ax = _setup_base_chart(f"Trends: Sleep & Study ({time_range})")
    ax_twin = ax.twinx()
    try:
        ax.set_box_aspect('auto')
        ax_twin.set_box_aspect('auto')
    except Exception:
        pass

    # Plot Study Minutes on the left Y-axis
    ax.plot(df_trends['date'], df_trends['total_study_minutes'], color=SKY_BLUE, label='Study Minutes')
    ax.set_ylabel('Study Minutes', color=SKY_BLUE)
    ax.tick_params(axis='y', colors=SKY_BLUE)

    # Plot Sleep Score and Sleep Duration on the right Y-axis
    ax_twin.plot(df_trends['date'], df_trends['sleep_score'], color=SEA_GREEN, label='Sleep Score')
    ax_twin.plot(df_trends['date'], df_trends['sleep_duration_hours_scaled'], color=GOLD, linestyle='--',
                 label='Sleep Hours x10')
    ax_twin.set_ylabel('Sleep Score / Hours x10', color=SEA_GREEN)
    ax_twin.tick_params(axis='y', colors=SEA_GREEN)

    ax.tick_params(axis='x', labelrotation=90)

    # Combine legends from both axes
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax_twin.get_legend_handles_labels()
    if lines or lines2:
        ax_twin.legend(lines + lines2, labels + labels2, loc='upper left')

    return fig


# --- New plotting helpers for advanced analytics ---

def create_ccf_heatmap(ccf_df, title="Lagged Correlations (CCF)"):
    """Render a heatmap for cross-correlation function values.
    ccf_df: DataFrame indexed by variable with columns as integer lags (e.g., -7..+7).
    """
    if ccf_df is None or ccf_df.empty:
        return None
    fig, ax = _setup_base_chart(title, xlabel="Lag (days)", ylabel="Feature")
    im = ax.imshow(ccf_df.values, aspect='auto', cmap='coolwarm', vmin=-1, vmax=1)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    ax.set_yticks(range(len(ccf_df.index)))
    ax.set_yticklabels(ccf_df.index, color=TEXT_COLOR)
    ax.set_xticks(range(len(ccf_df.columns)))
    ax.set_xticklabels([str(c) for c in ccf_df.columns], rotation=0, color=TEXT_COLOR)
    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.yaxis.set_tick_params(color=TEXT_COLOR)
    plt.setp(cbar.ax.get_yticklabels(), color=TEXT_COLOR)
    return fig


def create_event_study_plot(event_df, title="Event Study: Study Minutes Around Events"):
    """Plot mean study minutes by relative day offset with error bars if present.
    event_df columns: ['day_offset', 'mean', 'se'] (se optional).
    """
    if event_df is None or event_df.empty:
        return None
    fig, ax = _setup_base_chart(title, xlabel="Days relative to event", ylabel="Study Minutes")
    x = event_df['day_offset']
    y = event_df['mean']
    if 'se' in event_df.columns:
        ax.errorbar(x, y, yerr=event_df['se'], fmt='-o', color=SKY_BLUE)
    else:
        ax.plot(x, y, '-o', color=SKY_BLUE)
    ax.axvline(0, color='white', linestyle='--', alpha=0.5)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_quantile_coeff_plot(coeff_df, title="Quantile Regression Coefficients"):
    """Line plot of coefficients across quantiles for selected features.
    coeff_df: index=quantiles, columns=features.
    """
    if coeff_df is None or coeff_df.empty:
        return None
    fig, ax = _setup_base_chart(title, xlabel="Quantile", ylabel="Coefficient")
    for col in coeff_df.columns:
        ax.plot(coeff_df.index, coeff_df[col], marker='o', label=col)
    ax.legend(loc='best')
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_irf_plot(irf_df, title_prefix="Impulse Response: "):
    """Plot impulse responses for one or more responses over horizon.
    irf_df: dict mapping response_name -> DataFrame with columns ['horizon', 'irf', 'lower', 'upper']
    """
    if not irf_df:
        return None
    # If multiple responses, create subplots
    n = len(irf_df)
    fig, axes = plt.subplots(n, 1, figsize=(6, max(3, 2*n)), facecolor=BG_COLOR, constrained_layout=True)
    if n == 1:
        axes = [axes]
    for ax, (resp, df_resp) in zip(axes, irf_df.items()):
        ax.set_facecolor(FACE_COLOR)
        ax.set_title(f"{title_prefix}{resp}", color=TEXT_COLOR)
        ax.plot(df_resp['horizon'], df_resp['irf'], color=SEA_GREEN)
        if 'lower' in df_resp.columns and 'upper' in df_resp.columns:
            ax.fill_between(df_resp['horizon'], df_resp['lower'], df_resp['upper'], color=SEA_GREEN, alpha=0.2)
        ax.axhline(0, color='white', alpha=0.5, linestyle='--')
        ax.tick_params(colors=TEXT_COLOR, labelcolor=TEXT_COLOR)
        for spine in ax.spines.values():
            spine.set_color(TEXT_COLOR)
        ax.set_xlabel("Horizon (days)", color=TEXT_COLOR)
        ax.set_ylabel("Response", color=TEXT_COLOR)
    return fig


def create_aw_top_apps_bar(app_items, title="Top Applications"):
    """app_items: list of (app_name, seconds)"""
    if not app_items:
        return None
    labels = [a for a, s in app_items]
    mins = [s / 60.0 for a, s in app_items]
    fig, ax = _setup_base_chart(title, ylabel="Minutes")
    y_pos = range(len(labels))[::-1]
    ax.barh(list(range(len(labels))), mins, color=plt.cm.tab20.colors[:len(labels)])
    ax.set_yticks(list(range(len(labels))))
    ax.set_yticklabels(labels, color=TEXT_COLOR)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_aw_top_windows_bar(window_items, title="Top Window Titles"):
    # same layout as top apps but for window titles
    return create_aw_top_apps_bar(window_items, title=title)


def create_aw_daily_bar_chart(aw_df, title="AW Active Hours"):
    """aw_df should have columns ['date', 'active_hours']"""
    if aw_df is None or aw_df.empty:
        return None
    fig, ax = _setup_base_chart(title, ylabel="Active Hours")
    ax.bar(aw_df['date'].dt.strftime('%Y-%m-%d'), aw_df['active_hours'], color=SEA_GREEN)
    ax.tick_params(axis='x', labelrotation=90)
    try:
        ax.set_box_aspect('auto')
    except Exception:
        pass
    return fig


def create_aw_category_sunburst(cat_items, title="Top Categories"):
    """Approximate a sunburst using a donut pie chart. cat_items: list of (label, seconds)"""
    if not cat_items:
        return None
    labels = [l for l, s in cat_items]
    sizes = [s for l, s in cat_items]
    fig, ax = _setup_base_chart(title)
    # Use a donut chart to approximate a sunburst
    cmap = plt.cm.get_cmap('tab20', len(labels)).colors
    wedges, texts = ax.pie(sizes, labels=labels, colors=cmap, startangle=90, textprops={'color': TEXT_COLOR})
    # draw center circle for donut
    centre_circle = plt.Circle((0, 0), 0.55, color=BG_COLOR)
    ax.add_artist(centre_circle)
    ax.axis('equal')
    try:
        ax.set_box_aspect(1)
    except Exception:
        pass
    return fig