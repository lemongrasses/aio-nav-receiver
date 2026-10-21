"""Test sender: 100 Hz 0x04 plus 2 Hz 0x05 walking through the alignment sequence.

Cycle (seconds): 0-8 KEEP_STILL, 8-16 MOVE_STRAIGHT, 16-24 REFINING, 24-50 READY,
50-55 no 0x05 (receiver must block), then a new session starts.

    python tools/fake_sender.py --host 127.0.0.1 --port 9000
"""

import argparse
import math
import random
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from aio_receiver.core import protocol as P

ALIGN, HEADING, FINE, GNSS, ZUPT, NHC = 1 << 5, 1 << 6, 1 << 7, 1 << 3, 1 << 0, 1 << 2
PHASES = (  # (until s, state, action, nav flags, inhibit bits, moving)
    (8, 3, 1, ZUPT, (7, 8, 9), False),
    (16, 4, 2, ALIGN | NHC, (8, 9), True),
    (24, 5, 3, ALIGN | HEADING | NHC, (9,), True),
    (50, 6, 0, ALIGN | HEADING | FINE | NHC, (), True),
    (55, None, None, ALIGN | HEADING | FINE | NHC, (), True),
)
ORIGIN = (22.99690, 120.22180)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--seconds", type=float, default=0.0, help="stop after this long (0 = run until Ctrl+C)")
    a = ap.parse_args()
    sock, dest = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (a.host, a.port)
    t0 = time.perf_counter()
    session, seq, last_status, next_tick, cycle = random.getrandbits(32), 0, -1.0, t0, 0
    print(f"sending 0x04 + 0x05 to {a.host}:{a.port}")
    while True:
        now = time.perf_counter()
        t = now - t0
        if a.seconds and t >= a.seconds:
            return
        c, ct = divmod(t, 55.0)
        if int(c) != cycle:
            cycle, session = int(c), random.getrandbits(32)
        phase = next(p for p in PHASES if ct < p[0])
        _, state, action, flags, inhibit, moving = phase
        ang = 0.1 * t if moving else 0.0
        if int(t * 100) % 100 == 0:
            flags |= GNSS
        lat = ORIGIN[0] + math.degrees(80 * math.sin(ang) / 6378137.0)
        lon = ORIGIN[1] + math.degrees(80 * (1 - math.cos(ang)) / (6378137.0 * math.cos(math.radians(ORIGIN[0]))))
        spd = 8.0 if moving else 0.0
        hdg = math.degrees(ang) % 360 - 180            # sent as -180..180 on purpose
        sock.sendto(P.encode_nav(300000 + t, lat, lon, 35.0, spd * math.cos(ang), spd * math.sin(ang), 0.02,
                                 1.1 * math.sin(t), -0.6, hdg, flags,
                                 (0.05, 0.05, 0.1, 0.02, 0.02, 0.03, 0.05, 0.05, 0.3)), dest)
        if state is not None and now - last_status >= 0.5:
            last_status = now
            seq = (seq + 1) & 0xFFFFFFFF
            inh = sum(1 << b for b in inhibit)
            health = 0x3FF & ~inh if state != 6 else 0x10FFF
            sock.sendto(P.encode_status(state, action, session, seq, gnss_quality=3, uptime_ms=int(t * 1000),
                                        health=health, inhibit=inh, nav_flags=flags, nav_rate_dhz=1000,
                                        nav_age_ms=10), dest)
        next_tick += 0.01
        d = next_tick - time.perf_counter()
        if d > 0:
            time.sleep(d)
        else:
            next_tick = time.perf_counter()


if __name__ == "__main__":
    main()
