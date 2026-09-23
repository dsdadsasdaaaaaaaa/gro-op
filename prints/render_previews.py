"""Render an isometric PNG preview of every STL in stl/ into previews/ (matplotlib, no GPU needed)."""
import sys
from pathlib import Path
import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = Path("previews"); OUT.mkdir(exist_ok=True)
names = sys.argv[1:] or sorted(p.stem for p in Path("stl").glob("*.stl"))
for name in names:
    tm = trimesh.load(f"stl/{name}.stl", force="mesh")
    v, f = tm.vertices, tm.faces
    tris = v[f]
    n = tm.face_normals
    light = np.array([0.4, -0.6, 0.7]); light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(n @ light, 0, 1)
    colors = np.stack([shade * 0.35, shade * 0.75, shade * 0.55, np.ones_like(shade)], axis=1)
    fig = plt.figure(figsize=(6, 5), dpi=110)
    ax = fig.add_subplot(111, projection="3d")
    pc = Poly3DCollection(tris, facecolors=colors, edgecolors="none")
    ax.add_collection3d(pc)
    lo, hi = v.min(0), v.max(0); c = (lo + hi) / 2; r = (hi - lo).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(elev=32, azim=-50); ax.set_axis_off()
    ax.set_title(f"{name}   {np.round(hi - lo, 1)} mm", fontsize=9)
    fig.tight_layout(); fig.savefig(OUT / f"{name}.png"); plt.close(fig)
    print("preview", name)
