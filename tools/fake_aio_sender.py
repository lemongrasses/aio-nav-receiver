#!/usr/bin/env python3
"""Fake AIO NAV (0x04, 100 Hz) + dashboard (0x05, 2 Hz) sender for trying the app without a device.

The packets use the same layout as web_monitor (nav/decoder.py, nav/status_packet.py). One cycle
of the default scenario takes 90 s:

    0-6 s    CHECKING, no 0x04 yet
    6-12     NAV_STARTING, 0x04 without alignment
    12-20    KEEP_STILL (ALIGN), vehicle stopped
    20-28    MOVE_STRAIGHT (ALIGN + HEADING)
    28-34    REFINING (+ FINE)
    34-60    READY: the app turns green after 2 s
    60-64    0x05 stops: blocked "no current status packet"
    64-72    READY again; 0x04 pauses for 1 s at 68 s
    72-80    DEGRADED, GNSS quality low
    80-90    READY

    python3 tools/fake_aio_sender.py                      # to 127.0.0.1:9000 (Simulator)
    python3 tools/fake_aio_sender.py --host 192.168.1.23  # to an iPhone on the same Wi-Fi
"""

import argparse
import math
import random
import socket
import struct
import time

ORIGIN = (22.99690, 120.22180)  # Tainan, as web_monitor's fake_nav_sender
EARTH_R = 6378137.0
NAV_STRUCT = struct.Struct("<Qdd28fH3f")
STATUS_STRUCT = struct.Struct("<BBBBIIQIIBBHHH")
ALIGN, HEADING, FINE, GNSS, ZUPT, NHC = 1 << 5, 1 << 6, 1 << 7, 1 << 3, 1 << 0, 1 << 2
STATES = {"CHECKING": 1, "NAV_STARTING": 2, "KEEP_STILL": 3, "MOVE_STRAIGHT": 4, "REFINING": 5,
          "READY": 6, "DEGRADED": 7}
ACTIONS = {"KEEP_STILL": 1, "MOVE_STRAIGHT": 2, "REFINING": 3, "DEGRADED": 3}
HEALTH_ALL = (1 << 14) - 1 | 1 << 16 | 1 << 17


def reverse_bits8(x):
    return int(f"{x & 0xFF:08b}"[::-1], 2)


def frame(msg_id, payload):
    head = b"\x55\xAA" + bytes([msg_id]) + struct.pack("<H", len(payload))
    return head + payload + bytes([sum(head[2:] + payload) & 0xFF])


def phase(t):
    """(state name, nav flags, sending 0x04?, sending 0x05?, inhibit bits) at cycle time t."""
    if t < 6:
        return "CHECKING", 0, False, True, 1 << 5                 # NAV_NOT_RUNNING
    if t < 12:
        return "NAV_STARTING", 0, True, True, 1 << 6 | 1 << 7     # NAV_OUTPUT_STALE, KEEP_STILL_REQ
    if t < 20:
        return "KEEP_STILL", ALIGN | ZUPT, True, True, 1 << 7
    if t < 28:
        return "MOVE_STRAIGHT", ALIGN | HEADING, True, True, 1 << 8
    if t < 34:
        return "REFINING", ALIGN | HEADING, True, True, 1 << 9
    if 60 <= t < 64:
        return "READY", ALIGN | HEADING | FINE, True, False, 0
    if 68 <= t < 69:
        return "READY", ALIGN | HEADING | FINE, False, True, 0
    if 72 <= t < 80:
        return "DEGRADED", ALIGN | HEADING | FINE, True, True, 1 << 4  # GNSS_QUALITY_LOW
    return "READY", ALIGN | HEADING | FINE, True, True, 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--status-port", type=int, help="0x05 port (default: same as --port)")
    ap.add_argument("--ready", action="store_true", help="skip the cycle: always READY and aligned")
    ap.add_argument("--duration", type=float, default=0.0, help="stop after N s (0 = forever)")
    a = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    nav_dest, status_dest = (a.host, a.port), (a.host, a.status_port or a.port)
    session, seq = random.getrandbits(32), 0
    t0 = time.monotonic()
    next_nav, next_status, last_state = t0, t0, None
    sow0 = 300000.0
    driven = 0.0           # distance along the circle, metres
    radius, speed = 80.0, 8.0
    print(f"sending 0x04 to {nav_dest[0]}:{nav_dest[1]} and 0x05 to {status_dest[0]}:{status_dest[1]}")
    try:
        while True:
            now = time.monotonic()
            t = now - t0
            if a.duration and t >= a.duration:
                break
            ct = 40.0 if a.ready else t % 90
            state, flags, send_nav, send_status, inhibit = phase(ct)

            if now >= next_nav:
                next_nav += 0.01
                moving = state not in ("CHECKING", "NAV_STARTING", "KEEP_STILL")
                v = speed if moving else 0.0
                driven += v * 0.01
                a_ = driven / radius
                north, east = radius * math.sin(a_), radius * (1 - math.cos(a_))
                vn, ve = v * math.cos(a_), v * math.sin(a_)
                heading = math.degrees(a_) % 360.0
                if heading > 180:
                    heading -= 360                                   # sent as -180..180
                lat = ORIGIN[0] + math.degrees(north / EARTH_R)
                lon = ORIGIN[1] + math.degrees(east / (EARTH_R * math.cos(math.radians(ORIGIN[0]))))
                gnss_ok = state != "DEGRADED"
                f = flags | (GNSS if gnss_ok and int(t * 100) % 100 == 0 else 0) | (NHC if moving else 0)
                pos_sigma = (0.03 if gnss_ok else 0.4 + 0.05 * (ct - 72)) + 0.01 * math.sin(t * 0.2)
                hdg_sigma = 5.0 if not flags & HEADING else (0.4 if not flags & FINE else 0.12)
                stds = (pos_sigma, pos_sigma * 1.1, pos_sigma * 2, 0.02, 0.02, 0.03, 0.05, 0.05, hdg_sigma)
                payload = NAV_STRUCT.pack(int((sow0 + t) * 1e6), lat, lon, 35.0 + 0.5 * math.sin(t * 0.1),
                                          vn, ve, 0.02 * math.sin(t), 1.2 * math.sin(t * 0.7),
                                          -0.8 * math.cos(t * 0.5), heading, *stds,
                                          1.5, -0.7, 2.1, 0.3, -0.2, 0.5, 120, -80, 40, 200, 150, -90,
                                          reverse_bits8(f), 1.0, 0.2, -0.4)
                if send_nav:
                    sock.sendto(frame(0x04, payload), nav_dest)

            changed = state != last_state
            if now >= next_status or changed:
                next_status = now + 0.5
                last_state = state
                if send_status:
                    seq = (seq + 1) & 0xFFFFFFFF
                    gnss_quality = 2 if state == "DEGRADED" else 4
                    payload = STATUS_STRUCT.pack(1, STATES[state], ACTIONS.get(state, 0), gnss_quality, session,
                                                 seq, int(t * 1000), HEALTH_ALL & ~(inhibit << 0), inhibit,
                                                 flags, 0, 1000, 10 if send_nav else 0xFFFF, 0)
                    sock.sendto(frame(0x05, payload), status_dest)
                if changed:
                    print(f"[{t:6.1f}s] {state}{'' if send_status else ' (0x05 paused)'}"
                          f"{'' if send_nav else ' (0x04 paused)'}", flush=True)

            time.sleep(max(0.0, min(next_nav, next_status) - time.monotonic()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
