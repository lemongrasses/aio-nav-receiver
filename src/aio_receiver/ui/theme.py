"""Road-signage identity: traffic-sign colours that only ever carry meaning, DIN type for numbers.

Bahnschrift is Microsoft's DIN 1451, the German road-sign face; macOS has DIN Alternate / DIN
Condensed. Light theme: the laptop is read beside a vehicle, often in daylight.

Layout C: a signal mast on the left (position says the meaning, so it reads without colour), a
glance zone with the verdict and the one instruction, and an engineering zone with the detail.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# Surfaces and ink
ASPHALT = "#1D252C"         # text; the signal mast
KERB = "#E9ECEE"            # background and gutters
PANEL = "#FFFFFF"
SHADE = "#F6F7F8"           # dialog footers, quiet boxes
TEXT2 = "#3B454E"           # secondary text
MUTED = "#56616B"           # labels and hints
FAINT = "#6B757E"           # not received yet, future stations (4.5:1 on white)
LINE = "#D5DADF"            # rules and outlines, never text
GRID = "#EEF1F3"            # map graph paper
FOCUS = "#1B5FD9"

# Signal colours (RAL traffic green / yellow / red / grey). Meaning only.
GO = "#1E7B45"
WAIT = "#F2B705"            # dark text on it
STOP = "#B3261E"
IDLE = "#5F6A73"
GO_TINT = "#DDEFE3"         # recent aiding flag
GO_INK = "#145A32"
AMBER = "#8A5A00"           # counters worth a look (lost, out of order)
INFO = "#1B4F9C"            # mandatory-instruction blue: what to do now; the replay bar
INFO_INK = "#E3ECF9"        # secondary text on INFO

SIGNAL = {"go": GO, "wait": WAIT, "stop": STOP, "idle": IDLE}
WORD = {"go": GO, "wait": ASPHALT, "stop": STOP, "idle": IDLE}   # the big word: yellow text would not read

# The mast's unlit lamps
LAMP_OFF, LAMP_RING_OFF, LAMP_TEXT_OFF = "#2B353D", "#46525C", "#9AA4AC"

# Blocking-condition chips: (background, text, outline)
CHIP_EXPECTED = ("#FFF1BF", "#6B4600", "#E5C44D")    # a normal alignment step
CHIP_PROBLEM = ("#FBE4E2", STOP, "#E6A39E")
ALERT = ("#FBE4E2", "#8C1D17", STOP)                  # the recording-error box

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
ZOOM = 1.0                  # drawn geometry follows the text size (see fit_to_screen)


def px(n: float) -> int:
    """Canvas geometry in design pixels, scaled like the text so shapes and labels stay in proportion."""
    return round(n * ZOOM)


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
    """ttk widgets take the colour of the surface they sit on (native themes paint grey)."""
    style = ttk.Style(root)
    for name, bg in (("Kerb", KERB), ("Panel", PANEL), ("Shade", SHADE)):
        style.configure(f"{name}.TCheckbutton", background=bg, foreground=ASPHALT, font=(TXT, 10))


def fit_to_screen(root: tk.Tk) -> str:
    """Scale text so the whole layout fits the screen, and return the window geometry.

    Tk already enlarges fonts on high-DPI screens; on a small or highly scaled laptop screen that
    would push panels off the bottom, so the scaling is lowered just enough to fit.
    """
    global ZOOM
    scaling = float(root.tk.call("tk", "scaling"))
    zoom = scaling / DESIGN_SCALING
    w, h = DESIGN_SIZE[0] * zoom, DESIGN_SIZE[1] * zoom
    avail_w, avail_h = root.winfo_screenwidth() - 40, root.winfo_screenheight() - 100   # taskbar, title
    fit = min(1.0, avail_w / w, avail_h / h)
    if fit < 1.0:
        root.tk.call("tk", "scaling", scaling * fit)
        w, h, zoom = w * fit, h * fit, zoom * fit
    ZOOM = zoom
    return f"{int(w)}x{int(h)}"
