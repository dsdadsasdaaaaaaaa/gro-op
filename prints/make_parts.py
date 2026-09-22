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
SEG = 96  # circle resolution

# ---- Govee H5074 body (square puck). Measured values from the product spec; cradle adds clearance.
GOVEE_W = 41.0
GOVEE_H = 41.0
GOVEE_T = 13.5
CLEAR = 0.6


def cyl(h, r, seg=SEG):
    return Manifold.cylinder(h, r, r, seg)


def box(x, y, z, center=False):
    return Manifold.cube([x, y, z], center)


def save(part: Manifold, name: str) -> None:
    mesh = part.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    tris = np.asarray(mesh.tri_verts)
    tm = trimesh.Trimesh(vertices=verts, faces=tris, process=False)
    assert tm.is_watertight, f"{name} is not watertight"
    tm.export(OUT / f"{name}.stl")
    print(f"{name}.stl  {tm.extents.round(1)} mm  volume {tm.volume/1000:.1f} cm³")


# ---------------------------------------------------------------- pole clip (snap-on C clip + tab)

def pole_clip(pole_d: float, height: float = 22.0, wall: float = 3.2, tab_len: float = 14.0, tab_w: float = 20.0):
    """A C-shaped clip that snaps onto a vertical tent pole. Tab points in +X. Pole axis = Z."""
    r_in = pole_d / 2 + 0.25
    r_out = r_in + wall
    ring = cyl(height, r_out) - cyl(height, r_in).translate([0, 0, -1]).scale([1, 1, 1.2])
    # opening on the -X side, 80% of the pole diameter so PETG snaps over the pole
    gap = pole_d * 0.8
    ring = ring - box(r_out + 2, gap, height + 2).translate([-(r_out + 2), -gap / 2, -1])
    # small lead-in chamfers at the opening lips
    tab = box(tab_len + r_out, tab_w, height).translate([0, -tab_w / 2, 0])
    tab = tab - cyl(height + 2, r_in).translate([0, 0, -1])
    return ring + tab, r_out


# ---------------------------------------------------------------- 1. Govee H5074 pole holder

def govee_holder(pole_d: float):
    clip, r_out = pole_clip(pole_d, height=GOVEE_H + 2 * 2.4)
    w = GOVEE_W + 2 * CLEAR
    h = GOVEE_H + 2 * 2.4  # cradle height = sensor + top/bottom walls
    t = GOVEE_T + CLEAR
    wall = 2.4
    x0 = r_out + 10  # cradle starts here (in +X)
    # cradle: back plate + top/bottom rails + front retaining lips; open on both sides so the sensor slides in
    body = box(t + wall, w + 2 * wall, h).translate([x0, -(w / 2 + wall), 0])
    pocket = box(t, w, GOVEE_H + 2 * CLEAR).translate([x0 + wall, -w / 2, wall - CLEAR])
    body = body - pocket
    # front opening (sensor face shows through) leaving 4 mm lips top/bottom and 3 mm at the sides
    front = box(wall + 2, w - 6, GOVEE_H - 8 + 2 * CLEAR).translate([x0 + wall + t - 1, -(w - 6) / 2, wall + 4 - CLEAR])
    body = body - front
    # side windows for airflow through the cradle (the sensor must see tent air, not trapped air)
    for sgn in (-1, 1):
        win = box(t - 2, wall + 2, GOVEE_H - 10).translate([x0 + wall + 1, sgn * (w / 2 + wall / 2) - (wall + 2) / 2, wall + 5])
        body = body - win
    # ventilation slots in the back plate
    for i in range(4):
        slot = box(wall + 2, 3, GOVEE_H - 10).translate([x0 - 1, -w / 2 + 6 + i * (w - 12) / 3 - 1.5, wall + 5])
        body = body - slot
    # bridge from clip tab to cradle
    bridge = box(x0 - r_out + 1, 20, h).translate([r_out - 1, -10, 0])
    part = clip + bridge + body
    return part


# ---------------------------------------------------------------- 2. Wyze cam pole mount (1/4"-20 bolt platform)

def wyze_mount(pole_d: float):
    clip, r_out = pole_clip(pole_d, height=24)
    plate_t = 8.0
    plate = 44.0
    x0 = r_out + 8
    arm = box(x0 - r_out + 2, 20, 24).translate([r_out - 1, -10, 0])
    platform = box(plate, plate, plate_t).translate([x0, -plate / 2, 24 - plate_t])
    # 1/4"-20 bolt from below: 6.8 mm through hole + 13 mm counterbore for the head/washer
    cx, cy = x0 + plate / 2, 0
    platform = platform - cyl(plate_t + 2, 3.4).translate([cx, cy, 24 - plate_t - 1])
    platform = platform - cyl(5.0, 6.6).translate([cx, cy, 24 - plate_t - 0.01])
    # cable notch at the back edge of the platform
    platform = platform - box(6, 12, plate_t + 2).translate([x0 + plate - 5, -6, 24 - plate_t - 1])
    return clip + arm + platform


# ---------------------------------------------------------------- 3. Solo cup riser (16 oz cup)

def cup_riser():
    """Holds a standard 16 oz solo cup 22 mm off the floor with open drainage underneath."""
    h = 26.0
    outer_r = 42.0
    body = cyl(h, outer_r)
    # cup taper: bottom Ø ~60 mm, ~72 mm at 22 mm up
    cone = Manifold.cylinder(23, 30.6, 36.6, SEG).translate([0, 0, h - 23 + 0.01])
    body = body - cone
    # drainage: centre hole + 6 side arches so runoff leaves and air gets under the cup
    body = body - cyl(h + 2, 14).translate([0, 0, -1])
    for i in range(6):
        a = i * 60
        arch = box(outer_r + 4, 14, 10).translate([0, -7, -1]).rotate([0, 0, a])
        body = body - arch
    # holes in the cup floor
    for i in range(6):
        a = math.radians(i * 60 + 30)
        body = body - cyl(h + 2, 4).translate([22 * math.cos(a), 22 * math.sin(a), -1])
    return body


# ---------------------------------------------------------------- 4. Pole cable clip

def cable_clip(pole_d: float):
    clip, r_out = pole_clip(pole_d, height=14, tab_len=6, tab_w=14)
    # C channel for a cable up to 8 mm, opening facing up
    cx = r_out + 6 + 6
    chan = cyl(14, 8) - cyl(16, 4.5).translate([0, 0, -1]) - box(8, 4, 16).translate([0, -2, -1])
    chan = chan.rotate([0, 0, 90]).translate([cx, 0, 0])
    return clip + chan


# ---------------------------------------------------------------- 5. Plant name stake

def name_stake():
    """Flat stake with a label face; add the name with Bambu Studio's Text tool (emboss 1 mm)."""
    body = box(100, 22, 3)
    diamond = box(22, 22, 3).rotate([0, 0, 45]).translate([100 + 15.56 - 15.56, 11 - 15.56 + 15.56, 0])
    # a diamond centred on the stake's end gives a symmetric pointed tip once we keep only x >= 100
    diamond = box(22 / 1.4142, 22 / 1.4142, 3).rotate([0, 0, 45]).translate([100, 11 - 11, 0])
    diamond = box(15.56, 15.56, 3).rotate([0, 0, 45]).translate([100, 0, 0])  # 15.56 = 22/sqrt2
    tip = diamond ^ box(20, 22, 3).translate([100, 0, 0])
    return body + tip


if __name__ == "__main__":
    for d in (16, 19, 22):
        save(govee_holder(d), f"govee_h5074_pole_holder_{d}mm")
        save(wyze_mount(d), f"wyze_cam_pole_mount_{d}mm")
        save(cable_clip(d), f"pole_cable_clip_{d}mm")
    save(cup_riser(), "solo_cup_riser")
    save(name_stake(), "plant_name_stake")
