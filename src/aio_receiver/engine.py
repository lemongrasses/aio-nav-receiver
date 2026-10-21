"""The engine thread: source -> monitor -> recorder, published as frozen snapshots.

Only this thread touches the sockets, the replay file, the monitor and the recording files. The UI
reads `engine.snapshot` (one reference, replaced atomically) and sends commands through a queue.
Any failure inside it ends in a snapshot that says so, which the UI shows as 阻擋.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from . import __version__
from .config import Settings, to_dict
from .core import protocol as P
from .core.gate import Counters, GateConfig, Verdict
from .core.monitor import Monitor, Transition
from .core.track import TrackPoint
from .io.recording import BackgroundWriter, Recording
from .io.sources import ReplaySource, UdpSource

log = logging.getLogger(__name__)

PUBLISH_INTERVAL = 0.05         # seconds between snapshots
MAX_WAIT = 0.05                 # longest wait for packets before re-evaluating
WRITER_FINISH = 3.0             # seconds a stopped recording may take to write out its queue

Source = Union[UdpSource, ReplaySource]


@dataclass(frozen=True)
class ReplayInfo:
    file: str
    pos: int
    total: int
    elapsed: float
    duration: float
    speed: float
    done: bool
    has_senders: bool


@dataclass(frozen=True)
class Snapshot:
    """Everything the screen shows, at engine time `now`. Never mutated after publishing."""

    now: float                          # engine clock: receive clock live, recorded time in replay
    built: float                        # time.perf_counter() when published (UI watchdog)
    verdict: Verdict
    usable_total: float
    cfg: GateConfig
    nav: Optional[P.NavPacket]
    nav_at: float
    status: Optional[P.StatusPacket]
    status_at: float
    count: Counters
    nav_rate: float
    flag_seen: Dict[str, float]
    nav_sender: Optional[str]
    status_sender: Optional[str]
    track: Tuple[TrackPoint, ...]
    track_version: int
    source_kind: str                    # "live" | "replay" | "stopped"
    source_label: str
    source_errors: Tuple[str, ...] = ()
    replay: Optional[ReplayInfo] = None
    recording: Optional[str] = None     # while recording: its path, without extension
    recording_error: Optional[str] = None
    engine_error: Optional[str] = None
    verdict_since: float = 0.0          # when the verdict last changed
    status_rate: float = 0.0
    ready_since: Optional[float] = None  # READY without inhibit since (the 2 s stability count)
    recording_since: Optional[float] = None

    @property
    def nothing_received(self) -> bool:
        return self.count.nav == 0 and self.count.status == 0

    @property
    def status_fresh(self) -> bool:
        return self.status is not None and self.now - self.status_at <= self.cfg.status_timeout

    @property
    def failure(self) -> Optional[str]:
        """A fault that overrides the verdict: the screen must show 阻擋 with this text."""
        if self.engine_error:
            return f"監看程式內部錯誤：{self.engine_error}"
        if self.source_errors:
            return "；".join(self.source_errors)
        return None


Command = Tuple[str, object]


@dataclass
class _Run:
    """State of one engine thread run (one source). Owned by that thread."""

    source: Source
    monitor: Monitor
    settings: Settings
    writer: Optional[BackgroundWriter] = None
    recording_since: Optional[float] = None
    closing: List[BackgroundWriter] = field(default_factory=list)     # stopped, still finishing their files
    recording_error: Optional[str] = None
    engine_error: Optional[str] = None
    track_cache: Tuple[int, Tuple[TrackPoint, ...]] = (-1, ())


class Engine:
    def __init__(self, on_transition: Optional[Callable[[Transition], None]] = None) -> None:
        self.snapshot: Optional[Snapshot] = None
        self._commands: queue.Queue[Command] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._on_transition = on_transition

    # ------------------------------------------------------------- control
    def start_live(self, settings: Settings) -> None:
        self.stop()
        self._start(UdpSource(settings.host, settings.ports), settings, use_filter=True)

    def start_replay(self, path: Path, settings: Settings, speed: float = 1.0) -> None:
        """Opens the file first, so a bad file raises here and the current run keeps going."""
        rec = Recording(path)
        self.stop()
        self._start(ReplaySource(rec, speed), settings, use_filter=rec.has_senders)

    def start_recording(self, folder: Path) -> None:
        self._commands.put(("record", folder))

    def stop_recording(self) -> None:
        self._commands.put(("record", None))

    def set_speed(self, speed: float) -> None:
        self._commands.put(("speed", speed))

    def clear_track(self) -> None:
        self._commands.put(("clear_track", None))

    def stop(self) -> None:
        t = self._thread
        if t is not None:
            self._stop.set()
            t.join(WRITER_FINISH + 2.0)
            if t.is_alive():
                log.error("engine thread did not stop")
        self._thread = None
        self._stop = threading.Event()
        while not self._commands.empty():
            self._commands.get_nowait()

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --------------------------------------------------------------- thread
    def _start(self, source: Source, settings: Settings, use_filter: bool) -> None:
        run = _Run(source, Monitor(settings.gate_config(use_filter)), settings)
        self._handle(run, run.monitor.advance(source.start_time))
        self._publish(run)
        self._thread = threading.Thread(target=self._main, args=(run, self._stop), name="engine", daemon=True)
        self._thread.start()

    def _main(self, run: _Run, stop: threading.Event) -> None:
        log.info("engine start: %s", run.source.label)
        try:
            self._loop(run, stop)
        except Exception as e:      # the screen must learn about any failure
            log.exception("engine failed")
            run.engine_error = f"{type(e).__name__}: {e}"
            self._publish(run)
        finally:
            self._close_writer(run, "停止記錄")
            run.source.close()
            for w in run.closing:               # let the files be completed before the run ends
                if not w.join(WRITER_FINISH):
                    log.error("recording %s did not finish writing in %.0f s", w.base, WRITER_FINISH)
            log.info("engine stop: %s", run.source.label)

    def _loop(self, run: _Run, stop: threading.Event) -> None:
        mon, src = run.monitor, run.source
        last_publish = 0.0
        while not stop.is_set():
            self._drain_commands(run)
            deadline = mon.gate.next_deadline(mon.t)
            wait = MAX_WAIT if deadline is None else min(MAX_WAIT, max(0.0, deadline - src.clock()))
            packets, horizon = src.poll(wait)
            for p in packets:
                kind, trs = mon.feed(p.data, p.t, p.sender)
                self._handle(run, trs)
                if run.writer is not None:
                    run.writer.packet(p.t, p.sender, p.port, p.data, mon.gate.nav if kind == "nav" else None)
            self._handle(run, mon.advance(horizon))
            self._check_writer(run)
            real = time.perf_counter()
            if real - last_publish >= PUBLISH_INTERVAL:
                self._publish(run)
                last_publish = real

    def _drain_commands(self, run: _Run) -> None:
        while True:
            try:
                cmd, arg = self._commands.get_nowait()
            except queue.Empty:
                return
            if cmd == "record":
                if arg is None:
                    self._close_writer(run, "停止記錄")
                elif run.writer is None and run.source.kind == "live":
                    self._open_writer(run, Path(str(arg)))
            elif cmd == "speed" and isinstance(run.source, ReplaySource):
                run.source.set_speed(float(str(arg)))
            elif cmd == "clear_track":
                run.monitor.track.clear()

    # ------------------------------------------------------------ recording
    # All file work happens on the recorder thread: this thread only queues, so a slow USB stick can
    # never delay the receive time stamps or the verdict.
    def _open_writer(self, run: _Run, folder: Path) -> None:
        header = {"app": "aio-nav-receiver", "app_version": __version__, "listen": run.source.label,
                  "settings": to_dict(run.settings)}
        w = BackgroundWriter(folder, run.source.clock(), header, csv=run.settings.record_csv)
        run.writer, run.recording_error, run.recording_since = w, None, run.monitor.t
        log.info("recording to %s", w.base)
        w.event(run.monitor.t, "開始記錄")
        v = run.monitor.verdict
        if v is not None:
            w.event(run.monitor.t, f"{v.word} {v.text}")

    def _check_writer(self, run: _Run) -> None:
        """A failed recording stops; monitoring goes on."""
        w = run.writer
        if w is not None and w.error is not None:
            log.warning("recording stopped: %s", w.error)
            run.recording_error = w.error
            w.close()
            run.closing.append(w)
            run.writer, run.recording_since = None, None

    def _close_writer(self, run: _Run, text: str) -> None:
        w = run.writer
        if w is not None:
            w.event(run.monitor.t, text)
            w.close()
            run.closing.append(w)
            run.writer, run.recording_since = None, None

    def _handle(self, run: _Run, transitions: List[Transition]) -> None:
        for tr in transitions:
            v = tr.verdict
            log.debug("%.3f %s %s", tr.t, v.word, v.text)
            if run.writer is not None:
                run.writer.event(tr.t, f"{v.word} {v.text}")
            if self._on_transition is not None:
                self._on_transition(tr)

    # -------------------------------------------------------------- publish
    def _publish(self, run: _Run) -> None:
        mon, g, src = run.monitor, run.monitor.gate, run.source
        track_version = mon.track.version
        if run.track_cache[0] != track_version:      # copy the points only when they changed
            run.track_cache = (track_version, tuple(mon.track.points))
        track = run.track_cache[1]
        replay = None
        if isinstance(src, ReplaySource):
            rec = src.rec
            replay = ReplayInfo(rec.path.name, src.pos, len(rec), mon.t - rec.t0, rec.t_end - rec.t0, src.speed,
                                src.done, rec.has_senders)
        assert mon.verdict is not None
        self.snapshot = Snapshot(
            now=mon.t, built=time.perf_counter(), verdict=mon.verdict, usable_total=mon.usable_total, cfg=g.cfg,
            nav=g.nav, nav_at=g.nav_at, status=g.status, status_at=g.status_at, count=g.count.copy(),
            nav_rate=mon.nav_rate(mon.t), flag_seen=dict(mon.flag_seen), nav_sender=mon.nav_sender,
            status_sender=mon.status_sender, track=track, track_version=track_version, source_kind=src.kind,
            source_label=src.label, source_errors=tuple(src.errors), replay=replay,
            recording=str(run.writer.base) if run.writer else None, recording_error=run.recording_error,
            engine_error=run.engine_error, verdict_since=mon.changed_at, status_rate=mon.status_rate(mon.t),
            ready_since=g.ready_since, recording_since=run.recording_since)
