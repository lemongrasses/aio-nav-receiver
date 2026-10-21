"""Characterisation: real Jetson recordings must give exactly the verdicts the pre-1.0 gate gave.

The fixtures are windows of a 30-minute session (positions moved to 0°N 0°E): boot, CHECKING,
FAULT, the alignment states, READY. Their .expected.json files were produced by the old gate.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List

import pytest

from aio_receiver.analysis import analyse
from aio_receiver.config import Settings
from aio_receiver.core.gate import GateConfig
from aio_receiver.core.monitor import Transition
from aio_receiver.engine import Engine
from aio_receiver.io.recording import Recording
from helpers import expected, fixture_file, legacy_text

FIXTURES = ["real_restart_v1.bin.gz", "real_ready_v2.bin.gz"]


@pytest.mark.parametrize("name", FIXTURES)
def test_real_recording_matches_old_gate(name: str, tmp_path: Path) -> None:
    exp = expected(name)
    with Recording(fixture_file(name, tmp_path)) as rec:
        rep = analyse(rec, GateConfig())
    got = [[tr.t, tr.verdict.usable, legacy_text(tr.verdict)] for tr in rep.transitions]
    assert len(got) == len(exp["transitions"])
    for g, e in zip(got, exp["transitions"]):
        assert g[1:] == e[1:]
        assert g[0] == pytest.approx(e[0], abs=1e-9)
    assert rep.usable_total == pytest.approx(exp["usable_s"], abs=1e-6)
    assert vars(rep.count) == exp["count"]


def test_engine_replay_at_10x_equals_headless(tmp_path: Path) -> None:
    """Same packets, same transitions: the engine thread's timing must not matter."""
    path = fixture_file("real_ready_v2.bin.gz", tmp_path)
    with Recording(path) as rec:
        headless = analyse(rec, GateConfig())
    seen: List[Transition] = []
    lock = threading.Lock()

    def collect(tr: Transition) -> None:
        with lock:
            seen.append(tr)

    engine = Engine(on_transition=collect)
    engine.start_replay(path, Settings(), speed=10.0)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            snap = engine.snapshot
            if snap is not None and snap.replay is not None and snap.replay.done and snap.now >= headless.t_end:
                break
            time.sleep(0.05)
        else:
            pytest.fail("replay did not finish")
        time.sleep(0.2)
        snap = engine.snapshot
        assert snap is not None
    finally:
        engine.stop()
    assert [(tr.t, tr.verdict) for tr in seen] == [(tr.t, tr.verdict) for tr in headless.transitions]
    assert snap.usable_total == pytest.approx(headless.usable_total, abs=1e-9)
    assert snap.nav_sender == "192.168.116.1"


def test_source_filter_applies_to_v2_replay(tmp_path: Path) -> None:
    path = fixture_file("real_ready_v2.bin.gz", tmp_path)
    with Recording(path) as rec:
        rep = analyse(rec, Settings(allowed_from="10.0.0.1").gate_config())
    assert rep.count.foreign == rep.packets and rep.usable_total == 0


def test_source_filter_cannot_apply_to_v1_replay(tmp_path: Path) -> None:
    path = fixture_file("real_restart_v1.bin.gz", tmp_path)
    with Recording(path) as rec:
        rep = analyse(rec, Settings(allowed_from="10.0.0.1").gate_config())
    assert rep.count.foreign == 0 and rep.usable_total > 0
