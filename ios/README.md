# MyApp — AIO NAV monitor for iPhone

Receives the AIO NAV UDP packets on the iPhone and shows, live, whether the navigation output
may be used, following the spec "AIO NAV UDP 接收端 App 開發規格" and web_monitor's reference
`aio_system_dashboard/nav/vehicle_gate.py`. Monitoring only: the app never sends anything back.

- **Status** — green 可用 / red 阻擋 with the reason, dashboard state, operator instruction,
  navigation values (position, heading, speed, σ, flags, data age, receive rate), the 0x05
  inhibit/health bits and packet statistics.
- **Charts** — last 1 / 5 / 10 minutes: status timeline (verdict + dashboard state), position σ,
  heading σ, 0x04 data age against the 0.5 s limit, receive rate, speed, heading, height.
- **Track** — the vehicle's recent track on Apple Maps.
- **Settings** — this iPhone's IP address, ports, 0x05 message id, "accept only source IP",
  rule thresholds, keep screen on.

UI language follows the iPhone: 繁體中文 or English (`MyApp/Localizable.xcstrings`).

## Code

| Path | What |
| --- | --- |
| `MyApp/Protocol/AIOProtocol.swift` | 0x04 / 0x05 decoders (port of `nav/decoder.py`, `nav/status_packet.py`) |
| `MyApp/Protocol/VehicleGate.swift` | Usable / blocked rules (port of `nav/vehicle_gate.py`) |
| `MyApp/Network/UDPReceiver.swift` | BSD-socket receiver on its own thread |
| `MyApp/Monitor/` | Engine (gate behind a mutex), settings, 10 Hz store with chart history |
| `MyApp/Views/` | SwiftUI screens, Swift Charts, MapKit |
| `MyAppTests/` | Decoder tests and the step-by-step comparison with the reference gate |
| `tools/fake_aio_sender.py` | Fake 0x04 (100 Hz) + 0x05 (2 Hz) sender, standard library only |
| `tools/make_gate_vectors.py` | Regenerates `MyAppTests/Fixtures/gate_vectors.json` from a web_monitor checkout |

## Try it in the Simulator

Open `MyApp.xcodeproj`, run on an iPhone simulator (⌘R), then on the Mac:

```bash
python3 tools/fake_aio_sender.py
```

The Simulator shares the Mac's network, so it receives on port 9000 directly. The sender loops
through CHECKING → alignment → READY → 0x05 dropout → 0x04 pause → DEGRADED every 90 s.

## Use it with the real device

1. Put the iPhone on the same network as the AIO NAV device (direct link or closed VLAN).
2. Settings tab: note the iPhone's `en0` address; enter the device's IP under
   "Accept only source IP".
3. On the device: Maintenance → AIO NAV config → set `output_udp` to `<iPhone IP>:9000`, save,
   restart AIO NAV. `output_udp` has a single destination, so the iPhone replaces any other
   receiver while it is set. Point `status_udp.destination` at the same address for 0x05.
4. Allow "Local Network" access when iOS asks. Keep the app on screen; iOS pauses it in the
   background.

To install on your own iPhone: in Xcode select the MyApp target → Signing & Capabilities →
choose your team (a free Apple ID works for personal testing), connect the iPhone, ⌘R.

## Tests

```bash
xcodebuild test -project MyApp.xcodeproj -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```

`VehicleGateTests.matchesReferenceGateAtEveryStep` replays 460 steps of packets built by
web_monitor's own encoders and checks the verdict and counters against its `VehicleGate` at every
step. After changing the reference code, regenerate the vectors:

```bash
python3 tools/make_gate_vectors.py /path/to/web_monitor
```

## Notes on the reference behaviour

- Where the spec and web_monitor disagree, web_monitor wins (as the spec says). The spec says a
  status sequence more than 5 behind should clear authorisation ("two senders"); `VehicleGate`
  only ignores such a packet. The app does the same and counts it under "Two senders".
- `VehicleGate` does not clear `readySince` on a 0x05 timeout, so after a dropout longer than 3 s
  the verdict returns to usable at once when READY packets resume, without a new 2 s wait. The app
  matches this; worth raising with the web_monitor maintainers.
