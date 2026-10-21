"""May the 0x04 navigation data be used? Same rules as web_monitor nav/vehicle_gate.py.

Blocked by default. Usable only when all hold:
1. a valid 0x05 arrived within status_timeout (bad checksum / version / new session clears it);
2. state READY and inhibit 0, continuously for ready_stable in one session;
3. newest 0x04 at most nav_max_age old;  4. its time moved forward;
5. ALIGN, HEADING and FINE set;  6. every float finite.

Pure: the caller passes the receive time of each packet and the time to judge at. Rules 1-3 also
change with no packet at all, when a limit runs out; next_deadline() says when.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from .. import i18n
from . import protocol as P

REORDER_WINDOW = 5      # a 0x05 sequence going back more than this = a second sender (spec)

PacketKind = Literal["nav", "status"]


class Reason(enum.Enum):
    USABLE = "usable"
    NO_STATUS = "no_status"
    NOT_READY = "not_ready"
    READY_NOT_STABLE = "ready_not_stable"
    NAV_STALE = "nav_stale"
    NAV_TIME_NOT_FORWARD = "nav_time_not_forward"
    NAV_NOT_ALIGNED = "nav_not_aligned"
    NAV_NOT_FINITE = "nav_not_finite"




@dataclass(frozen=True)
class Verdict:
    usable: bool
    reason: Reason
    state: Optional[int] = None     # NOT_READY only: the 0x05 state and inhibit bits behind it
    inhibit: int = 0

    @property
    def text(self) -> str:
        """The reason in the current language (i18n)."""
        if self.reason is Reason.NOT_READY:
            bits = [i for i in range(len(P.INHIBIT_BITS)) if self.inhibit >> i & 1]
            inhibit = i18n.joined([i18n.inhibit_name(b) for b in bits]) or "—"
            return i18n.t("reason.not_ready", state=i18n.state_name(P.name_of(self.state or 0, P.STATES)),
                          inhibit=inhibit)
        return i18n.t(f"reason.{self.reason.value}")

    @property
    def word(self) -> str:
        return i18n.t("word.usable" if self.usable else "word.blocked")


USABLE = Verdict(True, Reason.USABLE)


@dataclass(frozen=True)
class GateConfig:
    status_id: int = P.STATUS_ID
    allowed_from: Optional[str] = None      # accept packets from this IPv4 only (None = any)
    status_timeout: float = 3.0
    ready_stable: float = 2.0
    nav_max_age: float = 0.5


@dataclass
class Counters:
    nav: int = 0
    status: int = 0
    lost: int = 0
    reordered: int = 0
    bad: int = 0
    conflicts: int = 0
    foreign: int = 0

    def copy(self) -> Counters:
        return Counters(**vars(self))


@dataclass
class Gate:
    cfg: GateConfig = field(default_factory=GateConfig)
    status: Optional[P.StatusPacket] = None
    status_at: float = 0.0
    ready_since: Optional[float] = None
    session: Optional[int] = None
    nav: Optional[P.NavPacket] = None
    nav_at: float = 0.0
    nav_backwards: bool = False
    count: Counters = field(default_factory=Counters)

    def _clear(self) -> None:
        self.status, self.ready_since, self.session = None, None, None

    def feed(self, pkt: bytes, now: float, sender: Optional[str]) -> Optional[PacketKind]:
        """Take one datagram received at `now`. Returns "nav", "status" or None (ignored or invalid).

        `sender` None means unknown (an old recording): the source filter cannot apply.
        """
        cfg = self.cfg
        if cfg.allowed_from and sender is not None and sender != cfg.allowed_from:
            self.count.foreign += 1
            return None
        mid = P.message_id(pkt)
        if mid == cfg.status_id:
            return self._feed_status(pkt, now)
        if mid == P.NAV_ID:
            n = P.decode_nav(pkt)
            if n is None:
                self.count.bad += 1
                return None
            self.count.nav += 1
            self.nav_backwards = self.nav is not None and n.time_us <= self.nav.time_us
            self.nav, self.nav_at = n, now
            return "nav"
        self.count.bad += 1
        return None

    def _feed_status(self, pkt: bytes, now: float) -> Optional[PacketKind]:
        s = P.decode_status(pkt, self.cfg.status_id)
        if s is None:
            self.count.bad += 1
            self._clear()                       # broken or unknown status: stop trusting
            return None
        self.count.status += 1
        if self.session is not None and s.session != self.session:
            self._clear()                       # the dashboard restarted
        elif self.status is not None:
            gap = (s.sequence - self.status.sequence) & 0xFFFFFFFF
            if gap == 0 or gap > 0x7FFFFFFF:
                back = (self.status.sequence - s.sequence) & 0xFFFFFFFF
                if back <= REORDER_WINDOW:
                    self.count.reordered += 1
                    return "status"             # old or duplicate: ignore its content
                self.count.conflicts += 1
                self._clear()                   # two senders in one session: start over from this one
            else:
                self.count.lost += gap - 1
        self.session, self.status, self.status_at = s.session, s, now
        if s.state == P.READY and s.inhibit == 0:
            if self.ready_since is None:
                self.ready_since = now
        else:
            self.ready_since = None
        return "status"

    def verdict(self, now: float) -> Verdict:
        cfg, s, n = self.cfg, self.status, self.nav
        if s is None or now - self.status_at > cfg.status_timeout:
            return Verdict(False, Reason.NO_STATUS)
        if self.ready_since is None:
            return Verdict(False, Reason.NOT_READY, s.state, s.inhibit)
        if now - self.ready_since < cfg.ready_stable:
            return Verdict(False, Reason.READY_NOT_STABLE)
        if n is None or now - self.nav_at > cfg.nav_max_age:
            return Verdict(False, Reason.NAV_STALE)
        if self.nav_backwards:
            return Verdict(False, Reason.NAV_TIME_NOT_FORWARD)
        if n.flags & P.ALIGN_MASK != P.ALIGN_MASK:
            return Verdict(False, Reason.NAV_NOT_ALIGNED)
        if not all(math.isfinite(v) for v in n if isinstance(v, float)):
            return Verdict(False, Reason.NAV_NOT_FINITE)
        return USABLE

    def next_deadline(self, after: float) -> Optional[float]:
        """The earliest time > `after` at which the verdict can change without a new packet."""
        cfg, times = self.cfg, []
        if self.status is not None:
            times.append(self.status_at + cfg.status_timeout)
            if self.ready_since is not None:
                times.append(self.ready_since + cfg.ready_stable)
        if self.nav is not None:
            times.append(self.nav_at + cfg.nav_max_age)
        later = [t for t in times if t > after]
        return min(later) if later else None
