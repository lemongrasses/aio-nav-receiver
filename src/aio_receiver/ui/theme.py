"""Road-signage identity: traffic-sign colours that only ever carry meaning, DIN type for numbers.

Bahnschrift is Microsoft's DIN 1451, the German road-sign face; macOS has DIN Alternate / DIN
Condensed. Light theme: the laptop is read beside a vehicle, often in daylight.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Surfaces and ink
ASPHALT = "#1D252C"         # text; the replay bar
KERB = "#E4E7EA"            # background and gutters
PANEL = "#FFFFFF"
MUTED = "#5B6670"
LINE = "#CBD1D6"
GRID = "#EEF1F3"            # map graph paper

# Signal colours (RAL traffic green / yellow / red / grey). Meaning only.
GO = "#1E7B45"
WAIT = "#F2B705"            # dark text on it
STOP = "#B3261E"
IDLE = "#69747E"
GO_TINT = "#DDEFE3"         # recent aiding flag
WAIT_INK = ASPHALT

BAND = {"go": (GO, "white"), "wait": (WAIT, WAIT_INK), "stop": (STOP, "white"), "idle": (IDLE, "white")}
DOT = {"go": GO, "stop": STOP, "idle": LINE}

# Kept for code that predates the signage names.
BASE, INK, CAUTION = KERB, ASPHALT, "#9A6700"

_TXT = ("Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC", "Noto Sans TC",
        "Source Han Sans TC", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "Droid Sans Fallback")
_TXT_EN = ("Segoe UI", "Helvetica Neue", "SF Pro Text", "Noto Sans", "DejaVu Sans", "Liberation Sans")
_NUM = ("Bahnschrift", "DIN Alternate", "DIN 1451", "Helvetica Neue", "Segoe UI", "DejaVu Sans", "Liberation Sans")
_NUM_COND = ("Bahnschrift SemiBold Condensed", "Bahnschrift Condensed", "DIN Condensed", "DejaVu Sans Condensed",
             "Liberation Sans Narrow", "Arial Narrow")

TXT = "TkDefaultFont"       # text in the current language (CJK-capable when Chinese)
NUM = "TkDefaultFont"       # numbers, codes (ASCII only)
NUM_COND = "TkDefaultFont"  # condensed ASCII where space is tight
NAME = "TkDefaultFont"      # translated names in tight spaces (states, conditions): condensed in English

DESIGN_SIZE = (1440, 900)   # pixels at 96 dpi
DESIGN_SCALING = 96 / 72    # Tk pixels per point at 96 dpi


def init_fonts(root: tk.Misc, language: str = "zh-TW") -> None:
    """Pick font families for `language` once the Tk root exists (Tk cannot list fonts before)."""
    global TXT, NUM, NUM_COND, NAME
    installed = set(tkfont.families(root))
    default = tkfont.nametofont("TkDefaultFont").actual("family")
    cjk = next((f for f in _TXT if f in installed), default)
    NUM = next((f for f in _NUM if f in installed), default)
    NUM_COND = next((f for f in _NUM_COND if f in installed), NUM)
    if language == "en":
        TXT = next((f for f in _TXT_EN if f in installed), default)
        NAME = NUM_COND
    else:
        TXT = NAME = cjk


def init_styles(root: tk.Misc) -> None:
    """ttk check buttons take the colour of the surface they sit on (native themes paint grey)."""
    style = ttk.Style(root)
    style.configure("Kerb.TCheckbutton", background=KERB)
    style.configure("Panel.TCheckbutton", background=PANEL)


def fit_to_screen(root: tk.Tk) -> str:
    """Scale text so the whole layout fits the screen, and return the window geometry.

    Tk already enlarges fonts on high-DPI screens; on a small or highly scaled laptop screen that
    would push panels off the bottom, so the scaling is lowered just enough to fit.
    """
    scaling = float(root.tk.call("tk", "scaling"))
    zoom = scaling / DESIGN_SCALING
    w, h = DESIGN_SIZE[0] * zoom, DESIGN_SIZE[1] * zoom
    avail_w, avail_h = root.winfo_screenwidth() - 40, root.winfo_screenheight() - 100   # taskbar, title
    fit = min(1.0, avail_w / w, avail_h / h)
    if fit < 1.0:
        root.tk.call("tk", "scaling", scaling * fit)
        w, h = w * fit, h * fit
    return f"{int(w)}x{int(h)}"
