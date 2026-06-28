# file: plot_manager.py

import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import matplotlib.patches as patches
# Try to import colormaps registry for newer MPL versions
try:
    from matplotlib import colormaps
except ImportError:
    colormaps = None

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
    fig = Figure(figsize=(6, 4), facecolor=BG_COLOR, constrained_layout=True)
    ax = fig.add_subplot(111)
    
    ax.set_title(title, color=TEXT_COLOR)
    if xlabel: ax.set_xlabel(xlabel, color=TEXT_COLOR)
    if ylabel: ax.set_ylabel(ylabel, color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelcolor=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(TEXT_COLOR)
    ax.set_facecolor(FACE_COLOR)
    return fig, ax


def embed_figure_in_frame(fig, frame):
    """Embeds or updates a Matplotlib figure in a frame with persistent canvas recycling."""
    if not fig:
        return

    # Define the resize logic
    def _on_resize(event, fig=fig, frame=frame):
        # We need the canvas associated with THIS frame
        canvas = getattr(frame, '_canvas_widget', None)
        widget = canvas.get_tk_widget() if canvas else None
        if not widget: return
        
        try:
            frame.update_idletasks()
            widget_w = max(frame.winfo_width() - 6, 50)
            widget_h = max(frame.winfo_height() - 6, 50)
            dpi = fig.get_dpi() or 100
            
            widget.place_configure(width=widget_w, height=widget_h)

            max_iters = 6
            target_w, target_h = widget_w, widget_h
            for _ in range(max_iters):
                fig.set_size_inches(target_w / dpi, target_h / dpi, forward=True)
                canvas.draw_idle()
                
                fig_w, fig_h = fig.bbox.width, fig.bbox.height
                if (fig_w - widget_w) <= 1 and (fig_h - widget_h) <= 1:
                    break
                target_w = max(target_w - max(int(np.ceil(fig_w - widget_w)) + 2, 0), 50)
                target_h = max(target_h - max(int(np.ceil(fig_h - widget_h)) + 2, 0), 50)
        except Exception:
            pass

    # Check for existing canvas
    existing_canvas = getattr(frame, '_canvas_widget', None)
    
    if existing_canvas and existing_canvas.get_tk_widget().winfo_exists():
        # --- RECYCLE PATH ---
        plt.close(existing_canvas.figure)
        existing_canvas.figure = fig
        fig.set_canvas(existing_canvas)
        
        # Update the resize callback to use new fig
        if hasattr(frame, '_on_resize_cb'):
            frame.unbind("<Configure>", frame._on_resize_cb)
        
        frame._on_resize_cb = frame.bind("<Configure>", _on_resize)
        existing_canvas.draw_idle()
    else:
        # --- FIRST-TIME PATH ---
        for widget in list(frame.winfo_children()):
            widget.destroy()

        canvas = FigureCanvasTkAgg(fig, master=frame)
        widget = canvas.get_tk_widget()
        
        # Apply styles
        widget.configure(bg=BG_COLOR)
        widget.place(x=3, y=3, width=50, height=50) # Initial dummy size
        
        frame._canvas_widget = canvas
        frame._on_resize_cb = frame.bind("<Configure>", _on_resize)
        
        canvas.draw_idle()

    # Initial trigger
    frame.after(50, lambda: frame.event_generate('<Configure>'))

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
    import matplotlib.cm as cm
    try:
        if hasattr(cm, 'get_cmap'):
             colors = cm.get_cmap('viridis', len(labels)).colors
        else:
             # Matplotlib 3.7+
             colors = [cm.viridis(x) for x in np.linspace(0, 1, len(labels))]
    except Exception:
         colors = None

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
    cbar.ax.yaxis.set_tick_params(color=TEXT_COLOR, labelcolor=TEXT_COLOR)
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
    fig = Figure(figsize=(6, max(3, 2*n)), facecolor=BG_COLOR, constrained_layout=True)
    axes = fig.subplots(n, 1)
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
    import matplotlib.cm as cm
    try:
        cmap = cm.get_cmap('tab20', len(labels)).colors if hasattr(cm, 'get_cmap') else [cm.tab20(x) for x in np.linspace(0, 1, len(labels))]
    except:
        cmap = None
        
    wedges, texts = ax.pie(sizes, labels=labels, colors=cmap, startangle=90, textprops={'color': TEXT_COLOR})
    # draw center circle for donut
    centre_circle = patches.Circle((0, 0), 0.55, color=BG_COLOR)
    ax.add_artist(centre_circle)
    ax.axis('equal')
    try:
        ax.set_box_aspect(1)
    except Exception:
        pass
    return fig