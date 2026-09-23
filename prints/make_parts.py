"""Parametric grow-tent parts for GrowOp, generated with manifold3d and exported as STL.

Run:  ../.venv/bin/python make_parts.py
Everything is in millimetres. Print in PETG. Pole clips are made for POLE_SIZES (Levi's tent: 19 mm).
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

POLE_SIZES = (19,)  # tent pole diameters to generate; Levi's tent measured 19 mm. Add 16/18/22 here for other tents.
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
    # cable notch at the back edge
    platform = platform - box(6, 12, plate_t + 3).translate([x0 + plate - 5, -6, height - plate_t - 1])
    # exported upside down: the platform prints flat on the bed, the clip stands on it
    return (clip + arm + platform).rotate([180, 0, 0]).translate([0, 0, height])


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




# ================================================================ Sensor parts (M5Stack Grove units)
# Unit outer sizes in mm (L x W x H) from the M5Stack docs. Cradles hold a unit by its four corners with
# small snap lips, so every edge centre stays open for the Grove plug and the front face is fully exposed.
ATOM = (24.0, 24.0, 9.5)      # C124 AtomS3 Lite
HUB = (32.0, 24.0, 12.0)      # U006 1-to-3 hub
U180 = (56.0, 24.0, 11.3)     # U180 Weight I2C unit (HX711 + screw plug)
NCIR = (32.0, 24.0, 8.6)      # U028 NCIR leaf-temperature unit
TOF = (32.0, 24.0, 8.0)       # U172 ToF4M distance unit

# Adafruit 4543 load bar: 75 x 12.7 x 12.7 mm, 4 x M4 threaded holes 5.5 and 15.5 mm from each end,
# strain-gauge bumps within +/-12 mm of the middle (keep everything clear of them).
BAR_L, BAR_W, BAR_H = 75.0, 12.7, 12.7
BAR_HOLES = (5.5, 15.5)
M4_THRU = 4.4
M4_HEAD = 8.5                 # counterbore for an M4 socket / pan head
BAR_Z = 14.0                  # bar underside height above the floor (base boss height)
DECK_Z0 = 30.0                # top spider underside (3.3 mm above the bar's top face)
RIB_H_TOP = 14.0
DECK_TOP = DECK_Z0 + RIB_H_TOP   # 44 mm: the pot sits here
SPIDER_R = 116.0              # 232 mm across: fits a 256 mm bed


def unit_cradle(L, W, H, post=1.6, leg=5.0, floor=3.0, clear=0.5, lip=0.6, lip_h=1.2):
    """Cradle for an L x W x H unit: floor plate + four L-shaped corner posts with inward snap lips.
    Pocket corner at (post, post, floor); footprint (L+clear+2*post) x (W+clear+2*post); front is +Z."""
    Li, Wi = L + clear, W + clear
    Lo, Wo = Li + 2 * post, Wi + 2 * post
    zl = floor + H + clear                 # lip underside = top of the unit
    Hp = zl + lip_h + 0.6
    body = box(Lo, Wo, floor)
    for sx in (0, 1):
        for sy in (0, 1):
            xa = 0 if sx == 0 else Lo - (leg + post)      # leg along X starts here
            ya = 0 if sy == 0 else Wo - (leg + post)      # leg along Y starts here
            xw = 0 if sx == 0 else Lo - post              # wall along Y (thickness in X) at this x
            yw = 0 if sy == 0 else Wo - post              # wall along X (thickness in Y) at this y
            body = body + box(leg + post, post, Hp).translate([xa, yw, 0])
            body = body + box(post, leg + post, Hp).translate([xw, ya, 0])
            # lips over the pocket
            body = body + box(leg, lip, lip_h).translate([xa if sx == 0 else Lo - post - leg, post if sy == 0 else Wo - post - lip, zl])
            body = body + box(lip, leg, lip_h).translate([post if sx == 0 else Lo - post - lip, ya if sy == 0 else Wo - post - leg, zl])
    return body


def cradle_footprint(L, W, post=1.6, clear=0.5):
    return L + clear + 2 * post, W + clear + 2 * post


def _spider(n_arms, rib_w, rib_h, ring_w, z0=0.0, flange_w=0.0, flange_t=0.0):
    R = SPIDER_R
    body = (cyl(rib_h, R) - cyl(rib_h + 2, R - ring_w).translate([0, 0, -1])).translate([0, 0, z0])
    for i in range(n_arms):
        arm = box(R - 2, rib_w, rib_h).translate([0, -rib_w / 2, z0])
        if flange_w:
            arm = arm + box(R - 2, flange_w, flange_t).translate([0, -flange_w / 2, z0 + rib_h - flange_t])
        body = body + arm.rotate([0, 0, i * 360 / n_arms])
    return body


# ---------------------------------------------------------------- 6. Pot scale: base spider (fixed end + weight unit cradle)

def scale_base():
    """Sits on the floor. The load bar's CABLE end bolts to the boss (M4 x 16 from below).
    The weight unit clips into the cradle; its Grove cable leaves toward the pole."""
    body = _spider(6, rib_w=5.0, rib_h=10.0, ring_w=8.0)
    # fixed-end boss with a 3 mm deep channel that locates the bar
    boss = box(25, 24, BAR_Z + 3).translate([-41, -12, 0])
    boss = boss - box(27, BAR_W + 0.5, 4).translate([-42, -(BAR_W + 0.5) / 2, BAR_Z])
    body = body + boss
    # overload stop: 1.5 mm under the bar's free end so a dropped pot can't bend the bar
    body = body + box(10, 10, BAR_Z - 1.5).translate([26, -5, 0])
    for hx in BAR_HOLES:
        x = -BAR_L / 2 + hx
        body = body - cyl(BAR_Z + 6, M4_THRU / 2).translate([x, 0, -1])
        body = body - cyl(6, M4_HEAD / 2).translate([x, 0, -0.01])
    # weight-unit cradle on a pad, tangential to the ring at 150 deg (between two arms)
    Lo, Wo = cradle_footprint(U180[0], U180[1])
    cr = unit_cradle(*U180).translate([-Lo / 2, -Wo / 2, 0]).rotate([0, 0, 90]).translate([97, 0, 0]).rotate([0, 0, 150])
    body = body + cr
    return body


# ---------------------------------------------------------------- 7. Pot scale: top spider (free end, pot sits on it)

def scale_top():
    """Bolts to the bar's FREE end from above (M4 x 16). Exported upside down so the flat deck prints on the bed."""
    body = _spider(8, rib_w=5.0, rib_h=RIB_H_TOP, ring_w=6.0, z0=DECK_Z0, flange_w=14.0, flange_t=3.0)
    hub = box(82, 24, RIB_H_TOP).translate([-41, -12, DECK_Z0])
    foot_z = BAR_Z + BAR_H - 3.0                       # 23.7: foot walls straddle the bar by 3 mm
    foot = box(25, 24, DECK_Z0 - foot_z).translate([16, -12, foot_z])
    foot = foot - box(27, BAR_W + 0.5, 3.01).translate([15, -(BAR_W + 0.5) / 2, foot_z - 0.01])  # channel, ceiling on the bar top
    body = body + hub + foot
    head_z = BAR_Z + BAR_H + 8.0                        # 8 mm of plastic under the bolt head
    for hx in BAR_HOLES:
        x = BAR_L / 2 - hx
        body = body - cyl(DECK_TOP, M4_THRU / 2).translate([x, 0, foot_z - 1])
        body = body - cyl(DECK_TOP - head_z + 1, M4_HEAD / 2).translate([x, 0, head_z])
    return body.rotate([180, 0, 0]).translate([0, 0, DECK_TOP])


# ---------------------------------------------------------------- 8. Pod shelf: AtomS3 Lite + hub on a pole clip

def pod_shelf(pole_d: float):
    height = 24.0
    clip, r_out = pole_clip(pole_d, height=height)
    x0 = r_out + 8
    arm = box(x0 - r_out + 2, 20, height).translate([r_out - 1, -10, 0])
    La, Wa = cradle_footprint(ATOM[0], ATOM[1])
    Lh, Wh = cradle_footprint(HUB[0], HUB[1])
    gap = 4.0
    shelf_w = Wa + Wh + gap + 4
    shelf_l = max(La, Lh) + 4
    shelf = box(shelf_l, shelf_w, 3).translate([x0, -shelf_w / 2, 0])   # on the bed: no overhang
    ya = -shelf_w / 2 + 2
    yh = ya + Wa + gap
    body = clip + arm + shelf
    body = body + unit_cradle(*ATOM).translate([x0 + 2, ya, 0])
    body = body + unit_cradle(*HUB).translate([x0 + 2, yh, 0])
    return body


# ---------------------------------------------------------------- 9. Leaf-sensor clip: NCIR unit looks straight down from a stake or pole

def ncir_mount(clip_d: float):
    """C-clip for a stake/pole of clip_d mm with the NCIR cradle on a short arm. Prints with the pocket
    facing up; INSTALL IT UPSIDE DOWN so the sensor looks down at the leaves. The lips hold the unit."""
    height = 14.0
    clip, r_out = pole_clip(clip_d, height=height, tab_len=8, tab_w=20)
    Lo, Wo = cradle_footprint(NCIR[0], NCIR[1])
    x0 = r_out + 6
    arm = box(x0 - r_out + 3, 20, height).translate([r_out - 1, -10, 0])
    # cradle long side tangential so the Grove plug leaves sideways; unit centre 20 mm past the arm
    cr = unit_cradle(*NCIR).rotate([0, 0, 90]).translate([x0 + Wo, -Lo / 2, 0])
    return clip + arm + cr


# ---------------------------------------------------------------- 10. Distance-sensor plate: zip-ties to the light frame, sensor faces down

def tof_light_mount():
    PL, PW, T = 56.0, 50.0, 3.0
    Lo, Wo = cradle_footprint(TOF[0], TOF[1])
    body = box(PL, PW, T) + unit_cradle(*TOF).translate([(PL - Lo) / 2, (PW - Wo) / 2, 0])
    slot_l, slot_w = 7.0, 3.2
    # ties running along Y (bar under the plate runs along X): slots long in X
    for x in (8.0, PL - 8.0):
        for y in (4.5, PW - 4.5):
            body = body - box(slot_l, slot_w, T + 2).translate([x - slot_l / 2, y - slot_w / 2, -1])
    # ties running along X: slots long in Y
    for y in (9.0, PW - 9.0):
        for x in (4.0, PL - 4.0):
            body = body - box(slot_w, slot_l, T + 2).translate([x - slot_w / 2, y - slot_l / 2, -1])
    # screw holes if the light has a place for them
    for x in (5.0, PL - 5.0):
        body = body - cyl(T + 2, 2.1).translate([x, PW / 2, -1])
    return body


# ---------------------------------------------------------------- 11. Grove ribbon-cable clip for the pole

def grove_clip(pole_d: float):
    clip, r_out = pole_clip(pole_d, height=12, tab_len=6, tab_w=14)
    x0 = r_out + 5
    blk = box(13, 9, 12).translate([x0, -4.5, 0])
    blk = blk - box(8.4, 3.4, 14).translate([x0 + 2.3, -1.7, -1])     # ribbon channel, width along X
    blk = blk - box(4, 2.4, 14).translate([x0 + 10, -1.2, -1])        # entry gap: ribbon slides in edge-first
    return clip + blk


if __name__ == "__main__":
    for d in POLE_SIZES:
        save(govee_holder(d), f"govee_h5074_pole_holder_{d}mm")
        save(wyze_mount(d), f"wyze_cam_pole_mount_{d}mm")
        save(cable_clip(d), f"pole_cable_clip_{d}mm")
    save(cup_riser(), "solo_cup_riser")
    save(name_stake(), "plant_name_stake")
    for d in POLE_SIZES:
        save(pod_shelf(d), f"sensor_pod_shelf_{d}mm")
        save(ncir_mount(d), f"leaf_sensor_pole_clip_{d}mm")
        save(grove_clip(d), f"grove_cable_clip_{d}mm")
    for d in (8, 10, 12):
        save(ncir_mount(d), f"leaf_sensor_stake_clip_{d}mm")
    save(scale_base(), "pot_scale_base")
    save(scale_top(), "pot_scale_top")
    save(tof_light_mount(), "distance_sensor_light_mount")
