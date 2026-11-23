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
import re
import warnings
from types import SimpleNamespace
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


_CANVAS_MARGIN = 3
_FIT_DELAY_MS = 50        # first fit of a newly embedded chart
_RESIZE_DELAY_MS = 120    # wait for a window resize to pause before redrawing


def _frame_canvas(frame):
    """The frame's live canvas, or None (never embedded, or destroyed by the caller)."""
    canvas = getattr(frame, '_canvas_widget', None)
    try:
        if canvas is not None and canvas.get_tk_widget().winfo_exists():
            return canvas
    except Exception:
        pass
    return None


def _canvas_size_for(frame):
    """Pixel size the canvas should have, or None while the frame has not been laid out."""
    w, h = frame.winfo_width(), frame.winfo_height()
    if w <= 1 or h <= 1:
        return None
    m = 2 * _CANVAS_MARGIN
    return max(w - m, 50), max(h - m, 50)


def _fit_canvas_to_frame(frame):
    """Size the frame's current canvas to the frame.

    Reads the canvas from the frame each time instead of closing over a figure, so a single
    binding per frame serves every figure that is later embedded in it. Only the widget is
    resized here: its own <Configure> handler resizes the figure and redraws it, once.
    """
    canvas = _frame_canvas(frame)
    if canvas is None or getattr(frame, '_canvas_hidden', False):
        return
    size = _canvas_size_for(frame)
    if size is None:
        return
    w, h = size
    widget = canvas.get_tk_widget()
    info = widget.place_info()
    if (str(info.get('width')), str(info.get('height'))) != (str(w), str(h)):
        widget.place_configure(width=w, height=h)
    elif (widget.winfo_width(), widget.winfo_height()) == (w, h):
        canvas.match_figure_to_widget()  # no-op when the figure is already drawn at this size


def _schedule_fit(frame, delay):
    """Fit the canvas `delay` ms after the last request, so a window drag redraws once."""
    job = getattr(frame, '_fit_job', None)
    if job:
        try:
            frame.after_cancel(job)
        except Exception:
            pass

    def _run():
        frame._fit_job = None
        try:
            if frame.winfo_exists():
                _fit_canvas_to_frame(frame)
        except Exception:
            pass

    frame._fit_job = frame.after(delay, _run)


def _on_frame_configure(frame):
    if _frame_canvas(frame) is not None and not getattr(frame, '_canvas_hidden', False):
        _schedule_fit(frame, _RESIZE_DELAY_MS)


def _hide_canvas(frame):
    canvas = _frame_canvas(frame)
    if canvas is not None:
        canvas.get_tk_widget().place_forget()
        frame._canvas_hidden = True


def clear_frame(frame):
    """Empty a chart frame, keeping its canvas (hidden) so the next chart can reuse it.

    Use this instead of destroying the frame's children: creating a canvas is slow, and
    destroying one has to clean up after itself (see embed_figure_in_frame).
    """
    canvas = _frame_canvas(frame)
    keep = canvas.get_tk_widget() if canvas is not None else None
    for child in list(frame.winfo_children()):
        if child is not keep:
            child.destroy()
    _hide_canvas(frame)


class _ChartCanvas(FigureCanvasTkAgg):
    """Canvas that can show one figure after another."""

    def resize(self, event):
        # Tk also sends <Configure> when nothing but the position changed, or when this size
        # is already drawn; redrawing is the expensive part, so skip it then.
        fig_size = tuple(int(round(v)) for v in self.figure.get_size_inches() * self.figure.dpi)
        photo_size = (self._tkphoto.width(), self._tkphoto.height())
        if getattr(self, '_drawn_once', False) and (event.width, event.height) == fig_size == photo_size:
            return
        super().resize(event)

    def draw(self):
        self._drawn_once = True
        super().draw()

    def match_figure_to_widget(self):
        w, h = self._tkcanvas.winfo_width(), self._tkcanvas.winfo_height()
        if w > 1 and h > 1:
            self.resize(SimpleNamespace(width=w, height=h))

    def _update_device_pixel_ratio(self, event=None):
        # On scaled displays this enlarges the figure. Normally the widget then grows to match,
        # but here the widget size is fixed by place(), so shrink the figure back instead.
        old_ratio = self.device_pixel_ratio
        super()._update_device_pixel_ratio(event)
        if self.device_pixel_ratio != old_ratio:
            self.match_figure_to_widget()

    def show_figure(self, fig):
        """Replace the displayed figure, keeping the canvas' current pixel size."""
        old_fig = self.figure
        fig._original_dpi = fig.dpi                             # as FigureCanvasBase.__init__ does
        fig.set_canvas(self)
        fig.dpi = fig._original_dpi * self.device_pixel_ratio   # HiDPI scaling
        # The new figure must match the image buffer, which has the size of the old one.
        fig.set_size_inches(self._tkphoto.width() / fig.dpi, self._tkphoto.height() / fig.dpi,
                            forward=False)
        self.figure = fig
        self._drawn_once = False
        if old_fig is not None and old_fig is not fig:
            old_fig.clear()


def embed_figure_in_frame(fig, frame):
    """Embeds or updates a Matplotlib figure in a frame with persistent canvas recycling.

    Leak notes: every Tk binding registered from Python stays alive (with everything its
    closure references) until the widget is destroyed, even when the binding is later
    replaced. Binding a fresh closure per refresh therefore kept every old Figure and
    FigureCanvasTkAgg alive, and each canvas leaves two handlers on the root window
    (<Destroy>, <MouseWheel>) that run for every widget destroyed anywhere in the app until
    the canvas is garbage-collected. So: bind <Configure> once per frame, and drop all
    references to a canvas whose widget the caller has destroyed.
    """
    if not fig:
        _hide_canvas(frame)  # nothing to plot: don't leave an outdated chart showing
        return

    existing_canvas = _frame_canvas(frame)
    size = _canvas_size_for(frame) or (50, 50)  # dummy size until the frame is laid out

    if existing_canvas is not None:
        # --- RECYCLE PATH: swap the figure into the existing canvas ---
        widget = existing_canvas.get_tk_widget()
        for child in list(frame.winfo_children()):
            if child is not widget:
                child.destroy()
        existing_canvas.show_figure(fig)
        widget.place(x=_CANVAS_MARGIN, y=_CANVAS_MARGIN, width=size[0], height=size[1])
        if size == (widget.winfo_width(), widget.winfo_height()):
            existing_canvas.draw_idle()
        # else: the size change sends <Configure>, which resizes the figure and draws it
    else:
        # --- FIRST-TIME PATH (or the previous canvas widget was destroyed by the caller) ---
        dead_canvas = getattr(frame, '_canvas_widget', None)
        if dead_canvas is not None:
            _release_canvas(dead_canvas)
            frame._canvas_widget = None
        for widget in list(frame.winfo_children()):
            widget.destroy()

        root = frame.winfo_toplevel()
        before = {seq: _root_binding_ids(root, seq) for seq in _MPL_ROOT_SEQUENCES}
        canvas = _ChartCanvas(fig, master=frame)
        widget = canvas.get_tk_widget()
        # FigureCanvasTkAgg adds <Destroy>/<MouseWheel> handlers to the toplevel that only
        # remove themselves lazily (after the canvas is garbage-collected *and* such an event
        # fires). Remove them as soon as this canvas widget is destroyed.
        added = [(seq, fid) for seq in _MPL_ROOT_SEQUENCES
                 for fid in _root_binding_ids(root, seq) - before[seq]]
        if added:
            def _on_canvas_destroy(event, w=widget, r=root, a=added):
                if event.widget is w:
                    try:
                        r.after_idle(_drop_root_bindings, r, a)
                    except Exception:
                        pass
            widget.bind("<Destroy>", _on_canvas_destroy, add="+")

        # Apply styles
        widget.configure(bg=BG_COLOR)
        widget.place(x=_CANVAS_MARGIN, y=_CANVAS_MARGIN, width=size[0], height=size[1])

        frame._canvas_widget = canvas
        # The first draw happens when the placed widget gets its size (<Configure>).

    frame._canvas_hidden = False

    if not getattr(frame, '_fit_bound', False):
        frame.bind("<Configure>", lambda e, f=frame: _on_frame_configure(f), add="+")
        frame._fit_bound = True

    # Fit again once layout has settled.
    _schedule_fit(frame, _FIT_DELAY_MS)


_MPL_ROOT_SEQUENCES = ("<Destroy>", "<MouseWheel>")
_BINDING_ID_RE = re.compile(r'^if \{"\[(\S+) ')


def _root_binding_ids(root, sequence):
    """Tcl command names of the Python callbacks bound to `sequence` on `root`."""
    try:
        script = root.tk.call("bind", root._w, sequence)
    except Exception:
        return set()
    ids = set()
    for line in str(script).split("\n"):
        m = _BINDING_ID_RE.match(line)
        if m:
            ids.add(m.group(1))
    return ids


def _drop_root_bindings(root, bindings):
    """Remove specific callbacks from root bindings, leaving all other handlers in place.

    Done by hand rather than with ``root.unbind(seq, funcid)``, which on older Python
    versions wipes every handler bound to that sequence.
    """
    for seq, funcid in bindings:
        try:
            if not root.winfo_exists():
                return
            lines = str(root.tk.call("bind", root._w, seq)).split("\n")
            prefix = f'if {{"[{funcid} '
            # Also drop blank lines: each add="+" bind leaves one, and they would pile up.
            keep = "\n".join(line for line in lines
                             if line.strip() and not line.startswith(prefix))
            root.tk.call("bind", root._w, seq, keep)
            root.deletecommand(funcid)
        except Exception:
            pass


def _release_canvas(canvas):
    """Break references from a dead canvas so it (and its PhotoImage) can be collected."""
    try:
        fig = canvas.figure
        if fig is not None:
            fig.clear()
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
    """Study minutes per day alongside the sleep that came *before* that day.

    No date shift is needed: Garmin (Health API, Personal API, CSV exports) dates a night's sleep by
    the morning you wake up, so the sleep row for date D is the night of D-1 -> D, i.e. the sleep
    preceding the studying on D.
    """
    if df.empty: return None
    df_trends = df.sort_values('date')

    # Scale sleep duration for better visibility on the chart. Missing nights stay as gaps
    # rather than being drawn as 0 hours.
    df_trends['sleep_duration_hours_scaled'] = df_trends['sleep_duration_hours'] * 10

    fig, ax = _setup_base_chart(f"Study vs. Previous Night's Sleep ({time_range})",
                                xlabel="Study day (sleep = the night before)")
    ax_twin = ax.twinx()
    try:
        ax.set_box_aspect('auto')
        ax_twin.set_box_aspect('auto')
    except Exception:
        pass

    # Plot Study Minutes on the left Y-axis
    ax.plot(df_trends['date'], df_trends['total_study_minutes'], color=SKY_BLUE, label='Study Minutes (that day)')
    ax.set_ylabel('Study Minutes', color=SKY_BLUE)
    ax.tick_params(axis='y', colors=SKY_BLUE)

    # Plot Sleep Score and Sleep Duration on the right Y-axis
    ax_twin.plot(df_trends['date'], df_trends['sleep_score'], color=SEA_GREEN,
                 label='Sleep Score (night before)')
    ax_twin.plot(df_trends['date'], df_trends['sleep_duration_hours_scaled'], color=GOLD, linestyle='--',
                 label='Sleep Hours x10 (night before)')
    ax_twin.set_ylabel("Previous Night: Sleep Score / Hours x10", color=SEA_GREEN)
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