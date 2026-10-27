"""Every user-visible string, in 繁體中文 and English. One language is shown at a time.

The core, io and engine never build sentences: they return codes, or a `Msg` (a key and its
arguments) that is rendered in the current language only when shown or written. Protocol
identifiers (READY, KEEP_STILL_REQUIRED) become readable words in each language; standard acronyms
(GNSS, IMU, RTK, DSO), units and packet ids (0x04) stay as they are in both.
"""

from __future__ import annotations

import errno
import locale
import os
import subprocess
import sys
from typing import Any, Dict, NamedTuple, Sequence, Tuple

LANGUAGES = ("zh-TW", "en")
LANGUAGE_NAMES = {"zh-TW": "繁體中文", "en": "English"}    # each in its own language
_current = 0                                                # index into LANGUAGES


def system_language() -> str:
    """zh-TW when the operating system's language is Chinese, otherwise en."""
    tag = ""
    try:
        if sys.platform == "win32":
            import ctypes
            tag = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        elif sys.platform == "darwin":
            tag = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                                 timeout=2).stdout.replace("(", "").strip().strip('",\n ')
        tag = tag or os.environ.get("LC_ALL") or os.environ.get("LANG") or (locale.getlocale()[0] or "")
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pass
    return "zh-TW" if tag.lower().startswith("zh") else "en"


def set_language(code: str) -> str:
    """Use `code` (zh-TW / en); "" = follow the operating system. Returns the language now in use."""
    global _current
    effective = code if code in LANGUAGES else system_language()
    _current = LANGUAGES.index(effective)
    return effective


def language() -> str:
    return LANGUAGES[_current]


def t(key: str, **kw: Any) -> str:
    text = _T[key][_current]
    return text.format(**kw) if kw else text


def pick(pair: Sequence[str]) -> str:
    return pair[_current]


class Msg(NamedTuple):
    """A message to show later, in whatever language is current then (crosses threads safely)."""

    key: str
    args: Tuple[Tuple[str, Any], ...] = ()

    def __str__(self) -> str:
        return t(self.key, **dict(self.args))


def msg(key: str, **kw: Any) -> Msg:
    return Msg(key, tuple(sorted(kw.items())))


class UserError(ValueError):
    """A ValueError whose text is a Msg: shown to the user in the current language."""

    def __init__(self, key: str, **kw: Any) -> None:
        self.msg = msg(key, **kw)
        super().__init__(key)

    def __str__(self) -> str:
        return str(self.msg)


def os_error(e: OSError) -> Msg:
    """A system error in the current language. The system's own text is in the system's language, so it
    is used only for rare errors that have no wording here."""
    win = getattr(e, "winerror", None)
    key = _OS_ERRORS.get(e.errno or 0) or _WIN_ERRORS.get(win or 0)
    if key:
        return msg(key)
    return msg("os.other", code=e.errno if e.errno is not None else win, text=e.strerror or str(e))


_OS_ERRORS = {errno.EADDRINUSE: "os.in_use", errno.EACCES: "os.denied", errno.EPERM: "os.denied",
              errno.EADDRNOTAVAIL: "os.no_address", errno.ENOSPC: "os.disk_full", errno.ENOENT: "os.not_found",
              errno.EROFS: "os.read_only", errno.EIO: "os.io", errno.ENODEV: "os.not_found"}
_WIN_ERRORS = {10048: "os.in_use", 10013: "os.denied", 10049: "os.no_address", 112: "os.disk_full",
               39: "os.disk_full", 21: "os.not_found", 3: "os.not_found", 2: "os.not_found", 5: "os.denied",
               19: "os.read_only", 1006: "os.not_found", 1117: "os.io"}


def joined(items: Sequence[str]) -> str:
    return pick(("、", ", ")).join(items)


# ---------------------------------------------------------------------- protocol vocabulary
_STATES = {
    "BOOTING": ("開機中", "Booting"), "CHECKING": ("檢查中", "Checking"),
    "NAV_STARTING": ("AIO NAV 啟動中", "Starting AIO NAV"), "KEEP_STILL": ("保持靜止", "Keep still"),
    "MOVE_STRAIGHT": ("直線行駛", "Drive straight"), "REFINING": ("精對準", "Refining"),
    "READY": ("就緒", "Ready"), "DEGRADED": ("降級", "Degraded"), "FAULT": ("故障", "Fault"),
    "MAINTENANCE": ("已停止", "Stopped"),
}
_ACTIONS = {
    "NONE": ("不需動作", "Nothing to do"),
    "HOLD_STILL": ("讓車輛完全靜止", "Keep the vehicle completely still"),
    "DRIVE_STRAIGHT": ("在安全、空曠的區域以穩定速度直線行駛", "Drive straight at a steady speed in a safe, open area"),
    "KEEP_DRIVING": ("在有 GNSS 的環境下繼續正常行駛", "Keep driving normally where GNSS is available"),
    "SAFE_STOP": ("停止使用導航，並依車輛安全程序處理",
                  "Stop using navigation and follow the vehicle's safety procedure"),
    "SERVICE_REQUIRED": ("需要維護", "Maintenance is needed"),
    "MAINTENANCE_HOLD": ("已停止，請在儀表板的總覽頁面按「恢復」或「啟動」",
                         "Stopped. Press Resume or Start on the dashboard's Overview page"),
}
_GNSS_QUALITY = (("未知", "Unknown"), ("無定位", "No fix"), ("單點定位", "Single point"),
                 ("RTK 浮動解", "RTK float"), ("RTK 固定解", "RTK fixed"))
_HEALTH = (("儀表板正常", "Dashboard OK"), ("設定有效", "Configuration valid"),
           ("IMU 資料正常", "IMU data OK"), ("GNSS 資料正常", "GNSS data OK"),
           ("GNSS 品質足夠", "GNSS quality sufficient"), ("AIO NAV 執行中", "Navigation process running"),
           ("導航輸出正常", "Navigation output OK"), ("粗對準完成", "Coarse alignment done"),
           ("初始航向完成", "Heading valid"), ("精對準完成", "Fine alignment done"), ("DSO 正常", "DSO OK"),
           ("到車端的路由正常", "Route to the vehicle OK"), ("RTK 修正資料正常", "RTK corrections OK"),
           ("儲存空間可寫入", "Storage writable"), ("車端已確認接收", "Vehicle acknowledged"),
           ("時間同步正常", "Time synchronised"), ("AIO NAV 沒有重複執行", "No duplicate process"),
           ("Wi-Fi 正常", "Wi-Fi OK"))
_INHIBIT = (("開機中", "Booting"), ("設定無效", "Configuration invalid"),
            ("IMU 資料缺少或延遲", "IMU data missing or stale"), ("GNSS 資料缺少或延遲", "GNSS data missing or stale"),
            ("GNSS 品質不足", "GNSS quality too low"), ("AIO NAV 未執行", "Navigation not running"),
            ("導航輸出延遲", "Navigation output stale"), ("需要保持靜止", "Must keep still"),
            ("需要直線行駛", "Must drive straight"), ("需要精對準", "Fine alignment needed"),
            ("DSO 尚未就緒", "DSO not ready"), ("沒有到車端的路由", "No route to the vehicle"),
            ("RTK 修正資料中斷", "RTK corrections lost"), ("儲存空間無法寫入", "Storage not writable"),
            ("操作人員已停止", "Stopped by an operator"), ("啟動逾時", "Startup timed out"),
            ("管理權衝突", "Ownership conflict"), ("內部錯誤", "Internal fault"))
_LAMPS = {"ALIGN": ("粗對準", "Coarse aligned"), "HEADING": ("初始航向", "Heading valid"),
          "FINE": ("精對準", "Fine aligned")}


def state_name(name: str) -> str:
    return pick(_STATES[name]) if name in _STATES else name


def action_text(name: str) -> str:
    return pick(_ACTIONS[name]) if name in _ACTIONS else name


def gnss_quality(code: int) -> str:
    return pick(_GNSS_QUALITY[code]) if 0 <= code < len(_GNSS_QUALITY) else f"#{code}"


def health_name(bit: int) -> str:
    return pick(_HEALTH[bit]) if 0 <= bit < len(_HEALTH) else f"#{bit}"


def inhibit_name(bit: int) -> str:
    return pick(_INHIBIT[bit]) if 0 <= bit < len(_INHIBIT) else f"#{bit}"


def lamp_name(flag: str) -> str:
    return pick(_LAMPS[flag])


# ------------------------------------------------------------------------------ messages
_T: Dict[str, Tuple[str, str]] = {
    "app.title": ("AIO NAV 接收監看", "AIO NAV Receiver"),

    # verdict
    "word.usable": ("可用", "Usable"),
    "word.blocked": ("不可用", "Blocked"),
    "reason.usable": ("可用", "Usable"),
    "reason.no_status": ("沒有最新的狀態封包 (0x05)", "No current status packet (0x05)"),
    "reason.not_ready": ("狀態不是就緒：{state}（{inhibit}）", "Status is not ready: {state} ({inhibit})"),
    "reason.ready_not_stable": ("就緒尚未穩定", "Ready, not yet stable"),
    "reason.nav_stale": ("導航資料太舊 (0x04)", "Navigation data too old (0x04)"),
    "reason.nav_time_not_forward": ("導航時間沒有往前", "Navigation time did not move forward"),
    "reason.nav_not_aligned": ("導航旗標未對準", "Navigation flags not aligned"),
    "reason.nav_not_finite": ("導航資料不是有限值", "Navigation data not finite"),
    "none": ("無", "None"),

    # band
    "band.usable": ("導航輸出可以使用", "The navigation output may be used"),
    "band.nothing": ("還沒收到任何封包", "No packets received yet"),
    "band.no_status": ("沒有狀態封包 0x05", "No status packets (0x05)"),
    "band.status_lost": ("狀態封包 0x05 中斷超過 {s} 秒", "Status packets (0x05) stopped for over {s} s"),
    "band.startup": ("系統啟動中", "Starting up"),
    "band.stage1": ("對準第 1 階段：保持靜止", "Alignment stage 1: keep still"),
    "band.stage2": ("對準第 2 階段：直線行駛", "Alignment stage 2: drive straight"),
    "band.stage3": ("對準第 3 階段：精對準", "Alignment stage 3: fine alignment"),
    "band.ready_inhibit": ("已就緒，但仍有不可用原因", "Ready, but a blocking condition remains"),
    "band.degraded": ("就緒後失去必要條件", "A required condition was lost after ready"),
    "band.fault": ("AIO NAV 故障", "AIO NAV fault"),
    "band.maintenance": ("AIO NAV 已停止", "AIO NAV stopped"),
    "band.state": ("狀態 {state}", "State {state}"),
    "band.settling": ("就緒確認中（需穩定 {s} 秒）", "Confirming ready (must hold for {s} s)"),
    "band.no_nav": ("沒有導航封包 0x04", "No navigation packets (0x04)"),
    "band.nav_lost": ("導航封包 0x04 中斷超過 {s} 秒", "Navigation packets (0x04) stopped for over {s} s"),
    "band.nav_backwards": ("導航時間沒有往前", "Navigation time did not move forward"),
    "band.not_aligned": ("導航旗標顯示未對準", "Navigation flags say not aligned"),
    "band.not_finite": ("導航資料含無效數值", "Navigation data has invalid values"),
    "band.since": ("已持續 {age}", "For {age}"),
    "band.total": ("累計可用", "Usable total"),
    "mast.stop": ("有問題", "Problem"),
    "mast.wait": ("等待", "Wait"),
    "mast.go": ("可用", "Usable"),
    "mast.dark": ("燈號未亮\n沒有資料", "Lights off:\nno data"),
    "fail.not_responding": ("監看程式沒有回應", "The monitor is not responding"),
    "fail.internal": ("監看程式內部錯誤：{error}", "Internal error: {error}"),
    "fail.render": ("畫面更新錯誤：{error}", "Screen update error: {error}"),
    "fail.not_started": ("監看程式尚未啟動", "The monitor has not started"),
    "fail.bind": ("無法監聽 {addr}：{error}", "Cannot listen on {addr}: {error}"),

    # system errors
    "os.in_use": ("這個連接埠已被其他程式使用", "the port is in use by another program"),
    "os.denied": ("沒有權限", "permission denied"),
    "os.no_address": ("這台電腦沒有這個位址", "this computer has no such address"),
    "os.disk_full": ("磁碟已滿", "the disk is full"),
    "os.not_found": ("找不到資料夾或儲存裝置", "the folder or storage device is gone"),
    "os.read_only": ("儲存裝置是唯讀的", "the storage device is read-only"),
    "os.io": ("儲存裝置讀寫錯誤", "the storage device failed to read or write"),
    "os.other": ("系統錯誤 {code}：{text}", "system error {code}: {text}"),

    # durations
    "age.s": ("{s:.1f} 秒", "{s:.1f} s"),
    "age.ms": ("{m} 分 {s:02d} 秒", "{m} min {s:02d} s"),
    "age.hm": ("{h} 小時 {m} 分", "{h} h {m} min"),

    # alignment route
    "station.start": ("啟動", "Start"),
    "station.still": ("靜止", "Still"),
    "station.straight": ("直行", "Straight"),
    "station.fine": ("精對準", "Fine"),
    "station.usable": ("可用", "Usable"),
    "station.confirming": ("確認中 {x:.1f} / {y:g} 秒", "Confirming {x:.1f} / {y:g} s"),
    "rail.no_status": ("沒有最新的狀態封包，無法判斷對準進度。",
                       "No current status packet, so alignment progress is unknown."),
    "rail.ready_inhibit": ("就緒，但仍有不可用原因", "Ready, but a blocking condition remains"),
    "rail.degraded": ("曾經就緒，之後失去條件", "Was ready, then lost a condition"),
    "rail.fault": ("AIO NAV、其輸出或管理權有問題", "Problem with AIO NAV, its output or its ownership"),
    "rail.stopped": ("操作人員已停止，或尚未啟動", "Stopped by the operator, or not started"),
    "rail.unknown": ("未知狀態 {state}", "Unknown state {state}"),

    # stream lights
    "link.none": ("沒有資料", "No data"),
    "link.never": ("從未收到", "Never received"),
    "link.lost": ("中斷 {age}", "Lost for {age}"),
    "link.nav": ("{rate:.0f} Hz   {ms:.0f} ms", "{rate:.0f} Hz   {ms:.0f} ms"),
    "link.status": ("{rate:.1f} Hz   {s:.1f} 秒前", "{rate:.1f} Hz   {s:.1f} s ago"),

    # guidance
    "setup.title": ("讓 AIO NAV 把資料送到這台電腦", "Send AIO NAV data to this computer"),
    "setup.step1": ("在裝置的維護頁面 → AIO NAV config 把 output_udp 設成 {here}，然後重新啟動 AIO NAV{others}",
                    "On the device, Maintenance → AIO NAV config: set output_udp to {here}, then restart AIO NAV"
                    "{others}"),
    "setup.others": ("\n（這台電腦的其他位址：{ips}）", "\n(this computer's other addresses: {ips})"),
    "setup.this_ip": ("這台電腦的 IP:{port}", "this computer's IP:{port}"),
    "setup.step2": ("在儀表板的設定檔寫入 status_udp.enabled: true，並把 destination 指向這台電腦（0x05）",
                    "In the dashboard config, set status_udp.enabled: true with the destination set to this "
                    "computer (0x05)"),
    "setup.copy": ("複製防火牆指令", "Copy firewall command"),
    "fw.windows": ("Windows 防火牆也要允許這個連接埠的輸入 UDP 連線。",
                   "Allow inbound UDP on this port in Windows Firewall."),
    "fw.macos": ("macOS 第一次啟動時請允許「接受傳入連線」與「區域網路」存取（系統設定 → 隱私權與安全性 → 區域網路）。",
                 "On first launch, allow incoming connections and Local Network access "
                 "(System Settings → Privacy & Security → Local Network)."),
    "fw.linux": ("若有啟用 ufw 防火牆，請允許這個連接埠的 UDP。", "If the ufw firewall is on, allow UDP on this port."),
    "fw.copied_windows": ("已複製。請在系統管理員 PowerShell 貼上執行。",
                          "Copied. Paste it into an administrator PowerShell."),
    "fw.copied_other": ("已複製。請在終端機貼上執行。", "Copied. Paste it into a terminal."),
    "guide.replay_empty": ("重播中，尚未讀到封包", "Replaying: no packets read yet"),
    "guide.wait_status": ("等待狀態封包 0x05", "Waiting for status packets (0x05)"),
    "guide.wait_status_replay": ("記錄的這段時間沒有有效的 0x05，無法判斷可否使用。",
                                 "The recording has no valid 0x05 here, so usability cannot be judged."),
    "guide.no_status": ("開啟儀表板的 0x05", "Turn on 0x05 in the dashboard"),
    "guide.no_status_sub": ("有 0x04，但從來沒有收到 0x05。請確認儀表板設定檔中的 status_udp.enabled: true，"
                            "且 destination 指向這台電腦。",
                            "0x04 is arriving but 0x05 never has. Check that the dashboard has "
                            "status_udp.enabled: true and that its destination is this computer."),
    "guide.status_lost": ("檢查儀表板與網路", "Check the dashboard and the network"),
    "guide.status_lost_sub": ("0x05 已中斷 {age}。之前已經收到 {n} 包，所以設定沒有問題。請確認儀表板還在執行，"
                              "以及這台電腦和裝置之間的網路沒有中斷。",
                              "0x05 stopped {age} ago. {n} packets arrived before that, so the settings are fine. "
                              "Check that the dashboard is still running and that the network between this "
                              "computer and the device is up."),
    "block.title": ("不可用原因", "Blocking conditions"),
    "block.unknown": ("沒有最新的 0x05，無法得知", "Unknown: no current 0x05"),
    "block.expected": ("對準流程的正常步驟，依序完成後會消失。",
                       "These are normal alignment steps. They clear one by one."),

    # panels
    "nav.title": ("導航 0x04", "Navigation 0x04"),
    "nav.aiding": ("輔助更新（距上次出現）", "Aiding updates (time since last seen)"),
    "nav.not_seen": ("{name} 未出現", "{name} not seen"),
    "nav.lat": ("緯度 (°)", "Latitude (°)"),
    "nav.lon": ("經度 (°)", "Longitude (°)"),
    "nav.height": ("高度 (m)", "Height (m)"),
    "nav.heading": ("航向 (°, 0–360)", "Heading (°, 0–360)"),
    "nav.speed": ("水平速率 (m/s)", "Ground speed (m/s)"),
    "nav.vu": ("垂直速度 (m/s，向上為正)", "Vertical speed (m/s, up +)"),
    "nav.att": ("滾轉 / 俯仰 (°)", "Roll / pitch (°)"),
    "nav.pos_std": ("位置 σ 北 / 東 / 下 (m)", "Position σ N / E / D (m)"),
    "nav.vel_std": ("速度 σ 北 / 東 / 下 (m/s)", "Velocity σ N / E / D (m/s)"),
    "nav.att_std": ("姿態 σ 滾轉 / 俯仰 / 航向 (°)", "Attitude σ roll / pitch / heading (°)"),
    "nav.time": ("GPS 週秒 (s)", "GPS time of week (s)"),
    "nav.age": ("資料延遲 (ms)", "Data age (ms)"),
    "status.title": ("狀態 0x05", "Status 0x05"),
    "status.state": ("狀態", "State"),
    "status.gnss": ("GNSS 品質", "GNSS quality"),
    "status.session": ("工作階段", "Session"),
    "status.sequence": ("序號", "Sequence"),
    "status.rate": ("導航頻率 (Hz)", "Navigation rate (Hz)"),
    "status.nav_age": ("0x04 延遲 (ms)", "0x04 age (ms)"),
    "status.health": ("成立條件（未成立在前）", "Conditions met (unmet first)"),
    "status.met": ("成立 {n} / {total}", "{n} / {total} met"),
    "status.out_of_date": ("（已過時）", " (out of date)"),
    "status.none_yet": ("還沒有 0x05", "No 0x05 yet"),
    "track.title": ("軌跡", "Track"),
    "track.meta": ("{n} 點   範圍 {span:.0f} m", "{n} points   span {span:.0f} m"),
    "track.empty": ("收到 0x04 後顯示軌跡", "The track appears once 0x04 arrives"),
    "track.clear": ("清除軌跡", "Clear track"),
    "track.usable": ("可用", "Usable"),
    "track.blocked": ("不可用", "Blocked"),

    # replay bar
    "replay.banner": ("重播記錄，不是即時資料", "Replaying a recording, not live data"),
    "replay.speed": ("速度", "Speed"),
    "replay.live": ("回到即時", "Back to live"),
    "replay.done": ("已播完", "finished"),

    # footer
    "foot.listening": ("監聽 {addr}", "Listening on {addr}"),
    "foot.replaying": ("重播 {file}", "Replaying {file}"),
    "foot.old_format": ("（舊格式記錄，沒有來源 IP）", " (old recording format, no sender IP)"),
    "foot.from": ("來源 {ips}", "From {ips}"),
    "foot.writing": ("寫入 {path}", "Writing {path}"),
    "foot.lost": ("遺失 {n}", "Lost {n}"),
    "foot.reordered": ("順序錯亂 {n}", "Out of order {n}"),
    "foot.bad": ("無效 {n}", "Invalid {n}"),
    "foot.conflicts": ("兩個發送者 {n}", "Two senders {n}"),
    "foot.foreign": ("其他來源 {n}", "Other senders {n}"),
    "foot.recording": ("記錄中 {t}", "Recording {t}"),
    "foot.start_rec": ("開始記錄", "Start recording"),
    "foot.stop_rec": ("停止記錄", "Stop recording"),
    "foot.replay": ("重播記錄…", "Replay…"),
    "foot.settings": ("設定", "Settings"),
    "foot.show_track": ("顯示軌跡", "Show track"),
    "foot.alert": ("中斷時提示音", "Sound on loss"),
    "foot.fullscreen": ("全螢幕 F11　離開 Esc", "Full screen F11, leave Esc"),

    # recording
    "rec.cannot_start": ("無法開始記錄：{error}（{folder}）", "Cannot start recording: {error} ({folder})"),
    "rec.stopped": ("記錄已停止：{error}", "Recording stopped: {error}"),
    "rec.error_help": ("監看沒有中斷。排除問題或在「設定」換一個記錄資料夾後，再按「開始記錄」。",
                       "Monitoring carries on. Fix the problem or choose another recording folder in Settings, "
                       "then press Start recording."),
    "rec.too_slow": ("儲存裝置太慢，已停止記錄", "Storage too slow; recording stopped"),
    "rec.event_start": ("開始記錄", "Recording started"),
    "rec.event_stop": ("停止記錄", "Recording stopped"),
    "rec.empty": ("檔案是空的", "The file is empty"),
    "rec.version": ("不支援的記錄檔版本 {version}", "Unsupported recording version {version}"),
    "rec.no_records": ("檔案裡沒有完整的封包記錄", "The file holds no complete packet record"),
    "rec.not_aio": ("不是 AIO 記錄檔（.bin）", "Not an AIO recording (.bin)"),

    # window and dialogs
    "win.title": ("{word}｜AIO NAV 接收監看 {version}", "{word} | AIO NAV Receiver {version}"),
    "win.replay_prefix": ("重播 ", "Replay "),
    "dlg.cannot_replay": ("無法重播", "Cannot replay"),
    "dlg.choose_recording": ("選擇要重播的記錄檔", "Choose a recording to replay"),
    "dlg.recordings": ("AIO 記錄檔", "AIO recordings"),
    "dlg.all_files": ("所有檔案", "All files"),
    "dlg.settings_problem": ("設定檔有問題", "Settings file problem"),
    "dlg.settings_ignored": ("下列設定無效，已改用預設值：", "These settings were invalid; the defaults are used:"),
    "dlg.settings_foot": ("接收已用預設值開始。要改用其他值，請到「設定」修改後儲存。設定檔位置：{path}",
                          "Receiving has started with the defaults. To use other values, change them in Settings "
                          "and save. Settings file: {path}"),
    "dlg.only_bin": ("重播只能開啟記錄時產生的 .bin 檔。同一次記錄的 _nav.csv 和 _events.log 無法重播。",
                     "Replay opens only the .bin file a recording makes. The _nav.csv and _events.log from the "
                     "same recording cannot be replayed."),
    "dlg.monitor_continues": ("目前的監看沒有中斷。", "Monitoring carries on as before."),
    "dlg.ok": ("確定", "OK"),

    # settings
    "set.title": ("設定", "Settings"),
    "set.sec_everyday": ("現場常用", "Everyday"),
    "set.everyday_sub": ("這些改了不會影響判斷結果。", "Changing these never changes the verdict."),
    "set.sec_advanced": ("進階：接收與判斷規則", "Advanced: receiving and rules"),
    "set.advanced_sub": ("要和裝置設定一致", "Must match the device's settings"),
    "set.rules_warning": ("判斷規則：實際使用時不可放寬。預設為 3.0、2.0、0.5 秒。",
                          "Rules: do not loosen them for real use. Defaults are 3.0, 2.0 and 0.5 s."),
    "set.restart_note": ("改了接收、判斷規則或 _nav.csv 選項，儲存後會重新開始監聽。",
                         "Saving a change to receiving, the rules or the _nav.csv option restarts listening."),
    "set.host": ("監聽位址", "Listen address"),
    "set.host_hint": ("0.0.0.0 表示所有網卡", "0.0.0.0 = all network adapters"),
    "set.nav_port": ("0x04 連接埠", "0x04 port"),
    "set.nav_port_hint": ("與 aio_nav.yaml 的 output_udp 埠號一致", "The port in output_udp of aio_nav.yaml"),
    "set.status_port": ("0x05 連接埠", "0x05 port"),
    "set.same_port": ("與 0x04 相同", "Same as 0x04"),
    "set.status_id": ("0x05 訊息 ID", "0x05 message ID"),
    "set.status_id_hint": ("對應 status_udp.message_id", "Matches status_udp.message_id"),
    "set.allowed_from": ("只接受來源 IP", "Accept only from IP"),
    "set.allowed_from_hint": ("空白表示不限。UDP 沒有驗證，任何人都能偽造就緒狀態；"
                              "填入裝置的 IP，其他來源只計數、不處理。",
                              "Empty = any. UDP has no authentication, so anyone can fake the ready status; "
                              "enter the device's IP so packets from other senders are only counted."),
    "set.status_timeout": ("狀態逾時 (s)", "Status timeout (s)"),
    "set.status_timeout_hint": ("多久沒收到 0x05 就判定為不可用", "Block when no 0x05 arrives for this long"),
    "set.ready_stable": ("就緒穩定時間 (s)", "Ready hold time (s)"),
    "set.ready_stable_hint": ("就緒要持續多久才可用", "How long ready must hold before usable"),
    "set.nav_max_age": ("導航最大延遲 (s)", "Navigation max age (s)"),
    "set.nav_max_age_hint": ("0x04 延遲超過此值就判定為不可用", "Block when 0x04 is older than this"),
    "set.record_dir": ("記錄資料夾", "Recording folder"),
    "set.record_dir_hint": ("空白表示寫到程式旁的 logs 資料夾", "Empty = logs next to the program"),
    "set.browse": ("選擇…", "Browse…"),
    "set.choose_folder": ("選擇記錄資料夾", "Choose the recording folder"),
    "set.csv": ("記錄時同時寫入 _nav.csv（之後也可用 export 指令由 .bin 產生）",
                "Also write _nav.csv while recording (it can be made later from the .bin with export)"),
    "set.language": ("語言", "Language"),
    "set.language_system": ("跟隨系統", "Follow system"),
    "set.language_hint": ("儲存後立即套用，接收不會中斷", "Applies as soon as you save. Receiving carries on."),
    "set.save": ("儲存", "Save"),
    "set.cancel": ("取消", "Cancel"),
    "set.cannot_save": ("無法儲存設定：{error}", "Cannot save settings: {error}"),
    "set.field_error": ("{label}：{error}", "{label}: {error}"),

    # validation
    "val.ipv4": ("{v} 不是 IPv4 位址", "{v} is not an IPv4 address"),
    "val.port": ("埠號要在 {lo}–65535", "The port must be {lo}–65535"),
    "val.msg_id": ("訊息 ID 要在 0x00–0xFF，且不能是 0x04", "The message ID must be 0x00–0xFF and not 0x04"),
    "val.seconds": ("秒數要大於 0 且不超過 60", "Seconds must be above 0 and at most 60"),
    "val.seconds0": ("秒數要在 0–60", "Seconds must be 0–60"),
    "val.number": ("{v} 不是數字", "{v} is not a number"),
    "val.bool": ("{v} 不是 true / false", "{v} is not true / false"),
    "val.language": ("不支援的語言 {v}", "Unsupported language {v}"),
    "val.not_object": ("不是 JSON 物件", "not a JSON object"),

    # command line
    "cli.summary": ("{name}：{n} 包，{d:.1f} 秒，累計可用 {u:.1f} 秒",
                    "{name}: {n} packets, {d:.1f} s, usable {u:.1f} s"),
    "cli.counts": ("0x04 {nav}  0x05 {status}  遺失 {lost}  順序錯亂 {reordered}  無效 {bad}  兩個發送者 {conflicts}  "
                   "其他來源 {foreign}",
                   "0x04 {nav}  0x05 {status}  lost {lost}  out of order {reordered}  invalid {bad}  "
                   "two senders {conflicts}  other senders {foreign}"),
    "cli.exported": ("{rows} 列 → {out}", "{rows} rows → {out}"),
}
