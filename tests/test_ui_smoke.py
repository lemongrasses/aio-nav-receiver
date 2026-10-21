"""Builds the window and renders snapshots for every state; skipped where there is no display.

One Tk root for the whole module: creating and destroying many roots in one process makes
Python 3.9's Tk fail intermittently ("Can't find a usable tk.tcl").
"""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from typing import Iterator, Optional

import pytest

from aio_receiver.config import Settings
from aio_receiver.core.monitor import Monitor
from aio_receiver.engine import Engine, ReplayInfo, Snapshot
from aio_receiver.ui import theme
from aio_receiver.ui.main_window import MainWindow
from aio_receiver.ui.panels import elide
from helpers import nav, status


class FakeEngine(Engine):
    def __init__(self) -> None:
        super().__init__()
        self.fixed: Optional[Snapshot] = None
        self.raise_next = False

    @property  # type: ignore[override]
    def snapshot(self) -> Optional[Snapshot]:
        if self.raise_next:
            self.raise_next = False
            raise RuntimeError("render input broke")
        return self.fixed

    @snapshot.setter
    def snapshot(self, value: Optional[Snapshot]) -> None:
        self.fixed = value


def snap_from(mon: Monitor, now: float, **kw: object) -> Snapshot:
    """Build a Snapshot the way the engine does, from a monitor fed by hand."""
    mon.advance(now)
    g = mon.gate
    assert mon.verdict is not None
    base = Snapshot(now=mon.t, built=time.perf_counter(), verdict=mon.verdict, usable_total=mon.usable_total,
                    cfg=g.cfg, nav=g.nav, nav_at=g.nav_at, status=g.status, status_at=g.status_at,
                    count=g.count.copy(), nav_rate=mon.nav_rate(mon.t), flag_seen=dict(mon.flag_seen),
                    nav_sender=mon.nav_sender, status_sender=mon.status_sender, track=tuple(mon.track.points),
                    track_version=mon.track.version, source_kind="live", source_label="監聽 0.0.0.0:9000",
                    verdict_since=mon.changed_at, status_rate=mon.status_rate(mon.t), ready_since=g.ready_since)
    return replace(base, **kw)  # type: ignore[arg-type]


def ready_monitor(seconds: float = 3.0, state: int = 6, sender: str = "192.168.116.1", action: int = 0) -> Monitor:
    """0x05 in `state` (asking for `action`) at 2 Hz and 0x04 at 100 Hz from t=0 for `seconds`."""
    mon = Monitor(Settings().gate_config())
    for i in range(int(seconds * 100)):
        t = i / 100
        if i % 50 == 0:
            mon.feed(status(i // 50 + 1, state=state, action=action), t, sender)
        mon.feed(nav(10.0 + t), t, sender)
    return mon


@pytest.fixture(scope="module")
def root() -> Iterator[tk.Tk]:
    try:
        r = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    r.withdraw()
    theme.init_fonts(r)
    yield r
    r.destroy()


@pytest.fixture
def window(root: tk.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    monkeypatch.setattr("aio_receiver.config.CONFIG_PATH", tmp_path / "settings.json")   # toggles save settings
    win = MainWindow(root, FakeEngine(), Settings())
    yield win
    win._closing = True
    for child in root.winfo_children():
        child.destroy()


def band(win: MainWindow) -> str:
    return f"{win.band.word.cget('text')} {win.band.headline.cget('text')} {win.band.frame.cget('bg')}"


def test_every_state_renders(window: MainWindow) -> None:
    mon = Monitor(Settings().gate_config())
    window.render(snap_from(mon, 0.0))
    assert band(window) == f"阻擋 還沒收到任何封包 {theme.IDLE}"
    assert window.guidance.title.cget("text") == "讓 AIO NAV 把資料送到這台電腦"

    mon.feed(nav(10.0), 0.1, "192.168.116.1")
    window.render(snap_from(mon, 0.1))
    assert window.guidance.title.cget("text") == "等待狀態封包 0x05"

    aligning = ready_monitor(state=4, action=2)                      # MOVE_STRAIGHT, DRIVE_STRAIGHT
    window.render(snap_from(aligning, 2.99))
    assert "對準第 2 階段" in band(window) and theme.WAIT in band(window)
    assert window.guidance.title.cget("text") == "在安全空曠處等速直線行駛"

    s = snap_from(ready_monitor(), 2.99)
    window.render(s)
    window.root.update_idletasks()
    assert band(window).startswith("可用") and theme.GO in band(window)
    assert window.guidance.title.cget("text") == "不需動作"
    assert "192.168.116.1" in window.footer.source.cget("text")
    assert window.root.title().startswith("可用")

    window.render(replace(s, recording="E:/logs/aio_20261021_101010", recording_since=s.now - 65))
    assert window.footer.rec_time.cget("text") == "記錄中 0:01:05"
    window.render(replace(s, recording_error="記錄已停止：No space left on device"))
    assert "No space" in window.footer.error.cget("text")


def test_faults_force_red(window: MainWindow) -> None:
    ok = snap_from(ready_monitor(), 2.99)
    assert ok.verdict.usable
    window.render(ok)
    window.render(replace(ok, built=time.perf_counter() - 2.0))               # engine stalled
    assert "沒有回應" in band(window)
    window.render(replace(ok, engine_error="RuntimeError: x"))
    assert "內部錯誤" in band(window)
    window.render(replace(ok, source_errors=("無法綁定 0.0.0.0:9000：in use",)))
    assert "無法綁定" in band(window)


def test_leaving_usable_flashes_and_sounds(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    bells = []
    monkeypatch.setattr(window.root, "bell", lambda: bells.append(1))
    mon = ready_monitor()
    window.render(snap_from(mon, 2.99))
    window.render(snap_from(mon, 4.0))                                        # 0x04 went stale
    assert bells == [1] and window.band._flash                                # the blink is running
    window.alert.set(False)
    window.render(snap_from(ready_monitor(), 2.99))
    window.render(snap_from(mon, 5.0))
    assert bells == [1]


def test_replay_bar_only_in_replay(window: MainWindow) -> None:
    s = snap_from(ready_monitor(), 2.99)
    window.render(s)
    window.root.update_idletasks()
    assert not window.replay_bar.frame.winfo_manager()
    info = ReplayInfo("aio_x.bin", 10, 100, 12.0, 44.0, 2.0, False, True)
    window.render(replace(s, source_kind="replay", source_label="重播 aio_x.bin", replay=info))
    assert window.replay_bar.frame.winfo_manager() == "pack"
    assert window.replay_bar.time.cget("text") == "0:00:12 / 0:00:44"
    assert window.root.title().startswith("重播")


def test_stale_status_is_not_shown_green(window: MainWindow) -> None:
    window.render(snap_from(ready_monitor(), 10.0))                           # 0x05 timed out
    state = window.status.v["state"]
    assert state.cget("text") == "READY" and state.cget("fg") == theme.MUTED


def test_a_failing_frame_still_schedules_the_next(window: MainWindow) -> None:
    engine = window.engine
    assert isinstance(engine, FakeEngine)
    engine.raise_next = True
    scheduled = []
    window.root.after = lambda ms, fn: scheduled.append(fn)  # type: ignore[method-assign, assignment, return-value]
    try:
        window._frame()
    finally:
        del window.root.after                                                 # back to the class method
    assert "畫面更新錯誤" in band(window) and theme.STOP in band(window)
    assert scheduled == [window._frame]


def test_elide_keeps_both_ends() -> None:
    p = "C:\\Users\\someone\\AppData\\Local\\Temp\\very\\deep\\folder\\logs\\aio_20261021_173320"
    short = elide(p, 40)
    assert len(short) == 40 and short.startswith("C:\\Users") and short.endswith("aio_20261021_173320")
    assert elide("E:\\logs\\aio_1", 40) == "E:\\logs\\aio_1"
