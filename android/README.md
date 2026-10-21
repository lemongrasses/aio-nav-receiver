# AIO NAV Receiver for Android

Receives the AIO NAV 0x04 and dashboard 0x05 UDP packets on an Android phone and shows, live, whether the
navigation output may be used. Same rules as the desktop app (`src/aio_receiver/core/gate.py`) and the
iPhone app; monitoring only, the app never sends anything back. Native Kotlin + Jetpack Compose,
Android 8.0 (API 26) or newer.

- **Status**: green 可用 / red 阻擋 with the reason, dashboard state, operator instruction, navigation
  values (position, heading, speed, σ, flags, data age, receive rate), the 0x05 inhibit/health bits and
  packet statistics.
- **Charts**: last 1 / 5 / 10 minutes: status timeline (verdict + dashboard state), position σ, heading σ,
  0x04 data age against the limit, receive rate, speed, heading, height.
- **Track**: the last 10 minutes drawn in local metres (no map tiles, no API key), green where usable and
  red where blocked, heading arrow, grid, scale bar; drag and pinch, "Follow vehicle" to fit again.
- **Settings**: this phone's IP addresses and Wi-Fi state, ports, 0x05 message id, "accept only source
  IP", rule thresholds, keep screen on, background receiving, apply / restore defaults / clear.
- **Background**: unlike iOS, Android keeps receiving when the app is not on screen. A foreground
  service (type `connectedDevice`) shows 可用 / 阻擋 in an ongoing green / red notification; its **Stop**
  button ends it. Turn off "Keep receiving in the background" to receive only while the app is on screen.

The UI follows the phone's language: 繁體中文 (`res/values-zh-rTW`) or English (`res/values`), with the
texts the iPhone app uses (`ios/MyApp/Localizable.xcstrings`).

## Code

| Path | What |
| --- | --- |
| `app/src/main/java/.../core/` | Pure Kotlin, no Android imports: 0x04 / 0x05 decoders (`Protocol.kt`), the gate (`Gate.kt`), the desktop's time-ordered `Monitor`, the `.bin` reader, track helpers |
| `app/src/main/java/.../monitor/` | UDP receiver threads, the store (gate behind a lock, 100 ms snapshot, 10 min history), settings, the foreground service, Wi-Fi keeper |
| `app/src/main/java/.../ui/` | Compose screens; charts and the track are drawn with Canvas |
| `app/src/test/` | JVM unit tests against the shared `../fixtures` |

The live app uses the same `Monitor` as the tests: the verdict is evaluated at every packet and just
after every gate deadline, so the usable time and the transition times do not depend on the 100 ms
screen refresh. The receive clock is `SystemClock.elapsedRealtimeNanos()` (monotonic, keeps counting
in deep sleep).

## Build and test

Needs JDK 17 and the Android SDK (platform 36). On a Mac with Homebrew:

```bash
brew install openjdk@17 && brew install --cask android-commandlinetools
```

Then, with `JAVA_HOME` pointing at JDK 17 and `ANDROID_HOME` at the SDK
(`/opt/homebrew/share/android-commandlinetools`), from `android/`:

```bash
./gradlew assembleDebug testDebugUnitTest
```

The unit tests run on the JVM, no device needed. They hold this port to the desktop rules:

- `fixtures/gate_vectors.json`: all 460 steps, verdict kind, usable and the nav / status / lost /
  reordered / conflicts / bad counters;
- `fixtures/real_*.bin.gz`: the real Jetson recordings replayed with the desktop `Monitor`'s deadline
  timing; every transition time (±1e-9 s), its desktop reason text, the usable total (±1e-6 s) and all
  counters must match the `.expected.json`;
- the decoders against the golden 0x05 and a 0x04 from the desktop encoder (and the encoders back);
- `core/` stays free of Android imports.

After changing a rule in the desktop gate, regenerate the vectors (`python tools/make_gate_vectors.py`)
and make `core/Gate.kt` follow; the `android` workflow runs these tests when `android/`, `fixtures/` or
the generator change, and uploads the debug APK.

## Try it in the emulator

```bash
sdkmanager "platform-tools" "emulator" "system-images;android-36;google_apis;arm64-v8a"
avdmanager create avd -n aionav36 -k "system-images;android-36;google_apis;arm64-v8a" -d pixel_7
emulator -avd aionav36 &
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb emu redir add udp:9000:9000          # forward the Mac's UDP 9000 into the emulator
python ../tools/fake_sender.py --host 127.0.0.1 --port 9000
```

The fake sender cycles KEEP_STILL → MOVE_STRAIGHT → REFINING → READY (2 s later 可用) → no 0x05 (阻擋)
every 55 s. In the emulator the packets arrive from `10.0.2.2`.

## Use it with the real device

1. Join the Jetson's Wi-Fi hotspot (gateway usually `10.42.0.1`). Android may say the network has no
   internet: choose to stay connected. While receiving, the app holds a request for that Wi-Fi network,
   so Android keeps it up even when it moves the default route to mobile data.
2. Settings tab: note the phone's `wlan0` address. For a fixed address, set the network's privacy to
   "Use device MAC" (Wi-Fi → the network → Privacy), or reserve the address on the Jetson.
3. On the Jetson, the relay copies every packet to the vehicle receiver (`192.168.116.154:9000`) and to
   `<phone IP>:9000`. Turn on `status_udp.enabled` in the dashboard config for 0x05.
4. In the app, enter the Jetson's address as the phone sees it (usually `10.42.0.1`) under "Accept only
   source IP", then Apply. Allow notifications when asked, so the background 可用 / 阻擋 shows.

To install on a phone: turn on Developer options → USB debugging, connect it, then
`adb install -r app/build/outputs/apk/debug/app-debug.apk` (or download the APK artifact from the
`android` workflow run and open it on the phone).

Battery: while it runs, the service holds a partial wake lock and a Wi-Fi lock so 100 Hz keeps arriving
with the screen off. Stop it from the notification when done. Some phone makers stop background apps
anyway; if monitoring stops with the screen off, set the app's battery use to "Unrestricted".
