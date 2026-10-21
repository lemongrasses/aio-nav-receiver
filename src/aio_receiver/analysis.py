"""Replay a recording headless, as fast as possible: the `check` command and the regression tests.

Uses the same Monitor as the live screen, so its transitions are the ones the screen showed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .core.gate import Counters, GateConfig
from .core.monitor import Monitor, Transition
from .io.recording import Recording


@dataclass(frozen=True)
class Report:
    t0: float
    t_end: float
    packets: int
    transitions: List[Transition]
    usable_total: float
    count: Counters

    @property
    def duration(self) -> float:
        return self.t_end - self.t0


def analyse(rec: Recording, cfg: GateConfig) -> Report:
    if not rec.has_senders and cfg.allowed_from:
        cfg = GateConfig(cfg.status_id, None, cfg.status_timeout, cfg.ready_stable, cfg.nav_max_age)
    mon = Monitor(cfg)
    out = mon.advance(rec.t0)
    for r in rec:
        out += mon.feed(r.data, r.t, r.sender)[1]
    out += mon.advance(rec.t_end)
    return Report(rec.t0, rec.t_end, len(rec), out, mon.usable_total, mon.gate.count.copy())
