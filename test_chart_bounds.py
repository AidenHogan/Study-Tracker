"""
Test script to check if matplotlib charts are getting cut off.
This runs automated checks to detect clipping issues.
"""

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import customtkinter as ctk
import numpy as np

def test_chart_bounds():
    """Test if chart elements are within the figure bounds."""
    
    # Create a test figure similar to what the app creates
    fig, ax = plt.subplots(figsize=(6, 4), facecolor='#2B2B2B')
    
    # Create test data with labels that might get cut off
    dates = ['2025-10-14', '2025-10-15', '2025-10-16', '2025-10-17', '2025-10-18']
    values = [100, 150, 120, 180, 160]
    
    ax.bar(dates, values, color='skyblue')
    ax.set_title('Test Chart', color='white')
    ax.set_ylabel('Minutes', color='white')
    ax.tick_params(colors='white', labelcolor='white')
    ax.tick_params(axis='x', labelrotation=45)
    ax.set_facecolor('#333333')
    for spine in ax.spines.values():
        spine.set_color('white')
    
    # Try tight_layout
    fig.tight_layout(pad=2.5, rect=[0.02, 0.02, 0.98, 0.98])
    
    # Get the figure's bounding box
    fig.canvas.draw()
    
    # Check each text element's position
    issues = []
    
    # Get figure dimensions in display coordinates
    fig_bbox = fig.bbox
    print(f"\nFigure bbox: {fig_bbox}")
    print(f"Figure width: {fig_bbox.width}, height: {fig_bbox.height}")
    
    # Check all text elements
    for text in fig.findobj(plt.Text):
        if text.get_text():
            bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())
            print(f"\nText: '{text.get_text()}'")
            print(f"  Position: ({bbox.x0:.1f}, {bbox.y0:.1f}) to ({bbox.x1:.1f}, {bbox.y1:.1f})")
            
            # Check if text extends beyond figure bounds
            if bbox.x1 > fig_bbox.width:
                issues.append(f"Text '{text.get_text()}' extends beyond right edge by {bbox.x1 - fig_bbox.width:.1f}px")
            if bbox.x0 < 0:
                issues.append(f"Text '{text.get_text()}' extends beyond left edge by {-bbox.x0:.1f}px")
            if bbox.y1 > fig_bbox.height:
                issues.append(f"Text '{text.get_text()}' extends beyond top edge by {bbox.y1 - fig_bbox.height:.1f}px")
            if bbox.y0 < 0:
                issues.append(f"Text '{text.get_text()}' extends beyond bottom edge by {-bbox.y0:.1f}px")
    
    # Check axis elements
    print(f"\nAxis bbox: {ax.bbox}")
    ax_bbox = ax.get_window_extent(renderer=fig.canvas.get_renderer())
    print(f"Axis position: ({ax_bbox.x0:.1f}, {ax_bbox.y0:.1f}) to ({ax_bbox.x1:.1f}, {ax_bbox.y1:.1f})")
    
    if issues:
        print("\n❌ CLIPPING ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n✓ No clipping issues detected!")
        return True

def test_in_tkinter_window():
    """Test the chart in an actual tkinter window to simulate real conditions."""
    
    app = ctk.CTk()
    app.geometry("800x600")
    app.title("Chart Bounds Test")
    
    frame = ctk.CTkFrame(app, fg_color='#2B2B2B', width=400, height=300)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    # Create test chart
    fig, ax = plt.subplots(figsize=(6, 4), facecolor='#2B2B2B')
    dates = ['2025-10-14', '2025-10-15', '2025-10-16', '2025-10-17', '2025-10-18']
    values = [100, 150, 120, 180, 160]
    
    ax.bar(dates, values, color='skyblue')
    ax.set_title('Test Chart - Check Right Edge', color='white')
    ax.set_ylabel('Minutes', color='white')
    ax.tick_params(colors='white', labelcolor='white')
    ax.tick_params(axis='x', labelrotation=45)
    ax.set_facecolor('#333333')
    for spine in ax.spines.values():
        spine.set_color('white')
    
    fig.tight_layout(pad=2.5, rect=[0.02, 0.02, 0.98, 0.98])
    
    # Embed in tkinter
    canvas = FigureCanvasTkAgg(fig, master=frame)
    widget = canvas.get_tk_widget()
    widget.configure(background='#2B2B2B', highlightthickness=0, borderwidth=0)
    widget.pack(fill="both", expand=True)
    
    def check_after_render():
        """Check bounds after the window has rendered."""
        widget.update()
        print(f"\nWidget actual size: {widget.winfo_width()}x{widget.winfo_height()}")
        print(f"Frame actual size: {frame.winfo_width()}x{frame.winfo_height()}")
        
        # Redraw and check
        canvas.draw()
        test_chart_bounds()
        
    app.after(500, check_after_render)
    app.mainloop()

if __name__ == "__main__":
    print("=" * 60)
    print("MATPLOTLIB CHART BOUNDS TEST")
    print("=" * 60)
    
    print("\n1. Testing chart bounds (no window)...")
    test_chart_bounds()
    
    print("\n\n2. Testing in actual Tkinter window...")
    print("(Window will open - close it to finish test)")
    test_in_tkinter_window()
