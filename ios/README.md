# AIO NAV Receiver for iPhone

Receives the AIO NAV 0x04 and dashboard 0x05 UDP packets on the iPhone and shows, live, whether the
navigation output may be used. Same rules as the desktop app (`src/aio_receiver/core/gate.py`, the
spec "AIO NAV UDP 接收端 App 開發規格"); monitoring only, the app never sends anything back.

- **Status**: green 可用 / red 阻擋 with the reason, dashboard state, operator instruction,
  navigation values (position, heading, speed, σ, flags, data age, receive rate), the 0x05
  inhibit/health bits and packet statistics.
- **Charts**: last 1 / 5 / 10 minutes: status timeline (verdict + dashboard state), position σ,
  heading σ, 0x04 data age against the 0.5 s limit, receive rate, speed, heading, height.
- **Track**: the vehicle's recent track on Apple Maps.
- **Settings**: this iPhone's IP address, ports, 0x05 message id, "accept only source IP",
  rule thresholds, keep screen on.

One language at a time, chosen in Settings → Display → Language (follow system / 繁體中文 / English); it
applies at once and listening carries on. Protocol codes are shown as readable words with the desktop
app's wording: `MyApp/Protocol/Vocabulary.swift` mirrors `src/aio_receiver/i18n.py` (`VocabularyTests`
compares them), and screen labels live in `MyApp/Localizable.xcstrings`. Version 1.2.0, as the desktop.

## Code

| Path | What |
| --- | --- |
| `MyApp/Protocol/AIOProtocol.swift` | 0x04 / 0x05 decoders (exact lengths, checksum, version) |
| `MyApp/Protocol/VehicleGate.swift` | Usable / blocked rules, the same as the desktop `Gate` |
| `MyApp/Network/UDPReceiver.swift` | BSD-socket receiver on its own thread |
| `MyApp/Monitor/` | Engine (gate behind a mutex), settings, 10 Hz store with chart history |
| `MyApp/Views/` | SwiftUI screens, Swift Charts, MapKit |
| `MyAppTests/` | Decoders, the shared step vectors, and replays of the real recordings in `../fixtures` |

## Try it in the Simulator

Open `ios/MyApp.xcodeproj`, run on an iPhone simulator (⌘R), then from the repository root:

```bash
python tools/fake_sender.py --host 127.0.0.1 --port 9000
```

The Simulator shares the Mac's network, so it receives on port 9000 directly.

## Use it with the real device

1. Join the Jetson's Wi-Fi hotspot (or the same closed network). If the iPhone does not list the
   hotspot while a Mac does, the hotspot is likely on a channel the iPhone does not scan (2.4 GHz
   12–13, or a high 5 GHz channel): set the Jetson's country (`iw reg set TW`) and use channel 1–11.
2. Settings tab: note the iPhone's `en0` address. Turn off Private Wi-Fi Address for that network
   so the address stays the same.
3. On the Jetson, `output_udp` has one destination. Either point it at `<iPhone IP>:9000` (the
   vehicle receiver then gets nothing), or run a relay on the Jetson that copies every packet to
   both the vehicle receiver and the iPhone. Turn on `status_udp.enabled` in the dashboard config for 0x05.
4. In the app, enter the Jetson's address as seen by the iPhone (the hotspot gateway, usually
   `10.42.0.1`) under "Accept only source IP". Allow "Local Network" access when iOS asks. Keep the
   app on screen; iOS pauses it in the background.

To install on your own iPhone: in Xcode select the MyApp target → Signing & Capabilities → choose
your team (`DEVELOPMENT_TEAM` is set to one Personal Team; change it to yours), turn on Developer Mode
on the iPhone, connect it, ⌘R. A free Apple ID's install runs for 7 days.

## Tests

```bash
xcodebuild test -project ios/MyApp.xcodeproj -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```

- `VehicleGateTests.matchesDesktopGateAtEveryStep` replays `../fixtures/gate_vectors.json` and checks
  the verdict and every counter against the desktop gate at each of its 460 steps.
- `RealRecordingTests` replays the real Jetson recordings `../fixtures/real_*.bin.gz` with the
  desktop's deadline timing and checks every transition time, reason, the usable time and counters
  against their `.expected.json`.

After changing the desktop rules, regenerate the vectors (`python tools/make_gate_vectors.py`) and
update `VehicleGate.swift` until these pass. The `ios` GitHub workflow runs them.

## Differences from web_monitor's VehicleGate

Both apps follow the spec where it and web_monitor differ:

- A 0x05 sequence more than 5 behind (two senders in one session) clears the authorisation and
  starts over from that packet; `VehicleGate` only ignores it.
- Packets must have the exact length (156 / 42 bytes); `VehicleGate` accepts longer ones.

Shared by all three: `readySince` is not cleared on a 0x05 timeout, so after a dropout longer than
3 s the verdict returns to usable at once when READY packets resume, without a new 2 s wait.
