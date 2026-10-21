#!/usr/bin/env python3
"""Generate fixtures/gate_vectors.json: a scripted packet stream and the desktop Gate's verdict at
every step.

The desktop gate (src/aio_receiver/core/gate.py) is the reference for the rules; the iOS tests replay
the same packets through VehicleGate.swift and must match at every step, and tests/test_shared_vectors.py
checks that the desktop gate still produces this file. Regenerate after changing the rules:

    python tools/make_gate_vectors.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from aio_receiver.core import protocol as P  # noqa: E402
from aio_receiver.core.gate import Gate, Reason  # noqa: E402

OUT = ROOT / "fixtures" / "gate_vectors.json"
ALIGNED = 0b1110_1000          # ALIGN | HEADING | FINE | GNSS (C-side bit order)
COARSE = 0b0010_1000           # ALIGN | GNSS
ZUPT = 0b0000_0001
KIND = {Reason.USABLE: "usable", Reason.NO_STATUS: "noStatus", Reason.NOT_READY: "notReady",
        Reason.READY_NOT_STABLE: "readyNotStable", Reason.NAV_STALE: "navTooOld",
        Reason.NAV_TIME_NOT_FORWARD: "navTimeBackwards", Reason.NAV_NOT_ALIGNED: "notAligned",
        Reason.NAV_NOT_FINITE: "notFinite"}


def nav(time_s: float, **kw: object) -> bytes:
    f: dict = dict(lat=22.9969, lon=120.2218, height=35.0, heading=45.0, vn=3.0, ve=4.0, flags=ALIGNED,
                   stds=(0.05, 0.05, 0.1, 0.02, 0.02, 0.03, 0.05, 0.05, 0.3))
    f.update(kw)
    return P.encode_nav(time_s, **f)


def status(seq: int, state: int = 6, inhibit: int = 0, session: int = 0x1234ABCD, action: int = 0) -> bytes:
    return P.encode_status(state, action, session, seq, gnss_quality=4, uptime_ms=1000 + seq * 500,
                           health=0x3FFFF & ~inhibit, inhibit=inhibit, nav_flags=0xE8, nav_rate_dhz=1000,
                           nav_age_ms=10)


def corrupt(p: bytes) -> bytes:
    b = bytearray(p)
    b[12] ^= 0x5A
    return bytes(b)


def version2(p: bytes) -> bytes:
    b = bytearray(p)
    b[5] = 2
    b[-1] = sum(b[2:-1]) & 0xFF
    return bytes(b)


def at(t: float, x: float) -> bool:
    return abs(t - x) < 1e-6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    gate = Gate()
    steps = []
    seq, session = 100, 0x1234ABCD
    nav_time = 345600.0
    dt = 0.1
    for i in range(460):
        t = round(i * dt, 3)
        packets = []

        # 0x04 every step unless paused; special packets at fixed times.
        kw: dict = {}
        send_nav = t >= 0.5
        if 9.0 <= t < 9.8:
            send_nav = False                                   # nav pause -> too old
        time_s = None
        if at(t, 12.0):
            time_s = nav_time - 1.0                            # time goes backwards once
        if 14.0 <= t < 15.0:
            kw["flags"] = COARSE                               # not fully aligned
        if at(t, 16.0):
            kw["lat"] = math.nan                               # not finite
        if at(t, 30.0):
            kw["heading"] = -90.0
        if send_nav:
            if time_s is None:
                nav_time += dt
                time_s = nav_time
            packets.append(nav(time_s, **kw))

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
            if at(t, 24.0):
                seq += 4                                       # four lost
            if at(t, 26.0):
                session, seq = 0x0BADF00D, 1                   # dashboard restart
            p = status(seq, state, inhibit, session, action=1 if state == 3 else 0)
            if at(t, 18.0):
                p = corrupt(p)                                 # bad checksum clears
            if at(t, 21.0):
                p = version2(p)                                # unknown version clears
            packets.append(p)
            if at(t, 25.0):
                packets.append(status(seq - 10, state, inhibit, session))  # 10 back: second sender, clears
            if at(t, 27.0):
                packets.append(status(seq - 3, state, inhibit, session))   # reordered by 3, ignored
            if at(t, 29.0):
                packets.append(status(seq, state, inhibit, session))       # duplicate, ignored
        if at(t, 32.0):
            packets.append(b"\x55\xAA\x07hello")                         # unknown id
        if at(t, 33.0):
            packets.append(b"\x13\x37")                                 # garbage
        if at(t, 34.0):
            packets.append(nav(nav_time + 0.05) + b"\x00")              # one byte too long: invalid

        for p in packets:
            gate.feed(p, t, None)
        v = gate.verdict(t)
        c = gate.count
        steps.append(dict(t=t, packets=[p.hex() for p in packets], usable=v.usable, reason=KIND[v.reason],
                          nav=c.nav, status=c.status, lost=c.lost, reordered=c.reordered, conflicts=c.conflicts,
                          bad=c.bad))

    golden = P.encode_status(6, 0, 0x12345678, 482, gnss_quality=3, uptime_ms=123456789, health=0x10FFF,
                             inhibit=0, nav_flags=0xE8, nav_rate_dhz=1000, nav_age_ms=12)
    nav_example = nav(345678.123456, lat=22.99690123, lon=120.22180456, height=35.25, vn=1.5, ve=-2.0, vu=0.25,
                      roll=1.25, pitch=-2.5, heading=-90.0, flags=ALIGNED | ZUPT,
                      imu=(1.5, -0.7, 2.1, 0.3, -0.2, 0.5, 120, -80, 40, 200, 150, -90),
                      odo_scale=1.01, mount_pitch=0.5, mount_yaw=-1.5)

    Path(a.out).write_text(json.dumps(dict(
        source="tools/make_gate_vectors.py (desktop aio_receiver.core.gate.Gate)",
        golden_status=golden.hex(), nav_example=nav_example.hex(), steps=steps), indent=1) + "\n")
    print(f"wrote {len(steps)} steps ({sum(s['usable'] for s in steps)} usable) to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
