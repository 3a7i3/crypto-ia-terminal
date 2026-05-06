from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objs as go
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


def main() -> int:
    exit_code = 0

    try:
        fig = go.Figure(
            data=[go.Scatter3d(x=[1, 2, 3], y=[4, 5, 6], z=[7, 8, 9], mode="markers")]
        )
        fig.write_image("test_plotly3d.png")
        fig.write_image("test_plotly3d.svg")
        print("[OK] Plotly 3D + export PNG/SVG")
    except Exception as exc:
        print(f"[ERREUR] Plotly 3D ou export PNG/SVG : {exc}")
        if "kaleido" in str(exc).lower():
            print("Installez la dépendance optionnelle avec: pip install kaleido")
        exit_code = 1

    try:
        fig = plt.figure()
        ax = fig.add_subplot(111, projection="3d")
        grid_x, grid_y = np.meshgrid(np.arange(0, 10, 1), np.arange(0, 10, 1))
        grid_z = np.sin(grid_x) + np.cos(grid_y)
        ax.plot_surface(grid_x, grid_y, grid_z)
        plt.savefig("test_matplotlib3d.png")
        plt.close(fig)
        print("[OK] Matplotlib 3D + export PNG")
    except Exception as exc:
        print(f"[ERREUR] Matplotlib 3D : {exc}")
        exit_code = 1

    try:
        fig, ax = plt.subplots()
        data = np.random.rand(10, 10)
        heatmap = ax.imshow(data, cmap="viridis")
        plt.colorbar(heatmap, ax=ax)
        plt.savefig("test_heatmap2d.png")
        plt.close(fig)
        print("[OK] Matplotlib heatmap 2D + export PNG")
    except Exception as exc:
        print(f"[ERREUR] Matplotlib heatmap 2D : {exc}")
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())