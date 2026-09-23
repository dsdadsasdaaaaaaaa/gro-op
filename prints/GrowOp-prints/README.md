# GrowOp 3D prints

Everything here prints in **PETG** on the Bambu (0.4 nozzle, 0.2 mm layers, 4 walls, 30 % infill, no supports unless noted).
Pole clips are made for **19 mm** poles (measured on this tent). Other sizes: edit `POLE_SIZES` in `make_parts.py` and rerun it. The clips open to 90 % of the pole width and have lead-in chamfers: they need a firm push to snap on and then grip. If a clip is loose or won't go on, tell Claude and it will regenerate the size.

## Made for this tent (files in `stl/`)

| File | What it is | Print notes |
|---|---|---|
| `govee_h5074_pole_holder_<pole>mm.stl` | Clips to a pole and cradles the Govee H5074 hygrometer: drop it in from the top, it sits by gravity behind a front lip, with vents on three sides so it reads tent air. Keep it at canopy height and move it up as the plants grow. | Print standing up exactly as the file is oriented (pocket opening up); no supports. |
| `wyze_cam_pole_mount_<pole>mm.stl` | Pole clip with a flat platform for the Wyze cam. Put a **1/4"-20 × 1/2" bolt** up through the platform (the head sits in the shallow recess underneath, about 6 mm of thread shows on top) and screw the camera's base onto it; the base's own joint gives the tilt. Mount it high on a corner pole, aimed down at the plants. | Print exactly as the file is oriented (platform on the bed, clip standing on it). No supports. |
| `pole_cable_clip_<pole>mm.stl` | Small clip that holds one plug cable (up to 8 mm) against a pole. Print 6–8. | Any orientation; 10-minute print. |
| `solo_cup_riser.stl` | Ring that holds a 16 oz solo cup 22 mm off the floor with slots underneath so runoff drains and air gets under the roots. One per plant. | Flat side down. No supports. |
| `plant_name_stake.stl` | Flat stake for the cup/pot. In Bambu Studio right-click → **Add Text**, type "LEVI" or "DAD", emboss 1 mm on the flat face, second colour from the AMS. | Flat. |
| `pot_scale_base.stl` | Floor half of the pot scale (one per plant): a six-arm spider. The load bar's **cable end** lies in the channel on the boss and bolts from underneath; the weight unit clips into the cradle by the rim. | Flat side down, exactly as oriented. No supports. About 130 g. |
| `pot_scale_top.stl` | Deck the pot sits on (one per plant): an eight-arm spider that bolts to the bar's free end. Nothing but the foot block may touch the bar. | Exactly as oriented (deck on the bed, foot block on top). No supports. About 200 g. |
| `sensor_pod_shelf_<pole>mm.stl` | Pole clip with a shelf: the AtomS3 Lite drops into the small pocket, the hub into the big one, push past the lips until they click. One per plant, clipped at mid-height. | As oriented. No supports. |
| `leaf_sensor_stake_clip_<8,10,12>mm.stl` / `leaf_sensor_pole_clip_<pole>mm.stl` | Holds the NCIR unit looking **straight down**. Print the stake size that matches your bamboo stake (measure it with the paper-strip trick), push the unit in, then snap the clip on **upside down** so the pocket faces the leaves, a hand's width above them. | As oriented. No supports. Tiny print. |
| `distance_sensor_light_mount.stl` | Plate for the ToF4M: push the unit into the cradle, zip-tie the plate to the light's frame or hanger bar with the sensor looking down at the plant. Slots run both ways so it straps to a bar in either direction; two screw holes if the light has threads. One per plant. | Flat. No supports. |
| `grove_cable_clip_<pole>mm.stl` | Clip for the flat Grove ribbon cables: slide the ribbon in edge-first through the gap. Print 6. | Any orientation. |

The Govee cradle is cut for a 41 × 41 × 14 mm sensor with 1 mm of slack; if yours measures differently, change `GOVEE_W`/`GOVEE_H`/`GOVEE_T` at the top of the script. Regenerate or resize anything with `../.venv/bin/python make_parts.py` (all dimensions are at the top of the file).

## Building a pot scale

Per scale: the base, the top, one Adafruit 4543 bar, one U180 weight unit, **four M4 × 16 mm bolts** (socket or pan head, any hardware store) and a small screwdriver.

1. The bar has two threaded holes at each end and the wires come out of one end. That end is the **base end**. Lay it in the channel on the base's boss, wires pointing outward past the boss, and put two bolts up through the recesses under the base into the bar. Snug, not gorilla-tight.
2. Set the top on the bar's free end: the foot block's channel straddles the bar. Two bolts down through the recesses in the deck into the bar.
3. Look at it side-on. The middle of the bar must float with air above and below it; only the boss and the foot touch it. The little post under the free end is a stop with a gap: it only touches if a pot is dropped on the scale.
4. Strip 5 mm off the bar's four wires and screw them into the green plug that came with the weight unit, matching the letters printed next to it: **red → E+, black → E−, green → A+, white → A−**. Plug it in, clip the unit into the cradle, plug a Grove cable into it and run it to the pod.
5. In the app, put the empty pot (with saucer) on the deck and tap **Tare**. If the number runs the wrong way when you add weight, say so and it gets flipped in software; it just means the bar is upside down and it doesn't matter.

Two scales are about two-thirds of a spool of PETG. Use 4 walls and 30 % infill for the base, 5 walls and 40 % for the top: it carries the pot on its arms.

## Existing models worth downloading

- **LST hooks** (bend branches down, grip the pot rim): [Low Stress Training Plant Hook Clamp – Printables](https://www.printables.com/model/49901-low-stress-training-lst-plant-hook-clamp), [LST Pot Hook – Thingiverse](https://www.thingiverse.com/thing:7041364), [LST Clip – MakerWorld](https://makerworld.com/en/models/582512-lst-clip-low-stress-training-for-plants), [Adjustable LST Clip – Printables](https://www.printables.com/model/308715-adjustable-low-stress-traininglst-clip). Print 8–10 in PETG when the plants have five or six nodes.
- **Wyze cam alternatives** if you'd rather use a tested design: [Wyze v3 mount for AC Infinity tent (22 mm poles) – Thingiverse](https://www.thingiverse.com/thing:6004384), [Wyze cam grow tent mount – Printables](https://www.printables.com/model/444818-wyze-cam-print-and-grow-tent-mount/files), [Wyze Cam V3 mount, zip-ties to a pole – Printables](https://www.printables.com/model/142541-wyze-cam-v3-mount).
- **Govee H5074 alternatives** (surface mounts, zip-tie to a pole): [Govee H5074 Mount – Printables](https://www.printables.com/model/618117-govee-h5074-mount), [H5074 mount – MakerWorld](https://makerworld.com/en/models/425659).
- **Pole clips and hangers** (16 mm designs): [Hanger clip for 16 mm poles – Printables](https://www.printables.com/model/319571-grow-tent-hangar-clip-for-16mm-poles-great-for-tre), [Pole clamp for fans – Printables](https://www.printables.com/model/9708-grow-tent-pole-clamp-for-fans), [16 mm clamp / light / fan holder – Printables](https://www.printables.com/model/334908-16mm-grow-tent-clamplightfan-holder).
- **Trellis corners** for a screen in flower: [16/19 mm pole to 22 mm PVC holder – Printables](https://www.printables.com/model/244929-16mm-or-19mm-tent-pole-to-22mm-pvc-holder-for-scro), [22 mm (AC Infinity) version – Printables](https://www.printables.com/model/902467-22-mm-tent-pole-ac-infinity-to-12-pvc-holder-for-s).
- **Pot risers** for the 11 L pots later: [Plant Pot Riser Stand – Thingiverse](https://www.thingiverse.com/thing:5827755).

Not made: a loupe phone clip (loupes and phone cases vary too much; tell me your loupe's outer diameter and phone thickness and I'll generate one) and duct parts.
