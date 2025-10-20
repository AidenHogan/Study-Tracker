import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend
import matplotlib.pyplot as plt
import numpy as np
from core import plot_manager as pm

BG = np.array([43, 43, 43])  # RGB for #2B2B2B


def is_clipped(img, bg_color=BG, tolerance=5):
    """Check if any non-background pixel touches the image edge."""
    h, w, _ = img.shape
    edges = [
        img[0, :, :],      # top
        img[-1, :, :],     # bottom
        img[:, 0, :],      # left
        img[:, -1, :]      # right
    ]
    for edge in edges:
        # If any pixel is not close to bg_color, it's likely clipped
        if np.any(np.abs(edge - bg_color).sum(axis=1) > tolerance):
            return True
    return False


def test_chart(fig, name):
    fig.tight_layout()  # Just in case
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    img = np.frombuffer(renderer.buffer_rgba(), dtype=np.uint8)
    img = img.reshape(fig.canvas.get_width_height()[::-1] + (4,))[:, :, :3]  # Drop alpha
    clipped = is_clipped(img)
    print(f"{name}: {'❌ CLIPPED' if clipped else '✓ OK'}")
    return not clipped


def run():
    print("\nHEADLESS CHART CLIPPING TEST\n" + "="*40)
    all_ok = True
    # Simple bar
    fig1, _ = pm._setup_base_chart("Simple Bar")
    fig1.gca().bar(['A', 'B', 'C'], [1, 2, 3], color=pm.SKY_BLUE)
    all_ok &= test_chart(fig1, "Simple Bar")
    # Rotated labels
    fig2, _ = pm._setup_base_chart("Rotated Labels")
    fig2.gca().bar(['2025-10-14', '2025-10-15', '2025-10-16'], [1, 2, 3], color=pm.SKY_BLUE)
    fig2.gca().tick_params(axis='x', labelrotation=45)
    all_ok &= test_chart(fig2, "Rotated Labels")
    # Twin axes
    fig3, ax = pm._setup_base_chart("Twin Axes")
    ax2 = ax.twinx()
    x = ['10-14', '10-15', '10-16']
    ax.plot(x, [1, 2, 3], color=pm.SKY_BLUE)
    ax2.plot(x, [3, 2, 1], color=pm.SEA_GREEN)
    ax.tick_params(axis='x', labelrotation=90)
    all_ok &= test_chart(fig3, "Twin Axes")
    # Pie chart
    fig4, _ = pm._setup_base_chart("Pie Chart")
    fig4.gca().pie([30, 70], labels=['A', 'B'], colors=[pm.SKY_BLUE, pm.GOLD], autopct='%1.1f%%', startangle=90, textprops={'color': pm.TEXT_COLOR})
    all_ok &= test_chart(fig4, "Pie Chart")
    print("\nResult: {}\n".format("ALL OK" if all_ok else "CLIPPING DETECTED"))

if __name__ == "__main__":
    run()
