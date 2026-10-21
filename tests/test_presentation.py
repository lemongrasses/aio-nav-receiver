"""What the screen says for each situation (pure functions; no window needed)."""

from __future__ import annotations

from dataclasses import replace

from aio_receiver.config import Settings
from aio_receiver.core import protocol as P
from aio_receiver.core.monitor import Monitor
from aio_receiver.ui import presentation as V
from helpers import nav, status
from test_ui_smoke import ready_monitor, snap_from


def test_band_kinds() -> None:
    assert V.band(snap_from(Monitor(Settings().gate_config()), 0.0), None) == (
        "idle", "阻擋", "還沒收到任何封包")
    assert V.band(snap_from(ready_monitor(), 2.99), None).kind == "go"
    for state, kind in (("KEEP_STILL", "wait"), ("REFINING", "wait"), ("BOOTING", "wait"),
                        ("DEGRADED", "stop"), ("FAULT", "stop"), ("MAINTENANCE", "idle")):
        b = V.band(snap_from(ready_monitor(state=P.STATES.index(state)), 2.99), None)
        assert b.kind == kind, state
    assert V.band(snap_from(ready_monitor(1.5), 1.49), None) == ("wait", "阻擋", "READY 確認中（需穩定 2 秒）")
    stale = V.band(snap_from(ready_monitor(), 3.6), None)
    assert stale.kind == "stop" and "0x04 中斷" in stale.headline
    lost = V.band(snap_from(ready_monitor(), 8.0), None)
    assert lost.kind == "stop" and "0x05 中斷超過 3 秒" in lost.headline
    assert V.band(snap_from(ready_monitor(), 2.99), "無法綁定").kind == "stop"


def test_nav_without_status() -> None:
    mon = Monitor(Settings().gate_config())
    mon.feed(nav(1.0), 0.0, "a")
    assert V.band(snap_from(mon, 0.1), None) == ("stop", "阻擋", "沒有狀態封包 0x05")


def test_rail() -> None:
    assert V.rail(snap_from(ready_monitor(state=P.STATES.index("MOVE_STRAIGHT")), 2.99))[:2] == (2, "progress")
    assert V.rail(snap_from(ready_monitor(), 2.99))[:2] == (4, "done")
    settling = V.rail(snap_from(ready_monitor(1.5), 1.49))
    assert settling.at == 4 and settling.mode == "progress" and abs(settling.fraction - 0.745) < 0.01
    assert V.rail(snap_from(ready_monitor(state=P.STATES.index("DEGRADED")), 2.99))[:2] == (4, "lost")
    assert V.rail(snap_from(ready_monitor(state=P.STATES.index("FAULT")), 2.99))[:2] == (-1, "fault")
    assert V.rail(snap_from(ready_monitor(), 8.0)).mode == "none"           # 0x05 timed out


def test_links_and_ages() -> None:
    s = snap_from(ready_monitor(), 2.99)
    assert V.nav_link(s).kind == "go" and "Hz" in V.nav_link(s).text
    assert V.status_link(s) == ("go", "2.0 Hz   0.5 s 前")
    gone = replace(s, now=s.now + 75)
    assert V.nav_link(gone) == ("stop", "中斷 1 分 15 秒")
    assert V.status_link(replace(s, status=None)) == ("idle", "沒有資料")
    mon = Monitor(Settings().gate_config())
    mon.feed(status(1), 0.0, "a")
    assert V.nav_link(snap_from(mon, 0.1)) == ("idle", "沒有資料")
    assert V.fmt_age(4000) == "1 小時 6 分" and V.fmt_dur(3725) == "1:02:05"
