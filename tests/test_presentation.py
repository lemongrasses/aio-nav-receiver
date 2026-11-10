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
        "idle", "不可用", "還沒收到任何封包")
    assert V.band(snap_from(ready_monitor(), 2.99), None).kind == "go"
    for state, kind in (("KEEP_STILL", "wait"), ("REFINING", "wait"), ("BOOTING", "wait"),
                        ("DEGRADED", "stop"), ("FAULT", "stop"), ("MAINTENANCE", "idle")):
        b = V.band(snap_from(ready_monitor(state=P.STATES.index(state)), 2.99), None)
        assert b.kind == kind, state
    assert V.band(snap_from(ready_monitor(1.5), 1.49), None) == ("wait", "不可用", "就緒確認中（需穩定 2 秒）")
    stale = V.band(snap_from(ready_monitor(), 3.6), None)
    assert stale.kind == "stop" and "0x04 中斷" in stale.headline
    lost = V.band(snap_from(ready_monitor(), 8.0), None)
    assert lost.kind == "stop" and "0x05 中斷超過 3 秒" in lost.headline
    assert V.band(snap_from(ready_monitor(), 2.99), "無法綁定").kind == "stop"


def test_nav_without_status() -> None:
    mon = Monitor(Settings().gate_config())
    mon.feed(nav(1.0), 0.0, "a")
    assert V.band(snap_from(mon, 0.1), None) == ("stop", "不可用", "沒有狀態封包 0x05")


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
    assert V.status_link(s) == ("go", "2.0 Hz   0.5 秒前")
    gone = replace(s, now=s.now + 75)
    assert V.nav_link(gone) == ("stop", "中斷 1 分 15 秒")
    assert V.status_link(replace(s, status=None)) == ("idle", "沒有資料")
    mon = Monitor(Settings().gate_config())
    mon.feed(status(1), 0.0, "a")
    assert V.nav_link(snap_from(mon, 0.1)) == ("idle", "沒有資料")
    assert V.fmt_age(4000) == "1 小時 6 分" and V.fmt_dur(3725) == "1:02:05"


def test_guide_tells_never_from_lost() -> None:
    assert V.guide(snap_from(Monitor(Settings().gate_config()), 0.0)).kind == "setup"
    mon = Monitor(Settings().gate_config())
    mon.feed(nav(1.0), 0.0, "a")
    never = snap_from(mon, 0.1)
    assert V.guide(never) == ("plate", "開啟儀表板的 0x05", V.guide(never).sub)
    assert V.status_link(never) == ("stop", "從未收到")
    lost = V.guide(snap_from(ready_monitor(), 8.0))
    assert lost.title == "檢查儀表板與網路" and "已中斷 5.5 秒" in lost.sub and "收到 6 包" in lost.sub
    replay = replace(snap_from(ready_monitor(), 8.0), source_kind="replay")
    assert V.guide(replay).title == "等待狀態封包 0x05"
    assert V.guide(snap_from(ready_monitor(), 2.99)) == ("quiet", "不需動作", "")
    assert V.guide(snap_from(ready_monitor(state=P.STATES.index("FAULT"), action=4), 2.99)).kind == "danger"


def test_blocking_conditions() -> None:
    assert V.blocking(snap_from(ready_monitor(), 8.0)) is None             # no current 0x05: unknown
    assert V.blocking(snap_from(ready_monitor(), 2.99)) == []
    still = 1 << P.INHIBIT_BITS.index("KEEP_STILL_REQUIRED") | 1 << P.INHIBIT_BITS.index("FINE_ALIGNMENT_REQUIRED")
    mon = Monitor(Settings().gate_config())
    mon.feed(status(1, state=P.STATES.index("KEEP_STILL"), inhibit=still), 0.0, "a")
    assert V.blocking(snap_from(mon, 0.1)) == [V.Chip("需要保持靜止", True), V.Chip("需要精對準", True)]
    rtk = still | 1 << P.INHIBIT_BITS.index("RTK_CORRECTION_LOST")
    mon.feed(status(2, state=P.STATES.index("DEGRADED"), inhibit=rtk), 0.2, "a")
    assert [c.expected for c in V.blocking(snap_from(mon, 0.3)) or []] == [False, False, False]


def test_conditions_unmet_first() -> None:
    assert V.conditions(snap_from(Monitor(Settings().gate_config()), 0.0)) == []
    rows = V.conditions(snap_from(ready_monitor(), 2.99))
    assert len(rows) == len(P.HEALTH_BITS)
    met = [ok for _, ok in rows]
    assert met == sorted(met)                                               # every unmet before every met
