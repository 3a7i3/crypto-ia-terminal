# Test de compatibilité Plotly/Matplotlib (Windows/Linux)
#
# Ce script vérifie que les principales fonctionnalités de visualisation utilisées dans le dashboard 3D fonctionnent sans erreur sur l’environnement courant.
#
# Il teste :
# - Création d’un graphique Plotly 3D
# - Export PNG/SVG avec kaleido
# - Création d’un graphique Matplotlib 3D
# - Affichage d’une heatmap 2D
#
# ---

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objs as go
from mpl_toolkits.mplot3d import Axes3D

# Test Plotly 3D
try:
    fig = go.Figure(
        data=[go.Scatter3d(x=[1, 2, 3], y=[4, 5, 6], z=[7, 8, 9], mode="markers")]
    )
    fig.write_image("test_plotly3d.png")
    fig.write_image("test_plotly3d.svg")
    print("[OK] Plotly 3D + export PNG/SVG")
except Exception as e:
    print(f"[ERREUR] Plotly 3D ou export PNG/SVG : {e}")

# Test Matplotlib 3D
try:
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    X, Y = np.meshgrid(np.arange(0, 10, 1), np.arange(0, 10, 1))
    Z = np.sin(X) + np.cos(Y)
    ax.plot_surface(X, Y, Z)
    plt.savefig("test_matplotlib3d.png")
    plt.close(fig)
    print("[OK] Matplotlib 3D + export PNG")
except Exception as e:
    print(f"[ERREUR] Matplotlib 3D : {e}")

# Test Heatmap 2D
try:
    fig, ax = plt.subplots()
    data = np.random.rand(10, 10)
    c = ax.imshow(data, cmap="viridis")
    plt.colorbar(c, ax=ax)
    plt.savefig("test_heatmap2d.png")
    plt.close(fig)
    print("[OK] Matplotlib heatmap 2D + export PNG")
except Exception as e:
    print(f"[ERREUR] Matplotlib heatmap 2D : {e}")
