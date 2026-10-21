"""The engine thread over real loopback UDP, and its failure handling."""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Callable, List

import pytest

from aio_receiver.config import Settings
from aio_receiver.core.gate import Reason
from aio_receiver.core.monitor import Transition
from aio_receiver.engine import Engine, Snapshot
from aio_receiver.io.recording import Recording, RecordingWriter
from aio_receiver.io.sources import UdpSource
from helpers import nav, status


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for(engine: Engine, cond: Callable[[Snapshot], bool], timeout: float = 5.0) -> Snapshot:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snap = engine.snapshot
        if snap is not None and cond(snap):
            return snap
        time.sleep(0.02)
    raise AssertionError(f"condition not met; last snapshot {engine.snapshot}")


def wait_written(events: Path, timeout: float = 5.0) -> str:
    """The recorder thread finishes in the background: wait for the last line of the session."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        text = events.read_text(encoding="utf-8") if events.exists() else ""
        if "停止記錄" in text:
            time.sleep(0.1)                         # the other files are closed right after
            return text
        time.sleep(0.05)
    raise AssertionError(f"{events} was not completed")


class Sender:
    """0x04 at 100 Hz and 0x05 at 20 Hz on a schedule. sleep() is coarse on some machines (about
    50 ms on CI macOS), so it catches up in bursts rather than sending fewer packets."""

    def __init__(self, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dest = ("127.0.0.1", port)
        self.seq, self.t = 0, 1000.0
        self.sent = 0

    def burst(self, seconds: float) -> None:
        start = time.perf_counter()
        for i in range(int(seconds * 100)):
            delay = start + i * 0.01 - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            if i % 5 == 0:
                self.seq += 1
                self.sock.sendto(status(self.seq), self.dest)
                self.sent += 1
            self.t += 0.01
            self.sock.sendto(nav(self.t), self.dest)
            self.sent += 1

    def close(self) -> None:
        self.sock.close()


@pytest.fixture
def live() -> tuple:  # type: ignore[type-arg]
    port = free_port()
    engine = Engine()
    settings = Settings(host="127.0.0.1", nav_port=port, ready_stable=0.2)
    engine.start_live(settings)
    sender = Sender(port)
    yield engine, sender, settings
    sender.close()
    engine.stop()


def test_live_udp_becomes_usable_then_blocks_when_silent(live: tuple) -> None:  # type: ignore[type-arg]
    engine, sender, _ = live
    sender.burst(0.6)
    snap = wait_for(engine, lambda s: s.verdict.usable)
    assert snap.nav_sender == "127.0.0.1" and snap.count.bad == 0 and snap.source_kind == "live"
    snap = wait_for(engine, lambda s: not s.verdict.usable)          # 0x04 older than 0.5 s
    assert snap.verdict.text == "導航資料太舊 (0x04)"
    assert snap.failure is None


def test_recording_writes_a_v2_file(live: tuple, tmp_path: Path) -> None:  # type: ignore[type-arg]
    engine, sender, settings = live
    engine.start_recording(tmp_path)
    base = wait_for(engine, lambda s: s.recording is not None).recording
    assert Path(str(base)).parent == tmp_path
    sender.burst(0.5)
    engine.stop_recording()
    wait_for(engine, lambda s: s.recording is None)
    events = wait_written(Path(f"{base}_events.log"))
    assert "開始記錄" in events and "可用" in events
    with Recording(Path(f"{base}.bin")) as rec:
        assert rec.version == 2 and len(rec) >= 0.95 * sender.sent and rec[0].sender == "127.0.0.1"
        assert rec.header["settings"]["nav_port"] == settings.nav_port


def test_slow_storage_does_not_delay_receiving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A USB stick that stalls a write for 0.8 s must not stamp packets late or invent a 0x04 timeout."""
    calls = [0]
    original = RecordingWriter.packet

    def stalling(self: RecordingWriter, *args: object) -> None:
        calls[0] += 1
        if calls[0] == 60:
            time.sleep(0.8)
        original(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(RecordingWriter, "packet", stalling)
    seen: List[Transition] = []
    port = free_port()
    engine = Engine(on_transition=seen.append)
    engine.start_live(Settings(host="127.0.0.1", nav_port=port, ready_stable=0.2))
    sender = Sender(port)
    try:
        engine.start_recording(tmp_path)
        base = wait_for(engine, lambda s: s.recording is not None).recording
        sender.burst(0.5)                                   # becomes usable
        wait_for(engine, lambda s: s.verdict.usable)
        sender.burst(1.5)                                   # the stall happens in here
        stamps = [t for t, s in [(tr.t, tr.verdict.reason) for tr in seen] if s is Reason.NAV_STALE]
        engine.stop_recording()
        wait_for(engine, lambda s: s.recording is None)
    finally:
        sender.close()
        engine.stop()
    assert calls[0] >= 60, "the stall was never reached"
    assert stamps == [], "a false 0x04 timeout was reported while storage was slow"
    wait_written(Path(f"{base}_events.log"))
    with Recording(Path(f"{base}.bin")) as rec:
        gaps = [b - a for a, b in zip(rec.times, rec.times[1:])]
        recorded = len(rec)
    assert recorded >= 0.95 * sender.sent, (recorded, sender.sent)
    assert max(gaps) < 0.4, "receive times were held back by the 0.8 s write stall"


def test_recording_failure_keeps_monitoring(live: tuple, tmp_path: Path) -> None:  # type: ignore[type-arg]
    engine, sender, _ = live
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("x")
    engine.start_recording(blocker / "logs")
    snap = wait_for(engine, lambda s: s.recording_error is not None)
    assert snap.recording is None
    sender.burst(0.6)
    wait_for(engine, lambda s: s.verdict.usable)


class _Exploding:
    kind, label, errors = "live", "test", []  # type: ignore[var-annotated]
    start_time = 0.0

    def clock(self) -> float:
        return time.perf_counter()

    def poll(self, timeout: float) -> tuple:  # type: ignore[type-arg]
        raise RuntimeError("boom")

    def close(self) -> None:
        pass


def test_engine_crash_is_reported_not_hidden() -> None:
    engine = Engine()
    engine._start(_Exploding(), Settings(), use_filter=True)  # type: ignore[arg-type]
    try:
        snap = wait_for(engine, lambda s: s.engine_error is not None)
    finally:
        engine.stop()
    assert snap.failure is not None and "boom" in snap.failure
    assert not snap.verdict.usable


def test_port_in_use_is_an_error_not_a_crash() -> None:
    port = free_port()
    first = UdpSource("127.0.0.1", [port])
    second = UdpSource("127.0.0.1", [port])
    try:
        assert first.errors == [] and len(second.errors) == 1 and str(port) in second.errors[0]
        packets: List[object] = []
        packets, _ = second.poll(0.01)
        assert packets == []
    finally:
        first.close()
        second.close()
