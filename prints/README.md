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
| `trellis_net_hook_<pole>mm.stl` | **Yield.** Snaps onto a corner pole with a notched tab pointing at the middle of the tent. Drop the trellis net's corner cord into the notch: the net pulls it against the tall end lip. Slide the hooks up as the net goes up (start 20–25 cm above the pot rims). Print 4 (8 for a second net layer). | As oriented (ring standing, notch up). No supports. |
| `lst_soil_peg.stl` | **Yield.** Low-stress-training anchor for any pot: push it into the soil near the pot edge, hook end up. Loop a soft plant tie round a branch, pull it down and slip the tie into the crook; the branch pulls up and the tie stays seated in the bend. Print 8–10 before topping (veg day ~12). | Flat. No supports. 4 walls, 40 % infill. |
| `pot_foot.stl` | Three under each 11 L pot, inside the saucer near its edge: lifts the pot 18 mm so runoff drains away instead of soaking back up, and air reaches the bottom roots. Print 6. | Flat. 4 walls, 30 % infill (each pot puts ~12 kg on three feet). |
| `bluetooth_proxy_atom_mount.stl` | Holds an M5Stack **ATOM Lite** (the Bluetooth proxy that fixes the tent hygrometer's dropouts): push it in past the corner lips, USB-C side open. Zip-tie it just **outside** the tent, within a metre of the Govee (a shelf leg, the tent's outer straps), or stand it on the floor there. | Flat. No supports. |

The Govee cradle is cut for a 41 × 41 × 14 mm sensor with 1 mm of slack; if yours measures differently, change `GOVEE_W`/`GOVEE_H`/`GOVEE_T` at the top of the script. Regenerate or resize anything with `python make_parts.py` (needs manifold3d, trimesh, numpy) (all dimensions are at the top of the file).

## Cheap upgrades (October 2026 plan)

| When | What | Cost | Why |
|---|---|---|---|
| Now | **M5Stack ATOM Lite** + USB-C cable + any USB charger, flashed as a Bluetooth proxy | ~CA$20–30 | The Govee hygrometer reaches Home Assistant over Bluetooth through the tent wall and drops out, which puts the tent in safe mode. A proxy beside the tent forwards it over Wi-Fi. Flash it from Chrome or Edge at esphome.github.io/bluetooth-proxies (plug it in by USB, Connect, pick M5Stack Atom Lite, enter the Wi-Fi; no code), then click Configure on the new device in Home Assistant. The sensor names stay the same. |
| Now | A smart plug with **its own app** (e.g. Wyze Plug) for the Home Assistant box | ~CA$15 | Lets you power-cycle the box from anywhere when Home Assistant hangs. Must not be controlled through Home Assistant. |
| Veg ~day 12 | 8–10 `lst_soil_peg`, soft plant ties | ~CA$8 | Topping + low-stress training spreads the plant flat under the light: more tops at the same height = more bud. |
| Veg ~day 18 | Trellis net for a 3×3 ft (90 cm) tent + 4 `trellis_net_hook` | ~CA$12 | Holds every top at the same height and supports the buds in flower. |
| Transplant | 6 `pot_foot` | filament | Drainage and air under the 11 L pots. |
| Transplant (optional) | **Blumat Tropf** gravity drip kit, 2 carriers per pot, fed from a bucket on a shelf above the pots | ~CA$60–90 | Waters by itself when the soil dries (ceramic sensors, no power, nothing to fail if Home Assistant is down). Fiddly to set up the first time and best with plain water or organic feeds; skip it if you'd rather keep watering by finger-test. |
| Flip to flower | A CA$10 mechanical timer in series with the light plug, set 06:00–18:00 | ~CA$10 | Backstop: if the box dies with the light on, the timer still gives the plants their 12 h of dark. |

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
