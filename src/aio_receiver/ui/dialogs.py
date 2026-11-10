"""Message dialogs in the screen's own look: an asphalt title strip with a sign, the facts, one button."""

from __future__ import annotations

import tkinter as tk
from typing import Sequence

from ..i18n import t
from . import theme as T
from .panels import Btn, wrapped


class Notice(tk.Toplevel):
    """`kind`: warn (a yellow warning sign) or error (a red no-entry sign). Enter or Esc closes it."""

    def __init__(self, parent: tk.Misc, kind: str, title: str, lead: str, items: Sequence[str], foot: str,
                 bold_lead: bool = False) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=T.PANEL)
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        wrap = 440
        head = tk.Frame(self, bg=T.ASPHALT, padx=18, pady=10)
        head.pack(fill="x")
        sign = tk.Canvas(head, width=24, height=24, bg=T.ASPHALT, highlightthickness=0)
        if kind == "warn":
            sign.create_polygon(12, 2, 23, 22, 1, 22, fill=T.WAIT, outline=T.WAIT, joinstyle="round")
            sign.create_line(12, 9, 12, 15, fill=T.ASPHALT, width=2.5, capstyle="round")
            sign.create_oval(10.6, 17.4, 13.4, 20.2, fill=T.ASPHALT, outline="")
        else:
            sign.create_oval(2, 2, 22, 22, fill=T.STOP, outline="")
            sign.create_line(8, 8, 16, 16, fill="white", width=2.5, capstyle="round")
            sign.create_line(16, 8, 8, 16, fill="white", width=2.5, capstyle="round")
        sign.pack(side="left", padx=(0, 10))
        tk.Label(head, text=title, font=(T.TXT, 13, "bold"), fg="white", bg=T.ASPHALT).pack(side="left")

        body = tk.Frame(self, bg=T.PANEL, padx=20, pady=16)
        body.pack(fill="x")
        font = (T.TXT, 11, "bold" if bold_lead else "normal")
        tk.Label(body, text=wrapped(lead, font, wrap), font=font, fg=T.ASPHALT, bg=T.PANEL, justify="left",
                 anchor="w").pack(anchor="w", fill="x")
        for item in items:
            box = tk.Frame(body, bg=T.SHADE, highlightthickness=1, highlightbackground=T.LINE, padx=10, pady=6)
            box.pack(anchor="w", fill="x", pady=(8, 0))
            tk.Label(box, text=wrapped(item, (T.TXT, 11), wrap - 24), font=(T.TXT, 11), fg=T.ASPHALT, bg=T.SHADE,
                     justify="left", anchor="w").pack(anchor="w", fill="x")
        if foot:
            tk.Label(body, text=wrapped(foot, (T.TXT, 10), wrap), font=(T.TXT, 10), fg=T.MUTED, bg=T.PANEL,
                     justify="left", anchor="w").pack(anchor="w", fill="x", pady=(12, 0))

        bottom = tk.Frame(self, bg=T.SHADE, padx=20, pady=10, highlightthickness=1, highlightbackground=T.LINE)
        bottom.pack(fill="x")
        ok = Btn(bottom, t("dlg.ok"), self.destroy, kbd="Enter", dark=True)
        ok.frame.pack(side="right")
        self.bind("<Return>", lambda _e: self.destroy())
        self.bind("<Escape>", lambda _e: self.destroy())
        ok.frame.focus_set()
        self.grab_set()
