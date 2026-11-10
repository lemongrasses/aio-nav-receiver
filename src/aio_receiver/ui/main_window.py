"""Main window: composes the parts and renders the engine's latest snapshot every 100 ms.

Layout C: the signal mast, the glance zone (verdict, what to do, the alignment route, what blocks)
and the engineering zone (actions, navigation 0x04, status 0x05 and track, source and counts).

Fail safe: an engine error, a bind error, a snapshot older than STALE_AFTER or an exception while
rendering all show 不可用. The next frame is always scheduled, whatever happened in this one.

Keys: Ctrl+R record, Ctrl+O open a recording, F11 full screen, Esc leave full screen.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import List, Optional

from .. import APP_NAME, __version__, config, i18n, osutil
from ..config import Settings
from ..engine import Engine, Snapshot
from ..i18n import os_error, t
from . import presentation as V
from . import theme as T
from .dialogs import Notice
from .panels import GAP, Footer, GuidanceStrip, NavPanel, ReplayBar, ScrollZone, StatusPanel, TrackPanel, VerdictBand
from .settings_dialog import SettingsDialog

log = logging.getLogger(__name__)
FRAME_MS = 100
STALE_AFTER = 0.5               # seconds without a fresh snapshot = the engine is not running
# Settings that change what the engine does; anything else (language, display, folder) needs no restart.
ENGINE_FIELDS = ("host", "nav_port", "status_port", "status_id", "allowed_from", "status_timeout",
                 "ready_stable", "nav_max_age", "record_csv")
IP_REFRESH = 5.0                # seconds between looking up this computer's addresses


class MainWindow:
    def __init__(self, root: tk.Tk, engine: Engine, settings: Settings) -> None:
        self.root, self.engine, self.settings = root, engine, settings
        self.show_track = tk.BooleanVar(value=settings.show_track)
        self.alert = tk.BooleanVar(value=settings.alert_sound)
        self._closing = False
        self._was_usable = False
        self._title = ""
        self._ips: List[str] = []
        self._ips_at = float("-inf")
        self._build()
        self.toggle_track()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-r>", lambda _e: self.toggle_record())
        root.bind("<Control-o>", lambda _e: self.open_replay())
        root.bind("<F11>", lambda _e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
        root.bind("<Escape>", lambda _e: root.attributes("-fullscreen", False))

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        r = self.root
        r.configure(bg=T.KERB)
        r.geometry(T.fit_to_screen(r))     # first: it sets the zoom the drawn parts use
        T.init_styles(r)
        r.minsize(T.px(1100), T.px(720))
        self.replay_bar = ReplayBar(r, self.change_speed, self.start_live)
        self.main = main = tk.Frame(r, bg=T.KERB)
        main.pack(fill="both", expand=True)
        main.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=5, uniform="z")      # glance zone
        main.columnconfigure(2, weight=7, uniform="z")      # engineering zone
        glance = tk.Frame(main, bg=T.PANEL, padx=32, pady=24)
        glance.grid(row=0, column=1, sticky="nsew")
        zone = ScrollZone(main)
        zone.outer.grid(row=0, column=2, sticky="nsew")
        eng = zone.inner
        self.band = VerdictBand(main, glance)
        self.guidance = GuidanceStrip(glance, self.copy_firewall)
        self.footer = Footer(eng, {"record": self.toggle_record, "replay": self.open_replay,
                                   "settings": self.open_settings, "track": self.toggle_track,
                                   "alert": self.toggle_alert}, self.show_track, self.alert)
        self.nav = NavPanel(eng)
        self.body = body = tk.Frame(eng, bg=T.KERB)
        body.pack(fill="both", expand=True, pady=(GAP, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=7, uniform="b")
        self.status = StatusPanel(body)
        self.track = TrackPanel(body, self.engine.clear_track)

    # ------------------------------------------------------------------- frame
    def start(self) -> None:
        self.root.after(FRAME_MS, self._frame)

    def _frame(self) -> None:
        try:
            self.render(self.engine.snapshot)
        except Exception as e:      # never leave a stale screen up
            log.exception("render failed")
            self.band.show(V.Band("stop", t("word.blocked"), t("fail.render", error=f"{type(e).__name__}: {e}")),
                           "", "")
        finally:
            if not self._closing:
                self.root.after(FRAME_MS, self._frame)

    def render(self, snap: Optional[Snapshot]) -> None:
        if snap is None:
            self.band.show(V.Band("idle", t("word.blocked"), t("fail.not_started")), "", "")
            return
        failure = snap.failure
        if failure is None and time.perf_counter() - snap.built > STALE_AFTER:
            failure = t("fail.not_responding")
        b = V.band(snap, failure)
        usable = b.kind == "go"
        if self._was_usable and not usable:                 # the output just stopped being usable
            self.band.flash()
            if self.alert.get():
                self.root.bell()
        self._was_usable = usable
        since = t("band.since", age=V.fmt_age(snap.now - snap.verdict_since)) if snap.verdict_since > 0 else ""
        self.band.show(b, since, V.fmt_dur(snap.usable_total))
        self._set_title(b, snap)

        replay = snap.source_kind == "replay"
        if replay != bool(self.replay_bar.frame.winfo_ismapped()):
            if replay:
                self.replay_bar.frame.pack(fill="x", before=self.main)
            else:
                self.replay_bar.frame.pack_forget()
        self.replay_bar.update(snap)
        self.guidance.update(snap, self.settings.nav_port, osutil.firewall_hint(self.settings.ports),
                             self._local_ips(snap))
        self.nav.update(snap)
        self.status.update(snap)
        if self.show_track.get():
            self.track.update(snap)
        self.footer.update(snap)

    def _local_ips(self, snap: Snapshot) -> List[str]:
        if snap.nothing_received and time.monotonic() - self._ips_at > IP_REFRESH:
            self._ips, self._ips_at = osutil.local_ipv4(), time.monotonic()
        return self._ips

    def _set_title(self, b: V.Band, snap: Snapshot) -> None:
        """The verdict in the title, so the taskbar shows it while the window is in the background."""
        prefix = t("win.replay_prefix") if snap.source_kind == "replay" else ""
        title = prefix + t("win.title", word=b.word, version=__version__)
        if title != self._title:
            self._title = title
            self.root.title(title)

    # ----------------------------------------------------------------- actions
    def start_live(self) -> None:
        self.engine.start_live(self.settings)

    def start_replay(self, path: Path, speed: Optional[float] = None) -> None:
        if speed is not None:
            self.replay_bar.speed.set(f"{speed:g}×")
        try:
            self.engine.start_replay(path, self.settings, self.replay_bar.speed_value)
        except (OSError, ValueError) as e:
            # The .bin explanation fits a file that is not a recording, not an empty or newer one.
            only_bin = path.suffix.lower() != ".bin" or (isinstance(e, i18n.UserError) and e.msg.key == "rec.not_aio")
            text = os_error(e) if isinstance(e, OSError) else e
            foot = " ".join(([t("dlg.only_bin")] if only_bin else []) + [t("dlg.monitor_continues")])
            Notice(self.root, "error", t("dlg.cannot_replay"), str(text), [str(path)], foot, bold_lead=True)

    def copy_firewall(self) -> None:
        hint = osutil.firewall_hint(self.settings.ports)
        if hint.command:
            self.root.clipboard_clear()
            self.root.clipboard_append(hint.command)
            self.guidance.copied.configure(text=osutil.firewall_copied_text())

    def toggle_record(self) -> None:
        snap = self.engine.snapshot
        if snap is None or snap.source_kind == "replay":
            return
        if snap.recording:
            self.engine.stop_recording()
        else:
            self.engine.start_recording(osutil.record_dir(self.settings.record_dir))

    def open_replay(self) -> None:
        folder = osutil.record_dir(self.settings.record_dir)
        path = filedialog.askopenfilename(
            parent=self.root, title=t("dlg.choose_recording"),
            initialdir=str(folder if folder.is_dir() else osutil.executable_dir()),
            filetypes=[(t("dlg.recordings"), "*.bin"), (t("dlg.all_files"), "*.*")])
        if path:
            self.start_replay(Path(path))

    def change_speed(self) -> None:
        self.engine.set_speed(self.replay_bar.speed_value)

    def toggle_track(self) -> None:
        if self.show_track.get():
            self.body.columnconfigure(1, weight=5, uniform="b")
            self.track.frame.grid()
        else:
            self.track.frame.grid_remove()
            self.body.columnconfigure(1, weight=0, uniform="")
        self._remember(show_track=self.show_track.get())

    def toggle_alert(self) -> None:
        self._remember(alert_sound=self.alert.get())

    def _remember(self, **changes: bool) -> None:
        new = self.settings.replace(**changes)
        if new != self.settings:
            self.settings = new
            try:
                config.save(new)
            except OSError as e:
                log.warning("settings not saved: %s", e)

    def open_settings(self) -> None:
        SettingsDialog(self.root, self.settings, self.apply_settings)

    def apply_settings(self, new: Settings) -> None:
        old, self.settings = self.settings, new
        log.info("settings changed: %s", new)
        if new.language != old.language:
            self.rebuild()
        if any(getattr(new, f) != getattr(old, f) for f in ENGINE_FIELDS):
            self.start_live()

    def rebuild(self) -> None:
        """Rebuild every widget in the current language; the engine and its data keep running."""
        i18n.set_language(self.settings.language)
        T.init_fonts(self.root, i18n.language())
        for child in self.root.winfo_children():
            child.destroy()
        self._title = ""
        self._build()
        self.toggle_track()
        snap = self.engine.snapshot
        if snap is not None and snap.replay is not None:
            self.replay_bar.speed.set(f"{snap.replay.speed:g}×")

    def warn_settings(self, problems: List[str]) -> None:
        """Settings that could not be used: shown once the window is up, with where the file is."""
        foot = t("dlg.settings_foot", path=config.CONFIG_PATH)
        self.root.after(300, lambda: Notice(self.root, "warn", t("dlg.settings_problem"), t("dlg.settings_ignored"),
                                            problems, foot))

    def close(self) -> None:
        self._closing = True
        self.engine.stop()
        self.root.destroy()


def run(settings: Settings, problems: List[str], replay: Optional[Path] = None, speed: float = 1.0) -> None:
    osutil.enable_dpi_awareness()
    root = tk.Tk(className=APP_NAME)
    T.init_fonts(root, i18n.language())
    engine = Engine()
    win = MainWindow(root, engine, settings)
    if problems:
        win.warn_settings(problems)
    if replay is not None:
        win.start_replay(replay, speed)
    if engine.snapshot is None:
        win.start_live()
    win.start()
    root.mainloop()
