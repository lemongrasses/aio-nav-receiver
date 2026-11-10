"""What the screen says, as pure functions of a Snapshot (no tkinter, so it is unit-tested).
All text comes from i18n, in the current language.

Colour carries meaning only:
  go    可用 - the output may be used
  wait  不可用, but as expected: alignment in progress or ready still settling; follow the instruction
  stop  不可用 because something is wrong: data lost, fault, stale, flags, internal error
  idle  不可用 with nothing to judge yet, or AIO NAV stopped on purpose
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from .. import i18n
from ..core import protocol as P
from ..core.gate import Reason
from ..engine import Snapshot
from ..i18n import t

STARTUP = frozenset({"BOOTING", "CHECKING", "NAV_STARTING"})
ALIGNING = frozenset({"KEEP_STILL", "MOVE_STRAIGHT", "REFINING"})
# Blocking conditions that are simply the next alignment steps while AIO NAV starts or aligns.
STEP_BITS = frozenset({"BOOT_IN_PROGRESS", "KEEP_STILL_REQUIRED", "MOVE_STRAIGHT_REQUIRED",
                       "FINE_ALIGNMENT_REQUIRED"})
DANGER_ACTIONS = frozenset({"SAFE_STOP", "SERVICE_REQUIRED"})

# The alignment as a route: (label key, states at that station). The last station is READY.
STATIONS = (("station.start", STARTUP), ("station.still", {"KEEP_STILL"}),
            ("station.straight", {"MOVE_STRAIGHT"}), ("station.fine", {"REFINING"}),
            ("station.usable", {"READY"}))

_STATE_HEADLINE = {
    "BOOTING": "band.startup", "CHECKING": "band.startup", "NAV_STARTING": "band.startup",
    "KEEP_STILL": "band.stage1", "MOVE_STRAIGHT": "band.stage2", "REFINING": "band.stage3",
    "READY": "band.ready_inhibit", "DEGRADED": "band.degraded", "FAULT": "band.fault",
    "MAINTENANCE": "band.maintenance",
}


class Band(NamedTuple):
    kind: str           # go | wait | stop | idle
    word: str           # 可用 | 不可用 in the current language
    headline: str       # one short line: why, in the operator's words


def state_name(snap: Snapshot) -> Optional[str]:
    """The 0x05 state's protocol name (READY, KEEP_STILL, ...), or None before any 0x05."""
    return P.name_of(snap.status.state, P.STATES) if snap.status is not None else None


def band(snap: Snapshot, failure: Optional[str]) -> Band:
    usable, blocked = t("word.usable"), t("word.blocked")
    if failure:
        return Band("stop", blocked, failure)
    v = snap.verdict
    if v.usable:
        return Band("go", usable, t("band.usable"))
    r = v.reason
    if r is Reason.NO_STATUS:
        if snap.nothing_received:
            return Band("idle", blocked, t("band.nothing"))
        if snap.count.status == 0:
            return Band("stop", blocked, t("band.no_status"))
        return Band("stop", blocked, t("band.status_lost", s=f"{snap.cfg.status_timeout:g}"))
    if r is Reason.NOT_READY:
        name = P.name_of(v.state or 0, P.STATES)
        key = _STATE_HEADLINE.get(name)
        headline = t(key) if key else t("band.state", state=name)
        if name == "MAINTENANCE":
            return Band("idle", blocked, headline)
        if name in STARTUP or name in ALIGNING:
            return Band("wait", blocked, headline)
        return Band("stop", blocked, headline)
    if r is Reason.READY_NOT_STABLE:
        return Band("wait", blocked, t("band.settling", s=f"{snap.cfg.ready_stable:g}"))
    if r is Reason.NAV_STALE:
        if snap.nav is None:
            return Band("stop", blocked, t("band.no_nav"))
        return Band("stop", blocked, t("band.nav_lost", s=f"{snap.cfg.nav_max_age:g}"))
    if r is Reason.NAV_TIME_NOT_FORWARD:
        return Band("stop", blocked, t("band.nav_backwards"))
    if r is Reason.NAV_NOT_ALIGNED:
        return Band("stop", blocked, t("band.not_aligned"))
    return Band("stop", blocked, t("band.not_finite"))


class Rail(NamedTuple):
    """Where the alignment stands. `at` is the current station (-1 = off the route)."""

    at: int
    mode: str           # progress | done | lost | fault | stopped | none
    fraction: float     # ready settling: 0..1 of the stability time
    note: str           # shown under the rail


def rail(snap: Snapshot) -> Rail:
    if not snap.status_fresh:
        return Rail(-1, "none", 0.0, t("rail.no_status") if not snap.nothing_received else "")
    name = state_name(snap)
    if name == "READY":
        if snap.ready_since is None:
            return Rail(4, "progress", 0.0, t("rail.ready_inhibit"))
        stable = snap.cfg.ready_stable
        f = 1.0 if stable <= 0 else max(0.0, min((snap.now - snap.ready_since) / stable, 1.0))
        return Rail(4, "done" if f >= 1.0 else "progress", f, "")   # done: anything still wrong is in the band
    for i, (_, states) in enumerate(STATIONS):
        if name in states:
            return Rail(i, "progress", 0.0, "")
    if name == "DEGRADED":
        return Rail(4, "lost", 0.0, t("rail.degraded"))
    if name == "FAULT":
        return Rail(-1, "fault", 0.0, t("rail.fault"))
    if name == "MAINTENANCE":
        return Rail(-1, "stopped", 0.0, t("rail.stopped"))
    return Rail(-1, "none", 0.0, t("rail.unknown", state=name))


class Guide(NamedTuple):
    """The one thing the operator does now, under the verdict."""

    kind: str           # setup | plate | danger | quiet (nothing to do: no plate)
    title: str
    sub: str


def guide(snap: Snapshot) -> Guide:
    if snap.nothing_received:
        if snap.source_kind == "replay":
            return Guide("plate", t("guide.replay_empty"), "")
        return Guide("setup", t("setup.title"), "")
    if not snap.status_fresh:
        if snap.source_kind == "replay":
            return Guide("plate", t("guide.wait_status"), t("guide.wait_status_replay"))
        if snap.count.status == 0 or snap.status is None:      # 0x04 arrives, 0x05 never has: setup
            return Guide("plate", t("guide.no_status"), t("guide.no_status_sub"))
        return Guide("plate", t("guide.status_lost"),            # it worked before: dashboard or network
                     t("guide.status_lost_sub", age=fmt_age(snap.now - snap.status_at), n=snap.count.status))
    assert snap.status is not None
    action = P.name_of(snap.status.action, P.ACTIONS)
    if action == "NONE":
        return Guide("quiet", i18n.action_text(action), "")
    return Guide("danger" if action in DANGER_ACTIONS else "plate", i18n.action_text(action), "")


class Chip(NamedTuple):
    text: str
    expected: bool      # a normal alignment step (amber), not a problem (red)


def blocking(snap: Snapshot) -> Optional[List[Chip]]:
    """The 0x05 blocking conditions, or None when there is no current 0x05 to say."""
    if not snap.status_fresh:
        return None
    s = snap.status
    assert s is not None
    aligning = P.name_of(s.state, P.STATES) in STARTUP | ALIGNING
    return [Chip(i18n.inhibit_name(b), aligning and P.INHIBIT_BITS[b] in STEP_BITS)
            for b in range(len(P.INHIBIT_BITS)) if s.inhibit >> b & 1]


def conditions(snap: Snapshot) -> List[Tuple[str, bool]]:
    """(condition, met) for every 0x05 health flag, the unmet first; empty before any 0x05."""
    s = snap.status
    if s is None:
        return []
    rows = [(i18n.health_name(i), bool(s.health >> i & 1)) for i in range(len(P.HEALTH_BITS))]
    return sorted(rows, key=lambda r: r[1])     # stable: bit order within each group


class Link(NamedTuple):
    kind: str           # go | stop | idle
    text: str


def nav_link(snap: Snapshot) -> Link:
    if snap.nav is None:
        return Link("idle", t("link.none"))
    age = snap.now - snap.nav_at
    if age > snap.cfg.nav_max_age:
        return Link("stop", t("link.lost", age=fmt_age(age)))
    return Link("go", t("link.nav", rate=snap.nav_rate, ms=age * 1000))


def status_link(snap: Snapshot) -> Link:
    if snap.status is None:
        if snap.nav is not None and snap.count.status == 0:     # 0x04 arrives, 0x05 never has
            return Link("stop", t("link.never"))
        return Link("idle", t("link.none"))
    age = snap.now - snap.status_at
    if age > snap.cfg.status_timeout:
        return Link("stop", t("link.lost", age=fmt_age(age)))
    return Link("go", t("link.status", rate=snap.status_rate, s=age))


def fmt_age(s: float) -> str:
    if s < 60:
        return t("age.s", s=s)
    if s < 3600:
        return t("age.ms", m=int(s // 60), s=int(s % 60))
    return t("age.hm", h=int(s // 3600), m=int(s % 3600 // 60))


def fmt_dur(s: float) -> str:
    s = int(max(s, 0))
    return f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}"
