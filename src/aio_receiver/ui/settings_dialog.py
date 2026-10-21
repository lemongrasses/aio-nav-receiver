"""Settings dialog, grouped by what the operator is setting up. Every field is validated by
config.parse_field before anything is saved; the first problem is shown next to the buttons."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable, Dict, List, Tuple

from .. import config, osutil
from ..config import Settings
from ..i18n import LANGUAGE_NAMES, LANGUAGES, os_error, t
from . import theme as T

# (section title key, ((setting, label key, hint key), ...))
SECTIONS = (
    ("set.sec_receive", (("host", "set.host", "set.host_hint"),
                         ("nav_port", "set.nav_port", "set.nav_port_hint"),
                         ("status_port", "set.status_port", "set.status_port_hint"),
                         ("status_id", "set.status_id", "set.status_id_hint"),
                         ("allowed_from", "set.allowed_from", "set.allowed_from_hint"))),
    ("set.sec_rules", (("status_timeout", "set.status_timeout", "set.status_timeout_hint"),
                       ("ready_stable", "set.ready_stable", "set.ready_stable_hint"),
                       ("nav_max_age", "set.nav_max_age", "set.nav_max_age_hint"))),
    ("set.sec_record", (("record_dir", "set.record_dir", "set.record_dir_hint"),)),
)


def language_choices() -> List[Tuple[str, str]]:
    """(setting value, what the list shows). Language names are written in their own language."""
    return [("", t("set.language_system"))] + [(code, LANGUAGE_NAMES[code]) for code in LANGUAGES]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, current: Settings, on_save: Callable[[Settings], None]) -> None:
        super().__init__(parent)
        self.current, self.on_save = current, on_save
        self.title(t("set.title"))
        self.configure(bg=T.PANEL, padx=24, pady=18)
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        shown = config.to_dict(current)
        self.vars: Dict[str, tk.StringVar] = {}
        self.labels: Dict[str, str] = {}
        row = 0
        for title, fields in SECTIONS:
            row = self._section(title, row)
            for key, label, hint in fields:
                tk.Label(self, text=t(label), font=(T.TXT, 10), fg=T.ASPHALT, bg=T.PANEL).grid(
                    row=row, column=0, sticky="w", pady=3, padx=(12, 0))
                var = tk.StringVar(value=str(shown[key]))
                ttk.Entry(self, textvariable=var, width=30 if key == "record_dir" else 18).grid(
                    row=row, column=1, padx=10, sticky="w")
                tk.Label(self, text=t(hint), font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).grid(row=row, column=2,
                                                                                         sticky="w")
                if key == "record_dir":
                    ttk.Button(self, text=t("set.browse"), command=self._pick_dir).grid(row=row, column=3,
                                                                                      padx=(8, 0))
                self.vars[key], self.labels[key] = var, t(label)
                row += 1
        self.csv = tk.BooleanVar(value=current.record_csv)
        ttk.Checkbutton(self, text=t("set.csv"), variable=self.csv, style="Panel.TCheckbutton").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(6, 0), padx=(12, 0))
        row = self._section("set.sec_display", row + 1)
        tk.Label(self, text=t("set.language"), font=(T.TXT, 10), fg=T.ASPHALT, bg=T.PANEL).grid(
            row=row, column=0, sticky="w", pady=3, padx=(12, 0))
        self.choices = language_choices()
        self.language = ttk.Combobox(self, values=[shown_name for _, shown_name in self.choices], width=16,
                                     state="readonly")
        self.language.current(next((i for i, (code, _) in enumerate(self.choices) if code == current.language), 0))
        self.language.grid(row=row, column=1, padx=10, sticky="w")
        row += 1
        bottom = tk.Frame(self, bg=T.PANEL)
        bottom.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(18, 0))
        self.err = tk.Label(bottom, text="", font=(T.TXT, 10), fg=T.STOP, bg=T.PANEL, justify="left")
        self.err.pack(side="left")
        ttk.Button(bottom, text=t("set.cancel"), command=self.destroy).pack(side="right")
        ttk.Button(bottom, text=t("set.save"), command=self.save).pack(side="right", padx=8)
        self.bind("<Return>", lambda _e: self.save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _section(self, title: str, row: int) -> int:
        tk.Label(self, text=t(title), font=(T.TXT, 12, "bold"), fg=T.ASPHALT, bg=T.PANEL).grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(0 if row == 0 else 14, 4))
        return row + 1

    def _pick_dir(self) -> None:
        start = self.vars["record_dir"].get().strip() or str(osutil.executable_dir())
        d = filedialog.askdirectory(parent=self, title=t("set.choose_folder"), initialdir=start)
        if d:
            self.vars["record_dir"].set(d)

    def save(self) -> None:
        values: Dict[str, Any] = {}
        for key, var in self.vars.items():
            try:
                values[key] = config.parse_field(key, var.get())
            except (ValueError, TypeError) as e:
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
