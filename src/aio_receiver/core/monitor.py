"""Feeds a Gate in time order and keeps everything the screen and the recording need.

The verdict changes only when a packet arrives or a gate deadline passes. advance() evaluates just
after each deadline and feed() evaluates at each packet, so transition times and the usable total
are exact and do not depend on how often anyone looks. Time always comes from the caller: the
receive clock live, the recorded times in a replay.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional

from . import protocol as P
from .gate import Gate, GateConfig, PacketKind, Verdict
from .track import Track

DEADLINE_EPS = 1e-6     # judge this long after a deadline: past it beyond any float rounding
RATE_WINDOW = 3.0       # seconds of 0x04 arrivals used for its rate
STATUS_RATE_WINDOW = 5.0  # 0x05 comes at 2 Hz: a longer window keeps its rate steady


@dataclass(frozen=True)
class Transition:
    t: float
    verdict: Verdict


class Monitor:
    def __init__(self, cfg: GateConfig) -> None:
        self.gate = Gate(cfg)
        self.verdict: Optional[Verdict] = None      # None until the first evaluation
        self.changed_at = float("-inf")             # when the verdict last changed
        self.t = float("-inf")                      # time of the last evaluation
        self.usable_total = 0.0
        self.track = Track()
        self.flag_seen: Dict[str, float] = {}       # aiding flag -> last 0x04 time it was set
        self.nav_sender: Optional[str] = None
        self.status_sender: Optional[str] = None
        self._nav_times: Deque[float] = deque()
        self._status_times: Deque[float] = deque()

    # ------------------------------------------------------------------ time
    def _evaluate(self, t: float, out: List[Transition]) -> None:
        v = self.gate.verdict(t)
        if self.verdict is not None and self.verdict.usable:
            self.usable_total += t - self.t
        self.t = t
        if v != self.verdict:
            self.verdict, self.changed_at = v, t
            out.append(Transition(t, v))

    def advance(self, now: float) -> List[Transition]:
        """Bring the verdict up to `now`, through every deadline on the way."""
        out: List[Transition] = []
        while True:
            d = self.gate.next_deadline(self.t)
            if d is None or d + DEADLINE_EPS > now:
                break
            self._evaluate(d + DEADLINE_EPS, out)
        if now >= self.t:
            self._evaluate(now, out)
        return out

    def feed(self, pkt: bytes, now: float, sender: Optional[str]) -> tuple[Optional[PacketKind], List[Transition]]:
        """One datagram received at `now`. A time before the last evaluation is taken as that time."""
        now = max(now, self.t)
        out = self.advance(now)
        kind = self.gate.feed(pkt, now, sender)
        self._evaluate(now, out)                    # even an invalid 0x05 changes the verdict: it clears it
        if kind == "nav":
            self._on_nav(now, sender)
        elif kind == "status":
            self.status_sender = sender
            _window(self._status_times, now, STATUS_RATE_WINDOW)
        return kind, out

    def _on_nav(self, now: float, sender: Optional[str]) -> None:
        n = self.gate.nav
        assert n is not None
        self.nav_sender = sender
        _window(self._nav_times, now, RATE_WINDOW)
        flags = n.flags
        for i, name in enumerate(P.FLAG_NAMES):
            if flags >> i & 1:
                self.flag_seen[name] = now
        self.track.add(n.time_s, n.lat, n.lon, bool(self.verdict and self.verdict.usable))

    # ------------------------------------------------------------- read-out
    def nav_rate(self, now: float) -> float:
        return _rate(self._nav_times, now, RATE_WINDOW)

    def status_rate(self, now: float) -> float:
        return _rate(self._status_times, now, STATUS_RATE_WINDOW)


def _rate(times: Deque[float], now: float, span: float) -> float:
    """Packets per second from their spacing in the last `span`: right from the second packet on."""
    recent = [t for t in times if t >= now - span]
    if len(recent) < 2 or recent[-1] <= recent[0]:
        return 0.0
    return (len(recent) - 1) / (recent[-1] - recent[0])


def _window(times: Deque[float], now: float, span: float) -> None:
    """Append `now` and drop the times older than `span`."""
    times.append(now)
    while times[0] < now - span:
        times.popleft()
