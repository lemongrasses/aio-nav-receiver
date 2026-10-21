"""The screen's parts. Each builds its widgets once and update()s them from a Snapshot.

All text comes from i18n in the current language; changing the language rebuilds the parts.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .. import i18n, osutil
from ..core import protocol as P
from ..core.track import nice_length, project
from ..engine import Snapshot
from ..i18n import t
from . import presentation as V
from . import theme as T

REPLAY_SPEEDS = (1, 2, 5, 10)
GAP = 14                    # gutter between the body's areas
fmt_dur = V.fmt_dur


def elide(text: str, n: int) -> str:
    """Shorten from the middle, keeping the drive and the file name of a path visible."""
    return text if len(text) <= n else text[:n // 3] + "…" + text[-(n - n // 3 - 1):]


def area(parent: tk.Misc, col: int, title: str) -> Tuple[tk.Frame, tk.Frame]:
    """A body area: plain white, no outline, separated by the kerb-grey gutter. Returns (frame, header)."""
    f = tk.Frame(parent, bg=T.PANEL, padx=20, pady=14)
    f.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else GAP, 0))
    head = tk.Frame(f, bg=T.PANEL)
    head.pack(fill="x", pady=(0, 12))
    tk.Label(head, text=title, font=(T.TXT, 13, "bold"), fg=T.ASPHALT, bg=T.PANEL).pack(side="left")
    return f, head


class LinkLight:
    """Header indicator for one packet stream: dot plus rate and age, or how long it has been gone."""

    def __init__(self, head: tk.Frame) -> None:
        self.text = tk.Label(head, text="", font=(T.TXT, 11), fg=T.MUTED, bg=T.PANEL)
        self.text.pack(side="right")
        self.dot = tk.Canvas(head, width=12, height=12, bg=T.PANEL, highlightthickness=0)
        self.dot.pack(side="right", padx=(0, 6))
        self._oval = self.dot.create_oval(1, 1, 11, 11, fill=T.LINE, outline="")

    def show(self, link: V.Link) -> None:
        self.dot.itemconfigure(self._oval, fill=T.DOT[link.kind])
        self.text.configure(text=link.text, fg=T.STOP if link.kind == "stop" else T.MUTED)


def value_grid(parent: tk.Misc, rows: Sequence[Tuple[str, str]], cols: int, size: int) -> Dict[str, tk.Label]:
    """Label above value; `rows` holds (key, i18n key of the label)."""
    g = tk.Frame(parent, bg=T.PANEL)
    g.pack(fill="x")
    out = {}
    for i, (key, label) in enumerate(rows):
        r, c = divmod(i, cols)
        cell = tk.Frame(g, bg=T.PANEL)
        cell.grid(row=r, column=c, sticky="w", padx=(0, 16), pady=(0, 10))
        tk.Label(cell, text=t(label), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(anchor="w")
        v = tk.Label(cell, text="—", font=(T.NUM, size), fg=T.ASPHALT, bg=T.PANEL)
        v.pack(anchor="w")
        out[key] = v
    for c in range(cols):
        g.columnconfigure(c, weight=1)
    return out


# ---------------------------------------------------------------------------------------- top
class ReplayBar:
    """Only while replaying: says plainly that this is not live, and holds the replay's controls."""

    def __init__(self, root: tk.Misc, on_speed: Callable[[], None], on_live: Callable[[], None]) -> None:
        self.frame = f = tk.Frame(root, bg=T.ASPHALT, padx=28, pady=8)
        tk.Label(f, text=t("replay.banner"), font=(T.TXT, 11, "bold"), fg="white", bg=T.ASPHALT).pack(side="left")
        self.file = tk.Label(f, text="", font=(T.NUM, 11), fg="#B9C2CA", bg=T.ASPHALT)
        self.file.pack(side="left", padx=(16, 0))
        ttk.Button(f, text=t("replay.live"), command=on_live).pack(side="right")
        self.speed = ttk.Combobox(f, values=[f"{s}×" for s in REPLAY_SPEEDS], width=5, state="readonly")
        self.speed.set("1×")
        self.speed.bind("<<ComboboxSelected>>", lambda _e: on_speed())
        self.speed.pack(side="right", padx=(0, 12))
        tk.Label(f, text=t("replay.speed"), font=(T.TXT, 10), fg="#B9C2CA", bg=T.ASPHALT).pack(side="right",
                                                                                            padx=(0, 6))
        self.time = tk.Label(f, text="", font=(T.TXT, 11), fg="white", bg=T.ASPHALT)
        self.time.pack(side="right", padx=(0, 16))
        self.bar = tk.Canvas(f, height=6, bg="#3A454F", highlightthickness=0)
        self.bar.pack(side="right", fill="x", expand=True, padx=(24, 12))
        self._fill = self.bar.create_rectangle(0, 0, 0, 6, fill="white", outline="")

    @property
    def speed_value(self) -> float:
        return float(self.speed.get().rstrip("×"))

    def update(self, snap: Snapshot) -> None:
        rp = snap.replay
        if rp is None:
            return
        self.file.configure(text=rp.file)
        done = f"  {t('replay.done')}" if rp.done else ""
        self.time.configure(text=f"{fmt_dur(rp.elapsed)} / {fmt_dur(rp.duration)}{done}")
        frac = rp.elapsed / rp.duration if rp.duration > 0 else 1.0
        self.bar.coords(self._fill, 0, 0, self.bar.winfo_width() * max(0.0, min(frac, 1.0)), 6)


class VerdictBand:
    """The answer. Colour: green use, yellow not yet (as expected), red a problem, grey nothing yet."""

    def __init__(self, root: tk.Misc) -> None:
        self.frame = f = tk.Frame(root, padx=28, pady=14)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        self.word = tk.Label(f, text=t("word.blocked"), font=(T.TXT, 42, "bold"))
        self.word.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 28))
        self.headline = tk.Label(f, text="", font=(T.TXT, 18, "bold"), anchor="w", justify="left")
        self.headline.grid(row=0, column=1, sticky="sw")
        self.since = tk.Label(f, text="", font=(T.TXT, 11), anchor="w")
        self.since.grid(row=1, column=1, sticky="nw")
        self.total_cap = tk.Label(f, text=t("band.total"), font=(T.TXT, 10), anchor="e")
        self.total_cap.grid(row=0, column=2, sticky="se")
        self.total = tk.Label(f, text="0:00:00", font=(T.NUM, 22), anchor="e")
        self.total.grid(row=1, column=2, sticky="ne")
        self._labels = (self.word, self.headline, self.since, self.total_cap, self.total)
        self._kind = ""
        self._flash: List[str] = []
        f.bind("<Configure>", lambda e: self.headline.configure(wraplength=max(e.width - 520, 200)))

    def _paint(self, bg: str, fg: str) -> None:
        self.frame.configure(bg=bg)
        for w in self._labels:
            w.configure(bg=bg, fg=fg)

    def show(self, b: V.Band, since: str, total: str) -> None:
        if b.kind != self._kind and not self._flash:
            self._paint(*T.BAND[b.kind])
        self._kind = b.kind
        self.word.configure(text=b.word)
        self.headline.configure(text=b.headline)
        self.since.configure(text=since)
        self.total.configure(text=total)

    def flash(self) -> None:
        """Usable just ended: blink three times so a glance from the vehicle catches it."""
        if self._flash:
            return
        self._flash = ["#6E1510", T.STOP] * 3

        def step() -> None:
            bg = self._flash.pop(0)
            self._paint(bg, "white")
            if self._flash:
                self.frame.after(160, step)
            else:
                self._paint(*T.BAND[self._kind or "stop"])
        step()


class AlignmentRail:
    """The alignment as a route: start, ① still, ② straight, ③ fine, usable. Shows where AIO NAV is."""

    H = 104

    def __init__(self, parent: tk.Misc) -> None:
        self.canvas = tk.Canvas(parent, height=self.H, bg=T.PANEL, highlightthickness=0)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self._last: Optional[V.Rail] = None
        self._key: Optional[tuple] = None
        self._stable = 2.0

    def update(self, r: V.Rail, ready_stable: float) -> None:
        self._last, self._stable = r, ready_stable
        self._redraw()

    def _redraw(self) -> None:
        r, c = self._last, self.canvas
        w = c.winfo_width()
        key = (r, w)
        if r is None or key == self._key or w < 200:
            return
        self._key = key
        c.delete("all")
        n = len(V.STATIONS)
        x0, x1, y = 40, w - 44, 34
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        for i in range(n - 1):                              # the road between stations
            done = r.at >= 0 and i < r.at
            c.create_line(xs[i], y, xs[i + 1], y, fill=T.ASPHALT if done else T.LINE, width=5 if done else 2,
                          capstyle="round")
        for i, (label, _) in enumerate(V.STATIONS):
            self._station(i, xs[i], y, t(label), r)
        if r.note:
            color = T.STOP if r.mode in ("fault", "lost") else T.MUTED
            c.create_text(x0 - 14, self.H - 8, text=r.note, anchor="w", fill=color, font=(T.TXT, 10))

    def _station(self, i: int, x: float, y: float, label: str, r: V.Rail) -> None:
        c = self.canvas
        last = i == len(V.STATIONS) - 1
        state = "future"
        if r.at >= 0 and i < r.at:
            state = "done"
        elif i == r.at:
            state = {"done": "go", "lost": "lost"}.get(r.mode, "now")
        fill, ink, outline = {"done": (T.ASPHALT, "white", T.ASPHALT), "now": (T.WAIT, T.ASPHALT, T.ASPHALT),
                              "go": (T.GO, "white", T.GO), "lost": (T.STOP, "white", T.STOP),
                              "future": (T.PANEL, T.MUTED, T.LINE)}[state]
        if i == 0:                                          # start: a small marker, not a step
            c.create_oval(x - 8, y - 8, x + 8, y + 8, fill=fill, outline=outline, width=2)
        elif last:                                          # destination: a sign plate
            s = 18
            if state == "now":                              # ready settling: the plate fills up
                c.create_rectangle(x - s, y - s, x + s, y + s, fill=T.PANEL, outline=T.ASPHALT, width=2)
                top = y + s - 2 - (2 * s - 4) * r.fraction
                c.create_rectangle(x - s + 2, top, x + s - 2, y + s - 2, fill=T.WAIT, outline="")
            else:
                c.create_rectangle(x - s, y - s, x + s, y + s, fill=fill, outline=outline, width=2)
            if state == "go":                               # drawn, not a glyph: every font has it
                c.create_line([x - 8, y, x - 2, y + 7, x + 9, y - 7], fill=ink, width=4, capstyle="round",
                              joinstyle="round")
            elif state == "lost":
                c.create_text(x, y, text="!", fill=ink, font=(T.NUM, 16, "bold"))
        else:
            c.create_oval(x - 16, y - 16, x + 16, y + 16, fill=fill, outline=outline, width=2)
            c.create_text(x, y, text=str(i), fill=ink, font=(T.NUM, 14, "bold"))
        current = state in ("now", "go", "lost")
        text = label
        if last and state == "now" and r.fraction > 0:
            text = t("station.confirming", x=r.fraction * self._stable, y=self._stable)
        # The destination label is right-aligned to its plate, so a longer countdown never runs off the edge.
        c.create_text(x + 18 if last else x, y + 32, text=text, anchor="e" if last else "center",
                      fill=T.ASPHALT if current else T.MUTED, font=(T.TXT, 11, "bold" if current else "normal"))


class GuidanceStrip:
    """What the operator does now, and where the alignment stands. Setup steps before any packet."""

    def __init__(self, root: tk.Misc, copy_firewall: Callable[[], None]) -> None:
        f = tk.Frame(root, bg=T.PANEL, padx=28, pady=16)
        f.pack(fill="x")
        left = tk.Frame(f, bg=T.PANEL)
        left.grid(row=0, column=0, sticky="nw")
        self.title = tk.Label(left, text="", font=(T.TXT, 26, "bold"), fg=T.ASPHALT, bg=T.PANEL, anchor="w",
                              justify="left")
        self.title.pack(anchor="w")
        self.sub = tk.Label(left, text="", font=(T.TXT, 12), fg=T.MUTED, bg=T.PANEL, anchor="w", justify="left")
        self.sub.pack(anchor="w", pady=(2, 0))
        self.steps = tk.Frame(left, bg=T.PANEL)
        self.step_text: List[tk.Label] = []
        for i in range(3):                                  # setup really is a sequence: numbered
            row = tk.Frame(self.steps, bg=T.PANEL)
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=str(i + 1), font=(T.NUM, 11, "bold"), fg="white", bg=T.ASPHALT, width=2).pack(
                side="left", padx=(0, 10))
            lbl = tk.Label(row, text="", font=(T.TXT, 11), fg=T.ASPHALT, bg=T.PANEL, anchor="w", justify="left")
            lbl.pack(side="left")
            self.step_text.append(lbl)
            if i == 2:
                self.copy_btn = ttk.Button(row, text=t("setup.copy"), command=copy_firewall)
                self.copied = tk.Label(row, text="", font=(T.TXT, 10), fg=T.GO, bg=T.PANEL)
        self.rail = AlignmentRail(f)
        self.rail.canvas.grid(row=0, column=1, sticky="ew", padx=(28, 0))
        f.columnconfigure(0, weight=1, uniform="g")         # equal halves: the rail never jumps in width
        f.columnconfigure(1, weight=1, uniform="g")
        self.frame = f
        self._mode = ""
        self._width = 0
        f.bind("<Configure>", lambda e: self._wrap(e.width))

    def _wrap(self, width: int) -> None:
        """Long instructions (English ones especially) wrap within their half instead of running under the rail."""
        self._width = width
        room = width - 56 if self._mode == "setup" else (width - 56) // 2 - 28
        for lbl in (self.title, self.sub):
            lbl.configure(wraplength=max(room, 200))

    def _set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        if mode == "setup":                                 # before any packet the rail means nothing
            self.sub.pack_forget()
            self.steps.pack(anchor="w", pady=(8, 0))
            self.rail.canvas.grid_remove()
            self.frame.columnconfigure(1, weight=0, uniform="")
        else:
            self.steps.pack_forget()
            self.sub.pack(anchor="w", pady=(2, 0))
            self.frame.columnconfigure(1, weight=1, uniform="g")
            self.rail.canvas.grid()
        if self._width:
            self._wrap(self._width)

    def update(self, snap: Snapshot, nav_port: int, firewall: osutil.FirewallHint, ips: Sequence[str]) -> None:
        self.rail.update(V.rail(snap), snap.cfg.ready_stable)
        if snap.nothing_received and snap.source_kind != "replay":
            self._set_mode("setup")
            self.title.configure(text=t("setup.title"), fg=T.ASPHALT)
            here = f"{ips[0]}:{nav_port}" if ips else t("setup.this_ip", port=nav_port)
            others = t("setup.others", ips=i18n.joined(ips[1:])) if len(ips) > 1 else ""
            self.step_text[0].configure(text=t("setup.step1", here=here, others=others))
            self.step_text[1].configure(text=t("setup.step2"))
            self.step_text[2].configure(text=firewall.text)
            if firewall.command and not self.copy_btn.winfo_ismapped():
                self.copy_btn.pack(side="left", padx=(12, 0))
                self.copied.pack(side="left", padx=8)
            return
        self._set_mode("normal")
        if snap.nothing_received:
            self.title.configure(text=t("guide.replay_empty"), fg=T.ASPHALT)
            self.sub.configure(text="")
        elif not snap.status_fresh:
            self.title.configure(text=t("guide.wait_status"), fg=T.ASPHALT)
            self.sub.configure(text=t("guide.wait_status_replay" if snap.source_kind == "replay"
                                      else "guide.wait_status_live"))
        else:
            s = snap.status
            assert s is not None
            action = P.name_of(s.action, P.ACTIONS)
            danger = action in ("SAFE_STOP", "SERVICE_REQUIRED")
            self.title.configure(text=i18n.action_text(action), fg=T.STOP if danger else T.ASPHALT)
            self.sub.configure(text="")                     # the state itself is in the band and the rail


# --------------------------------------------------------------------------------------- body
class NavPanel:
    def __init__(self, body: tk.Misc) -> None:
        f, head = area(body, 0, t("nav.title"))
        self.link = LinkLight(head)
        lamps = tk.Frame(f, bg=T.PANEL)
        lamps.pack(fill="x", pady=(0, 12))
        self.lamps: Dict[str, tk.Label] = {}
        for name in ("ALIGN", "HEADING", "FINE"):
            lamp = tk.Label(lamps, text=i18n.lamp_name(name), font=(T.TXT, 11, "bold"), padx=14, pady=6,
                            fg=T.MUTED, bg=T.KERB)
            lamp.pack(side="left", padx=(0, 8))
            self.lamps[name] = lamp
        tk.Label(f, text=t("nav.aiding"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(anchor="w")
        aid = tk.Frame(f, bg=T.PANEL)
        aid.pack(fill="x", pady=(4, 14))
        self.aid: Dict[str, tk.Label] = {}
        for name in P.AIDING_FLAGS:                         # standard INS acronyms: the same in both languages
            lbl = tk.Label(aid, text=name, font=(T.NUM, 11), fg=T.MUTED, bg=T.PANEL, padx=8, pady=3)
            lbl.pack(side="left", padx=(0, 6))
            self.aid[name] = lbl
        self.v = value_grid(f, [
            ("lat", "nav.lat"), ("lon", "nav.lon"), ("height", "nav.height"), ("heading", "nav.heading"),
            ("speed", "nav.speed"), ("vu", "nav.vu"), ("att", "nav.att"), ("pos_std", "nav.pos_std"),
            ("vel_std", "nav.vel_std"), ("att_std", "nav.att_std"), ("time", "nav.time"), ("age", "nav.age"),
        ], cols=3, size=15)

    def update(self, snap: Snapshot) -> None:
        n, now = snap.nav, snap.now
        self.link.show(V.nav_link(snap))
        flags = n.flags if n is not None else 0
        for name, lamp in self.lamps.items():
            on = bool(flags >> P.FLAG_NAMES.index(name) & 1)
            lamp.configure(bg=T.GO if on else T.KERB, fg="white" if on else T.MUTED)
        for name, lbl in self.aid.items():
            seen = snap.flag_seen.get(name)
            if seen is None:
                lbl.configure(text=name, fg=T.LINE, bg=T.PANEL)
                continue
            a = now - seen
            shown = f"{a:.1f}" if a < 10 else (f"{a:.0f}" if a < 100 else "99+")   # keeps the row narrow
            recent = a < 1.5
            lbl.configure(text=f"{name} {shown}s", fg=T.GO if recent else T.MUTED,
                          bg=T.GO_TINT if recent else T.PANEL)
        if n is None:
            return
        v, age = self.v, now - snap.nav_at
        ink = T.ASPHALT if age <= snap.cfg.nav_max_age else T.MUTED     # stale values read as old
        for lbl in v.values():
            lbl.configure(fg=ink)
        v["lat"].configure(text=f"{n.lat:.8f}")
        v["lon"].configure(text=f"{n.lon:.8f}")
        v["height"].configure(text=f"{n.height:.2f}")
        v["heading"].configure(text=f"{n.heading % 360:.1f}")
        v["speed"].configure(text=f"{math.hypot(n.vn, n.ve):.2f}")
        v["vu"].configure(text=f"{n.vu:+.2f}")
        v["att"].configure(text=f"{n.roll:+.2f} / {n.pitch:+.2f}")
        v["pos_std"].configure(text=f"{n.pos_n_std:.2f} / {n.pos_e_std:.2f} / {n.pos_d_std:.2f}")
        v["vel_std"].configure(text=f"{n.vel_n_std:.2f} / {n.vel_e_std:.2f} / {n.vel_d_std:.2f}")
        v["att_std"].configure(text=f"{n.roll_std:.2f} / {n.pitch_std:.2f} / {n.heading_std:.2f}")
        v["time"].configure(text=f"{n.time_s:.3f}")
        v["age"].configure(text=f"{age * 1000:.0f}", fg=T.STOP if age > snap.cfg.nav_max_age else T.ASPHALT)


class StatusPanel:
    def __init__(self, body: tk.Misc) -> None:
        f, head = area(body, 1, t("status.title"))
        self.link = LinkLight(head)
        self.v = value_grid(f, [
            ("state", "status.state"), ("gnss", "status.gnss"), ("session", "status.session"),
            ("sequence", "status.sequence"), ("rate", "status.rate"), ("nav_age", "status.nav_age"),
        ], cols=2, size=13)
        self.v["state"].configure(font=(T.NAME, 16, "bold"))
        self.v["gnss"].configure(font=(T.NAME, 13))
        tk.Label(f, text=t("status.inhibit"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(anchor="w", pady=(2, 0))
        self.inhibit = tk.Label(f, text="—", font=(T.NAME, 12), fg=T.STOP, bg=T.PANEL, justify="left", anchor="w")
        self.inhibit.pack(anchor="w", fill="x", pady=(2, 10))
        tk.Label(f, text=t("status.health"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(anchor="w")
        grid = tk.Frame(f, bg=T.PANEL)
        grid.pack(fill="x", pady=(4, 0))
        self.health: List[tk.Label] = []
        rows = (len(P.HEALTH_BITS) + 1) // 2
        for i in range(len(P.HEALTH_BITS)):
            lbl = tk.Label(grid, text=f"○ {i18n.health_name(i)}", font=(T.NAME, 10), fg=T.LINE, bg=T.PANEL,
                           anchor="w")
            lbl.grid(row=i % rows, column=i // rows, sticky="w", padx=(0, 14))
            self.health.append(lbl)

    def update(self, snap: Snapshot) -> None:
        self.link.show(V.status_link(snap))
        s = snap.status
        if s is None:
            return
        v, fresh = self.v, snap.status_fresh
        ink = T.ASPHALT if fresh else T.MUTED                # stale values read as old, never as green
        for lbl in v.values():
            lbl.configure(fg=ink)
        state = P.name_of(s.state, P.STATES)
        color = T.GO if state == "READY" else (T.STOP if state in ("FAULT", "DEGRADED") else T.ASPHALT)
        v["state"].configure(text=i18n.state_name(state), fg=color if fresh else T.MUTED)
        v["gnss"].configure(text=i18n.gnss_quality(s.gnss_quality))
        v["session"].configure(text=f"0x{s.session:08X}")
        v["sequence"].configure(text=str(s.sequence))
        v["rate"].configure(text=f"{s.nav_rate_dhz / 10:.1f}")
        v["nav_age"].configure(text="—" if s.nav_age_ms == P.NAV_AGE_UNKNOWN else str(s.nav_age_ms))
        inh = [i18n.inhibit_name(b) for b in range(len(P.INHIBIT_BITS)) if s.inhibit >> b & 1]
        self.inhibit.configure(text="\n".join(inh) or t("none"), fg=(T.STOP if inh else T.GO) if fresh else T.MUTED,
                               font=(T.NAME, 12, "normal" if inh else "bold"))
        for i, lbl in enumerate(self.health):
            ok = bool(s.health >> i & 1)
            lbl.configure(text=f"{'●' if ok else '○'} {i18n.health_name(i)}", fg=T.GO if ok and fresh else T.MUTED)


class TrackPanel:
    """Trajectory on graph paper: green where the output was usable, grey where blocked; north up."""

    def __init__(self, body: tk.Misc, clear: Callable[[], None]) -> None:
        self.frame, head = area(body, 2, t("track.title"))
        self.meta = tk.Label(head, text="", font=(T.TXT, 11), fg=T.MUTED, bg=T.PANEL)
        self.meta.pack(side="right")
        foot = tk.Frame(self.frame, bg=T.PANEL)
        foot.pack(side="bottom", fill="x", pady=(10, 0))
        for color, text in ((T.GO, t("word.usable")), (T.IDLE, t("word.blocked"))):
            tk.Frame(foot, bg=color, width=18, height=4).pack(side="left", padx=(0, 6))
            tk.Label(foot, text=text, font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(side="left", padx=(0, 14))
        ttk.Button(foot, text=t("track.clear"), command=clear).pack(side="right")
        self.canvas = tk.Canvas(self.frame, bg=T.PANEL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._drawn: Optional[tuple] = None

    def update(self, snap: Snapshot) -> None:
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        heading = snap.nav.heading if snap.nav is not None else None
        key = (snap.track_version, w, h, heading)
        if key == self._drawn:
            return                  # nothing moved: skip redrawing up to 3000 points
        self._drawn = key
        c.delete("all")
        if w < 60 or h < 60:
            return
        pts = snap.track
        proj = project(pts)
        if proj is None:
            c.create_text(w / 2, h / 2, text=t("track.empty"), fill=T.MUTED, font=(T.TXT, 11))
            self.meta.configure(text="")
            return
        xs, ys, span = proj.xs, proj.ys, proj.span
        margin = 22
        scale = (min(w, h - 24) - 2 * margin) / span
        ox, oy = w / 2 - proj.cx * scale, (h - 24) / 2 + proj.cy * scale    # canvas spot of the newest point
        bar = nice_length(span / 4)
        step = bar * scale                                  # graph paper at the scale bar's spacing
        if step >= 8:
            gx = ox % step
            while gx < w:
                c.create_line(gx, 0, gx, h, fill=T.GRID)
                gx += step
            gy = oy % step
            while gy < h:
                c.create_line(0, gy, w, gy, fill=T.GRID)
                gy += step

        def px(i: int) -> Tuple[float, float]:
            return ox + xs[i] * scale, oy - ys[i] * scale

        # Consecutive points with the same verdict become one polyline.
        run: List[Tuple[float, float]] = [px(0)]
        for i in range(1, len(pts)):
            run.append(px(i))
            if pts[i].usable != pts[i - 1].usable or i == len(pts) - 1:
                if len(run) >= 2:
                    c.create_line(*[v for xy in run for v in xy], fill=T.GO if pts[i - 1].usable else T.IDLE,
                                  width=4, capstyle="round", joinstyle="round")
                run = [run[-1]]
        x, y = px(len(pts) - 1)
        if heading is not None and math.isfinite(heading):
            a = math.radians(heading)
            c.create_line(x, y, x + 26 * math.sin(a), y - 26 * math.cos(a), fill=T.ASPHALT, width=3,
                          arrow="last", arrowshape=(10, 12, 5))
        c.create_oval(x - 6, y - 6, x + 6, y + 6, fill=T.ASPHALT, outline=T.PANEL, width=2)

        bl = bar * scale
        c.create_rectangle(margin - 4, h - 22, margin + bl + 52, h - 2, fill=T.PANEL, outline="")
        c.create_line(margin, h - 10, margin + bl, h - 10, fill=T.ASPHALT, width=2)
        c.create_line(margin, h - 15, margin, h - 5, fill=T.ASPHALT, width=2)
        c.create_line(margin + bl, h - 15, margin + bl, h - 5, fill=T.ASPHALT, width=2)
        c.create_text(margin + bl + 8, h - 10, text=f"{bar:g} m", anchor="w", fill=T.ASPHALT, font=(T.NUM, 10))
        c.create_line(w - 16, 34, w - 16, 10, fill=T.ASPHALT, width=2, arrow="last")
        c.create_text(w - 16, 46, text="N", fill=T.ASPHALT, font=(T.NUM, 11, "bold"))   # compass mark, as on maps
        self.meta.configure(text=t("track.meta", n=len(pts), span=span))


# ------------------------------------------------------------------------------------- footer
class Footer:
    _ANOMALY = (("lost", T.CAUTION), ("reordered", T.CAUTION), ("bad", T.STOP), ("conflicts", T.STOP),
                ("foreign", T.STOP))

    def __init__(self, root: tk.Misc, actions: Dict[str, Callable[[], None]], show_track: tk.BooleanVar,
                 alert: tk.BooleanVar) -> None:
        f = tk.Frame(root, bg=T.KERB, padx=16, pady=10)
        f.pack(side="bottom", fill="x")         # packed before the body so it never gets squeezed out
        # Buttons first: pack gives space in order, so the long lines can never push them out.
        self.rec_btn = ttk.Button(f, text=t("foot.start_rec"), command=actions["record"])
        self.rec_btn.pack(side="right")
        ttk.Button(f, text=t("foot.replay"), command=actions["replay"]).pack(side="right", padx=(8, 0))
        ttk.Button(f, text=t("foot.settings"), command=actions["settings"]).pack(side="right", padx=(8, 0))
        ttk.Checkbutton(f, text=t("foot.show_track"), variable=show_track, command=actions["track"],
                        style="Kerb.TCheckbutton").pack(side="right", padx=(12, 0))
        self.alert_cb = ttk.Checkbutton(f, text=t("foot.alert"), variable=alert, command=actions["alert"],
                                        style="Kerb.TCheckbutton")
        self.alert_cb.pack(side="right")
        self.rec = tk.Frame(f, bg=T.KERB)                   # shown only while recording
        dot = tk.Canvas(self.rec, width=12, height=12, bg=T.KERB, highlightthickness=0)
        dot.create_oval(1, 1, 11, 11, fill=T.STOP, outline="")
        dot.pack(side="left", padx=(0, 6))
        self.rec_time = tk.Label(self.rec, text="", font=(T.TXT, 11, "bold"), fg=T.STOP, bg=T.KERB)
        self.rec_time.pack(side="left")
        left = tk.Frame(f, bg=T.KERB)
        left.pack(side="left", fill="x", expand=True)
        self.source = tk.Label(left, text="", font=(T.TXT, 10), fg=T.MUTED, bg=T.KERB, anchor="w")
        self.source.pack(anchor="w")
        counts = tk.Frame(left, bg=T.KERB)
        counts.pack(anchor="w")
        self._colors = dict(self._ANOMALY)
        self.counts: Dict[str, tk.Label] = {}
        for key in ("nav", "status", *self._colors):
            lbl = tk.Label(counts, text="", font=(T.TXT, 10), fg=T.MUTED, bg=T.KERB)
            lbl.pack(side="left", padx=(0, 14))
            self.counts[key] = lbl
        self.error = tk.Label(left, text="", font=(T.TXT, 10, "bold"), fg=T.STOP, bg=T.KERB, anchor="w")
        self._rec_shown = False
        self._error_shown = False

    def update(self, snap: Snapshot) -> None:
        self.rec_btn.state(["disabled"] if snap.source_kind == "replay" else ["!disabled"])
        recording = snap.recording is not None
        self.rec_btn.configure(text=t("foot.stop_rec" if recording else "foot.start_rec"))
        if recording != self._rec_shown:
            self._rec_shown = recording
            if recording:
                self.rec.pack(side="right", padx=(0, 20), after=self.alert_cb)
            else:
                self.rec.pack_forget()
        if recording and snap.recording_since is not None:
            self.rec_time.configure(text=t("foot.recording", t=fmt_dur(snap.now - snap.recording_since)))

        if snap.source_kind == "replay":
            source = t("foot.replaying", file=snap.source_address)
            if snap.replay is not None and not snap.replay.has_senders:
                source += t("foot.old_format")
        else:
            source = t("foot.listening", addr=snap.source_address)
        senders = sorted({s for s in (snap.nav_sender, snap.status_sender) if s})
        if senders:
            source += "    " + t("foot.from", ips=" / ".join(senders))
        if snap.recording:
            source += "    " + t("foot.writing", path=elide(snap.recording, 64))
        self.source.configure(text=source)
        c = vars(snap.count)
        for key, lbl in self.counts.items():
            n = c[key]
            if key in ("nav", "status"):
                lbl.configure(text=f"{'0x04' if key == 'nav' else '0x05'} {n}")
                continue
            bad = n > 0
            lbl.configure(text=t(f"foot.{key}", n=n), fg=self._colors[key] if bad else T.MUTED,
                          font=(T.TXT, 10, "bold" if bad else "normal"))
        err = snap.recording_error
        if bool(err) != self._error_shown:
            self._error_shown = bool(err)
            if err:
                self.error.pack(anchor="w")
            else:
                self.error.pack_forget()
        self.error.configure(text=str(err) if err else "")
