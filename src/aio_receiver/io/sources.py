"""Packet sources for the engine: live UDP sockets, or a recording on a virtual clock.

poll(timeout) returns the packets that arrived and a horizon: the time up to which every packet has
been delivered. The engine advances the monitor only to the horizon, so a replay never judges a
moment whose packets it has not fed yet.
"""

from __future__ import annotations

import select
import socket
import time
from typing import List, NamedTuple, Optional, Sequence, Tuple

from ..i18n import Msg, msg, os_error
from .recording import Record, Recording

RCVBUF = 1 << 20
MAX_BATCH = 512                 # datagrams read per poll before the engine gets to evaluate


class Packet(NamedTuple):
    t: float
    sender: Optional[str]
    port: int
    data: bytes


Batch = Tuple[List[Packet], float]


class UdpSource:
    """Receive-only UDP sockets on one or two ports. Bind errors are kept, not raised."""

    kind = "live"

    def __init__(self, host: str, ports: Sequence[int]) -> None:
        self.host = host
        self.ports = sorted(set(ports))
        self.errors: List[Msg] = []
        self.socks: List[socket.socket] = []
        for port in self.ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: nobody else may share the port
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
                s.bind((host, port))
                s.setblocking(False)
            except OSError as e:
                s.close()
                self.errors.append(msg("fail.bind", addr=f"{host}:{port}", error=os_error(e)))
                continue
            self.socks.append(s)

    @property
    def address(self) -> str:
        return f"{self.host}:" + "/".join(str(p) for p in self.ports)

    @property
    def label(self) -> str:
        """For the application log and the recording header (not shown on screen)."""
        return f"listen {self.address}"

    @staticmethod
    def clock() -> float:
        return time.perf_counter()

    @property
    def start_time(self) -> float:
        return self.clock()

    def poll(self, timeout: float) -> Batch:
        out: List[Packet] = []
        if not self.socks:
            time.sleep(timeout)
            return out, self.clock()
        ready, _, _ = select.select(self.socks, [], [], max(timeout, 0.0))
        for s in ready:
            while len(out) < MAX_BATCH:
                try:
                    data, addr = s.recvfrom(2048)
                except BlockingIOError:
                    break
                except OSError:
                    break           # e.g. Windows WSAECONNRESET; the socket stays usable
                out.append(Packet(time.perf_counter(), addr[0], addr[1], data))
        return out, self.clock()     # stamped as read, so later datagrams always get later times

    def close(self) -> None:
        for s in self.socks:
            s.close()
        self.socks = []


class ReplaySource:
    """A recording played on a virtual clock that starts at the first packet's receive time."""

    kind = "replay"

    def __init__(self, rec: Recording, speed: float = 1.0) -> None:
        self.rec = rec
        self.pos = 0
        self.speed = speed
        self.errors: List[Msg] = []
        self._anchor_real, self._anchor_virt = time.perf_counter(), rec.t0

    @property
    def address(self) -> str:
        return self.rec.path.name

    @property
    def label(self) -> str:
        return f"replay {self.rec.path.name}"

    def clock(self) -> float:
        return min(self._anchor_virt + (time.perf_counter() - self._anchor_real) * self.speed, self.rec.t_end)

    @property
    def start_time(self) -> float:
        return self.rec.t0          # judge from the first packet exactly, whatever the start-up delay

    def set_speed(self, speed: float) -> None:
        self._anchor_virt, self._anchor_real, self.speed = self.clock(), time.perf_counter(), speed

    @property
    def done(self) -> bool:
        return self.pos >= len(self.rec)

    def poll(self, timeout: float) -> Batch:
        now = self.clock()
        if not self.done and self.rec.times[self.pos] > now:
            wait = (self.rec.times[self.pos] - now) / self.speed
            time.sleep(max(0.0, min(timeout, wait)))
            now = self.clock()
        elif self.done:
            time.sleep(max(0.0, timeout))
        out: List[Packet] = []
        times = self.rec.times
        while self.pos < len(times) and times[self.pos] <= now and len(out) < MAX_BATCH:
            r: Record = self.rec[self.pos]
            out.append(Packet(r.t, r.sender, r.port, r.data))
            self.pos += 1
        horizon = now if len(out) < MAX_BATCH else out[-1].t
        return out, horizon

    def close(self) -> None:
        self.rec.close()
