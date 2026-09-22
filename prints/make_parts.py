"""Parametric grow-tent parts for GrowOp, generated with manifold3d and exported as STL.

Run:  ../.venv/bin/python make_parts.py
Everything is in millimetres. Print in PETG. Pole clips are made for 16, 19 and 22 mm poles.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold

OUT = Path("stl")
OUT.mkdir(exist_ok=True)
SEG = 128  # circle resolution

# Govee H5074 (the small square one without a screen): ~41 x 41 x 14 mm. Measure yours if it rattles or won't drop in.
GOVEE_W = 41.0   # width (left-right)
GOVEE_H = 41.0   # height (top-bottom)
GOVEE_T = 14.0   # thickness (front-back)
GOVEE_CLEAR = 1.0  # total slack added to each dimension; it drops in from the top and sits by gravity

POLE_WALL = 2.6     # clip wall thickness (PETG flexes enough at this)
POLE_GAP = 0.90     # opening = 0.9 x pole diameter, so the ring wraps ~245° and snaps on firmly


def cyl(h, r, seg=SEG):
    return Manifold.cylinder(h, r, r, seg)


def box(x, y, z):
    return Manifold.cube([x, y, z], False)


def save(part: Manifold, name: str) -> None:
    assert part.status() == part.status().__class__.NoError, f"{name}: bad CSG"
    mesh = part.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    tris = np.asarray(mesh.tri_verts)
    tm = trimesh.Trimesh(vertices=verts, faces=tris, process=False)
    assert tm.is_watertight, f"{name} is not watertight"
    tm.export(OUT / f"{name}.stl")
    print(f"{name}.stl  {tm.extents.round(1)} mm  volume {tm.volume/1000:.1f} cm³")


# ---------------------------------------------------------------- pole clip (snap-on C clip + tab)

def pole_clip(pole_d: float, height: float, tab_len: float = 14.0, tab_w: float = 20.0):
    """C-shaped clip that snaps onto a vertical tent pole. Pole axis = Z, opening faces -X, tab points +X."""
    r_in = pole_d / 2 + 0.25
    r_out = r_in + POLE_WALL
    ring = cyl(height, r_out) - cyl(height + 2, r_in).translate([0, 0, -1])
    gap = pole_d * POLE_GAP
    ring = ring - box(r_out + 2, gap, height + 2).translate([-(r_out + 2), -gap / 2, -1])
    # lead-in chamfers on the lips so it pushes on easily
    for sgn in (-1, 1):
        wedge = box(4, 4, height + 2).rotate([0, 0, 45]).translate([-r_out - 1.2, sgn * (gap / 2 + 1.6), -1])
        ring = ring - wedge
    tab = box(tab_len + r_out, tab_w, height).translate([0, -tab_w / 2, 0])
    tab = tab - cyl(height + 2, r_in).translate([0, 0, -1])
    return ring + tab, r_out


# ---------------------------------------------------------------- 1. Govee H5074 pole holder (drop-in cradle)

def govee_holder(pole_d: float):
    wall = 2.4
    lip = 2.0              # front plate that keeps the sensor in
    w = GOVEE_W + GOVEE_CLEAR
    t = GOVEE_T + GOVEE_CLEAR
    h = GOVEE_H + GOVEE_CLEAR + wall  # closed bottom, open top
    clip, r_out = pole_clip(pole_d, height=h)
    x0 = r_out + 9           # cradle back face starts here
    depth = wall + t + lip   # back plate + pocket + front lip
    body = box(depth, w + 2 * wall, h).translate([x0, -(w / 2 + wall), 0])
    # pocket open at the top: sensor drops in and rests on the bottom wall
    body = body - box(t, w, h).translate([x0 + wall, -w / 2, wall])
    # front window (leave 3 mm lips at the sides, 4 mm at the bottom; open to the top edge)
    body = body - box(lip + 2, w - 6, h).translate([x0 + wall + t - 1, -(w - 6) / 2, wall + 4])
    # side windows so tent air reaches the sensor (keep 5 mm posts at the corners)
    for sgn in (-1, 1):
        y = sgn * (w / 2 + wall / 2)
        body = body - box(t - 3, wall + 2, h - wall - 5 - 4).translate([x0 + wall + 1.5, y - (wall + 2) / 2, wall + 5])
    # ventilation slots through the back plate
    for i in range(3):
        y = -w / 2 + 8 + i * (w - 16) / 2
        body = body - box(wall + 2, 3, h - wall - 12).translate([x0 - 1, y - 1.5, wall + 6])
    bridge = box(x0 - r_out + 1, 20, h).translate([r_out - 1, -10, 0])
    return clip + bridge + body


# ---------------------------------------------------------------- 2. Wyze cam pole mount (1/4"-20 bolt platform)

def wyze_mount(pole_d: float):
    height = 24.0
    clip, r_out = pole_clip(pole_d, height=height)
    plate_t = 8.0
    plate = 46.0
    x0 = r_out + 8
    arm = box(x0 - r_out + 2, 20, height).translate([r_out - 1, -10, 0])
    platform = box(plate, plate, plate_t).translate([x0, -plate / 2, height - plate_t])
    cx, cy = x0 + plate / 2, 0
    # 1/4"-20 x 1/2" bolt from below: 6.8 mm through-hole, 13.5 mm counterbore 2.5 mm deep for the head
    platform = platform - cyl(plate_t + 2, 3.4).translate([cx, cy, height - plate_t - 1])
    platform = platform - cyl(2.5, 6.75).translate([cx, cy, height - plate_t - 0.01])
    # anti-rotation ring: a shallow 1 mm rim the camera base sits inside
    rim = cyl(1.0, plate / 2 - 1) - cyl(1.2, 22.5).translate([0, 0, -0.1])
    platform = platform + rim.translate([cx, cy, height])
    # cable notch at the back edge
    platform = platform - box(6, 12, plate_t + 3).translate([x0 + plate - 5, -6, height - plate_t - 1])
    return clip + arm + platform


# ---------------------------------------------------------------- 3. Solo cup riser (16 oz cup)

def cup_riser():
    """Holds a standard 16 oz solo cup (60 mm base) 23 mm up on six spokes, with open slots for runoff and air."""
    h = 26.0
    floor = 3.0
    outer_r = 42.0
    body = cyl(h, outer_r)
    # cup taper: 60 mm at the base, ~66.8 mm 23 mm up (solo cup slope ≈ 0.146 mm/mm); +0.5 mm clearance
    cone = Manifold.cylinder(h - floor + 0.01, 30.5, 33.9, SEG).translate([0, 0, floor])
    body = body - cone
    body = body - cyl(h + 2, 12).translate([0, 0, -1])  # centre drain
    for i in range(6):  # six drain/air slots through the wall and floor
        body = body - box(outer_r + 4, 12, 10).translate([0, -6, -1]).rotate([0, 0, i * 60])
    return body


# ---------------------------------------------------------------- 4. Pole cable clip

def cable_clip(pole_d: float):
    clip, r_out = pole_clip(pole_d, height=14, tab_len=6, tab_w=14)
    cx = r_out + 6 + 6.5
    chan = cyl(14, 8.5) - cyl(16, 4.6).translate([0, 0, -1]) - box(9, 5.5, 16).translate([0, -2.75, -1])
    chan = chan.rotate([0, 0, 90]).translate([cx, 0, 0])  # opening faces +Y (up when the clip is on a horizontal run)
    return clip + chan


# ---------------------------------------------------------------- 5. Plant name stake

def name_stake():
    """Flat stake with a rounded label face; add the name with Bambu Studio's Text tool (emboss 1 mm)."""
    body = box(100, 22, 3)
    tip = box(15.56, 15.56, 3).rotate([0, 0, 45]).translate([100, 0, 0]) ^ box(20, 22, 3).translate([100, 0, 0])
    head = cyl(3, 11).translate([0, 11, 0]) ^ box(11, 22, 3).translate([-11, 0, 0])
    return body + tip + head


if __name__ == "__main__":
    for d in (16, 19, 22):
        save(govee_holder(d), f"govee_h5074_pole_holder_{d}mm")
        save(wyze_mount(d), f"wyze_cam_pole_mount_{d}mm")
        save(cable_clip(d), f"pole_cable_clip_{d}mm")
    save(cup_riser(), "solo_cup_riser")
    save(name_stake(), "plant_name_stake")
