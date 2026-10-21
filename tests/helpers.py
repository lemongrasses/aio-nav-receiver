"""Packet builders and fixture access shared by the tests."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Dict

from aio_receiver.core import protocol as P
from aio_receiver.core.gate import Reason, Verdict

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ALIGNED = 0b1110_0000
GOLDEN = bytes.fromhex("55aa0524000106000378563412e201000015cd5b0700000000ff0f010000000000e800e8030c0000005c")


def nav(t: float, flags: int = ALIGNED, lat: float = 23.0) -> bytes:
    return P.encode_nav(t, lat, 120.0, flags=flags)


def status(seq: int, state: int = P.READY, inhibit: int = 0, session: int = 1, msg_id: int = P.STATUS_ID,
           action: int = 0) -> bytes:
    return P.encode_status(state, action, session, seq, inhibit=inhibit, msg_id=msg_id)


def fixture_file(name: str, tmp: Path) -> Path:
    """A fixture .bin.gz unpacked into tmp (Recording needs a real file for mmap)."""
    out = tmp / name.replace(".gz", "")
    out.write_bytes(gzip.decompress((FIXTURES / name).read_bytes()))
    return out


def expected(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name.replace(".bin.gz", ".expected.json")).read_text(encoding="utf-8"))


_LEGACY = {"usable": "可用", "no_status": "沒有最新的狀態封包 (0x05)", "ready_not_stable": "READY 尚未穩定",
           "nav_stale": "導航資料太舊 (0x04)", "nav_time_not_forward": "導航時間沒有往前",
           "nav_not_aligned": "導航旗標未對準", "nav_not_finite": "導航資料不是有限值"}


def legacy_text(v: Verdict) -> str:
    """The sentence the pre-1.0 gate printed for this verdict, rebuilt from its codes, so the
    characterisation fixtures (.expected.json) stay comparable whatever the display language."""
    if v.reason is Reason.NOT_READY:
        inhibit = ", ".join(P.bit_names(v.inhibit, P.INHIBIT_BITS)) or "—"
        return f"狀態不是 READY：{P.name_of(v.state or 0, P.STATES)}（{inhibit}）"
    return _LEGACY[v.reason.value]
