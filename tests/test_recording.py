from __future__ import annotations

import gzip
import struct
import time
from pathlib import Path

import pytest

from aio_receiver.core import protocol as P
from aio_receiver.io.recording import (
    CSV_HEADER,
    BackgroundWriter,
    Recording,
    RecordingWriter,
    export_csv,
    nav_csv_row,
    new_base,
)
from helpers import nav, status


def write_v1(path: Path, packets: list) -> None:  # type: ignore[type-arg]
    path.write_bytes(b"".join(struct.pack("<dH", t, len(d)) + d for t, d in packets))


def test_v1_files_still_read(tmp_path: Path) -> None:
    packets = [(100.0, status(1)), (100.5, nav(1.0)), (102.0, status(2))]
    f = tmp_path / "old.bin"
    write_v1(f, packets)
    with open(f, "ab") as fh:
        fh.write(b"\x00\x00\x00")                  # a truncated tail is ignored
    with Recording(f) as rec:
        assert rec.version == 1 and not rec.has_senders and rec.header == {}
        assert [(r.t, r.data) for r in rec] == packets
        assert rec[0].sender is None
        assert (rec.t0, rec.t_end, len(rec)) == (100.0, 102.0, 3)
        assert rec.unix_time(101.0) is None


def test_v2_roundtrip_with_header_csv_and_events(tmp_path: Path) -> None:
    w = RecordingWriter(new_base(tmp_path / "logs"), 1000.0, time.time(), {"listen": "監聽 0.0.0.0:9000"})
    n = P.decode_nav(nav(5.0))
    w.packet(1000.5, "192.168.116.1", 50000, nav(5.0), n)
    w.packet(1001.0, "192.168.116.1", 50001, status(1), None)
    w.event(1001.0, "可用 可用")
    w.close()
    with Recording(Path(f"{w.base}.bin")) as rec:
        assert rec.version == 2 and rec.has_senders
        assert rec.header["listen"] == "監聽 0.0.0.0:9000"
        assert [(r.t, r.sender, r.port) for r in rec] == [(1000.5, "192.168.116.1", 50000),
                                                          (1001.0, "192.168.116.1", 50001)]
        assert rec[1].data == status(1)
        assert rec.unix_time(1000.0) == pytest.approx(time.time(), abs=60)
    csv = Path(f"{w.base}_nav.csv").read_text(encoding="utf-8").splitlines()
    assert csv[0] + "\n" == CSV_HEADER and len(csv) == 2
    assert csv[1].split(",")[0] == "1000.500000"
    assert Path(f"{w.base}_events.log").read_text(encoding="utf-8").endswith(" 可用 可用\n")


def test_csv_keeps_full_precision() -> None:
    n = P.decode_nav(P.encode_nav(1.0, 22.99690123456789, 120.2218000001, height=35.123456789))
    assert n is not None
    cells = nav_csv_row(0.0, n, None).rstrip("\n").split(",")
    names = ["rx_time", *P.NAV_NAMES, "flags", "unix_time"]
    row = dict(zip(names, cells))
    assert float(row["lat"]) == n.lat and float(row["lon"]) == n.lon
    assert struct.pack("<f", float(row["height"])) == struct.pack("<f", n.height)
    assert row["unix_time"] == ""


def test_export(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    write_v1(f, [(1.0, nav(1.0)), (1.1, status(1)), (1.2, nav(1.01))])
    with Recording(f) as rec:
        assert export_csv(rec, tmp_path / "x.csv") == 2


@pytest.mark.parametrize("content,msg", [
    (b"", "空"),
    (b"\x00" * 5, "沒有完整"),
    (gzip.compress(struct.pack("<dH", 1.0, 3) + b"abc" * 50), "不是 AIO|沒有完整"),  # e.g. a .gz handed over
    (struct.pack("<dH", 1.0, 3) + b"abc", "不是 AIO"),
])
def test_unusable_files_are_rejected(tmp_path: Path, content: bytes, msg: str) -> None:
    f = tmp_path / "bad.bin"
    f.write_bytes(content)
    with pytest.raises(ValueError, match=msg):
        Recording(f)


def test_writer_failure_is_an_oserror(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(OSError):
        RecordingWriter(blocker / "logs" / "x", 0.0, 0.0, {})    # a file where the folder should be


def wait(cond, timeout: float = 5.0) -> bool:  # type: ignore[no-untyped-def]
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_background_writer_writes_everything_then_closes(tmp_path: Path) -> None:
    w = BackgroundWriter(tmp_path, 10.0, {})
    for i in range(500):
        w.packet(10.0 + i / 100, "10.0.0.1", 1, nav(i / 100), None)
    w.event(15.0, "停止記錄")
    w.close()
    assert w.join(5.0) and w.error is None
    with Recording(Path(f"{w.base}.bin")) as rec:
        assert len(rec) == 500


def test_background_writer_reports_failures_instead_of_raising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    w = BackgroundWriter(blocker / "logs", 0.0, {})                    # cannot create the folder
    assert wait(lambda: w.error is not None) and str(w.error).startswith("無法開始記錄")
    w.packet(0.0, None, 0, b"x", None)                                 # ignored, never raises

    monkeypatch.setattr(BackgroundWriter, "QUEUE_MAX", 3)
    monkeypatch.setattr(RecordingWriter, "packet", lambda *a: time.sleep(1))   # storage that hangs
    slow = BackgroundWriter(tmp_path, 0.0, {})
    for i in range(10):
        slow.packet(i, None, 0, b"x", None)
    assert str(slow.error) == "記錄裝置太慢，已停止記錄"
