"""The screen's parts. Each builds its widgets once and update()s them from a Snapshot.

Layout C, left to right:
  signal mast | glance zone: verdict, instruction plate, alignment route, blocking conditions
              | engineering zone: actions, navigation 0x04, status 0x05 and track, source and counts

All text comes from i18n in the current language; changing the language rebuilds the parts.
"""

from __future__ import annotations

import math
import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import i18n, osutil
from ..core import protocol as P
from ..core.track import nice_length, project
from ..engine import Snapshot
from ..i18n import t
from . import presentation as V
from . import theme as T

REPLAY_SPEEDS = (1, 2, 5, 10)
GAP = 12                    # gutter between the engineering zone's sections
fmt_dur = V.fmt_dur
Point = Tuple[float, float]


def elide(text: str, n: int) -> str:
    """Shorten from the middle, keeping the drive and the file name of a path visible."""
    return text if len(text) <= n else text[:n // 3] + "…" + text[-(n - n // 3 - 1):]


_CJK = "　-〿㐀-鿿＀-￯"
_TOKENS = re.compile(f"[{_CJK}]|[^\\s{_CJK}]+|\\s+")
_NO_LINE_START = frozenset("，。、；：？！）」』")
_FONTS: Dict[str, tkfont.Font] = {}


def wrap(text: str, font: tkfont.Font, width: int) -> str:
    """Lines of at most `width` pixels. Tk breaks only at spaces, so a Chinese sentence would run on
    as one long word; here a line may also break between two Chinese characters (not before ，。)."""
    lines = []
    for para in text.split("\n"):
        line = ""
        for tok in _TOKENS.findall(para):
            if line.strip() and not tok.isspace() and tok not in _NO_LINE_START and font.measure(line + tok) > width:
                lines.append(line.rstrip())
                line = tok
            else:
                line += tok
        lines.append(line.rstrip())
    return "\n".join(lines)


class Para:
    """A label whose text is wrapped by wrap() to the width it is given."""

    def __init__(self, label: tk.Label) -> None:
        self.label, self.text, self.width = label, "", 0
        self._shown: Optional[tuple] = None

    def set(self, text: Optional[str] = None, width: Optional[int] = None) -> None:
        self.text = self.text if text is None else text
        self.width = self.width if width is None else width
        spec = str(self.label.cget("font"))
        key = (self.text, self.width, spec)
        if key == self._shown:
            return
        self._shown = key
        if self.width <= 50:                                # not laid out yet
            self.label.configure(text=self.text)
            return
        font = _FONTS.get(spec) or _FONTS.setdefault(spec, tkfont.Font(font=self.label.cget("font")))
        self.label.configure(text=wrap(self.text, font, self.width))


def wrapped(text: str, font: Any, width: int) -> str:
    """wrap() for text that never changes: dialog hints and messages. `width` in design pixels."""
    return wrap(text, tkfont.Font(font=font), T.px(width))


def section(parent: tk.Misc, title: str) -> Tuple[tk.Frame, tk.Frame]:
    """An engineering-zone section: plain white on the kerb grey. Returns (frame, header)."""
    f = tk.Frame(parent, bg=T.PANEL, padx=16, pady=10)
    head = tk.Frame(f, bg=T.PANEL)
    head.pack(fill="x", pady=(0, 6))
    tk.Label(head, text=title, font=(T.TXT, 12, "bold"), fg=T.ASPHALT, bg=T.PANEL).pack(side="left")
    return f, head


def round_rect(c: tk.Canvas, x0: float, y0: float, x1: float, y1: float, r: float, **kw: Any) -> int:
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
           x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


def dashed(c: tk.Canvas, pts: Sequence[Point], on: float = 8, off: float = 7, **kw: Any) -> None:
    """A dashed polyline drawn as short solid pieces: Tk's own dash patterns turn solid on wide lines."""
    drawing, left, dash = True, on, [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        done = 0.0
        while seg - done > left:
            done += left
            p = (x0 + (x1 - x0) * done / seg, y0 + (y1 - y0) * done / seg)
            if drawing:
                dash.append(p)
                c.create_line([v for xy in dash for v in xy], **kw)
            else:
                dash = [p]
            drawing, left = not drawing, off if drawing else on
        left -= seg - done
        if drawing:
            dash.append((x1, y1))
    if drawing and len(dash) >= 2:
        c.create_line([v for xy in dash for v in xy], **kw)


class Btn:
    """A signage button: flat, outlined in asphalt; its keyboard shortcut follows the label.

    Built on a label: macOS draws tk.Button natively and ignores its colours, which would leave white
    text on a light button. Tab reaches it (a blue ring shows the focus) and Space presses it."""

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None], kbd: str = "",
                 dark: bool = False) -> None:
        self._bg, self._fg = (T.ASPHALT, "white") if dark else (T.PANEL, T.ASPHALT)
        self._kbd, self._command = kbd, command
        surface = str(parent.cget("bg"))
        self.frame = tk.Frame(parent, bg=surface, highlightthickness=2, highlightcolor=T.FOCUS,
                              highlightbackground=surface, takefocus=1)
        self._line = tk.Frame(self.frame, bg=T.ASPHALT, padx=2, pady=2)    # the outline
        self._line.pack()
        self.button = tk.Label(self._line, font=(T.TXT, 10, "bold"), padx=12, pady=3, cursor="hand2")
        self.button.pack()
        for w in (self._line, self.button):
            w.bind("<ButtonRelease-1>", self._click)
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))
        self.frame.bind("<space>", lambda _e: self._press())
        self._enabled = True
        self._shown: Optional[tuple] = None
        self.set(text)

    def set(self, text: str, enabled: bool = True, color: Optional[str] = None) -> None:
        shown = (text, enabled, color)
        if shown == self._shown:
            return
        self._shown, self._enabled = shown, enabled
        self.button.configure(text=f"{text}   {self._kbd}" if self._kbd else text,
                              fg=(color or self._fg) if enabled else T.FAINT, bg=self._bg if enabled else "#F1F3F5",
                              cursor="hand2" if enabled else "arrow")
        self._line.configure(bg=(color or T.ASPHALT) if enabled else "#B7BEC4")

    def _hover(self, inside: bool) -> None:
        if self._enabled:
            lit = "#36424C" if self._bg == T.ASPHALT else "#EEF1F3"
            self.button.configure(bg=lit if inside else self._bg)

    def _click(self, e: tk.Event) -> None:
        w = e.widget
        if 0 <= e.x < w.winfo_width() and 0 <= e.y < w.winfo_height():   # released over the button
            self._press()

    def _press(self) -> None:
        if self._enabled:
            self._command()


def fit_to_columns(grid: tk.Frame, paras: Sequence[Para], cols: int, pad: int) -> None:
    """Labels in a grid of equal columns wrap to the column's width instead of pushing past it."""
    def resize(e: tk.Event) -> None:
        for p in paras:
            p.set(width=e.width // cols - pad)
    grid.bind("<Configure>", resize, add="+")


def value_grid(parent: tk.Misc, rows: Sequence[Tuple[str, str]], cols: int) -> Dict[str, tk.Label]:
    """Label above value; `rows` holds (key, i18n key of the label)."""
    g = tk.Frame(parent, bg=T.PANEL)
    g.pack(fill="x")
    out = {}
    paras = []
    for i, (key, label) in enumerate(rows):
        r, c = divmod(i, cols)
        cell = tk.Frame(g, bg=T.PANEL)
        cell.grid(row=r, column=c, sticky="nw", padx=(0, 12), pady=(0, 4))
        name = tk.Label(cell, text=t(label), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL, justify="left")
        name.pack(anchor="w")
        paras.append(Para(name))
        paras[-1].set(t(label))
        v = tk.Label(cell, text="—", font=(T.NUM, 12), fg=T.FAINT, bg=T.PANEL)
        v.pack(anchor="w")
        out[key] = v
    for c in range(cols):
        g.columnconfigure(c, weight=1, uniform="v")
    fit_to_columns(g, paras, cols, 14)
    return out


class LinkText:
    """Header text for one packet stream: rate and age, or how long it has been gone (red)."""

    def __init__(self, head: tk.Frame) -> None:
        self.text = tk.Label(head, text="", font=(T.TXT, 11), fg=T.MUTED, bg=T.PANEL)   # 秒前: not in DIN
        self.text.pack(side="right")

    def show(self, link: V.Link) -> None:
        bad = link.kind == "stop"
        self.text.configure(text=link.text, fg=T.STOP if bad else T.MUTED,
                            font=(T.TXT, 11, "bold" if bad else "normal"))


# ---------------------------------------------------------------------------------------- top
class ReplayBar:
    """Only while replaying: says plainly that this is not live, and holds the replay's controls."""

    def __init__(self, root: tk.Misc, on_speed: Callable[[], None], on_live: Callable[[], None]) -> None:
        self.frame = f = tk.Frame(root, bg=T.INFO, padx=24, pady=8)
        tk.Label(f, text=t("replay.banner"), font=(T.TXT, 12, "bold"), fg="white", bg=T.INFO).pack(side="left")
        self.file = tk.Label(f, text="", font=(T.NUM, 11), fg=T.INFO_INK, bg=T.INFO)
        self.file.pack(side="left", padx=(16, 0))
        Btn(f, t("replay.live"), on_live).frame.pack(side="right")
        self.speed = ttk.Combobox(f, values=[f"{s}×" for s in REPLAY_SPEEDS], width=5, state="readonly")
        self.speed.set("1×")
        self.speed.bind("<<ComboboxSelected>>", lambda _e: on_speed())
        self.speed.pack(side="right", padx=(0, 16))
        tk.Label(f, text=t("replay.speed"), font=(T.TXT, 11), fg="white", bg=T.INFO).pack(side="right", padx=(0, 6))
        self.time = tk.Label(f, text="", font=(T.NUM, 12), fg="white", bg=T.INFO)
        self.time.pack(side="right", padx=(0, 16))
        self.bar = tk.Canvas(f, height=6, bg="#3D6AB0", highlightthickness=0)
        self.bar.pack(side="right", fill="x", expand=True, padx=(24, 16))
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


# -------------------------------------------------------------------------------- mast, verdict
class VerdictBand:
    """The answer. The mast: red on top (a problem), yellow (wait, as expected), green at the bottom
    (usable), all dark when there is nothing to judge. Beside it: the word, why, and for how long."""

    LAMPS = (("stop", "mast.stop"), ("wait", "mast.wait"), ("go", "mast.go"))

    def __init__(self, main: tk.Misc, glance: tk.Misc) -> None:
        w, r = T.px(148), T.px(46)
        self.mast = c = tk.Canvas(main, width=w, bg=T.ASPHALT, highlightthickness=0)
        c.grid(row=0, column=0, sticky="ns")
        x, y = w / 2, T.px(28) + r
        self._lamps: Dict[str, Tuple[int, List[Tuple[int, str]], int]] = {}
        for kind, key in self.LAMPS:
            lamp = c.create_oval(x - r, y - r, x + r, y + r, width=T.px(4))
            label = c.create_text(x, y + r + T.px(16), text=t(key), font=(T.TXT, 11))
            self._lamps[kind] = (lamp, self._icon(kind, x, y, r), label)
            y += 2 * r + T.px(52)
        self._dark = c.create_text(x, y - r, text=t("mast.dark"), fill="white", font=(T.TXT, 10, "bold"),
                                   justify="center", anchor="n")

        self.frame = f = tk.Frame(glance, bg=T.PANEL)
        f.pack(fill="x")
        self.word = tk.Label(f, text=t("word.blocked"), font=(T.TXT, 54, "bold"), bg=T.PANEL, anchor="w")
        self.word.pack(anchor="w")
        self.headline = tk.Label(f, text="", font=(T.TXT, 18, "bold"), fg=T.ASPHALT, bg=T.PANEL, anchor="w",
                                 justify="left")
        self.headline.pack(anchor="w", fill="x")
        row = tk.Frame(f, bg=T.PANEL)
        row.pack(anchor="w", pady=(6, 0))
        self.since = tk.Label(row, text="", font=(T.TXT, 13, "bold"), fg=T.ASPHALT, bg=T.PANEL)
        self.since.pack(side="left", padx=(0, 28))
        self.total_cap = tk.Label(row, text=t("band.total"), font=(T.TXT, 12), fg=T.TEXT2, bg=T.PANEL)
        self.total_cap.pack(side="left")
        self.total = tk.Label(row, text="0:00:00", font=(T.NUM, 13), fg=T.ASPHALT, bg=T.PANEL)
        self.total.pack(side="left", padx=(8, 0))
        self._kind = ""
        self._flash: List[bool] = []
        self._headline = Para(self.headline)
        f.bind("<Configure>", lambda e: self._headline.set(width=e.width - 8))
        self._paint("idle")

    def _icon(self, kind: str, x: float, y: float, r: float) -> List[Tuple[int, str]]:
        """Drawn, not glyphs: every font has them. Returns (item, colour option) pairs."""
        c, k = self.mast, r / 48
        if kind == "stop":                                  # !
            return [(c.create_line(x, y - 13 * k, x, y + 3 * k, width=6 * k, capstyle="round"), "fill"),
                    (c.create_oval(x - 4 * k, y + 9 * k, x + 4 * k, y + 17 * k, width=0), "fill")]
        if kind == "wait":                                  # a clock
            return [(c.create_oval(x - 17 * k, y - 17 * k, x + 17 * k, y + 17 * k, width=4.5 * k), "outline"),
                    (c.create_line([x, y - 10 * k, x, y + 1 * k, x + 7 * k, y + 6 * k], width=4.5 * k,
                                   capstyle="round", joinstyle="round"), "fill")]
        return [(c.create_line([x - 12 * k, y + 1 * k, x - 3 * k, y + 10 * k, x + 13 * k, y - 9 * k], width=6 * k,
                               capstyle="round", joinstyle="round"), "fill")]          # a tick

    def _paint(self, lit: str, dim: bool = False) -> None:
        c = self.mast
        for kind, (lamp, icon, label) in self._lamps.items():
            on = kind == lit and not dim
            ink = (T.ASPHALT if kind == "wait" else "white") if on else T.LAMP_RING_OFF
            c.itemconfigure(lamp, fill=T.SIGNAL[kind] if on else T.LAMP_OFF, outline="white" if on else T.LAMP_RING_OFF)
            for item, option in icon:
                c.itemconfigure(item, {option: ink})
            c.itemconfigure(label, fill="white" if on else T.LAMP_TEXT_OFF,
                            font=(T.TXT, 11, "bold" if on else "normal"))
        c.itemconfigure(self._dark, state="normal" if lit == "idle" else "hidden")

    def lit(self) -> str:
        """The colour of the lamp that is on, "" when the mast is dark."""
        for lamp, _, _ in self._lamps.values():
            fill = self.mast.itemcget(lamp, "fill")
            if fill != T.LAMP_OFF:
                return str(fill)
        return ""

    def show(self, b: V.Band, since: str, total: str) -> None:
        if b.kind != self._kind:
            if not self._flash:
                self._paint(b.kind)
            self.word.configure(fg=T.WORD[b.kind])
        self._kind = b.kind
        self.word.configure(text=b.word)
        self._headline.set(b.headline)
        if bool(since) != bool(self.since.cget("text")):                # no gap before the total when empty
            self.since.pack_configure(padx=(0, 28 if since else 0))
        self.since.configure(text=since)
        self.total.configure(text=total)

    def flash(self) -> None:
        """Usable just ended: the lit lamp blinks three times so a glance from the vehicle catches it."""
        if self._flash:
            return
        self._flash = [True, False] * 3                     # dim, lit, ...

        def step() -> None:
            dim = self._flash.pop(0)
            self._paint(self._kind if self._kind in T.SIGNAL and self._kind != "idle" else "stop", dim)
            if self._flash:
                self.mast.after(160, step)
            else:
                self._paint(self._kind or "stop")
        step()


# -------------------------------------------------------------------------------- glance zone
class AlignmentRail:
    """The alignment as a route: start, 1 still, 2 straight, 3 fine, usable. Shows where AIO NAV is."""

    def __init__(self, parent: tk.Misc) -> None:
        self.size = T.px(54)
        self.canvas = tk.Canvas(parent, height=self.size + T.px(62), bg=T.PANEL, highlightthickness=0)
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
        key = (r, w, i18n.language())
        if r is None or key == self._key or w < 200:
            return
        self._key = key
        c.delete("all")
        n, half = len(V.STATIONS), self.size / 2
        x0, x1, y = half + 2, w - half - 2, half + 2
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        road = T.px(18)
        c.create_line(x0, y, x1, y, fill=T.LINE, width=road, capstyle="round")
        if r.at > 0:
            c.create_line(x0, y, xs[r.at], y, fill=T.ASPHALT, width=road, capstyle="round")
        gx = x0
        while gx < x1:                                      # the centre line
            c.create_line(gx, y, min(gx + 12, x1), y, fill=T.PANEL, width=2)
            gx += 24
        for i, (label, _) in enumerate(V.STATIONS):
            self._station(i, xs[i], y, t(label), r)
        note, color = r.note, T.STOP if r.mode in ("fault", "lost") else T.MUTED
        if r.at == n - 1 and r.mode == "progress" and r.fraction > 0:     # ready settling: the countdown
            note, color = t("station.confirming", x=r.fraction * self._stable, y=self._stable), T.ASPHALT
        if note:
            c.create_text(0, self.size + T.px(48), text=note, anchor="w", fill=color, font=(T.TXT, 10), width=w)

    def _station(self, i: int, x: float, y: float, label: str, r: V.Rail) -> None:
        c, s = self.canvas, self.size / 2
        last = i == len(V.STATIONS) - 1
        state = "future"
        if r.at >= 0 and i < r.at:
            state = "done"
        elif i == r.at:
            state = {"done": "go", "lost": "lost"}.get(r.mode, "now")
        fill, ink, outline = {"done": (T.ASPHALT, "white", T.ASPHALT), "now": (T.WAIT, T.ASPHALT, T.ASPHALT),
                              "go": (T.GO, "white", T.GO), "lost": (T.STOP, "white", T.STOP),
                              "future": (T.PANEL, T.FAINT, "#AEB6BD")}[state]
        bw = T.px(3)
        if last:                                            # destination: a sign plate
            if state == "now":                              # ready settling: the plate fills up
                round_rect(c, x - s, y - s, x + s, y + s, T.px(8), fill=T.PANEL, outline=T.ASPHALT, width=bw)
                top = y + s - bw - (2 * s - 2 * bw) * r.fraction
                if r.fraction > 0:
                    c.create_rectangle(x - s + bw, top, x + s - bw, y + s - bw, fill=T.WAIT, outline="")
            else:
                round_rect(c, x - s, y - s, x + s, y + s, T.px(8), fill=fill, outline=outline, width=bw)
            k = s / 27
            if state == "go":                               # drawn, not a glyph: every font has it
                c.create_line([x - 11 * k, y, x - 3 * k, y + 9 * k, x + 12 * k, y - 9 * k], fill=ink, width=5 * k,
                              capstyle="round", joinstyle="round")
            elif state == "lost":
                c.create_text(x, y, text="!", fill=ink, font=(T.NUM, 18, "bold"))
        else:
            c.create_oval(x - s, y - s, x + s, y + s, fill=fill, outline=outline, width=bw)
            if i > 0:                                       # start is a marker, not a step
                c.create_text(x, y, text=str(i), fill=ink, font=(T.NUM, 17, "bold"))
        current = state in ("now", "go", "lost")
        # The ends are aligned to their markers, so they never run off the edge.
        c.create_text(x - s if i == 0 else (x + s if last else x), y + s + T.px(16), text=label,
                      anchor="w" if i == 0 else ("e" if last else "center"),
                      fill=T.ASPHALT if current or state == "done" else T.FAINT,
                      font=(T.TXT, 11, "bold" if current else "normal"))


class GuidanceStrip:
    """What the operator does now (the blue instruction plate), where the alignment stands, and what
    still blocks. Before any packet: the setup steps instead."""

    def __init__(self, glance: tk.Misc, copy_firewall: Callable[[], None]) -> None:
        self.frame = f = tk.Frame(glance, bg=T.PANEL)
        f.pack(fill="both", expand=True, pady=(20, 0))
        f.columnconfigure(0, weight=1)
        # The plate: blue with a white inner ring, as an instruction sign. Quiet when there is nothing to do.
        self.plate = tk.Frame(f, padx=2, pady=2)
        self.plate.grid(row=0, column=0, sticky="ew")
        self.ring = tk.Frame(self.plate, padx=3, pady=3)
        self.ring.pack(fill="x")
        self.body = tk.Frame(self.ring)
        self.body.pack(fill="x")
        self.title = tk.Label(self.body, text="", anchor="w", justify="left")
        self.title.pack(anchor="w", fill="x")
        self.sub = tk.Label(self.body, text="", font=(T.TXT, 11), anchor="w", justify="left")
        self._style = ""

        self.steps = tk.Frame(f, bg=T.PANEL)
        self.steps.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        self.step_text: List[tk.Label] = []
        for i in range(3):                                  # setup really is a sequence: numbered
            row = tk.Frame(self.steps, bg=T.PANEL)
            row.pack(anchor="w", fill="x", pady=(0, 14))
            d = T.px(28)
            mark = tk.Canvas(row, width=d, height=d, bg=T.PANEL, highlightthickness=0)
            mark.create_oval(1, 1, d - 1, d - 1, outline=T.INFO, width=2)
            mark.create_text(d / 2, d / 2, text=str(i + 1), fill=T.INFO, font=(T.NUM, 11, "bold"))
            mark.pack(side="left", anchor="n", padx=(0, 12))
            col = tk.Frame(row, bg=T.PANEL)
            col.pack(side="left", fill="x", expand=True)
            lbl = tk.Label(col, text="", font=(T.TXT, 12), fg=T.ASPHALT, bg=T.PANEL, anchor="w", justify="left")
            lbl.pack(anchor="w")
            self.step_text.append(lbl)
            if i == 2:
                self.copy_btn = Btn(col, t("setup.copy"), copy_firewall, dark=True)
                self.copied = tk.Label(col, text="", font=(T.TXT, 10, "bold"), fg=T.GO, bg=T.PANEL, justify="left")

        self.rail = AlignmentRail(f)
        self.rail.canvas.grid(row=2, column=0, sticky="ew", pady=(22, 0))

        self.block = tk.Frame(f, bg=T.PANEL)
        self.block.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        tk.Label(self.block, text=t("block.title"), font=(T.TXT, 10), fg=T.MUTED, bg=T.PANEL).pack(anchor="w")
        self.chips = tk.Frame(self.block, bg=T.PANEL)
        self.chips.pack(anchor="w", fill="x", pady=(6, 0))
        self.block_text = tk.Label(self.block, text="", font=(T.TXT, 13), bg=T.PANEL, anchor="w")
        self.block_note = tk.Label(self.block, text=t("block.expected"), font=(T.TXT, 10), fg=T.MUTED, bg=T.PANEL,
                                   anchor="w", justify="left")
        self._title, self._sub, self._note = Para(self.title), Para(self.sub), Para(self.block_note)
        self._steps = [Para(lbl) for lbl in self.step_text]
        self._note.set(t("block.expected"))
        self._chip_key: Optional[tuple] = None
        self._chip_font = tkfont.Font(font=(T.NAME, 11, "bold"))
        self._mode = ""
        self._width = 0
        f.bind("<Configure>", lambda e: self._wrap(e.width))

    def _wrap(self, width: int) -> None:
        self._width = width
        for para in (self._title, self._sub):
            para.set(width=width - 50)
        for para in self._steps:
            para.set(width=width - T.px(44))
        self._note.set(width=width)
        self.copied.configure(wraplength=max(width - T.px(44), 200))

    def _set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        if mode == "setup":                                 # before any packet the route means nothing
            self.steps.grid()
            self.rail.canvas.grid_remove()
            self.block.grid_remove()
        else:
            self.steps.grid_remove()
            self.rail.canvas.grid()
            self.block.grid()

    def _plate(self, title: str, sub: str, style: str) -> None:
        quiet = style == "quiet"
        if style != self._style:
            self._style = style
            bg = {"info": T.INFO, "danger": T.STOP, "quiet": T.PANEL}[style]
            self.plate.configure(bg=bg, padx=0 if quiet else 2, pady=0 if quiet else 2)
            self.ring.configure(bg=bg if quiet else T.PANEL, padx=0 if quiet else 3, pady=0 if quiet else 3)
            self.body.configure(bg=bg, padx=0 if quiet else 18, pady=0 if quiet else 14)
            self.title.configure(bg=bg, fg=T.MUTED if quiet else "white")
            self.sub.configure(bg=bg, fg=T.INFO_INK)
        size = 14 if quiet else (17 if sub or self._mode == "setup" else 21)    # a long sentence: smaller
        self.title.configure(font=(T.TXT, size, "normal" if quiet else "bold"))
        self._title.set(title)
        self._sub.set(sub)
        if sub and not self.sub.winfo_manager():
            self.sub.pack(anchor="w", fill="x", pady=(6, 0))
        elif not sub and self.sub.winfo_manager():
            self.sub.pack_forget()

    def update(self, snap: Snapshot, nav_port: int, firewall: osutil.FirewallHint, ips: Sequence[str]) -> None:
        g = V.guide(snap)
        self._set_mode("setup" if g.kind == "setup" else "normal")
        self._plate(g.title, g.sub, {"danger": "danger", "quiet": "quiet"}.get(g.kind, "info"))
        if g.kind == "setup":
            here = f"{ips[0]}:{nav_port}" if ips else t("setup.this_ip", port=nav_port)
            others = t("setup.others", ips=i18n.joined(ips[1:])) if len(ips) > 1 else ""
            for para, text in zip(self._steps, (t("setup.step1", here=here, others=others), t("setup.step2"),
                                                firewall.text)):
                para.set(text)
            if firewall.command and not self.copy_btn.frame.winfo_manager():
                self.copy_btn.frame.pack(anchor="w", pady=(10, 0))
                self.copied.pack(anchor="w", pady=(6, 0))
            return
        self.rail.update(V.rail(snap), snap.cfg.ready_stable)
        chips = V.blocking(snap)
        self._show_chips(chips or [])
        if chips is None:
            self.block_text.configure(text=t("block.unknown"), fg=T.MUTED, font=(T.TXT, 12))
        elif not chips:
            self.block_text.configure(text=t("none"), fg=T.GO, font=(T.TXT, 13, "bold"))
        show_text = not chips
        if show_text != bool(self.block_text.winfo_manager()):
            if show_text:
                self.block_text.pack(anchor="w", before=self.chips)
            else:
                self.block_text.pack_forget()
        expected = bool(chips) and all(c.expected for c in chips or [])
        if expected != bool(self.block_note.winfo_manager()):
            if expected:
                self.block_note.pack(anchor="w", pady=(2, 0))
            else:
                self.block_note.pack_forget()

    def _show_chips(self, chips: Sequence[V.Chip]) -> None:
        """Chips flow into rows that fit the zone's width."""
        width = self._width if self._width > 100 else 10_000
        key = (tuple(chips), width)
        if key == self._chip_key:
            return
        self._chip_key = key
        for w in self.chips.winfo_children():
            w.destroy()
        row: Optional[tk.Frame] = None
        x = 0
        for chip in chips:
            bg, fg, line = T.CHIP_EXPECTED if chip.expected else T.CHIP_PROBLEM
            need = self._chip_font.measure(chip.text) + 32
            if row is None or (x and x + need > width):
                row = tk.Frame(self.chips, bg=T.PANEL)
                row.pack(anchor="w", pady=(0, 6))
                x = 0
            tk.Label(row, text=chip.text, font=self._chip_font, bg=bg, fg=fg, padx=10, pady=3, highlightthickness=1,
                     highlightbackground=line, highlightcolor=line).pack(side="left", padx=(0, 8))
            x += need


# --------------------------------------------------------------------------- engineering zone
class ScrollZone:
    """The engineering zone: fills its column, and scrolls only when the window is too short for it.
    The glance zone beside it never scrolls."""

    def __init__(self, parent: tk.Misc) -> None:
        self.outer = tk.Frame(parent, bg=T.KERB)
        self.canvas = tk.Canvas(self.outer, bg=T.KERB, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self.outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T.KERB, padx=GAP, pady=GAP)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self._size: Optional[tuple] = None
        self.canvas.bind("<Configure>", lambda _e: self._fit())
        self.inner.bind("<Configure>", lambda _e: self._fit())
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):  # Windows and macOS; X11 sends buttons
            self.canvas.bind_all(event, self._wheel)              # one zone per window; a rebuild replaces it

    def _fit(self) -> None:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        need = self.inner.winfo_reqheight()
        size = (w, max(h, need))
        if size != self._size:
            self._size = size
            self.canvas.itemconfigure(self._window, width=w, height=size[1])
            self.canvas.configure(scrollregion=(0, 0, *size))
        scroll = need > h > 1
        if scroll != bool(self.bar.winfo_manager()):
            if scroll:
                self.bar.pack(side="right", fill="y", before=self.canvas)
            else:
                self.bar.pack_forget()
                self.canvas.yview_moveto(0)

    def _wheel(self, e: tk.Event) -> None:
        over = self.outer.winfo_containing(e.x_root, e.y_root)
        if self.bar.winfo_manager() and over is not None and str(over).startswith(str(self.outer)):
            self.canvas.yview_scroll(-1 if e.delta > 0 or e.num == 4 else 1, "units")


class NavPanel:
    ORDER = (("age", "nav.age"), ("pos_std", "nav.pos_std"), ("att_std", "nav.att_std"),
             ("lat", "nav.lat"), ("lon", "nav.lon"), ("height", "nav.height"),
             ("heading", "nav.heading"), ("speed", "nav.speed"), ("vu", "nav.vu"),
             ("att", "nav.att"), ("vel_std", "nav.vel_std"), ("time", "nav.time"))

    def __init__(self, eng: tk.Misc) -> None:
        f, head = section(eng, t("nav.title"))
        f.pack(fill="x", pady=(GAP, 0))
        self.link = LinkText(head)
        lamps = tk.Frame(f, bg=T.PANEL)
        lamps.pack(fill="x", pady=(0, 6))
        self.lamps: Dict[str, Tuple[tk.Canvas, tk.Label]] = {}
        for name in ("ALIGN", "HEADING", "FINE"):
            dot = tk.Canvas(lamps, width=12, height=12, bg=T.PANEL, highlightthickness=0)
            dot.create_oval(1, 1, 11, 11, width=2, tags="dot")
            dot.pack(side="left", padx=(0, 6))
            lbl = tk.Label(lamps, text=i18n.lamp_name(name), font=(T.TXT, 11), bg=T.PANEL)
            lbl.pack(side="left", padx=(0, 18))
            self.lamps[name] = (dot, lbl)
        tk.Label(f, text=t("nav.aiding"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(anchor="w")
        self.aid_row = aid = tk.Frame(f, bg=T.PANEL)
        aid.pack(fill="x", pady=(3, 6))
        self.aid: Dict[str, tk.Label] = {}
        for name in P.AIDING_FLAGS:                         # standard INS acronyms: the same in both languages
            self.aid[name] = tk.Label(aid, text=name, font=(T.NUM, 10), padx=7, pady=1, highlightthickness=1)
        self._flowed: Optional[tuple] = None
        aid.bind("<Configure>", lambda _e: self._flow())
        self.v = value_grid(f, self.ORDER, cols=3)

    def update(self, snap: Snapshot) -> None:
        n, now = snap.nav, snap.now
        self.link.show(V.nav_link(snap))
        flags = n.flags if n is not None else 0
        for name, (dot, lbl) in self.lamps.items():
            on = bool(flags >> P.FLAG_NAMES.index(name) & 1)
            dot.itemconfigure("dot", fill=T.GO if on else T.PANEL, outline=T.GO if on else "#8A949C")
            lbl.configure(fg=T.ASPHALT if on else T.FAINT, font=(T.TXT, 11, "bold" if on else "normal"))
        for name, lbl in self.aid.items():
            seen = snap.flag_seen.get(name)
            if seen is None:
                lbl.configure(text=t("nav.not_seen", name=name), fg=T.FAINT, bg=T.PANEL, highlightbackground=T.LINE,
                              font=(T.TXT, 10))
                continue
            a = now - seen
            shown = f"{a:.1f}" if a < 10 else (f"{a:.0f}" if a < 100 else "99+")   # keeps the row narrow
            recent = a < 1.5
            lbl.configure(text=f"{name} {shown}s", fg=T.GO_INK if recent else T.ASPHALT, font=(T.NUM, 10),
                          bg=T.GO_TINT if recent else T.PANEL, highlightbackground="#BFDCC9" if recent else T.LINE)
        self._flow()
        if n is None:
            return
        v, age = self.v, now - snap.nav_at
        stale = age > snap.cfg.nav_max_age
        for lbl in v.values():
            lbl.configure(fg=T.FAINT if stale else T.ASPHALT)            # stale values read as old
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
        v["age"].configure(text=f"{age * 1000:.0f}", fg=T.STOP if stale else T.ASPHALT)


    def _flow(self) -> None:
        """The aiding chips wrap onto a second row when the zone is narrow."""
        width = self.aid_row.winfo_width()
        width = width if width > 50 else 10_000
        places, x, row, col = [], 0, 0, 0
        for lbl in self.aid.values():
            need = lbl.winfo_reqwidth() + 6
            if x and x + need > width:
                x, row, col = 0, row + 1, 0
            places.append((row, col))
            x, col = x + need, col + 1
        if tuple(places) != self._flowed:
            self._flowed = tuple(places)
            for lbl, (r, c) in zip(self.aid.values(), places):
                lbl.grid(row=r, column=c, sticky="w", padx=(0, 6), pady=(0, 4))


class StatusPanel:
    def __init__(self, body: tk.Misc) -> None:
        self.frame, head = section(body, t("status.title"))
        self.frame.grid(row=0, column=0, sticky="nsew")
        self.link = LinkText(head)
        self.v = value_grid(self.frame, [
            ("state", "status.state"), ("gnss", "status.gnss"), ("session", "status.session"),
            ("sequence", "status.sequence"), ("rate", "status.rate"), ("nav_age", "status.nav_age"),
        ], cols=3)
        self.v["state"].configure(font=(T.NAME, 13, "bold"))
        self.v["gnss"].configure(font=(T.NAME, 12))
        cap = tk.Frame(self.frame, bg=T.PANEL)
        cap.pack(fill="x", pady=(4, 4))
        tk.Label(cap, text=t("status.health"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).pack(side="left")
        self.met = tk.Label(cap, text=t("status.none_yet"), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL)
        self.met.pack(side="right")
        grid = tk.Frame(self.frame, bg=T.PANEL)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="h")
        grid.columnconfigure(1, weight=1, uniform="h")
        self.health: List[tk.Label] = []
        self._health: List[Para] = []
        rows = (len(P.HEALTH_BITS) + 1) // 2
        for i in range(len(P.HEALTH_BITS)):
            lbl = tk.Label(grid, font=(T.NAME, 10), fg=T.FAINT, bg=T.PANEL, anchor="w", justify="left")
            lbl.grid(row=i % rows, column=i // rows, sticky="w", padx=(0, 10))
            self.health.append(lbl)
            self._health.append(Para(lbl))
            self._health[-1].set(f"○ {i18n.health_name(i)}")
        fit_to_columns(grid, self._health, 2, 12)

    def update(self, snap: Snapshot) -> None:
        link = V.status_link(snap)
        self.link.show(link)
        s = snap.status
        if s is None:
            return
        v, fresh = self.v, snap.status_fresh
        ink = T.ASPHALT if fresh else T.FAINT               # stale values read as old, never as green
        for lbl in v.values():
            lbl.configure(fg=ink)
        state = P.name_of(s.state, P.STATES)
        color = T.GO if state == "READY" else (T.STOP if state in ("FAULT", "DEGRADED") else T.ASPHALT)
        v["state"].configure(text=i18n.state_name(state), fg=color if fresh else T.FAINT)
        v["gnss"].configure(text=i18n.gnss_quality(s.gnss_quality))
        v["session"].configure(text=f"0x{s.session:08X}", font=(T.NUM_COND, 12))
        v["sequence"].configure(text=str(s.sequence))
        v["rate"].configure(text=f"{s.nav_rate_dhz / 10:.1f}")
        v["nav_age"].configure(text="—" if s.nav_age_ms == P.NAV_AGE_UNKNOWN else str(s.nav_age_ms))
        rows = V.conditions(snap)
        met = sum(ok for _, ok in rows)
        self.met.configure(text=t("status.met", n=met, total=len(rows)) + ("" if fresh else t("status.out_of_date")),
                           fg=T.MUTED if fresh else T.STOP)
        for lbl, para, (name, ok) in zip(self.health, self._health, rows):
            lbl.configure(fg=(T.GO if ok else T.ASPHALT) if fresh else T.FAINT,
                          font=(T.NAME, 10, "normal" if ok else "bold"))
            para.set(f"{'●' if ok else '○'} {name}")


class TrackPanel:
    """Trajectory on graph paper: solid green where the output was usable, dashed grey where blocked."""

    def __init__(self, body: tk.Misc, clear: Callable[[], None]) -> None:
        self.frame, head = section(body, t("track.title"))
        self.frame.grid(row=0, column=1, sticky="nsew", padx=(GAP, 0))
        Btn(head, t("track.clear"), clear).frame.pack(side="right")
        foot = tk.Frame(self.frame, bg=T.PANEL)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        for usable, text in ((True, t("track.usable")), (False, t("track.blocked"))):
            sample = tk.Canvas(foot, width=24, height=10, bg=T.PANEL, highlightthickness=0)
            if usable:
                sample.create_line(3, 5, 21, 5, fill=T.GO, width=5, capstyle="round")
            else:
                for x in (2, 10, 18):
                    sample.create_line(x, 5, x + 5, 5, fill=T.IDLE, width=3)
            sample.pack(side="left", padx=(0, 5))
            tk.Label(foot, text=text, font=(T.TXT, 9), fg=T.TEXT2, bg=T.PANEL).pack(side="left", padx=(0, 12))
        self.canvas = tk.Canvas(self.frame, height=T.px(170), bg=T.PANEL, highlightthickness=1,
                                highlightbackground=T.LINE)
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
            c.create_text(w / 2, h / 2, text=t("track.empty"), fill=T.MUTED, font=(T.TXT, 10), width=w - 20,
                          justify="center")
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

        def px(i: int) -> Point:
            return ox + xs[i] * scale, oy - ys[i] * scale

        # Consecutive points with the same verdict become one line: solid green, or dashed grey.
        run: List[Point] = [px(0)]
        for i in range(1, len(pts)):
            run.append(px(i))
            if pts[i].usable != pts[i - 1].usable or i == len(pts) - 1:
                if len(run) >= 2:
                    if pts[i - 1].usable:
                        c.create_line(*[v for xy in run for v in xy], fill=T.GO, width=5, capstyle="round",
                                      joinstyle="round")
                    else:
                        dashed(c, run, fill=T.IDLE, width=3, capstyle="butt")
                run = [run[-1]]
        x, y = px(len(pts) - 1)
        if heading is not None and math.isfinite(heading):
            a = math.radians(heading)
            c.create_line(x, y, x + 26 * math.sin(a), y - 26 * math.cos(a), fill=T.ASPHALT, width=3,
                          arrow="last", arrowshape=(10, 12, 5))
        c.create_oval(x - 7, y - 7, x + 7, y + 7, fill=T.ASPHALT, outline=T.PANEL, width=2)

        bl = bar * scale
        c.create_rectangle(margin - 4, h - 22, margin + bl + 52, h - 2, fill=T.PANEL, outline="")
        c.create_line(margin, h - 10, margin + bl, h - 10, fill=T.ASPHALT, width=2)
        c.create_line(margin, h - 15, margin, h - 5, fill=T.ASPHALT, width=2)
        c.create_line(margin + bl, h - 15, margin + bl, h - 5, fill=T.ASPHALT, width=2)
        c.create_text(margin + bl + 8, h - 10, text=f"{bar:g} m", anchor="w", fill=T.ASPHALT, font=(T.NUM, 10))
        c.create_line(w - 16, 34, w - 16, 10, fill=T.ASPHALT, width=2, arrow="last")
        c.create_text(w - 16, 46, text="N", fill=T.ASPHALT, font=(T.NUM, 11, "bold"))   # compass mark, as on maps
        meta = c.create_text(8, 6, text=t("track.meta", n=len(pts), span=span), anchor="nw", fill=T.MUTED,
                             font=(T.TXT, 9))
        c.create_rectangle(*c.bbox(meta), fill=T.PANEL, outline="")
        c.tag_raise(meta)


# ------------------------------------------------------------------------ actions, source strip
class Footer:
    """The engineering zone's edges: the actions with their shortcuts on top, a recording error under
    them when there is one, and where the data comes from with the packet counts at the bottom."""

    _ANOMALY = (("lost", T.AMBER), ("reordered", T.AMBER), ("bad", T.STOP), ("conflicts", T.STOP),
                ("foreign", T.STOP))

    def __init__(self, eng: tk.Misc, actions: Dict[str, Callable[[], None]], show_track: tk.BooleanVar,
                 alert: tk.BooleanVar) -> None:
        self.bar = bar = tk.Frame(eng, bg=T.KERB)
        bar.pack(side="top", fill="x")
        self.buttons = left = tk.Frame(bar, bg=T.KERB)
        left.pack(side="left")
        self.rec = tk.Frame(left, bg=T.KERB)                # shown only while recording
        dot = tk.Canvas(self.rec, width=12, height=12, bg=T.KERB, highlightthickness=0)
        dot.create_oval(1, 1, 11, 11, fill=T.STOP, outline="")
        dot.pack(side="left", padx=(0, 6))
        self.rec_time = tk.Label(self.rec, text="", font=(T.TXT, 11, "bold"), fg=T.STOP, bg=T.KERB)
        self.rec_time.pack(side="left")
        self.rec_btn = Btn(left, t("foot.start_rec"), actions["record"], kbd="Ctrl+R")
        self.rec_btn.frame.pack(side="left")
        Btn(left, t("foot.replay"), actions["replay"], kbd="Ctrl+O").frame.pack(side="left", padx=(8, 0))
        Btn(left, t("foot.settings"), actions["settings"]).frame.pack(side="left", padx=(8, 0))
        self.toggles = tk.Frame(bar, bg=T.KERB)
        self.alert_cb = ttk.Checkbutton(self.toggles, text=t("foot.alert"), variable=alert, command=actions["alert"],
                                        style="Kerb.TCheckbutton")
        self.alert_cb.pack(side="left", padx=(16, 0))
        ttk.Checkbutton(self.toggles, text=t("foot.show_track"), variable=show_track, command=actions["track"],
                        style="Kerb.TCheckbutton").pack(side="left", padx=(12, 0))
        tk.Label(self.toggles, text=t("foot.fullscreen"), font=(T.TXT, 9), fg=T.MUTED, bg=T.KERB).pack(
            side="left", padx=(16, 0))
        self._toggles_below: Optional[bool] = None
        bar.bind("<Configure>", lambda e: self._fit(e.width))
        left.bind("<Configure>", lambda _e: self._fit(bar.winfo_width()))    # the recording indicator came or went
        self._fit(10_000)

        self.error_box = tk.Frame(eng, bg=T.ALERT[0], highlightthickness=2, highlightbackground=T.ALERT[2],
                                  padx=12, pady=8)
        self.error = tk.Label(self.error_box, text="", font=(T.TXT, 11, "bold"), fg=T.ALERT[1], bg=T.ALERT[0],
                              anchor="w", justify="left")
        self.error.pack(anchor="w", fill="x")
        self._help = tk.Label(self.error_box, text=t("rec.error_help"), font=(T.TXT, 10), fg=T.ALERT[1],
                              bg=T.ALERT[0], anchor="w", justify="left")
        self._help.pack(anchor="w", fill="x")
        self._error, help_text = Para(self.error), Para(self._help)
        help_text.set(t("rec.error_help"))
        def resize(e: tk.Event) -> None:
            for p in (self._error, help_text):
                p.set(width=e.width - 30)
        self.error_box.bind("<Configure>", resize)

        strip = tk.Frame(eng, bg=T.PANEL, padx=16, pady=8)
        strip.pack(side="bottom", fill="x", pady=(GAP, 0))  # packed before the body so it never gets squeezed out
        self.source = tk.Label(strip, text="", font=(T.TXT, 10), fg=T.TEXT2, bg=T.PANEL, anchor="w", justify="left")
        self.source.pack(anchor="w", fill="x")
        strip.bind("<Configure>", lambda e: self.source.configure(wraplength=max(e.width - 32, 200)))
        counts = tk.Frame(strip, bg=T.PANEL)
        counts.pack(fill="x")
        self._colors = dict(self._ANOMALY)
        self.counts: Dict[str, tk.Label] = {}
        for key in ("nav", "status", *self._colors):
            lbl = tk.Label(counts, text="", font=(T.TXT, 10), fg=T.TEXT2, bg=T.PANEL)
            lbl.pack(side="left", padx=(0, 14))
            self.counts[key] = lbl
        self._rec_shown = False
        self._error_shown = False

    def _fit(self, width: int) -> None:
        """The check boxes go under the buttons when one row is too narrow (English, a small window)."""
        below = self.buttons.winfo_reqwidth() + self.toggles.winfo_reqwidth() > width
        if below == self._toggles_below or width <= 1:          # 1: not laid out yet
            return
        self._toggles_below = below
        self.buttons.pack_forget()
        self.toggles.pack_forget()
        if below:
            self.buttons.pack(side="top", anchor="w")
            self.toggles.pack(side="top", anchor="w", pady=(6, 0))
        else:
            self.buttons.pack(side="left")
            self.toggles.pack(side="left")
        self.alert_cb.pack_configure(padx=(0 if below else 16, 0))

    def update(self, snap: Snapshot) -> None:
        recording = snap.recording is not None
        self.rec_btn.set(t("foot.stop_rec" if recording else "foot.start_rec"), enabled=snap.source_kind != "replay",
                         color=T.STOP if recording else None)
        if recording != self._rec_shown:
            self._rec_shown = recording
            if recording:
                self.rec.pack(side="left", padx=(0, 12), before=self.rec_btn.frame)
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
            lbl.configure(text=t(f"foot.{key}", n=n), fg=self._colors[key] if bad else T.TEXT2,
                          font=(T.TXT, 10, "bold" if bad else "normal"))
        err = snap.recording_error
        if bool(err) != self._error_shown:
            self._error_shown = bool(err)
            if err:
                self.error_box.pack(side="top", fill="x", pady=(GAP, 0), after=self.bar)
            else:
                self.error_box.pack_forget()
        self._error.set(str(err) if err else "")
