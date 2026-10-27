"""Builds the window and renders snapshots for every state; skipped where there is no display.

One Tk root for the whole module: creating and destroying many roots in one process makes
Python 3.9's Tk fail intermittently ("Can't find a usable tk.tcl").
"""

from __future__ import annotations

import re
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from typing import Iterator, List, Optional

import pytest

from aio_receiver import i18n
from aio_receiver.config import Settings
from aio_receiver.core.monitor import Monitor
from aio_receiver.engine import Engine, ReplayInfo, Snapshot
from aio_receiver.ui import theme
from aio_receiver.ui.main_window import MainWindow
from aio_receiver.ui.panels import elide, wrap
from aio_receiver.ui.settings_dialog import SettingsDialog
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
                    track_version=mon.track.version, source_kind="live", source_address="0.0.0.0:9000",
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
    theme.init_fonts(root, "zh-TW")
    win = MainWindow(root, FakeEngine(), Settings())
    yield win
    win._closing = True
    for child in root.winfo_children():
        child.destroy()


def band(win: MainWindow) -> str:
    """The verdict as shown: word, headline, the word's colour and the colour of the lit lamp on the mast."""
    b = win.band
    return f"{b.word.cget('text')} {b.headline.cget('text')} {b.word.cget('fg')} {b.lit()}".rstrip()


def test_every_state_renders(window: MainWindow) -> None:
    mon = Monitor(Settings().gate_config())
    window.render(snap_from(mon, 0.0))
    assert band(window) == f"不可用 還沒收到任何封包 {theme.IDLE}"
    assert window.guidance.title.cget("text") == "讓 AIO NAV 把資料送到這台電腦"

    mon.feed(nav(10.0), 0.1, "192.168.116.1")
    window.render(snap_from(mon, 0.1))
    assert window.guidance.title.cget("text") == "開啟儀表板的 0x05"        # 0x05 never arrived: setup
    assert window.status.link.text.cget("text") == "從未收到"

    aligning = ready_monitor(state=4, action=2)                      # MOVE_STRAIGHT, DRIVE_STRAIGHT
    window.render(snap_from(aligning, 2.99))
    assert "對準第 2 階段" in band(window) and theme.WAIT in band(window)
    assert window.guidance.title.cget("text") == "在安全、空曠的區域以穩定速度直線行駛"

    s = snap_from(ready_monitor(), 2.99)
    window.render(s)
    window.root.update_idletasks()
    assert band(window).startswith("可用") and theme.GO in band(window)
    assert window.guidance.block_text.cget("text") == "無"
    assert window.guidance.title.cget("text") == "不需動作"
    assert "192.168.116.1" in window.footer.source.cget("text")
    assert window.root.title().startswith("可用")

    window.render(replace(s, recording="E:/logs/aio_20261021_101010", recording_since=s.now - 65))
    assert window.footer.rec_time.cget("text") == "記錄中 0:01:05"
    window.render(replace(s, recording_error="記錄已停止：No space left on device"))
    assert "No space" in window.footer.error.cget("text")
    window.root.update_idletasks()
    assert window.footer.error_box.winfo_manager() == "pack"

    window.render(snap_from(ready_monitor(), 8.0))                   # 0x05 worked, then stopped
    assert window.guidance.title.cget("text") == "檢查儀表板與網路"
    assert "已經收到 6 包" in window.guidance.sub.cget("text")
    assert window.guidance.block_text.cget("text") == "沒有最新的 0x05，無法得知"


def test_alignment_steps_are_amber_and_problems_red(window: MainWindow) -> None:
    window.render(snap_from(ready_monitor(state=3, action=1), 2.99))      # KEEP_STILL asks to hold still
    assert band(window).endswith(theme.WAIT)
    assert window.guidance.title.cget("text") == "讓車輛完全靜止"
    window.render(snap_from(ready_monitor(state=7, action=4), 2.99))      # DEGRADED asks for a safe stop
    assert band(window).endswith(theme.STOP)
    assert window.guidance.plate.cget("bg") == theme.STOP                   # the instruction turns red too


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
    window.render(replace(s, source_kind="replay", source_address="aio_x.bin", replay=info))
    assert window.replay_bar.frame.winfo_manager() == "pack"
    assert window.replay_bar.time.cget("text") == "0:00:12 / 0:00:44"
    assert window.root.title().startswith("重播")


def test_stale_status_is_not_shown_green(window: MainWindow) -> None:
    window.render(snap_from(ready_monitor(), 10.0))                           # 0x05 timed out
    state = window.status.v["state"]
    assert state.cget("text") == "就緒" and state.cget("fg") == theme.FAINT


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


def test_settings_same_port_saves_zero(root: tk.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """「與 0x04 相同」 saves 0 (follow the 0x04 port), never the 0x04 number the field shows."""
    monkeypatch.setattr("aio_receiver.config.CONFIG_PATH", tmp_path / "settings.json")
    saved: List[Settings] = []
    d = SettingsDialog(root, Settings(), saved.append)
    assert d.same.get() and d.vars["status_port"].get() == "9000"
    d.vars["nav_port"].set("9100")
    assert d.vars["status_port"].get() == "9100"                              # the field follows 0x04
    d.save()
    assert saved[-1].nav_port == 9100 and saved[-1].status_port == 0
    d = SettingsDialog(root, saved[-1], saved.append)
    d.same.set(False)
    d._same_port()
    d.vars["status_port"].set("9200")
    d.save()
    assert saved[-1].status_port == 9200


def test_settings_error_opens_advanced(root: tk.Tk, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aio_receiver.config.CONFIG_PATH", tmp_path / "settings.json")
    saved: List[Settings] = []
    d = SettingsDialog(root, Settings(), saved.append)
    assert not d._advanced
    d.vars["status_timeout"].set("0")
    d.save()
    assert saved == [] and d._advanced and "狀態逾時" in d.err.cget("text")
    d.destroy()


def test_wrap_breaks_chinese_between_characters(root: tk.Tk) -> None:
    from tkinter import font as tkfont
    f = tkfont.Font(family=theme.TXT, size=12)
    text = "0x05 已中斷 5.6 秒。之前已經收到 90 包，所以設定沒有問題。"
    lines = wrap(text, f, f.measure("0x05 已中斷 5.6 秒。之前"))
    assert "".join(lines.splitlines()).replace(" ", "") == text.replace(" ", "")
    assert all(f.measure(line) <= f.measure("0x05 已中斷 5.6 秒。之前") for line in lines.splitlines())
    assert not any(line.startswith(("，", "。")) for line in lines.splitlines())
    assert wrap("Check the dashboard", f, 10_000) == "Check the dashboard"


def test_elide_keeps_both_ends() -> None:
    p = "C:\\Users\\someone\\AppData\\Local\\Temp\\very\\deep\\folder\\logs\\aio_20261021_173320"
    short = elide(p, 40)
    assert len(short) == 40 and short.startswith("C:\\Users") and short.endswith("aio_20261021_173320")
    assert elide("E:\\logs\\aio_1", 40) == "E:\\logs\\aio_1"


# ------------------------------------------------------------------------- one language at a time
CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
CODE = re.compile(r"\b[A-Z]{2,}_[A-Z_]+\b")                  # protocol identifiers such as KEEP_STILL


def visible_text(win: MainWindow) -> List[str]:
    """Every string on screen: widget texts, canvas texts, the window title."""
    out = [win.root.title()]
    todo: List[tk.Misc] = [win.root]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if isinstance(w, tk.Canvas):
            out += [w.itemcget(i, "text") for i in w.find_all() if w.type(i) == "text"]
            continue
        try:
            out.append(str(w.cget("text")))
        except tk.TclError:
            pass
    return [s for s in out if s]


def every_state(win: MainWindow) -> Iterator[None]:
    win.render(snap_from(Monitor(Settings().gate_config()), 0.0))                       # setup steps
    yield
    for state, action in ((3, 1), (4, 2), (5, 3), (7, 4), (8, 5), (9, 6)):
        win.render(snap_from(ready_monitor(state=state, action=action), 2.99))
        yield
    s = snap_from(ready_monitor(1.5), 1.49)                                            # ready settling
    win.render(s)
    yield
    s = snap_from(ready_monitor(), 2.99)
    win.render(replace(s, recording="E:/logs/aio_1", recording_since=s.now - 3))
    yield
    win.render(snap_from(ready_monitor(), 10.0))                                       # both streams lost
    yield
    win.render(replace(s, source_errors=(i18n.msg("fail.bind", addr="0.0.0.0:9000",
                                                     error=i18n.os_error(OSError(98, "x"))),)))
    yield
    info = ReplayInfo("aio_x.bin", 10, 100, 12.0, 44.0, 2.0, True, False)
    win.render(replace(s, source_kind="replay", source_address="aio_x.bin", replay=info))
    yield


def test_english_screen_has_no_chinese_and_no_codes(window: MainWindow) -> None:
    window.apply_settings(window.settings.replace(language="en"))
    assert i18n.language() == "en"
    for _ in every_state(window):
        window.root.update_idletasks()
        for text in visible_text(window):
            assert not CJK.search(text), text
            assert not CODE.search(text), text


def test_chinese_screen_shows_no_protocol_codes(window: MainWindow) -> None:
    for _ in every_state(window):
        window.root.update_idletasks()
        for text in visible_text(window):
            assert not CODE.search(text), text


def test_changing_only_the_language_keeps_listening(window: MainWindow) -> None:
    engine = window.engine
    assert isinstance(engine, FakeEngine)
    starts: List[Settings] = []
    engine.start_live = starts.append  # type: ignore[method-assign]
    window.render(snap_from(ready_monitor(), 2.99))
    window.apply_settings(window.settings.replace(language="en"))
    window.render(snap_from(ready_monitor(), 2.99))
    assert starts == [] and window.band.word.cget("text") == "Usable"
    assert window.root.title().startswith("Usable | AIO NAV Receiver")
    window.apply_settings(window.settings.replace(nav_port=9100))
    assert len(starts) == 1
