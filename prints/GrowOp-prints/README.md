# GrowOp 3D prints

Everything here prints in **PETG** on the Bambu (0.4 nozzle, 0.2 mm layers, 4 walls, 30 % infill, no supports unless noted).
Pole clips come in **16, 19 and 22 mm** versions: measure your tent pole with a ruler across its width and pick the matching file. The clips open to 90 % of the pole width and have lead-in chamfers: they need a firm push to snap on and then grip. If one is loose, print the next size down; if it won't go on, the next size up.

## Made for this tent (files in `stl/`)

| File | What it is | Print notes |
|---|---|---|
| `govee_h5074_pole_holder_<pole>mm.stl` | Clips to a pole and cradles the Govee H5074 hygrometer: drop it in from the top, it sits by gravity behind a front lip, with vents on three sides so it reads tent air. Keep it at canopy height and move it up as the plants grow. | Print standing up exactly as the file is oriented (pocket opening up); no supports. |
| `wyze_cam_pole_mount_<pole>mm.stl` | Pole clip with a flat platform for the Wyze cam. Put a **1/4"-20 × 1/2" bolt** up through the platform (the head sits in the shallow recess underneath, about 6 mm of thread shows on top) and screw the camera's base onto it; a 1 mm rim keeps the base from spinning, and the base's own joint gives the tilt. Mount it high on a corner pole, aimed down at the plants. | Print upside down (platform on the bed) so the counterbore prints clean. No supports. |
| `pole_cable_clip_<pole>mm.stl` | Small clip that holds one plug cable (up to 8 mm) against a pole. Print 6–8. | Any orientation; 10-minute print. |
| `solo_cup_riser.stl` | Ring that holds a 16 oz solo cup 22 mm off the floor with slots underneath so runoff drains and air gets under the roots. One per plant. | Flat side down. No supports. |
| `plant_name_stake.stl` | Flat stake for the cup/pot. In Bambu Studio right-click → **Add Text**, type "LEVI" or "DAD", emboss 1 mm on the flat face, second colour from the AMS. | Flat. |

The Govee cradle is cut for a 41 × 41 × 14 mm sensor with 1 mm of slack; if yours measures differently, change `GOVEE_W`/`GOVEE_H`/`GOVEE_T` at the top of the script. Regenerate or resize anything with `../.venv/bin/python make_parts.py` (all dimensions are at the top of the file).

## Existing models worth downloading

- **LST hooks** (bend branches down, grip the pot rim): [Low Stress Training Plant Hook Clamp – Printables](https://www.printables.com/model/49901-low-stress-training-lst-plant-hook-clamp), [LST Pot Hook – Thingiverse](https://www.thingiverse.com/thing:7041364), [LST Clip – MakerWorld](https://makerworld.com/en/models/582512-lst-clip-low-stress-training-for-plants), [Adjustable LST Clip – Printables](https://www.printables.com/model/308715-adjustable-low-stress-traininglst-clip). Print 8–10 in PETG when the plants have five or six nodes.
- **Wyze cam alternatives** if you'd rather use a tested design: [Wyze v3 mount for AC Infinity tent (22 mm poles) – Thingiverse](https://www.thingiverse.com/thing:6004384), [Wyze cam grow tent mount – Printables](https://www.printables.com/model/444818-wyze-cam-print-and-grow-tent-mount/files), [Wyze Cam V3 mount, zip-ties to a pole – Printables](https://www.printables.com/model/142541-wyze-cam-v3-mount).
- **Govee H5074 alternatives** (surface mounts, zip-tie to a pole): [Govee H5074 Mount – Printables](https://www.printables.com/model/618117-govee-h5074-mount), [H5074 mount – MakerWorld](https://makerworld.com/en/models/425659).
- **Pole clips and hangers** (16 mm designs): [Hanger clip for 16 mm poles – Printables](https://www.printables.com/model/319571-grow-tent-hangar-clip-for-16mm-poles-great-for-tre), [Pole clamp for fans – Printables](https://www.printables.com/model/9708-grow-tent-pole-clamp-for-fans), [16 mm clamp / light / fan holder – Printables](https://www.printables.com/model/334908-16mm-grow-tent-clamplightfan-holder).
- **Trellis corners** for a screen in flower: [16/19 mm pole to 22 mm PVC holder – Printables](https://www.printables.com/model/244929-16mm-or-19mm-tent-pole-to-22mm-pvc-holder-for-scro), [22 mm (AC Infinity) version – Printables](https://www.printables.com/model/902467-22-mm-tent-pole-ac-infinity-to-12-pvc-holder-for-s).
- **Pot risers** for the 11 L pots later: [Plant Pot Riser Stand – Thingiverse](https://www.thingiverse.com/thing:5827755).

Not made: a loupe phone clip (loupes and phone cases vary too much; tell me your loupe's outer diameter and phone thickness and I'll generate one) and duct parts.
