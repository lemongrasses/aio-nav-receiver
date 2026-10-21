"""Cut a window out of a real recording into a test fixture, with the position moved to 0°N 0°E.

Only latitude and longitude change (by one offset for the whole file, so windows stay aligned), and
checksums are recomputed; every time, flag and status field is kept, so verdicts are unchanged.

    python tools/make_fixture.py REC.bin --start 550 --end 650 --format v1 -o fixtures/x.bin.gz
    python tools/make_fixture.py ... --expect      also write x.expected.json from the CURRENT gate

The committed .expected.json files were produced by the pre-1.0 gate (characterisation), not by
the code under test.
"""

from __future__ import annotations

import argparse
import gzip
import json
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from aio_receiver.core import protocol as P
from aio_receiver.io.recording import _PREAMBLE, _REC_V1, _REC_V2, MAGIC, VERSION, Recording


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", type=Path)
    ap.add_argument("--start", type=float, required=True, help="seconds after the first packet")
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--format", choices=("v1", "v2"), default="v2")
    ap.add_argument("--sender", default="192.168.116.1", help="v2: sender written for every packet")
    ap.add_argument("-o", "--out", type=Path, required=True, help=".bin or .bin.gz")
    ap.add_argument("--expect", action="store_true")
    a = ap.parse_args()

    with Recording(a.recording) as rec:
        first = next(n for n in (P.decode_nav(r.data) for r in rec) if n is not None)
        dlat, dlon = first.lat, first.lon
        out = bytearray()
        if a.format == "v2":
            head = json.dumps({"app": "aio-nav-receiver", "fixture": True,
                               "clock": {"monotonic": rec.t0, "unix": 1792540800.0}}).encode()
            out += _PREAMBLE.pack(MAGIC, VERSION, len(head)) + head
        n_rec = 0
        for r in rec:
            if not a.start <= r.t - rec.t0 <= a.end:
                continue
            data = r.data
            n = P.decode_nav(data)
            if n is not None:
                data = P.pack_nav(n._replace(lat=n.lat - dlat, lon=n.lon - dlon))
            if a.format == "v1":
                out += _REC_V1.pack(r.t, len(data)) + data
            else:
                out += _REC_V2.pack(r.t, len(data), socket.inet_aton(a.sender), 50000) + data
            n_rec += 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(gzip.compress(bytes(out), 9, mtime=0) if a.out.suffix == ".gz" else bytes(out))
    print(f"{n_rec} packets -> {a.out} ({a.out.stat().st_size} bytes)")
    if a.expect:
        from aio_receiver.analysis import analyse
        from aio_receiver.core.gate import GateConfig
        tmp = a.out.with_suffix(".tmp")
        tmp.write_bytes(bytes(out))
        with Recording(tmp) as fx:
            rep = analyse(fx, GateConfig())
        tmp.unlink()
        exp = a.out.with_name(a.out.name.split(".")[0] + ".expected.json")
        exp.write_text(json.dumps({"usable_s": rep.usable_total, "transitions": [
            [tr.t, tr.verdict.usable, tr.verdict.text] for tr in rep.transitions]}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"expected -> {exp}")


if __name__ == "__main__":
    main()
