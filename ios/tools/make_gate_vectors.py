#!/usr/bin/env python3
"""Generate MyAppTests/Fixtures/gate_vectors.json from web_monitor's own code.

Packets are built with web_monitor's encoders and fed to its reference VehicleGate; after every
step the verdict and counters are recorded. The Swift tests replay the same packets through
VehicleGate.swift and must get the same result at every step.

    python3 tools/make_gate_vectors.py /path/to/web_monitor
"""

import argparse
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "MyAppTests" / "Fixtures" / "gate_vectors.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("web_monitor", help="path to a web_monitor checkout")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    sys.path.insert(0, str(Path(a.web_monitor).resolve()))
    from aio_system_dashboard.nav import status_packet
    from aio_system_dashboard.nav.decoder import encode_nav_packet, flags_to_int
    from aio_system_dashboard.nav.vehicle_gate import VehicleGate

    aligned = flags_to_int(alignment=True, heading_valid=True, fine_alignment=True, gnss=True)
    coarse = flags_to_int(alignment=True, gnss=True)

    def nav(nav_time, **kw):
        f = dict(time_s=nav_time, latitude=22.9969, longitude=120.2218, height=35.0, heading=45.0,
                 velocity_north=3.0, velocity_east=4.0, flags_c=aligned,
                 stds=(0.05, 0.05, 0.1, 0.02, 0.02, 0.03, 0.05, 0.05, 0.3))
        f.update(kw)
        return encode_nav_packet(**f)

    def status(seq, state=6, inhibit=0, session=0x1234ABCD, action=0):
        return status_packet.encode(dict(state=state, requested_action=action, gnss_quality=4,
                                         session_id=session, sequence=seq, uptime_ms=1000 + seq * 500,
                                         health_flags=0x3FFFF & ~inhibit, inhibit_flags=inhibit,
                                         nav_flags=0xE8, nav_rate_dhz=1000, nav_age_ms=10))

    def corrupt(p):
        b = bytearray(p)
        b[12] ^= 0x5A
        return bytes(b)

    def version2(p):
        b = bytearray(p)
        b[5] = 2
        b[-1] = sum(b[2:-1]) & 0xFF
        return bytes(b)

    def kind(reason):
        for prefix, k in (("no current status", "noStatus"), ("status not READY", "notReady"),
                          ("READY not yet stable", "readyNotStable"), ("navigation data too old", "navTooOld"),
                          ("navigation time did not", "navTimeBackwards"),
                          ("navigation flags not aligned", "notAligned"),
                          ("navigation data not finite", "notFinite"), ("ok", "usable")):
            if reason.startswith(prefix):
                return k
        raise ValueError(reason)

    gate = VehicleGate()
    steps = []
    seq, session = 100, 0x1234ABCD
    nav_time = 345600.0
    dt = 0.1
    for i in range(0, 460):
        t = round(i * dt, 3)
        packets = []

        # 0x04 every step unless paused; special packets at fixed times.
        nav_kw = {}
        send_nav = t >= 0.5
        if 9.0 <= t < 9.8:
            send_nav = False                                   # nav pause -> too old
        if abs(t - 12.0) < 1e-6:
            nav_kw["time_s"] = nav_time - 1.0                  # time goes backwards once
        if 14.0 <= t < 15.0:
            nav_kw["flags_c"] = coarse                         # not fully aligned
        if abs(t - 16.0) < 1e-6:
            nav_kw["latitude"] = math.nan                      # not finite
        if abs(t - 30.0) < 1e-6:
            nav_kw["heading"] = -90.0
        if send_nav:
            if "time_s" not in nav_kw:
                nav_time += dt
                nav_kw["time_s"] = nav_time
            packets.append(nav(nav_kw.pop("time_s"), **nav_kw))

        # 0x05 every 0.5 s with its own scenario.
        if i % 5 == 0 and t >= 1.0 and not (35.0 <= t < 39.0):
            if t < 3.0:
                state, inhibit = 1, 0x20                       # CHECKING, NAV_NOT_RUNNING
            elif t < 5.0:
                state, inhibit = 3, 0x80                       # KEEP_STILL
            else:
                state, inhibit = 6, 0
            if 40.0 <= t < 42.0:
                state, inhibit = 7, 0x10                       # DEGRADED, GNSS_QUALITY_LOW
            seq += 1
            if abs(t - 24.0) < 1e-6:
                seq += 4                                       # four lost
            if abs(t - 26.0) < 1e-6:
                session = 0x0BADF00D                           # dashboard restart
                seq = 1
            p = status(seq, state, inhibit, session, action=1 if state == 3 else 0)
            if abs(t - 18.0) < 1e-6:
                p = corrupt(p)                                 # bad checksum clears
            if abs(t - 21.0) < 1e-6:
                p = version2(p)                                # unknown version clears
            packets.append(p)
            if abs(t - 27.0) < 1e-6:
                packets.append(status(seq - 3, state, inhibit, session))   # reordered by 3
            if abs(t - 25.0) < 1e-6:
                packets.append(status(seq - 10, state, inhibit, session))  # 10 back: second sender
            if abs(t - 29.0) < 1e-6:
                packets.append(status(seq, state, inhibit, session))       # duplicate
        if abs(t - 32.0) < 1e-6:
            packets.append(b"\x55\xAA\x07hello")                         # unknown id
        if abs(t - 33.0) < 1e-6:
            packets.append(b"\x13\x37")                                 # garbage

        for p in packets:
            gate.feed(p, t)
        ok, reason = gate.allowed(t)
        steps.append(dict(t=t, packets=[p.hex() for p in packets], usable=ok, reason=kind(reason),
                          lost=gate.lost, reordered=gate.reordered, bad=gate.bad))

    golden_status = ("55aa052400010600037856341 2e2010000 15cd5b0700000000 ff0f0100 00000000"
                     " e8 00 e803 0c00 0000").replace(" ", "")
    golden_status += f"{sum(bytes.fromhex(golden_status)[2:]) & 0xFF:02x}"
    nav_example = nav(345678.123456, latitude=22.99690123, longitude=120.22180456, height=35.25,
                      velocity_north=1.5, velocity_east=-2.0, velocity_up=0.25, roll=1.25, pitch=-2.5,
                      heading=-90.0, flags_c=aligned | flags_to_int(zupt=True),
                      imu_cal=(1.5, -0.7, 2.1, 0.3, -0.2, 0.5, 120, -80, 40, 200, 150, -90),
                      odo_scale=1.01, mount_pitch=0.5, mount_yaw=-1.5)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(dict(
        source="web_monitor aio_system_dashboard/nav (decoder.py, status_packet.py, vehicle_gate.py)",
        golden_status=golden_status, nav_example=nav_example.hex(), steps=steps), indent=1) + "\n")
    usable = sum(s["usable"] for s in steps)
    print(f"wrote {len(steps)} steps ({usable} usable) to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
