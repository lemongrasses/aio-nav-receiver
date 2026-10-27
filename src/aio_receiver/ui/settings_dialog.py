"""Settings dialog in two parts: what an operator changes on site (language, recording), and the
receiving setup and rules that must match the device, folded away under Advanced until needed.
Every field is validated by config.parse_field before anything is saved; the first problem is shown
above the buttons, with the Advanced part opened when the problem is there."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable, Dict, List, Sequence, Tuple

from .. import config, osutil
from ..config import Settings
from ..i18n import LANGUAGE_NAMES, LANGUAGES, os_error, t
from . import theme as T
from .panels import Btn, wrapped

Field = Tuple[str, str, str]        # (setting, label key, hint key)
RECEIVE: Sequence[Field] = (("host", "set.host", "set.host_hint"),
                            ("nav_port", "set.nav_port", "set.nav_port_hint"))
RECEIVE_2: Sequence[Field] = (("status_id", "set.status_id", "set.status_id_hint"),)
RULES: Sequence[Field] = (("status_timeout", "set.status_timeout", "set.status_timeout_hint"),
                          ("ready_stable", "set.ready_stable", "set.ready_stable_hint"),
                          ("nav_max_age", "set.nav_max_age", "set.nav_max_age_hint"))
ADVANCED = frozenset({"host", "nav_port", "status_port", "status_id", "allowed_from", "status_timeout",
                      "ready_stable", "nav_max_age"})
WRAP = 250                          # hint width, design pixels


def language_choices() -> List[Tuple[str, str]]:
    """(setting value, what the list shows). Language names are written in their own language."""
    return [("", t("set.language_system"))] + [(code, LANGUAGE_NAMES[code]) for code in LANGUAGES]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, current: Settings, on_save: Callable[[Settings], None]) -> None:
        super().__init__(parent)
        self.current, self.on_save = current, on_save
        self.title(t("set.title"))
        self.configure(bg=T.PANEL)
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        self._shown = config.to_dict(current)
        self.vars: Dict[str, tk.StringVar] = {}
        self.labels: Dict[str, str] = {}

        head = tk.Frame(self, bg=T.ASPHALT, padx=24, pady=10)
        head.pack(fill="x")
        tk.Label(head, text=t("set.title"), font=(T.TXT, 14, "bold"), fg="white", bg=T.ASPHALT).pack(side="left")

        page = tk.Frame(self, bg=T.PANEL, padx=28, pady=16)
        page.pack(fill="x")
        page.columnconfigure(0, weight=1)
        tk.Label(page, text=t("set.sec_everyday"), font=(T.TXT, 13, "bold"), fg=T.ASPHALT, bg=T.PANEL).grid(
            row=0, column=0, sticky="w")
        tk.Label(page, text=t("set.everyday_sub"), font=(T.TXT, 10), fg=T.MUTED, bg=T.PANEL).grid(
            row=1, column=0, sticky="w", pady=(0, 10))
        everyday = tk.Frame(page, bg=T.PANEL)
        everyday.grid(row=2, column=0, sticky="ew")
        cell = self._cell(everyday, 0, 0, t("set.language"), t("set.language_hint"))
        self.choices = language_choices()
        self.language = ttk.Combobox(cell, values=[name for _, name in self.choices], width=18, state="readonly",
                                     font=(T.TXT, 11))
        self.language.current(next((i for i, (code, _) in enumerate(self.choices) if code == current.language), 0))
        self.language.pack(anchor="w", before=cell.winfo_children()[1])
        cell = self._cell(everyday, 1, 0, t("set.record_dir"), t("set.record_dir_hint"), span=2)
        row = tk.Frame(cell, bg=T.PANEL)
        row.pack(anchor="w", fill="x", before=cell.winfo_children()[1])
        self.vars["record_dir"] = var = tk.StringVar(value=str(self._shown["record_dir"]))
        self.labels["record_dir"] = t("set.record_dir")
        ttk.Entry(row, textvariable=var, width=44, font=(T.NUM, 11)).pack(side="left", fill="x", expand=True)
        Btn(row, t("set.browse"), self._pick_dir).frame.pack(side="left", padx=(8, 0))
        self.csv = tk.BooleanVar(value=current.record_csv)
        ttk.Checkbutton(everyday, text=t("set.csv"), variable=self.csv, style="Panel.TCheckbutton").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Advanced: a heading that opens and closes the part under it.
        tk.Frame(page, bg=T.ASPHALT, height=2).grid(row=3, column=0, sticky="ew", pady=(18, 0))
        top = tk.Frame(page, bg=T.PANEL)
        top.grid(row=4, column=0, sticky="ew")
        self.adv_btn = tk.Button(top, text="", font=(T.TXT, 13, "bold"), fg=T.ASPHALT, bg=T.PANEL, relief="flat",
                                 bd=0, activebackground=T.PANEL, cursor="hand2", command=self.toggle_advanced,
                                 highlightthickness=0, padx=0, pady=8)
        self.adv_btn.pack(side="left")
        tk.Label(top, text=t("set.advanced_sub"), font=(T.TXT, 10), fg=T.MUTED, bg=T.PANEL).pack(side="left",
                                                                                               padx=(12, 0))
        self.adv = adv = tk.Frame(page, bg=T.PANEL)
        self.adv.grid(row=5, column=0, sticky="ew")
        self.adv.grid_remove()
        for i, f in enumerate(RECEIVE):
            self._entry(adv, 0, i, f)
        cell = self._cell(adv, 1, 0, t("set.status_port"), "")
        self.labels["status_port"] = t("set.status_port")
        port = self._shown["status_port"] or self._shown["nav_port"]
        self.vars["status_port"] = tk.StringVar(value=str(port))
        self.status_entry = ttk.Entry(cell, textvariable=self.vars["status_port"], width=18, font=(T.NUM, 11))
        self.status_entry.pack(anchor="w", before=cell.winfo_children()[1])
        self.same = tk.BooleanVar(value=current.status_port == 0)
        ttk.Checkbutton(cell, text=t("set.same_port"), variable=self.same, command=self._same_port,
                        style="Panel.TCheckbutton").pack(anchor="w", before=cell.winfo_children()[1])
        self.vars["nav_port"].trace_add("write", lambda *_: self._same_port())
        self._same_port()
        self._entry(adv, 1, 1, RECEIVE_2[0])
        self._entry(adv, 2, 0, ("allowed_from", "set.allowed_from", "set.allowed_from_hint"), span=2, wrap=520)
        rules = tk.Frame(adv, bg=T.PANEL, highlightthickness=2, highlightbackground=T.STOP, highlightcolor=T.STOP,
                         padx=14, pady=10)
        rules.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        tk.Label(rules, text=wrapped(t("set.rules_warning"), (T.TXT, 11, "bold"), 540), font=(T.TXT, 11, "bold"),
                 fg=T.STOP, bg=T.PANEL, justify="left").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        for i, f in enumerate(RULES):
            self._entry(rules, 1, i, f, width=10, wrap=170)

        bottom = tk.Frame(self, bg=T.SHADE, padx=28, pady=12, highlightthickness=1, highlightbackground=T.LINE)
        bottom.pack(fill="x")
        self.err = tk.Label(bottom, text="", font=(T.TXT, 10, "bold"), fg=T.STOP, bg=T.SHADE, justify="left",
                            anchor="w", wraplength=T.px(600))
        self.err.pack(anchor="w", fill="x")
        tk.Label(bottom, text=wrapped(t("set.restart_note"), (T.TXT, 10), 380), font=(T.TXT, 10), fg=T.MUTED,
                 bg=T.SHADE, justify="left").pack(side="left")
        Btn(bottom, t("set.save"), self.save, kbd="Enter", dark=True).frame.pack(side="right")
        Btn(bottom, t("set.cancel"), self.destroy, kbd="Esc").frame.pack(side="right", padx=(0, 10))
        self._advanced = False
        self._show_advanced(False)
        self.bind("<Return>", lambda _e: self.save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    # --------------------------------------------------------------------------------- fields
    def _cell(self, parent: tk.Misc, row: int, col: int, label: str, hint: str, span: int = 1,
              wrap: int = WRAP) -> tk.Frame:
        """Label, (the caller's input goes here), hint."""
        cell = tk.Frame(parent, bg=T.PANEL)
        cell.grid(row=row, column=col, columnspan=span, sticky="nw", padx=(0, 24), pady=(0, 12))
        tk.Label(cell, text=label, font=(T.TXT, 11, "bold"), fg=T.ASPHALT, bg=T.PANEL).pack(anchor="w", pady=(0, 3))
        tk.Label(cell, text=wrapped(hint, (T.TXT, 9), wrap), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL,
                 justify="left").pack(anchor="w", pady=(3, 0))
        return cell

    def _entry(self, parent: tk.Misc, row: int, col: int, f: Field, span: int = 1, width: int = 18,
               wrap: int = WRAP) -> None:
        key, label, hint = f
        cell = self._cell(parent, row, col, t(label), t(hint), span=span, wrap=wrap)
        self.vars[key] = var = tk.StringVar(value=str(self._shown[key]))
        self.labels[key] = t(label)
        ttk.Entry(cell, textvariable=var, width=width, font=(T.NUM, 11)).pack(anchor="w",
                                                                          before=cell.winfo_children()[1])

    def _same_port(self) -> None:
        """Same as 0x04: the field shows the 0x04 port, and 0 (= the same port) is what gets saved."""
        if self.same.get():
            self.vars["status_port"].set(self.vars["nav_port"].get())
            self.status_entry.state(["disabled"])
        else:
            self.status_entry.state(["!disabled"])

    def toggle_advanced(self) -> None:
        self._show_advanced(not self._advanced)

    def _show_advanced(self, show: bool) -> None:
        self._advanced = show
        self.adv_btn.configure(text=("▾ " if show else "▸ ") + t("set.sec_advanced"))
        if show:
            self.adv.grid()
        else:
            self.adv.grid_remove()

    def _pick_dir(self) -> None:
        start = self.vars["record_dir"].get().strip() or str(osutil.executable_dir())
        d = filedialog.askdirectory(parent=self, title=t("set.choose_folder"), initialdir=start)
        if d:
            self.vars["record_dir"].set(d)

    def save(self) -> None:
        values: Dict[str, Any] = {}
        for key, var in self.vars.items():
            if key == "status_port" and self.same.get():
                values[key] = 0
                continue
            try:
                values[key] = config.parse_field(key, var.get())
            except (ValueError, TypeError) as e:
                if key in ADVANCED and not self._advanced:
                    self._show_advanced(True)
                self.err.configure(text=t("set.field_error", label=self.labels[key], error=e))
                return
        language = self.choices[max(self.language.current(), 0)][0]
        new = self.current.replace(record_csv=self.csv.get(), language=language, **values)
        try:
            config.save(new)
        except OSError as e:
            self.err.configure(text=t("set.cannot_save", error=os_error(e)))
            return
        self.destroy()
        self.on_save(new)
