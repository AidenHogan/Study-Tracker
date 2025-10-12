# file: plot_manager.py

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- Constants for Chart Styling ---
BG_COLOR = '#2B2B2B'
FACE_COLOR = '#333333'
TEXT_COLOR = 'white'
SKY_BLUE = 'skyblue'
SEA_GREEN = 'mediumseagreen'
GOLD = '#FFD700'


def _setup_base_chart(title, xlabel=None, ylabel=None):
    """Creates and styles a base Matplotlib figure and axis to avoid repeating code."""
    fig, ax = plt.subplots(facecolor=BG_COLOR, constrained_layout=True)
    ax.set_title(title, color=TEXT_COLOR)
    if xlabel: ax.set_xlabel(xlabel, color=TEXT_COLOR)
    if ylabel: ax.set_ylabel(ylabel, color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelcolor=TEXT_COLOR)
    for spine in ax.spines.values():
        spine.set_color(TEXT_COLOR)
    ax.set_facecolor(FACE_COLOR)
    return fig, ax


def embed_figure_in_frame(fig, frame):
    """Clears a frame and embeds a Matplotlib figure in it."""
    for widget in frame.winfo_children():
        widget.destroy()
    if fig:
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
        plt.close(fig)


def create_pie_chart(data, time_range):
    """Creates a pie chart of time by subject."""
    if not data: return None
    labels, sizes, colors = zip(*data)
    fig, ax = _setup_base_chart(f"Time by Subject ({time_range})")
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90, textprops={'color': TEXT_COLOR})
    ax.axis('equal')
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
    return fig

def create_daily_bar_chart(df, time_range):
    """Creates a bar chart of minutes studied per day."""
    if df.empty: return None
    fig, ax = _setup_base_chart(f"Minutes Studied Per Day ({time_range})", ylabel="Total Minutes")
    ax.bar(df['day'], df['minutes'])
    ax.tick_params(axis='x', labelrotation=90)
    return fig


def create_hourly_bar_chart(df, time_range):
    if df.empty: return None
    fig, ax = _setup_base_chart(f"Productivity by Hour ({time_range})", ylabel="Total Minutes")
    ax.bar(df['hour'], df['minutes'], color=SKY_BLUE)
    ax.tick_params(axis='x', labelrotation=45)
    return fig


def create_weekly_bar_chart(df, time_range):
    if df.empty: return None
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    fig, ax = _setup_base_chart(f"Productivity by Day of Week ({time_range})", ylabel="Total Minutes")
    ax.bar(day_names, df['minutes'], color=SEA_GREEN)
    return fig


def create_correlation_scatter_plot(df, x_col, y_col, title, xlabel, ylabel):
    if df.empty or df[x_col].isnull().all() or df[y_col].isnull().all(): return None
    fig, ax = _setup_base_chart(title, xlabel=xlabel, ylabel=ylabel)
    ax.scatter(df[x_col], df[y_col])
    return fig


def create_trends_chart(df, time_range):
    if df.empty: return None
    df_trends = df.sort_values('date')

    # Scale sleep duration for better visibility on the chart
    df_trends['sleep_duration_hours_scaled'] = df_trends['sleep_duration_hours'].fillna(0) * 10

    fig, ax = _setup_base_chart(f"Trends: Sleep & Study ({time_range})")
    ax_twin = ax.twinx()

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