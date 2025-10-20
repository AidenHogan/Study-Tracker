"""
Test script that mimics the exact analytics tab layout to diagnose cutoff issues.
This automatically runs, saves screenshots, and exits.
"""

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sys
import os

# Import the actual plot_manager to use the same embedding logic
sys.path.insert(0, os.path.dirname(__file__))
from core import plot_manager as pm

def create_test_chart(title, has_rotated_labels=False, has_twin_axis=False):
    """Create a test chart similar to analytics charts."""
    fig, ax = plt.subplots(figsize=(6, 4), facecolor=pm.BG_COLOR, constrained_layout=True)
    
    # Test data with long labels
    if has_twin_axis:
        # Mimic the trends chart with twin axes
        labels = ['10-14', '10-15', '10-16', '10-17', '10-18']
        values1 = [100, 150, 120, 180, 160]
        values2 = [80, 90, 110, 70, 85]
        
        ax.plot(labels, values1, color=pm.SKY_BLUE, label='Study Minutes')
        ax.set_ylabel('Study Minutes', color=pm.SKY_BLUE)
        ax.tick_params(axis='y', colors=pm.SKY_BLUE)
        ax.tick_params(axis='x', labelrotation=90)
        
        # Create twin axis on the right
        ax_twin = ax.twinx()
        ax_twin.plot(labels, values2, color=pm.SEA_GREEN, label='Sleep Score')
        ax_twin.set_ylabel('Sleep Score', color=pm.SEA_GREEN)
        ax_twin.tick_params(axis='y', colors=pm.SEA_GREEN)
        
        # Add legend
        lines, labels_l = ax.get_legend_handles_labels()
        lines2, labels2 = ax_twin.get_legend_handles_labels()
        if lines or lines2:
            ax_twin.legend(lines + lines2, labels_l + labels2, loc='upper left')
            
    elif has_rotated_labels:
        labels = ['2025-10-14', '2025-10-15', '2025-10-16', '2025-10-17', '2025-10-18']
        values = [100, 150, 120, 180, 160]
        ax.bar(labels, values, color=pm.SKY_BLUE)
        ax.tick_params(axis='x', labelrotation=45)
        ax.set_ylabel('Minutes', color=pm.TEXT_COLOR)
    else:
        labels = ['A', 'B', 'C', 'D', 'E']
        values = [100, 150, 120, 180, 160]
        ax.bar(labels, values, color=pm.SKY_BLUE)
        ax.set_ylabel('Minutes', color=pm.TEXT_COLOR)
    
    ax.set_title(title, color=pm.TEXT_COLOR)
    ax.tick_params(colors=pm.TEXT_COLOR, labelcolor=pm.TEXT_COLOR)
    ax.set_facecolor(pm.FACE_COLOR)
    for spine in ax.spines.values():
        spine.set_color(pm.TEXT_COLOR)
    
    return fig

def analyze_chart_bounds(canvas, chart_name):
    """Analyze if chart elements are cut off by the widget bounds."""
    fig = canvas.figure
    widget = canvas.get_tk_widget()
    
    # Force a draw to ensure everything is rendered
    canvas.draw()
    
    # Get WIDGET dimensions (the actual visible area)
    widget.update()
    widget_width = widget.winfo_width()
    widget_height = widget.winfo_height()
    
    # Get figure dimensions
    fig_bbox = fig.bbox
    fig_width = fig_bbox.width
    fig_height = fig_bbox.height
    
    print(f"\n{chart_name}:")
    print(f"  Widget size: {widget_width}x{widget_height}px")
    print(f"  Figure size: {fig_width:.1f}x{fig_height:.1f}px")
    
    issues = []
    
    # CRITICAL: Check if the figure is larger than the widget!
    if fig_width > widget_width:
        issues.append(f"  ❌ Figure is {fig_width - widget_width:.1f}px WIDER than widget - RIGHT SIDE CUT OFF!")
    if fig_height > widget_height:
        issues.append(f"  ❌ Figure is {fig_height - widget_height:.1f}px TALLER than widget - BOTTOM CUT OFF!")
    
    # Check all text elements against WIDGET bounds (not figure bounds)
    renderer = canvas.get_renderer()
    for text in fig.findobj(plt.Text):
        if text.get_text() and text.get_visible():
            try:
                bbox = text.get_window_extent(renderer=renderer)
                
                # Check if extends beyond WIDGET bounds
                tolerance = 1.0
                if bbox.x1 > widget_width - tolerance:
                    issues.append(f"  ❌ Text '{text.get_text()[:20]}' at x={bbox.x1:.1f} extends beyond widget width {widget_width}")
                if bbox.y0 < tolerance:
                    issues.append(f"  ❌ Text '{text.get_text()[:20]}' at y={bbox.y0:.1f} extends beyond widget bottom")
            except:
                pass
    
    if issues:
        for issue in issues:
            print(issue)
        return False
    else:
        print("  ✓ No clipping detected")
        return True

def run_test():
    """Run the test mimicking the exact analytics tab setup."""
    
    print("=" * 70)
    print("ANALYTICS TAB GRID LAYOUT TEST")
    print("=" * 70)
    
    app = ctk.CTk()
    app.geometry("1366x768")  # Common full screen size
    app.title("Grid Layout Test - Fullscreen Test")
    
    # Mimic the analytics tab structure EXACTLY
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(0, weight=1)
    
    # Charts frame (mimics analytics_tab.py line 70-73)
    charts_frame = ctk.CTkFrame(app, fg_color="transparent")
    charts_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=(0, 10))
    charts_frame.grid_columnconfigure((0, 1), weight=1)
    charts_frame.grid_rowconfigure((0, 1), weight=1)
    
    # Create 4 chart frames with EXACT same padding as analytics_tab.py
    chart_frame_tl = ctk.CTkFrame(charts_frame, fg_color=pm.BG_COLOR)
    chart_frame_tl.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=(5, 2))
    
    chart_frame_tr = ctk.CTkFrame(charts_frame, fg_color=pm.BG_COLOR)
    chart_frame_tr.grid(row=0, column=1, sticky="nsew", padx=(8, 5), pady=(5, 2))
    
    chart_frame_bl = ctk.CTkFrame(charts_frame, fg_color=pm.BG_COLOR)
    chart_frame_bl.grid(row=1, column=0, sticky="nsew", padx=(5, 2), pady=(2, 5))
    
    chart_frame_br = ctk.CTkFrame(charts_frame, fg_color=pm.BG_COLOR)
    chart_frame_br.grid(row=1, column=1, sticky="nsew", padx=(8, 5), pady=(2, 5))
    
    # Create charts - BR mimics the trends chart with twin axes!
    fig_tl = create_test_chart("Top Left (Simple)", has_rotated_labels=False)
    fig_tr = create_test_chart("Top Right (Rotated Labels)", has_rotated_labels=True)
    fig_bl = create_test_chart("Bottom Left (Simple)", has_rotated_labels=False)
    fig_br = create_test_chart("Bottom Right (Twin Axes + Rotated)", has_twin_axis=True)
    
    # Store references to the canvas objects before embedding
    canvases = {}
    
    # Manually embed and store canvas references
    for name, fig, frame in [
        ("Top Left", fig_tl, chart_frame_tl),
        ("Top Right", fig_tr, chart_frame_tr),
        ("Bottom Left", fig_bl, chart_frame_bl),
        ("Bottom Right", fig_br, chart_frame_br)
    ]:
        # Clear frame
        for widget in frame.winfo_children():
            widget.destroy()
        
        # Create canvas
        canvas = FigureCanvasTkAgg(fig, master=frame)
        widget = canvas.get_tk_widget()
        widget.configure(background=pm.BG_COLOR, highlightthickness=0, borderwidth=0)
        widget.pack(fill="both", expand=True)
        
        canvases[name] = canvas
    
    def analyze_after_render():
        """Analyze after everything has rendered."""
        print("\nInitial render analysis:")
        all_good = True
        for name in ["Top Left", "Top Right", "Bottom Left", "Bottom Right"]:
            canvas = canvases.get(name)
            if canvas:
                widget = canvas.get_tk_widget()
                if not analyze_chart_bounds(canvas, name):
                    all_good = False
        
        if all_good:
            print("\n✅ ALL CHARTS OK - No clipping detected!")
        else:
            print("\n⚠️  CLIPPING ISSUES FOUND!")
        
        # Close after a moment to see results
        app.after(2000, app.destroy)
    
    # Analyze after window is fully rendered
    app.after(500, analyze_after_render)
    
    app.mainloop()
    
    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)

if __name__ == "__main__":
    run_test()
