# AIO NAV UDP receiver: pre-check

Source: [lemongrasses/web_monitor](https://github.com/lemongrasses/web_monitor). Authoritative spec is
`docs/OPERATION.md` §6. Reference code: `aio_system_dashboard/nav/decoder.py` (0x04),
`nav/status_packet.py` (0x05), `nav/vehicle_gate.py` (receiver rules), `tools/fake_nav_sender.py` (test sender).

## 1. Network path

```
Jetson (192.168.116.1, eno1)  aio_nav_node ──UDP──▶ 127.0.0.1:9000        (dashboard, on the device)
                                            └─UDP──▶ output_udp host:port  (ONE external unicast IPv4 = our Windows PC)
                              dashboard ───UDP 0x05 (optional)──▶ same output_udp host:port
```

* Each destination gets its own copy, so our receiver does not compete with the dashboard.
* `config/dashboard.yaml` says the external PC on the sensor LAN is fixed at **192.168.116.154**.
  Confirm the Windows PC really has that address on the sensor-LAN NIC.
* On the Jetson, set the destination in `aio_nav.yaml` (Live) **and** `aio_nav_bag.yaml` (bag replay) if both are used,
  then restart AIO NAV (Maintenance → AIO NAV config → *Save and restart*):
  ```yaml
  output_udp: "192.168.116.154:9000"
  ```
* Only one external destination. To feed several apps, receive on one PC and forward.

## 2. Windows-side requirements

| Item | What to do |
|---|---|
| Bind | `0.0.0.0:9000` (or the sensor-LAN NIC IP). **Not** `127.0.0.1`: that only sees local traffic. |
| Firewall | Inbound UDP is blocked by default, especially when the network is "Public". The user must add a rule (admin): `New-NetFirewallRule -DisplayName "AIO NAV UDP" -Direction Inbound -Protocol UDP -LocalPort 9000 -Action Allow`. Also check the network profile of the sensor-LAN adapter. |
| Port sharing | Use `SO_EXCLUSIVEADDRUSE`, never `SO_REUSEADDR` (on Windows it lets another process steal the port / split the stream). |
| Receive-only socket | If the program ever sends on the same socket, Windows raises `WSAECONNRESET` (10054) on `recvfrom` after an ICMP port-unreachable. Keep the socket receive-only, or disable it via `SIO_UDP_CONNRESET`. |
| Buffer | 100 Hz × 156 B is tiny; still set `SO_RCVBUF` ≈ 1 MB so UI stalls don't drop packets. |
| Threading | Receive on a dedicated thread; UI redraws at 10–30 Hz from the latest state (don't redraw per packet). |

## 3. Demultiplexing (one port, two message types)

All packets: `55 AA | msg_id u8 | payload_len u16 LE | payload | checksum u8`,
checksum = `sum(bytes[2 : 5+payload_len]) & 0xFF`. Branch on **byte 2**:

| msg_id | Name | Total | payload_len | Python struct | Rate | Default |
|---|---|---|---|---|---|---|
| `0x04` | Navigation solution | 156 B | 150 | `<Qdd28fH3f` | `output_rate` (100 Hz) | always on |
| `0x05` | Readiness status | 42 B | 36 | `<BBBBIIQIIBBHHH` | 2 Hz + on change | **off** (`status_udp.enabled: false`; id configurable, not yet formally reserved) |

Do **not** copy the manual's example filter (`len == 156`), or 0x05 will be counted as bad packets.
Discard anything with wrong sync / id / length / checksum.

## 4. 0x04 payload (offsets from packet start)

| Off | Field | Type | Unit / note |
|---:|---|---|---|
| 5 | time | u64 | µs, GPS time-of-week ×10⁶ (wraps weekly; follows replay clock in bag mode) |
| 13 / 21 | latitude / longitude | f64 | deg WGS84 |
| 29 | height | f32 | m |
| 33 / 37 / 41 | vel N / E / **Up** | f32 | m/s (Up positive) |
| 45 / 49 / 53 | roll / pitch / heading | f32 | deg; heading 0=N, 90=E, may be −180…180 → normalize |
| 57–77 | pos σ N/E/D, vel σ N/E/D | 6×f32 | m, m/s (1σ) |
| 81–89 | roll σ / pitch σ / heading σ | 3×f32 | deg |
| 93–101 | gyro bias xyz | 3×f32 | deg/h |
| 105–113 | accel bias xyz | 3×f32 | mg |
| 117–125 | gyro scale xyz | 3×f32 | ppm |
| 129–137 | accel scale xyz | 3×f32 | ppm |
| 141 | flags | u16 | low byte only, **bit-reversed** on the wire |
| 143 | odo scale | f32 | |
| 147 / 151 | mount pitch / yaw | f32 | deg |

C/C#: `#pragma pack(1)` / `[StructLayout(LayoutKind.Sequential, Pack = 1)]`, 150-byte payload.

Flags after `reverse_bits8(flags & 0xFF)`:

| bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| name | ZUPT | ZIHR | NHC | GNSS | VUPT | ALIGN | HEADING | FINE |

* **Valid data = ALIGN && HEADING && FINE** (same as dashboard *Ready*). Packets start flowing *before* alignment.
* ZUPT/ZIHR/NHC/GNSS/VUPT are per-epoch aiding indicators; GNSS pulses at the GNSS rate (≈1 Hz), so
  show "last seen N s ago" rather than the per-packet bit (the dashboard does this).
* Time going backwards (>1 s) = AIO NAV restarted / replay looped → reset the trajectory (dashboard rule).
* Dashboard health thresholds worth reusing: Stale after 0.5 s, Lost after 2.0 s, Low rate < 0.8 × expected.

## 5. 0x05 payload (only if `status_udp` is enabled on the Jetson)

`protocol_version`(=1), `state`, `requested_action`, `gnss_quality`, `session_id` u32, `sequence` u32,
`uptime_ms` u64, `health_flags` u32, `inhibit_flags` u32, `nav_flags` u8 (**not** reversed), reserved,
`nav_rate_dhz` u16 (Hz×10), `nav_age_ms` u16 (65535 = none), reserved.

* state: 0 BOOTING, 1 CHECKING, 2 NAV_STARTING, 3 KEEP_STILL, 4 MOVE_STRAIGHT, 5 REFINING, **6 READY**, 7 DEGRADED, 8 FAULT, 9 MAINTENANCE
* action: 0 NONE, 1 HOLD_STILL, 2 DRIVE_STRAIGHT, 3 KEEP_DRIVING, 4 SAFE_STOP, 5 SERVICE_REQUIRED, 6 MAINTENANCE_HOLD
* gnss_quality: 0 unknown, 1 none, 2 SPP, 3 RTK float, 4 RTK fix
* health / inhibit bit tables: OPERATION.md §6.8 (bits 0–17); any inhibit bit set = do not use 0x04.
* Gate rules (`vehicle_gate.py`): start blocked; need READY && inhibit==0 for 2 s in the same session;
  block on no 0x05 for 3 s, bad checksum/version, or session change; 0x04 must be ≤0.5 s old, aligned, time increasing, finite.
  A single lost 0x05 never blocks (use `sequence` to count loss).
* Golden vector (must decode exactly):
  `55aa0524000106000378563412e201000015cd5b0700000000ff0f010000000000e800e8030c0000005c`
  → READY, NONE, RTK float, session 0x12345678, seq 482, uptime 123456789, health 0x10FFF, inhibit 0, nav_flags 0xE8, 100.0 Hz, age 12 ms.

If 0x05 is off, the viewer must work from 0x04 alone (ALIGN+HEADING+FINE rule + packet age).
The same readiness snapshot is also at `http://<jetson>:8080/api/readiness` (JSON), usable as a fallback.

## 6. Pre-check results on this PC (Windows 11, Python 3.9.13)

* Independent decoder written from the manual only (not importing repo code):
  `C:\Users\POINT-~1\AppData\Local\Temp\claude\D--tool-AI-dev-AIO-reciever\c50ebf94-2b3c-4d28-8420-028f7adec9de\scratchpad\scripts\precheck_rx.py`
* Repo's `tools/fake_nav_sender.py --port 19000` → 0 bad packets, fields and flags decoded correctly
  (lat 22.997…, lon 120.221…, heading, NHC/ALIGN/HEADING/FINE). Packet count/rate from this run is not meaningful
  (receive window outlived the sender); this was loopback only, so LAN + firewall are still untested.
* 0x05 golden vector decodes to the documented values.
* Payload sizes confirmed: 0x04 = 150 B, 0x05 = 36 B.

## 7. Test tooling for development (no Jetson needed)

* 0x04: `python tools/fake_nav_sender.py --host 127.0.0.1 --port 9000 --scenario all`
  (scenarios: normal, align, gnss_loss, flags, pause, loss, heading_wrap, restart).
* 0x05: the fake sender emits none; build packets with `nav/status_packet.encode()` or reuse the golden vector.
  `tools/vehicle_gate.py --port 9000` shows the gate rules on live traffic.

## 8. Suggested viewer features (mirrors the dashboard)

Status line (Streaming / Stale / Lost / Low rate, packets, bad, Hz), alignment lamps (ALIGN/HEADING/FINE),
aiding lamps with last-seen age, lat/lon/height, speed = hypot(vN, vE), attitude, σ values, IMU calibration,
map trajectory (reset on time jump), optional 0x05 state/action/inhibit decode, CSV/raw-binary recording.

## Open item on the Jetson side

* Is `status_udp.enabled` going to be turned on, and is 0x05 formally reserved?
* Exact `output_udp` / `output_rate` currently configured.
