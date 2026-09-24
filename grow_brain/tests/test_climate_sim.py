"""Behaviour check: run decide() against a simple model of the real tent and look at the humidity it holds.

Model (fitted to the seedling tent on 2026-09-24, big light at ~176 W): humidity drifts down ~0.1 pt/min on its own,
the exhaust pulls it toward ~40 % (about 2 pts/min near 62 %), the humidifier adds ~2 pts/min, and the Govee sensor
lags the air by a couple of minutes and reports once a minute. The runtime's switch intervals and the learning of
the swap drop are reproduced, so this exercises the whole humidity loop, not just single decisions.
"""
import math
import random
from datetime import datetime, timedelta, timezone

from grow_brain import controller as C
from grow_brain.targets import Targets


def _simulate(hours=6.0, seed=1, drop0=2.0, k_ex=2.0 / 22, hum_rate=2.0):
    rng = random.Random(seed)
    rh = sensed = 62.0
    now = datetime(2026, 9, 25, 6, 0, tzinfo=timezone(timedelta(hours=-4)))
    t = Targets(21.0, 27.0, 60.0, 75.0, 0.5, 1.0, "06:00", 18)
    roles = ("light", "exhaust_fan", "circulation_fan", "humidifier")
    dev = {r: {"state": "on" if r in ("light", "circulation_fan") else "off", "last": None, "reading": None, "tag": None, "at": None}
           for r in roles}
    drop, swap_min, pending = drop0, None, []
    reported, reported_at = 62.0, now
    below = mist = total = 0
    for step in range(int(hours * 360)):          # 10 s steps
        if step % 6 == 0:
            reported, reported_at = round(sensed, 1), now
        if step % 3 == 0:
            for smp in list(pending):             # the runtime's learning from each refill
                if (now - smp["ended"]).total_seconds() >= C.LAG_S and reported_at > smp["ended"]:
                    pending.remove(smp)
                    if not (dev["exhaust_fan"]["last"] and dev["exhaust_fan"]["last"] > smp["ended"]):
                        drop = round(min(6.0, max(0.3, drop + max(-0.5, min(0.5, 0.5 * (smp["aim"] - reported) / smp["swap"])))), 2)
            devices = {r: C.DeviceInput(r, f"switch.{r}", dev[r]["state"], True, dev[r]["last"], None, None, dev[r]["reading"], dev[r]["tag"])
                       for r in roles}
            ctx = C.ControlContext(now_local=now, stage="seedling", targets=t, day_targets=t, light_scheduled_on=True, lights_on=True,
                                   sensor=C.SensorSnapshot(24.5, reported, None, None, reported_at, False), safety_temp_max_c=35.0,
                                   safety_temp_min_c=12.0, exhaust_ducted=True, paused=False, devices=devices, hum_gain=1.965,
                                   exchange_drop=drop)
            for role, dec in C.decide(ctx).items():
                d = dev.get(role)
                want = "on" if dec.desired else "off"
                if d is None or dec.desired is None or d["state"] == want:
                    continue
                iv = 60 if role == "humidifier" or (role == "exhaust_fan" and d["tag"] == "exhaust_duty") else 180
                if d["last"] and not dec.force and (now - d["last"]).total_seconds() < iv:
                    continue
                if want == "on":
                    d["reading"] = dec.basis if dec.basis is not None else (reported if role == "humidifier" else 24.5)
                    d["tag"], d["at"] = dec.tag, now
                else:
                    if role == "exhaust_fan" and d["tag"] == "exhaust_duty":
                        swap_min = (now - d["at"]).total_seconds() / 60
                    if role == "humidifier" and d["tag"] == "humidifier_ff" and dec.tag == "humidifier_ff_done":
                        swap_s, _ = C.exchange_plan("seedling", drop)
                        pending.append({"aim": C.humidity_aim(t, drop * swap_s / 60), "ended": now, "swap": swap_min or swap_s / 60})
                    d["reading"] = d["tag"] = None
                d["state"], d["last"] = want, now
        ex_on, hum_on = dev["exhaust_fan"]["state"] == "on", dev["humidifier"]["state"] == "on"
        rh += (-0.1 / 12 * (rh - 50) - (k_ex * (rh - 40) if ex_on else 0) + (hum_rate if hum_on else 0)) / 6 + rng.gauss(0, 0.03)
        sensed += (rh - sensed) * (1 - math.exp(-1 / 12))
        below += rh < 60
        mist += hum_on
        total += 1
        now += timedelta(seconds=10)
    return {"below_pct": 100 * below / total, "mist_min_per_h": mist / 6 / hours, "drop": drop}


def test_seedling_humidity_stays_in_the_band():
    r = _simulate()
    assert r["below_pct"] < 2.0              # was ~27 % with the old fixed 3-min-every-30 swaps
    assert r["mist_min_per_h"] < 7.5         # and less water than before (~7.9 min/h)
    assert 1.8 <= r["drop"] <= 3.2           # learned the tent's real swap drop


def test_the_learned_swap_drop_adapts_to_a_different_tent():
    strong = _simulate(hours=8, k_ex=4.0 / 22)       # an exhaust twice as strong as assumed
    weak = _simulate(hours=8, k_ex=1.0 / 22)
    assert strong["drop"] > 3.5 and weak["drop"] < 1.5
    assert strong["below_pct"] < 8.0 and weak["below_pct"] < 2.0
    assert _simulate(hours=8, drop0=5.0)["drop"] < 3.2      # a wrong starting guess comes back down
