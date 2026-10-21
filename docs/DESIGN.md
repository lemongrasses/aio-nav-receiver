# AIO NAV Receiver: design

## 1. What it is for

A laptop beside the vehicle receives two UDP streams from the AIO NAV Jetson:

| Stream | Rate | Size | Content |
|---|---|---|---|
| 0x04 navigation | 100 Hz | 156 B | position, velocity, attitude, σ, flags |
| 0x05 status | 2 Hz | 42 B | state, operator action, inhibit / health bits, session, sequence |

The app answers one question at every instant: **may the 0x04 output be used right now?** It answers
with the same rules as web_monitor `nav/vehicle_gate.py`, and it shows the operator instruction from
0x05. It also records sessions and replays them.

### Requirements

| | Requirement |
|---|---|
| F1 | Show 可用 / 阻擋 and the first failing rule, plus the operator instruction from 0x05 |
| F2 | Show the 0x04 and 0x05 contents, packet counters, rate and the trajectory |
| F3 | Record to `.bin` (raw packets), `_nav.csv` and `_events.log`; replay `.bin` at 1–10× |
| N1 | **Fail safe.** Any missing input, bad packet, stalled or crashed engine thread, or full disk shows 阻擋, never a stale 可用. A frozen window thread is the one exception (§5) |
| N2 | **Exact verdicts.** Transition times and 累計可用 do not depend on screen refresh, window dragging, slow storage or replay speed |
| N3 | Windows, Linux and macOS laptops; one portable file each; no Python on the target |
| N4 | Bounded memory over an 8-hour session; recordings readable forever, including old ones |
| N5 | The gate is testable without a network, a screen or a clock |

**Load.** About 16 KB/s, roughly 100 datagrams/s. A single Python thread handles this at under 1 % CPU,
so the design spends nothing on throughput and everything on correctness and isolation.

## 2. Components

```
                 ┌──────────── engine thread ────────────┐          ┌──── Tk main thread ────┐
 UDP :9000 ──►   │ Source ──► Monitor                    │ publish  │ MainWindow (10 Hz)     │
 .bin file ──►   │  live /     Gate (pure rules),        ├────────► │  reads latest Snapshot │
                 │  replay     deadlines, totals, track  │ Snapshot │  watchdog: stale = 阻擋 │
                 └───────────────────┬───────────────────┘ (frozen) │  commands ──► queue    │
                                     │ put_nowait (bounded)         └────────────────────────┘
                          ┌──────────▼──────────┐
                          │ recorder thread     │  .bin / _nav.csv / _events.log
                          └─────────────────────┘
```

| Package | Contents | May import |
|---|---|---|
| `core/` | `protocol` (frames, NamedTuple packets), `gate` (rules, `Verdict`, deadlines), `monitor` (time-ordered evaluation, totals, rates, track), `track` (geometry) | standard library only; no I/O, threads or clock |
| `io/` | `recording` (`.bin` v1/v2 reader and writer, CSV, events), `sources` (UDP and replay sources) | `core` |
| `engine.py` | the worker thread: source → monitor → recorder; publishes `Snapshot`; takes commands | `core`, `io` |
| `analysis.py` | headless replay as fast as possible (`check` command, regression tests) | `core`, `io` |
| `i18n.py` | every user-visible string in 繁體中文 and English; `Msg` (a key and its arguments) carries text across threads and is rendered in the current language only when shown | — |
| `config.py`, `osutil.py` | typed settings with validation; per-OS paths, firewall hints, console | — |
| `ui/` | tkinter views; the only code that imports tkinter. `ui/presentation.py` decides what the screen says (band colour and reason, alignment route, stream lights) as pure functions of a snapshot, so it is unit-tested | everything above |

## 3. The time model (why verdicts are exact)

The verdict changes at only two kinds of instant:

1. **Packet arrival.** A packet can change the state, session, flags or time.
2. **Deadline.** With no packet at all, the verdict still changes when a limit runs out:
   `status_at + 3 s` (0x05 timeout), `ready_since + 2 s` (READY stable) and `nav_at + 0.5 s` (0x04 too old).

`Gate.next_deadline(t)` returns the earliest of these after `t`. `Monitor.advance(t)` evaluates the gate
just after each deadline up to `t`, then at `t`. `Monitor.feed` advances to the packet time first, then
feeds it. Every transition therefore has its exact time, and 累計可用 is the exact integral of the
可用 intervals.

The monitor never reads a clock. The caller passes the time:

* Live: the receive time (`time.perf_counter`, whose resolution is about 100 ns; `time.monotonic`
  is 15.6 ms on Windows).
* Replay: the time stored in the recording.

So a live run, a 10× replay and the headless `check` command all give **identical** transitions for the
same packets. The tests assert this.

One difference is inherent: a replay starts with no history. If a recording began in the middle of
a READY session, the replay sees its first READY at the start of the file and shows 阻擋 (READY
尚未穩定) for the first ~2 s. The live run was already 可用 at that moment.

A source reports a *horizon* with each batch: the time up to which it has delivered every packet. The
engine advances only to the horizon, so a replay never evaluates past a packet it hasn't fed yet.

## 4. Data flow and threads

* **Engine thread.** It owns the sockets or the replay file and the monitor. Its loop is: wait on
  `select` (live) or sleep (replay) until the next packet or deadline, capped at 50 ms; stamp and
  feed the packets; advance; queue them for the recorder; publish a new frozen `Snapshot` at most
  every 50 ms. It never touches a file, so slow storage cannot delay a receive time stamp.
* **Recorder thread** (only while recording). It drains a bounded queue of 30,000 items, about
  5 minutes, into the three files, and flushes every second. A full queue or a write error stops the
  recording and sets an error that the engine publishes.
* **Tk thread.** Every 100 ms it reads the latest snapshot reference (an atomic assignment) and
  renders it. It never touches sockets, files or the monitor. Commands such as start recording,
  replay speed and stop go through a `queue.Queue` that the engine drains on each loop.
* **Rendering is a pure function of the snapshot.** Ages are computed from `snapshot.now`, so a replay
  shows the ages the original run had.

## 5. Failure modes

| Failure | Effect | Handling |
|---|---|---|
| No 0x05, or 0x05 stops | Blocked after 3 s | Gate rule 1 (deadline-driven, exact) |
| 0x04 stops | Blocked after 0.5 s | Gate rule 3 |
| Bad checksum, wrong version, new session | Authorisation cleared | Gate; counted as 無效 |
| Second sender in one session (sequence back > 5) | Authorisation cleared | Gate; counted as 兩個發送者 |
| Port already in use | No data | Bind error shown in the red band; monitor keeps running on the ports that did bind |
| Exception in the engine thread | Engine stops | Logged; snapshot carries `engine_error`; band forced red |
| Engine hangs, or the snapshot is older than 0.5 s | Stale screen | UI watchdog forces 阻擋 "監看程式沒有回應" |
| Exception while rendering | One frame lost | Logged; the band is forced red; the next frame is always scheduled (`finally`) |
| USB pulled or disk full while recording | Recording stops | `OSError` caught on the recorder thread; recording closed; error shown; **monitoring continues** |
| Storage stalls (slow USB stick) | None for monitoring | Writes queue up on the recorder thread; packets keep their true receive times. If the queue fills (about 5 minutes behind), recording stops with "記錄裝置太慢" |
| Window thread frozen (dragging the window, a modal dialog, opening a long recording for replay) | Screen not updated | The watchdog runs on that thread and cannot fire, so the last frame stays up. The engine and the recording are unaffected, and the next frame is correct |
| Power loss while recording | Last ≤ 1 s lost | Files flushed every second; the reader drops a truncated last record |
| Corrupt settings file | Defaults used | Each bad field falls back to its default and the problem is logged |

## 6. Recording format

`.bin` **v2** (written from 1.0):

```
"AIONREC\0"  u16 version=2  u32 header_len  header (UTF-8 JSON)
record*:     f64 rx_time   u16 length   4s sender IPv4   u16 sender port   bytes[length]
```

The header holds the app version, the local start time, a `(monotonic, unix)` clock pair for
converting receive times to wall time, the listen address and the gate settings. The sender
address lets replay apply the 只接受來源 IP filter and show which device sent the data.

`.bin` **v1** (before 1.0) has no header: `f64 rx_time, u16 length, bytes`. The reader recognises it
by the missing magic, and it stays supported. Because v1 has no magic, the reader checks that it
really holds AIO frames with receive times that only go forward, and refuses other files.

The reader indexes a file through `mmap` into two compact arrays (times and offsets). An 8-hour
recording (about 3 M packets) uses roughly 50 MB, not 1 GB of Python objects.

`_nav.csv` has the same columns as before, plus `unix_time` at the end. Floats are written at their
true precision: `repr` for the f64 latitude and longitude, 9 significant digits for the f32 fields.
That makes the file about 30 % smaller than before (455 instead of 647 bytes per row; ~110 MB per 30 minutes before). `aio-receiver export
<file>.bin` rebuilds the CSV from a `.bin`, and the CSV can be turned off in the settings.

## 7. Trade-offs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Language | Python 3.9+ | Go, Rust, C# | Same language as web_monitor's reference gate, already verified against it; load is trivial; the cross-platform build runs in CI |
| UI toolkit | tkinter | PySide6 / Qt | In the standard library, 8 MB executable, enough for this screen. Qt would add 60–100 MB. Only `ui/` would change |
| Threads | engine + recorder + Tk | asyncio, process per role | Each thread owns its state; they talk only through one-way snapshots and queues. The recorder is separate so storage can never delay receiving |
| Snapshot | Frozen copy every 50 ms | Locks around shared state | No locks to forget; the UI cannot see half-updated state |
| Gate evaluation | Per packet and deadline | Per screen tick (before 1.0) | Exact transition times and totals; independent of UI stalls (N2) |
| Packets | `NamedTuple` | `dict` | Typed fields that mypy checks; tuple speed |
| Recording | Own binary format with header | pcap | Ten lines to read or write, carries the gate settings and clock pair; pcap tools are not needed by the users |
| Settings location | `~/.aio_receiver.json` | Next to the executable | Kept where it was (the user's choice); recordings default to next to the executable so a USB stick carries them |

### Known difference from `vehicle_gate.py`

The spec says that a 0x05 sequence going back by more than 5 means a second sender: the
authorisation is cleared. `VehicleGate` treats any step back as reordering. Both agree on every
other input. `tools/parity_vehicle_gate.py` checks this, with 0 mismatches on random streams and
on a 30-minute real recording.

## 8. Verification

| Level | What |
|---|---|
| Unit | Protocol golden vector, round-trips, malformed frames; every gate rule; deadlines; sequence rules; settings validation; `.bin` v1 and v2 |
| Characterisation | Two windows cut from a real 30-minute Jetson session (positions moved to 0°, 0°): boot, CHECKING, FAULT, alignment, READY, DEGRADED. The expected transitions were produced by the pre-1.0 gate and must be reproduced exactly |
| Determinism | Engine thread at 10× replay = headless replay, transition for transition |
| Slow storage | A write stalled for 0.8 s while recording live: no false 0x04 timeout, no gap in the recorded receive times |
| Integration | Real UDP on loopback through the engine thread |
| UI smoke | Main window built and fed snapshots for every state (headless display on CI Linux) |
| Static | ruff, mypy (strict on `core/`, `io/`, `engine`, `analysis`) |
| CI | Windows, Linux, macOS × Python 3.9 and 3.12; tagged builds publish all three executables |

## 9. What to revisit as it grows

* **Another language.** Add a column to every entry in `i18n.py`; `tests/test_i18n.py` fails until each
  message has it with the same fields.
* **Several vehicles at once.** The monitor is per sender; run one monitor per session ID and show a list.
* **Richer plots** (σ over time, rate history). Switch `ui/` to Qt with pyqtgraph; nothing else changes.
* **Signed macOS build.** It needs an Apple Developer ID. Until then, users open the app once with
  right-click → Open.
