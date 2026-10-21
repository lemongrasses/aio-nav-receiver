"""Settings dialog, grouped by what the operator is setting up. Every field is validated by
config.parse_field before anything is saved; the first problem is shown next to the buttons."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable, Dict

from .. import config, osutil
from ..config import Settings
from . import theme as T

SECTIONS = (
    ("接收", (("host", "綁定位址", "0.0.0.0 = 所有網卡"),
              ("nav_port", "0x04 埠", "與 aio_nav.yaml 的 output_udp 埠號一致"),
              ("status_port", "0x05 埠", "0 = 與 0x04 同埠"),
              ("status_id", "0x05 message ID", "對應 status_udp.message_id"),
              ("allowed_from", "只接受來源 IP", "空白 = 不限；填裝置 IP"))),
    ("判斷規則", (("status_timeout", "狀態逾時 (s)", "多久沒收到 0x05 就阻擋"),
                  ("ready_stable", "READY 穩定時間 (s)", "READY 要持續多久才可用"),
                  ("nav_max_age", "導航最大年齡 (s)", "0x04 超過多久就阻擋"))),
    ("記錄", (("record_dir", "記錄資料夾", "空白 = 程式旁的 logs"),)),
)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, current: Settings, on_save: Callable[[Settings], None]) -> None:
        super().__init__(parent)
        self.current, self.on_save = current, on_save
        self.title("設定")
        self.configure(bg=T.PANEL, padx=24, pady=18)
        self.resizable(False, False)
        self.transient(parent)  # type: ignore[call-overload]
        shown = config.to_dict(current)
        self.vars: Dict[str, tk.StringVar] = {}
        self.labels: Dict[str, str] = {}
        row = 0
        for title, fields in SECTIONS:
            tk.Label(self, text=title, font=(T.TXT, 12, "bold"), fg=T.ASPHALT, bg=T.PANEL).grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(0 if row == 0 else 14, 4))
            row += 1
            for key, label, hint in fields:
                tk.Label(self, text=label, font=(T.TXT, 10), fg=T.ASPHALT, bg=T.PANEL).grid(
                    row=row, column=0, sticky="w", pady=3, padx=(12, 0))
                var = tk.StringVar(value=str(shown[key]))
                ttk.Entry(self, textvariable=var, width=30 if key == "record_dir" else 18).grid(
                    row=row, column=1, padx=10, sticky="w")
                tk.Label(self, text=hint, font=(T.TXT, 9), fg=T.MUTED, bg=T.PANEL).grid(row=row, column=2, sticky="w")
                if key == "record_dir":
                    ttk.Button(self, text="選擇…", command=self._pick_dir).grid(row=row, column=3, padx=(8, 0))
                self.vars[key], self.labels[key] = var, label
                row += 1
        self.csv = tk.BooleanVar(value=current.record_csv)
        ttk.Checkbutton(self, text="記錄時同時寫入 _nav.csv（之後也可用 export 指令由 .bin 產生）",
                        variable=self.csv, style="Panel.TCheckbutton").grid(
            row=row, column=0, columnspan=4, sticky="w", pady=(6, 0), padx=(12, 0))
        row += 1
        bottom = tk.Frame(self, bg=T.PANEL)
        bottom.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(18, 0))
        self.err = tk.Label(bottom, text="", font=(T.TXT, 10), fg=T.STOP, bg=T.PANEL, justify="left")
        self.err.pack(side="left")
        ttk.Button(bottom, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="儲存並重新監聽", command=self.save).pack(side="right", padx=8)
        self.bind("<Return>", lambda _e: self.save())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _pick_dir(self) -> None:
        start = self.vars["record_dir"].get().strip() or str(osutil.executable_dir())
        d = filedialog.askdirectory(parent=self, title="選擇記錄資料夾", initialdir=start)
        if d:
            self.vars["record_dir"].set(d)

    def save(self) -> None:
        values: Dict[str, Any] = {}
        for key, var in self.vars.items():
            try:
                values[key] = config.parse_field(key, var.get())
            except (ValueError, TypeError) as e:
                self.err.configure(text=f"{self.labels[key]}：{e}")
                return
        new = self.current.replace(record_csv=self.csv.get(), **values)
        try:
            config.save(new)
        except OSError as e:
            self.err.configure(text=f"無法儲存設定：{e.strerror or e}")
            return
        self.destroy()
        self.on_save(new)
