from __future__ import annotations

import math

from aio_receiver.core.gate import Gate, GateConfig, Reason
from helpers import nav, status


def ready_gate() -> Gate:
    g = Gate()
    g.feed(status(1), 0.0, "x")
    g.feed(status(2), 1.0, "x")
    g.feed(nav(1.0), 2.4, "x")
    g.feed(nav(2.0), 2.5, "x")
    return g


def reason(g: Gate, t: float) -> Reason:
    return g.verdict(t).reason


def test_blocked_until_ready_is_stable() -> None:
    g = Gate()
    assert reason(g, 0) is Reason.NO_STATUS
    g.feed(status(1, state=3, inhibit=1 << 7), 0.0, "x")
    v = g.verdict(0.1)
    assert v.reason is Reason.NOT_READY and v.state == 3 and v.inhibit == 1 << 7
    assert v.text == "狀態不是就緒：保持靜止（需要保持靜止）"
    g = ready_gate()
    assert reason(g, 1.5) is Reason.READY_NOT_STABLE
    assert g.verdict(2.5).usable
    assert reason(g, 3.1) is Reason.NAV_STALE


def test_each_rule_blocks() -> None:
    g = ready_gate()
    g.feed(status(3, session=2), 2.5, "x")          # new session: READY starts over
    assert reason(g, 2.5) is Reason.READY_NOT_STABLE
    g = ready_gate()
    g.feed(nav(1.5), 2.5, "x")
    assert reason(g, 2.5) is Reason.NAV_TIME_NOT_FORWARD
    g = ready_gate()
    g.feed(nav(3.0, flags=0b0110_0000), 2.5, "x")
    assert reason(g, 2.5) is Reason.NAV_NOT_ALIGNED
    g = ready_gate()
    g.feed(nav(3.0, lat=math.nan), 2.5, "x")
    assert reason(g, 2.5) is Reason.NAV_NOT_FINITE
    assert reason(ready_gate(), 5.1) is Reason.NO_STATUS


def test_bad_status_clears_authorisation() -> None:
    g = ready_gate()
    bad = status(3)
    assert g.feed(bad[:-1] + bytes([bad[-1] ^ 1]), 2.5, "x") is None
    assert reason(g, 2.5) is Reason.NO_STATUS
    assert g.count.bad == 1


def test_sequence_rules() -> None:
    g = Gate()
    g.feed(status(10), 0.0, "x")
    g.feed(status(13), 0.5, "x")
    assert g.count.lost == 2
    g.feed(status(10), 0.6, "x")                    # back 3: reordered, content ignored
    assert g.count.reordered == 1 and g.status is not None and g.status.sequence == 13
    g.feed(status(2), 0.7, "x")                     # back 11: a second sender
    assert g.count.conflicts == 1
    assert g.ready_since == 0.7


def test_sequence_wraps() -> None:
    g = Gate()
    g.feed(status(0xFFFFFFFF), 0.0, "x")
    g.feed(status(0), 0.5, "x")
    assert (g.count.lost, g.count.reordered, g.count.conflicts) == (0, 0, 0)


def test_source_filter() -> None:
    g = Gate(GateConfig(allowed_from="192.168.116.1"))
    g.feed(status(1), 0.0, "10.0.0.9")
    assert (g.count.foreign, g.status) == (1, None)
    g.feed(status(1), 0.0, None)                    # unknown sender (old recording): filter cannot apply
    assert g.status is not None


def test_custom_status_id() -> None:
    g = Gate(GateConfig(status_id=0x06))
    assert g.feed(status(1, msg_id=0x06), 0.0, "x") == "status"
    assert g.feed(status(2), 0.1, "x") is None and g.count.bad == 1


def test_next_deadline() -> None:
    g = Gate()
    assert g.next_deadline(0.0) is None
    g.feed(status(1), 0.0, "x")
    assert g.next_deadline(0.0) == 2.0               # READY stable
    assert g.next_deadline(2.0) == 3.0               # status timeout
    g.feed(nav(1.0), 2.8, "x")
    assert g.next_deadline(2.8) == 3.0
    assert g.next_deadline(3.0) == 3.3               # nav age
    assert g.next_deadline(3.3) is None
