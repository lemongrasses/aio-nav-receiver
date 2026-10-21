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

**Language:** one language at a time, 繁體中文 (`res/values-zh-rTW`) or English (`res/values`), like the
desktop app since 1.2.0. It follows the phone until you choose one in **設定 / Settings → 顯示 / Display →
語言 / Language** (跟隨系統 / 繁體中文 / English); the change applies at once and does not restart receiving
(on Android 13+ it is also under the phone's Settings → Apps → AIO NAV Receiver → Language). Protocol codes
are shown as words, with the desktop's wording (`src/aio_receiver/i18n.py`): READY → 就緒 / Ready,
KEEP_STILL_REQUIRED → 需要保持靜止 / Must keep still, the 18 health and 18 blocking conditions, GNSS quality,
the alignment lamps. Acronyms (GNSS, ZUPT, NHC), units and packet ids (0x04) stay as they are.

Version 1.2.0 (`versionName` in `app/build.gradle.kts`), the same as the desktop app.

## Code

| Path | What |
| --- | --- |
| `app/src/main/java/.../core/` | Pure Kotlin, no Android imports: 0x04 / 0x05 decoders (`Protocol.kt`), the gate (`Gate.kt`), the desktop's time-ordered `Monitor`, the `.bin` reader, track helpers |
| `app/src/main/java/.../monitor/` | UDP receiver threads, the store (gate behind a lock, 100 ms snapshot, 10 min history), settings, the foreground service, Wi-Fi keeper |
| `app/src/main/java/.../ui/` | Compose screens; charts and the track are drawn with Canvas |
| `app/src/main/res/values*/strings.xml` | Every user-visible text in English and 繁體中文, including the protocol vocabulary (string-arrays) |
| `app/src/test/` | JVM unit tests against the shared `../fixtures`, and the string tables |

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
- `core/` stays free of Android imports;
- both languages hold the same texts with the same arguments and a word for every protocol code; English
  has no Chinese; no raw protocol code (KEEP_STILL_REQUIRED) is shown on screen. The recordings' reason text
  is compared as the pre-1.0 sentence rebuilt from the codes (`Verdict.legacyText`, the desktop's
  `legacy_text`), so the fixtures stay valid whatever the display language.

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

To install on a phone: download `AIO_NAV_Receiver-android-<version>.apk` from the GitHub Release and open
it on the phone (allow "Install unknown apps" for the browser or file manager when Android asks). Or turn
on Developer options → USB debugging, connect it, and `adb install -r <apk>`. A debug build and a release
build are signed with different keys: uninstall one before installing the other.

Battery: while it runs, the service holds a partial wake lock and a Wi-Fi lock so 100 Hz keeps arriving
with the screen off. Stop it from the notification when done. Some phone makers stop background apps
anyway; if monitoring stops with the screen off, set the app's battery use to "Unrestricted".

## Release and signing

Release APKs are signed with the project's release key (`CN=AIO NAV Receiver, O=lemongrass, C=TW`,
certificate SHA-256 `4e:e6:a3:49:19:d7:61:a4:7e:1b:57:b1:c0:9d:9e:10:1f:6d:67:f9:b0:a9:28:a6:98:ef:cc:61:32:81:7e:94`).
Android only installs an update signed with the same key, so **every release must use this keystore;
if it is lost, installed copies can no longer be updated** (they have to be uninstalled first).

- **The keystore is never in the repository.** The original is on the release Mac in
  `~/.android-release/aio-nav-receiver/` (`aionav-release.jks` and `keystore.properties` with the
  passwords, readable only by the owner). Keep a backup of both files somewhere safe, such as a password
  manager.
- **CI** gets it from four repository secrets: `AIONAV_KEYSTORE_BASE64` (the .jks, base64),
  `AIONAV_KEYSTORE_PASSWORD`, `AIONAV_KEY_ALIAS` (`aionav`) and `AIONAV_KEY_PASSWORD`. The `android` workflow
  builds the signed APK whenever the secrets are available, checks it carries the certificate above, and
  uploads it as the `aio-nav-receiver-release-apk` artifact.
- **Publishing:** push a `v*` tag. The `android` workflow waits for the `ci` workflow to create that GitHub
  Release, then attaches `AIO_NAV_Receiver-android-<versionName>.apk`. To attach it to a release that already
  exists, run the `android` workflow by hand (Actions → android → Run workflow) with `release_tag` set, for
  example `v1.2.0`. Bump `versionName` and `versionCode` (major × 10000 + minor × 100 + patch) first: Android
  does not install an update with a lower or equal `versionCode`.
- **On the Mac:** `~/.gradle/gradle.properties` has `aionav.signing=<path to keystore.properties>`, so
  `./gradlew assembleRelease` writes a signed `app/build/outputs/apk/release/app-release.apk`. Without that
  property (or the CI variables), the release APK is left unsigned. Check a signature with
  `$ANDROID_HOME/build-tools/36.0.0/apksigner verify --print-certs <apk>`.
