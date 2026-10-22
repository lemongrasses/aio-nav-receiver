# Changelog

## Unreleased

### Changed
- **不可用 instead of 阻擋.** The verdict reads 可用 / 不可用 (may the navigation output be used?),
  and the 0x05 blocking conditions are 不可用原因, on the screen, in the notification, the window
  title and the events log. English (Usable / Blocked) is unchanged.
- **The 0x05 words mean what the dashboard means**, checked against the shared glossary's protocol
  tables: BOOTING 開機中 (was 啟動中, the dashboard's word for AIO NAV starting), NAV_STARTING
  AIO NAV 啟動中, MAINTENANCE 已停止 / Stopped (was 維護 / Maintenance: it is an operator stop, not a
  service need), the HEADING lamp 初始航向, 到車端的路由 / Route to the vehicle (was 對外路由 /
  External route), 操作人員已停止 / Stopped by an operator (was 維護暫停 / Maintenance hold), 管理權.
  The stop instruction names both buttons the dashboard can show: 「恢復」或「啟動」 / Resume or Start.
  A DEGRADED state reads 就緒後失去必要條件 / A required condition was lost after ready (any required
  condition, not only alignment).
- **繁體中文 wording shared with web_monitor** (`docs/TERMINOLOGY.zh-TW.md`, the same file in both
  repositories), on the desktop, iPhone and Android alike: 滾轉 (roll, was 橫滾), RTK 浮動解 (was
  浮點解), 水平速率 (ground speed), GPS 週秒, 延遲 for a data age or stale data (was 年齡 / 過舊),
  連接埠 (port), 儀表板 (dashboard), 重新啟動; the operator instructions read as on the dashboard's
  pages. A test keeps the replaced words out.


## 1.2.0 — 2026-10-21

### Changed
- **One language at a time.** The screen, dialogs, command-line output and events log are all
  in either 繁體中文 or English; they no longer mix the two. Protocol codes become readable words in
  each language: READY → 就緒 / Ready, KEEP_STILL_REQUIRED → 需要保持靜止 / Must keep still, and the
  same for all 18 conditions and the GNSS quality. Standard acronyms (GNSS, IMU, RTK, DSO), units and
  packet ids (0x04, 0x05) stay as they are in both.
- Common system errors (port in use, permission denied, disk full, storage gone, read-only) are
  worded in the chosen language instead of showing the operating system's own text.
- Each events-log line ends with a fixed reason code such as [not_ready], so logs can be searched
  whatever language they were written in.
- **設定 / Settings → 顯示 / Display → 語言 / Language:** 跟隨系統 (follow system) / 繁體中文 / English.
  The new language applies at once. Saving restarts listening only when a receiving or rule
  setting changed.
- Long instructions wrap instead of running under the alignment route.


## 1.1.0 — 2026-10-21

The screen was redesigned around what the operator needs: the answer, what to do, and how far along
alignment is. The verdict rules are unchanged.

### Changed
- **Four band colours (road-sign signal colours), each with one meaning.**
  - Green: usable.
  - Yellow: blocked as expected (aligning, READY settling).
  - Red: blocked because something is wrong.
  - Grey: no data yet, or stopped.

  A normal alignment no longer looks like a fault.
- The band says why in plain words, such as 對準第 2 階段：直線行駛 or 狀態封包 0x05 中斷超過 3 秒. It
  also shows how long it has been in that state. The full technical reason stays in the events log.
- Panels have no outlines, and the map is drawn on graph paper at the scale bar's spacing.
- Values from a stream that is out of date turn grey. A lost 0x05 no longer leaves READY in green.
- Packet rates are measured from packet spacing, so they are right from the second packet.
- The settings dialog is grouped (接收 / 判斷規則 / 記錄); Enter saves and Esc cancels.
- The window size follows the screen, and text scales down to fit small or highly scaled laptop
  screens.

### Added
- **Alignment route**: 啟動 → ① 靜止 → ② 直行 → ③ 精對準 → 可用. It shows the current station, and the
  2 s READY count fills the last sign.
- Setup steps before the first packet, with this PC's IP address to enter in output_udp.
- Stream lights for 0x04 and 0x05: rate and age, or how long the stream has been gone.
- All 18 health conditions shown as met or not met.
- When usable ends, the band blinks three times and the PC beeps (switch: 中斷時提示音).
- Replay bar: says it is not live data, and holds the progress, speed and 回到即時 controls.
- The verdict in the window title.
- Keys: Ctrl+R, Ctrl+O, F11, Esc.
- A recording indicator with elapsed time.
- The 中斷時提示音 and 顯示軌跡 choices are remembered.


## 1.0.0 — 2026-10-21

The functionality is unchanged. The internals were rebuilt as an engineering project.

### Changed
- **Exact verdicts.** The gate is now evaluated at every packet and at every deadline (0x05
  timeout, READY stable, 0x04 age), not once per screen refresh. Transition times and 累計可用 no
  longer depend on screen refresh, window dragging or replay speed.
- **Fail safe.** These now show 阻擋 instead of leaving the last screen up:
  - an internal error;
  - a stalled engine (no snapshot for 0.5 s);
  - a rendering exception.

  While the window itself is frozen (dragging it, a dialog), the screen cannot update.
- **Recording.**
  - Files are written on their own thread. A slow USB stick can no longer delay receive time stamps
    or cause a false 阻擋.
  - A full disk, a pulled USB stick or storage falling far behind stops the recording with a
    message; monitoring carries on.
  - Files are flushed every second.
  - The footer shows the full path of the recording in progress.
- **.bin v2.** Adds a header (app version, wall-clock reference, settings) and the sender
  address of each packet. Older recordings (v1) still open.
- Replay applies the 只接受來源 IP filter when the recording has sender addresses.
- A replay starts with no history. A recording started while the output was already 可用 replays
  as 阻擋 (READY 尚未穩定) for its first ~2 s.
- `_nav.csv` is about 30 % smaller: values keep their true precision without extra digits, and a
  `unix_time` column was added. Writing it can be turned off.
- Settings are validated field by field. A bad value falls back to its default and is reported.
  The settings file is written atomically.
- Fonts are chosen from those installed, so Chinese text renders on Linux and macOS too.
- The firewall hint matches the operating system.
- The 0x05 panel uses two columns, so long states such as MOVE_STRAIGHT are no longer clipped.

### Added
- `check` command: replays a recording headless and prints every 可用 / 阻擋 change, with `--json`.
- `export` command: rebuilds `_nav.csv` from a `.bin`.
- The footer shows the sender IP.
- The recording folder can be set in 設定.
- A diagnostic application log.
- Tests:
  - two windows of a real Jetson session, checked against the verdicts of the pre-1.0 gate;
  - engine replay compared with the headless replay;
  - loopback UDP;
  - UI smoke tests.
- ruff and mypy checks.
- GitHub Actions: tests on Windows, Linux and macOS; tagged releases with all three executables.
- `docs/DESIGN.md`.
