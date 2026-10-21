"""Recording files: raw packets (.bin), decoded 0x04 (_nav.csv) and verdict changes (_events.log).

.bin v2:  b"AIONREC\\0" u16 version u32 header_len header(JSON)  then per packet
          f64 rx_time  u16 length  4s sender IPv4  u16 sender port  bytes[length]
.bin v1:  no header; per packet  f64 rx_time  u16 length  bytes[length]   (before 1.0; still read)

rx_time is the receiver's monotonic clock in seconds; the v2 header pairs it with Unix time.
A truncated last record (power loss, USB pulled) is ignored.
"""

from __future__ import annotations

import json
import math
import mmap
import queue
import socket
import struct
import threading
import time
from array import array
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Dict, Iterator, NamedTuple, Optional, Tuple

from ..core import protocol as P
from ..i18n import Msg, UserError, msg, os_error

MAGIC = b"AIONREC\x00"
VERSION = 2
_PREAMBLE = struct.Struct("<8sHI")
_REC_V1 = struct.Struct("<dH")
_REC_V2 = struct.Struct("<dH4sH")
FLUSH_INTERVAL = 1.0            # seconds: at most this much is lost on power loss

CSV_HEADER = "rx_time," + ",".join(P.NAV_NAMES) + ",flags,unix_time\n"


class Record(NamedTuple):
    t: float
    sender: Optional[str]       # None in v1 recordings
    port: int
    data: bytes


class Recording:
    """A .bin file indexed in place (mmap + two arrays), so hours of packets cost little memory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._f = open(path, "rb")             # noqa: SIM115 - lives as long as the mmap
        try:
            size = self._f.seek(0, 2)
            if size == 0:
                raise UserError("rec.empty")
            self._mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ)
        except BaseException:
            self._f.close()
            raise
        self.header: Dict[str, Any] = {}
        self.version = 1
        start = 0
        if self._mm[:8] == MAGIC:
            _, self.version, n = _PREAMBLE.unpack_from(self._mm, 0)
            if self.version != VERSION:
                self.close()
                raise UserError("rec.version", version=self.version)
            start = _PREAMBLE.size + n
            self.header = json.loads(bytes(self._mm[_PREAMBLE.size:start]).decode("utf-8"))
        self._rec = _REC_V2 if self.version == 2 else _REC_V1
        self.times = array("d")
        self.offsets = array("Q")
        self._index(start, size)
        if not self.times:
            self.close()
            raise UserError("rec.no_records")
        if self.version == 1 and not any(self[i].data[:2] == P.SYNC for i in range(min(len(self), 20))):
            self.close()                        # v1 has no magic: refuse files that hold no AIO frames
            raise UserError("rec.not_aio")

    def _index(self, i: int, size: int) -> None:
        mm, rec, unpack = self._mm, self._rec.size, _REC_V1.unpack_from
        times, offsets = self.times, self.offsets
        last = float("-inf")
        while i + rec <= size:
            t, n = unpack(mm, i)
            if i + rec + n > size:
                break                           # truncated last record
            if not (math.isfinite(t) and t >= last):
                break                           # receive times only go forward: the rest is not a record
            last = t
            times.append(t)
            offsets.append(i)
            i += rec + n

    def __len__(self) -> int:
        return len(self.times)

    def __getitem__(self, i: int) -> Record:
        o = self.offsets[i]
        if self.version == 1:
            t, n = _REC_V1.unpack_from(self._mm, o)
            return Record(t, None, 0, bytes(self._mm[o + _REC_V1.size:o + _REC_V1.size + n]))
        t, n, ip, port = _REC_V2.unpack_from(self._mm, o)
        return Record(t, socket.inet_ntoa(ip), port, bytes(self._mm[o + _REC_V2.size:o + _REC_V2.size + n]))

    def __iter__(self) -> Iterator[Record]:
        return (self[i] for i in range(len(self)))

    @property
    def t0(self) -> float:
        return self.times[0]

    @property
    def t_end(self) -> float:
        return self.times[-1]

    @property
    def has_senders(self) -> bool:
        return self.version >= 2

    def unix_time(self, t: float) -> Optional[float]:
        clock = self.header.get("clock")
        if not isinstance(clock, dict):
            return None
        return float(clock["unix"]) + t - float(clock["monotonic"])

    def close(self) -> None:
        mm = getattr(self, "_mm", None)
        if mm is not None:
            mm.close()
        self._f.close()

    def __enter__(self) -> Recording:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def nav_csv_row(rx_time: float, n: P.NavPacket, unix_time: Optional[float]) -> str:
    """One CSV line. f64 fields at full precision; f32 fields at 9 digits, which round-trips f32."""
    cells = [f"{rx_time:.6f}"]
    for name, v in zip(P.NAV_NAMES, n):
        if isinstance(v, int):
            cells.append(str(v))
        elif name in P.NAV_F64:
            cells.append(repr(v))
        else:
            cells.append(f"{v:.9g}")
    cells.append(str(n.flags))
    cells.append("" if unix_time is None else f"{unix_time:.6f}")
    return ",".join(cells) + "\n"


def event_line(unix_time: float, text: str) -> str:
    return f"{datetime.fromtimestamp(unix_time).isoformat(timespec='milliseconds')} {text}\n"


def new_base(folder: Path) -> Path:
    """Path of a new recording without extension: folder/aio_YYYYmmdd_HHMMSS."""
    return folder / f"aio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class RecordingWriter:
    """Writes one session, synchronously. Every method may raise OSError (disk full, USB pulled).

    (mono_ref, unix_ref) is one instant on the receive clock and on the wall clock.
    """

    def __init__(self, base: Path, mono_ref: float, unix_ref: float, header: Dict[str, Any],
                 csv: bool = True) -> None:
        base.parent.mkdir(parents=True, exist_ok=True)
        self.base = base
        self._mono_ref, self._unix_ref = mono_ref, unix_ref
        head = dict(header, clock={"monotonic": self._mono_ref, "unix": self._unix_ref},
                    created=datetime.now().astimezone().isoformat(timespec="seconds"))
        self._files: list[IO[Any]] = []
        try:
            self.raw = self._open(f"{self.base}.bin", "wb")
            blob = json.dumps(head, ensure_ascii=False).encode("utf-8")
            self.raw.write(_PREAMBLE.pack(MAGIC, VERSION, len(blob)) + blob)
            self.csv = self._open(f"{self.base}_nav.csv", "w", encoding="utf-8", newline="") if csv else None
            if self.csv:
                self.csv.write(CSV_HEADER)
            self.events = self._open(f"{self.base}_events.log", "w", encoding="utf-8")
        except BaseException:
            self.close()
            raise
        self._last_flush = time.perf_counter()

    def _open(self, path: str, mode: str, **kw: Any) -> IO[Any]:
        f = open(path, mode, **kw)             # noqa: SIM115 - closed by close()
        self._files.append(f)
        return f

    @property
    def name(self) -> str:
        return self.base.name

    def unix_time(self, t: float) -> float:
        return self._unix_ref + t - self._mono_ref

    def packet(self, t: float, sender: Optional[str], port: int, data: bytes, nav: Optional[P.NavPacket]) -> None:
        ip = socket.inet_aton(sender) if sender else b"\0\0\0\0"
        self.raw.write(_REC_V2.pack(t, len(data), ip, port) + data)
        if nav is not None and self.csv:
            self.csv.write(nav_csv_row(t, nav, self.unix_time(t)))

    def event(self, t: float, text: str) -> None:
        self.events.write(event_line(self.unix_time(t), text))
        self.events.flush()

    def flush_if_due(self) -> None:
        now = time.perf_counter()
        if now - self._last_flush >= FLUSH_INTERVAL:
            self._last_flush = now
            for f in self._files:
                f.flush()

    def close(self) -> None:
        """Close every file; errors are swallowed, since this also runs after a write failed."""
        for f in self._files:
            try:
                f.close()
            except OSError:
                pass
        self._files = []


Item = Tuple[Any, ...]


class BackgroundWriter:
    """A RecordingWriter on its own thread, so slow or failing storage never delays receiving.

    packet() and event() only queue and never block or raise. Any failure (cannot create the files,
    a write error, storage too slow for the queue) is put in .error; the owner then stops recording.
    """

    QUEUE_MAX = 30000           # about 5 minutes of 0x04 at 100 Hz

    def __init__(self, folder: Path, clock_now: float, header: Dict[str, Any], csv: bool = True) -> None:
        self.base = new_base(folder)
        self.error: Optional[Msg] = None
        self._q: queue.Queue[Optional[Item]] = queue.Queue(self.QUEUE_MAX)
        self._abort = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(clock_now, time.time(), header, csv),
                                        name="recorder", daemon=True)
        self._thread.start()

    def packet(self, t: float, sender: Optional[str], port: int, data: bytes, nav: Optional[P.NavPacket]) -> None:
        self._put(("p", t, sender, port, data, nav))

    def event(self, t: float, text: str) -> None:
        self._put(("e", t, text))

    def _put(self, item: Optional[Item]) -> None:
        if self.error is not None:
            return
        try:
            self._q.put_nowait(item)
        except queue.Full:
            self.error = msg("rec.too_slow")
            self._abort.set()

    def close(self) -> None:
        """Finish writing what is queued, then close the files (in the background)."""
        try:
            self._q.put_nowait(None)
        except queue.Full:
            self._abort.set()

    def join(self, timeout: float) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self, mono_ref: float, unix_ref: float, header: Dict[str, Any], csv: bool) -> None:
        try:
            w = RecordingWriter(self.base, mono_ref, unix_ref, header, csv)
        except OSError as e:
            self.error = msg("rec.cannot_start", error=os_error(e), folder=str(self.base.parent))
            return
        try:
            while not self._abort.is_set():
                try:
                    item = self._q.get(timeout=FLUSH_INTERVAL)
                except queue.Empty:
                    w.flush_if_due()
                    continue
                if item is None:
                    break
                if item[0] == "p":
                    w.packet(*item[1:])
                else:
                    w.event(*item[1:])
                w.flush_if_due()
        except OSError as e:
            self.error = msg("rec.stopped", error=os_error(e))
        finally:
            w.close()


def export_csv(rec: Recording, out: Path) -> int:
    """Write the decoded 0x04 packets of a recording as CSV. Returns the number of rows."""
    rows = 0
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(CSV_HEADER)
        for r in rec:
            n = P.decode_nav(r.data)
            if n is not None:
                f.write(nav_csv_row(r.t, n, rec.unix_time(r.t)))
                rows += 1
    return rows
