"""fixtures/gate_vectors.json is the contract between the desktop and iOS gates.

tools/make_gate_vectors.py wrote it from this gate; the iOS tests replay the same packets through
VehicleGate.swift. If this test fails, the desktop rules changed: regenerate the file and make the
iOS gate follow (ios/MyApp/Protocol/VehicleGate.swift).
"""

from __future__ import annotations

import json
from pathlib import Path

from aio_receiver.core import protocol as P
from aio_receiver.core.gate import Gate, Reason

VECTORS = Path(__file__).resolve().parent.parent / "fixtures" / "gate_vectors.json"
KIND = {Reason.USABLE: "usable", Reason.NO_STATUS: "noStatus", Reason.NOT_READY: "notReady",
        Reason.READY_NOT_STABLE: "readyNotStable", Reason.NAV_STALE: "navTooOld",
        Reason.NAV_TIME_NOT_FORWARD: "navTimeBackwards", Reason.NAV_NOT_ALIGNED: "notAligned",
        Reason.NAV_NOT_FINITE: "notFinite"}


def test_desktop_gate_reproduces_shared_vectors() -> None:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    gate = Gate()
    for step in data["steps"]:
        for packet in step["packets"]:
            gate.feed(bytes.fromhex(packet), step["t"], None)
        v, c = gate.verdict(step["t"]), gate.count
        got = dict(usable=v.usable, reason=KIND[v.reason], nav=c.nav, status=c.status, lost=c.lost,
                   reordered=c.reordered, conflicts=c.conflicts, bad=c.bad)
        assert got == {k: step[k] for k in got}, f"t={step['t']}"
    assert gate.count.conflicts == 1


def test_shared_golden_packets_decode() -> None:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    s = P.decode_status(bytes.fromhex(data["golden_status"]))
    assert s is not None and s.sequence == 482 and s.session == 0x12345678
    assert data["golden_status"].endswith("5c")         # the checksum printed in the spec
    n = P.decode_nav(bytes.fromhex(data["nav_example"]))
    assert n is not None and n.heading == -90.0
