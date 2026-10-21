"""Trajectory buffer and its flat-earth projection (pure; drawn by ui/panels.py)."""

from __future__ import annotations

import math
from collections import deque
from typing import Deque, NamedTuple, Optional, Sequence

EARTH_R = 6378137.0
TRACK_MAX = 3000                # points kept: 5 minutes at one point per 0.1 s of navigation time
TRACK_STEP_S = 0.1              # navigation time between points
TRACK_RESET_S = 1.0             # navigation time going back more than this = AIO NAV restarted
TRACK_MIN_SPAN_M = 20.0         # never zoom in further, so a parked vehicle does not plot its noise


class TrackPoint(NamedTuple):
    lat: float
    lon: float
    usable: bool


class Track:
    def __init__(self, maxlen: int = TRACK_MAX) -> None:
        self.points: Deque[TrackPoint] = deque(maxlen=maxlen)
        self.version = 0            # bumped on every change, so a reader copies only when needed
        self._last_time: Optional[float] = None

    def add(self, nav_time_s: float, lat: float, lon: float, usable: bool) -> None:
        last = self._last_time
        if last is not None and nav_time_s < last - TRACK_RESET_S:
            self.points.clear()     # AIO NAV restarted: a new trajectory
            last = None
        if last is not None and nav_time_s < last + TRACK_STEP_S - 1e-6:    # tolerance: decimal times
            return
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return
        self._last_time = nav_time_s
        self.points.append(TrackPoint(lat, lon, usable))
        self.version += 1

    def clear(self) -> None:
        self.points.clear()
        self._last_time = None
        self.version += 1


class Projection(NamedTuple):
    xs: list[float]             # metres east of the newest point
    ys: list[float]             # metres north of the newest point
    span: float                 # metres covered by the larger axis, at least TRACK_MIN_SPAN_M
    cx: float                   # centre of the bounding box
    cy: float


def project(points: Sequence[TrackPoint]) -> Optional[Projection]:
    """Local east/north metres around the newest point (equirectangular; exact enough for a few km)."""
    if not points:
        return None
    lat0, lon0 = points[-1].lat, points[-1].lon
    ky = math.radians(1) * EARTH_R
    kx = ky * math.cos(math.radians(lat0))
    xs = [(p.lon - lon0) * kx for p in points]
    ys = [(p.lat - lat0) * ky for p in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), TRACK_MIN_SPAN_M)
    return Projection(xs, ys, span, (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)


def nice_length(x: float) -> float:
    """The largest 1, 2 or 5 x 10^k not above x (scale bar length)."""
    k = 10 ** math.floor(math.log10(max(x, 1e-9)))
    return max(m * k for m in (1, 2, 5) if m * k <= x) if x >= k else k
