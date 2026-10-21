"""What the screen says, as pure functions of a Snapshot (no tkinter, so it is unit-tested).

Colour carries meaning only:
  go    可用 - the output may be used
  wait  阻擋, but as expected: alignment in progress or READY still settling; follow the instruction
  stop  阻擋 because something is wrong: data lost, fault, stale, flags, internal error
  idle  阻擋 with nothing to judge yet, or AIO NAV stopped on purpose
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from ..core import protocol as P
from ..core.gate import Reason
from ..engine import Snapshot

STARTUP = frozenset({"BOOTING", "CHECKING", "NAV_STARTING"})

# The alignment as a route: (label, states at that station). The last station is READY.
STATIONS = (("啟動", STARTUP), ("靜止", {"KEEP_STILL"}), ("直行", {"MOVE_STRAIGHT"}),
            ("精對準", {"REFINING"}), ("可用", {"READY"}))

_STATE_HEADLINE = {
    "BOOTING": "系統啟動中", "CHECKING": "系統啟動中", "NAV_STARTING": "系統啟動中",
    "KEEP_STILL": "對準第 1 階段：保持靜止", "MOVE_STRAIGHT": "對準第 2 階段：直線行駛",
    "REFINING": "對準第 3 階段：精對準", "READY": "READY，但仍有阻擋條件",
    "DEGRADED": "已失去對準條件", "FAULT": "AIO NAV 故障", "MAINTENANCE": "AIO NAV 已停止",
}


class Band(NamedTuple):
    kind: str           # go | wait | stop | idle
    word: str           # 可用 | 阻擋
    headline: str       # one short line: why, in the operator's words


def state_name(snap: Snapshot) -> Optional[str]:
    return P.name_of(snap.status.state, P.STATES) if snap.status is not None else None


def band(snap: Snapshot, failure: Optional[str]) -> Band:
    if failure:
        return Band("stop", "阻擋", failure)
    v = snap.verdict
    if v.usable:
        return Band("go", "可用", "導航輸出可以使用")
    r = v.reason
    if r is Reason.NO_STATUS:
        if snap.nothing_received:
            return Band("idle", "阻擋", "還沒收到任何封包")
        if snap.count.status == 0:
            return Band("stop", "阻擋", "沒有狀態封包 0x05")
        return Band("stop", "阻擋", f"狀態封包 0x05 中斷超過 {snap.cfg.status_timeout:g} 秒")
    if r is Reason.NOT_READY:
        name = P.name_of(v.state or 0, P.STATES)
        headline = _STATE_HEADLINE.get(name, f"狀態 {name}")
        if name == "MAINTENANCE":
            return Band("idle", "阻擋", headline)
        if name in STARTUP or name in ("KEEP_STILL", "MOVE_STRAIGHT", "REFINING"):
            return Band("wait", "阻擋", headline)
        return Band("stop", "阻擋", headline)
    if r is Reason.READY_NOT_STABLE:
        return Band("wait", "阻擋", f"READY 確認中（需穩定 {snap.cfg.ready_stable:g} 秒）")
    if r is Reason.NAV_STALE:
        if snap.nav is None:
            return Band("stop", "阻擋", "沒有導航封包 0x04")
        return Band("stop", "阻擋", f"導航封包 0x04 中斷超過 {snap.cfg.nav_max_age:g} 秒")
    if r is Reason.NAV_TIME_NOT_FORWARD:
        return Band("stop", "阻擋", "導航時間沒有往前")
    if r is Reason.NAV_NOT_ALIGNED:
        return Band("stop", "阻擋", "導航旗標顯示未對準")
    return Band("stop", "阻擋", "導航資料含無效數值")


class Rail(NamedTuple):
    """Where the alignment stands. `at` is the current station (-1 = off the route)."""

    at: int
    mode: str           # progress | done | lost | fault | stopped | none
    fraction: float     # READY settling: 0..1 of the stability time
    note: str           # shown under the rail


def rail(snap: Snapshot) -> Rail:
    if not snap.status_fresh:
        return Rail(-1, "none", 0.0, "沒有最新的狀態封包" if not snap.nothing_received else "")
    name = state_name(snap)
    if name == "READY":
        if snap.ready_since is None:
            return Rail(4, "progress", 0.0, "READY，但仍有阻擋條件")
        stable = snap.cfg.ready_stable
        f = 1.0 if stable <= 0 else max(0.0, min((snap.now - snap.ready_since) / stable, 1.0))
        return Rail(4, "done" if f >= 1.0 else "progress", f, "")   # done: anything still wrong is in the band
    for i, (_, states) in enumerate(STATIONS):
        if name in states:
            return Rail(i, "progress", 0.0, "")
    if name == "DEGRADED":
        return Rail(4, "lost", 0.0, "曾經 READY，之後失去條件")
    if name == "FAULT":
        return Rail(-1, "fault", 0.0, "AIO NAV、其輸出或擁有權有問題")
    if name == "MAINTENANCE":
        return Rail(-1, "stopped", 0.0, "操作員已停止，或尚未啟動")
    return Rail(-1, "none", 0.0, f"未知狀態 {name}")


class Link(NamedTuple):
    kind: str           # go | stop | idle
    text: str


def nav_link(snap: Snapshot) -> Link:
    if snap.nav is None:
        return Link("idle", "沒有資料")
    age = snap.now - snap.nav_at
    if age > snap.cfg.nav_max_age:
        return Link("stop", f"中斷 {fmt_age(age)}")
    return Link("go", f"{snap.nav_rate:.0f} Hz   {age * 1000:.0f} ms")


def status_link(snap: Snapshot) -> Link:
    if snap.status is None:
        return Link("idle", "沒有資料")
    age = snap.now - snap.status_at
    if age > snap.cfg.status_timeout:
        return Link("stop", f"中斷 {fmt_age(age)}")
    return Link("go", f"{snap.status_rate:.1f} Hz   {age:.1f} s 前")


def fmt_age(s: float) -> str:
    if s < 60:
        return f"{s:.1f} s"
    if s < 3600:
        return f"{int(s // 60)} 分 {int(s % 60):02d} 秒"
    return f"{int(s // 3600)} 小時 {int(s % 3600 // 60)} 分"


def fmt_dur(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}"
