"""Check that our gate agrees with web_monitor's reference VehicleGate.

    python tools/parity_vehicle_gate.py --web-monitor ../web_monitor [--recording logs/aio_….bin]

Random streams (bad checksums, session changes, small reordering, time going back, unaligned flags,
NaN) and, optionally, a real recording: both gates get every packet and are asked at every packet
and every deadline. Expected result: 0 mismatches.

Known, intended difference (the spec): a 0x05 sequence going back by more than 5 clears the
authorisation here (a second sender); VehicleGate counts it as reordering. Random streams below
never go back that far.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Iterable, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from aio_receiver.core import protocol as P
from aio_receiver.core.gate import Gate
from aio_receiver.io.recording import Recording


def random_stream(n: int, seed: int) -> Iterable[Tuple[float, bytes]]:
    rnd = random.Random(seed)
    t, seq, navt = 0.0, 0, 5000.0
    for _ in range(n):
        t += rnd.choice([0.01, 0.01, 0.01, 0.3, 0.7])
        if rnd.random() < 0.15:
            seq += rnd.choice([1, 1, 1, 2])
            st = rnd.choice([6, 6, 6, 3, 5])
            pkt = P.encode_status(st, 0, rnd.choice([1] * 50 + [2]), seq,
                                  inhibit=0 if rnd.random() < 0.85 else 1 << 7)
            if rnd.random() < 0.02:
                pkt = pkt[:-1] + b"\x00"
        else:
            navt += rnd.choice([0.01] * 30 + [-0.05])
            pkt = P.encode_nav(navt, float("nan") if rnd.random() < 0.003 else 23.0, 120.0,
                               flags=0xE0 if rnd.random() < 0.95 else 0x60)
        yield t, pkt


def compare(stream: Iterable[Tuple[float, bytes]], vehicle_gate: type) -> Tuple[int, int]:
    ours, ref = Gate(), vehicle_gate()
    checks = mismatches = 0
    prev = None
    for t, pkt in stream:
        if prev is not None:
            d = ours.next_deadline(prev)
            while d is not None and d + 1e-6 < t:
                checks += 1
                mismatches += ours.verdict(d + 1e-6).usable != ref.allowed(d + 1e-6)[0]
                d = ours.next_deadline(d + 1e-6)
        ours.feed(pkt, t, None)
        ref.feed(pkt, t)
        for q in (t, t + 0.2):
            checks += 1
            mismatches += ours.verdict(q).usable != ref.allowed(q)[0]
        prev = t
    return checks, mismatches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--web-monitor", type=Path, required=True, help="web_monitor checkout")
    ap.add_argument("--recording", type=Path, action="append", default=[])
    ap.add_argument("--steps", type=int, default=20000)
    a = ap.parse_args()
    sys.path.insert(0, str(a.web_monitor))
    from aio_system_dashboard.nav.vehicle_gate import VehicleGate

    failed = False
    for seed in (1, 2, 3):
        checks, bad = compare(random_stream(a.steps, seed), VehicleGate)
        print(f"random seed {seed}: {checks} checks, {bad} mismatches")
        failed |= bad > 0
    for path in a.recording:
        with Recording(path) as rec:
            checks, bad = compare(((r.t, r.data) for r in rec), VehicleGate)
        print(f"{path.name}: {checks} checks, {bad} mismatches")
        failed |= bad > 0
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
