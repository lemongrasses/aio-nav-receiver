from __future__ import annotations

import pytest

from aio_receiver.core.gate import GateConfig, Reason
from aio_receiver.core.monitor import DEADLINE_EPS, Monitor
from aio_receiver.core.track import Track, nice_length, project
from helpers import nav, status


def run_ready(m: Monitor) -> None:
    """0x05 READY at 2 Hz from t=0 to 4.5 s, 0x04 at 100 Hz from t=0 to 5 s, then silence."""
    for i in range(500):
        t = i / 100
        if i % 50 == 0:
            m.feed(status(i // 50 + 1), t, "a")
        m.feed(nav(100 + t), t, "a")


def test_transitions_are_exact_without_packets() -> None:
    m = Monitor(GateConfig())
    run_ready(m)
    trs = m.advance(100.0)
    assert m.verdict is not None and m.verdict.reason is Reason.NO_STATUS
    # 0x04 stops at 4.99 -> stale at 5.49; 0x05 stops at 4.5 -> timeout at 7.5
    assert [(round(tr.t, 6), tr.verdict.reason) for tr in trs] == [
        (round(4.99 + 0.5 + DEADLINE_EPS, 6), Reason.NAV_STALE),
        (round(4.5 + 3.0 + DEADLINE_EPS, 6), Reason.NO_STATUS)]


def test_usable_total_is_independent_of_how_often_it_is_asked() -> None:
    a, b = Monitor(GateConfig()), Monitor(GateConfig())
    run_ready(a)
    run_ready(b)
    for i in range(1, 1001):
        b.advance(5 + i * 0.0137)                   # an irregular "screen"
    a.advance(20.0)
    b.advance(20.0)
    # usable from READY stable (2.0) until 0x04 is stale (5.49)
    assert a.usable_total == pytest.approx(3.49, abs=1e-5)
    assert b.usable_total == pytest.approx(a.usable_total, abs=1e-9)


def test_invalid_status_blocks_at_once() -> None:
    m = Monitor(GateConfig())
    run_ready(m)
    pkt = status(99)
    _, trs = m.feed(pkt[:-1] + b"\0", 4.995, "a")
    assert [tr.verdict.reason for tr in trs] == [Reason.NO_STATUS]


def test_rate_flags_senders() -> None:
    m = Monitor(GateConfig())
    run_ready(m)
    assert m.nav_rate(4.99) == pytest.approx(100, abs=1)
    assert m.flag_seen["FINE"] == pytest.approx(4.99)
    assert "GNSS" not in m.flag_seen
    assert m.nav_sender == m.status_sender == "a"


def test_time_never_goes_back() -> None:
    m = Monitor(GateConfig())
    m.feed(status(1), 5.0, "a")
    m.feed(status(2), 4.0, "a")                     # clock glitch: treated as 5.0
    assert m.gate.status_at == 5.0


def test_track_decimates_and_resets() -> None:
    m = Monitor(GateConfig())
    run_ready(m)
    pts = list(m.track.points)
    assert len(pts) == 50                           # one per 0.1 s of navigation time
    assert not pts[0].usable and pts[-1].usable
    tr = Track()
    tr.add(100.0, 1.0, 2.0, True)
    tr.add(100.05, 1.0, 2.0, True)
    tr.add(98.0, 1.0, 2.0, True)                    # back 2 s: AIO NAV restarted
    tr.add(98.1, float("nan"), 2.0, True)
    assert len(tr.points) == 1 and tr.version == 2


def test_projection_and_scale_bar() -> None:
    tr = Track()
    tr.add(0.0, 0.0, 0.0, True)
    tr.add(1.0, 0.001, 0.0, True)                   # ~111 m north
    p = project(list(tr.points))
    assert p is not None and p.ys[0] == pytest.approx(-111.3, abs=0.1) and p.span == pytest.approx(111.3, abs=0.1)
    assert project([]) is None
    assert [nice_length(x) for x in (7, 20, 0.3, 140)] == [5, 20, 0.2, 100]
