//
//  MyAppTests.swift
//  MyAppTests
//
//  The rules are shared with the desktop app through the repository's fixtures/ folder:
//  - gate_vectors.json: a scripted packet stream with the desktop gate's verdict and counters
//    at every step (tools/make_gate_vectors.py);
//  - real_*.bin.gz + .expected.json: real Jetson recordings with the verdict transitions the
//    desktop expects (tests/test_regression.py checks the same files).
//  The tests run in the Simulator on the Mac, so they read the files from the source tree.
//

import Compression
import Foundation
import Testing
@testable import MyApp

enum Fixtures {
    /// <repo>/fixtures, found from this file's location: <repo>/ios/MyAppTests/MyAppTests.swift.
    static let folder = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appendingPathComponent("fixtures")

    static func data(_ name: String) throws -> Data {
        try Data(contentsOf: folder.appendingPathComponent(name))
    }
}

struct GateVectors: Decodable {
    struct Step: Decodable {
        let t: Double
        let packets: [String]
        let usable: Bool
        let reason: String
        let nav: Int
        let status: Int
        let lost: Int
        let reordered: Int
        let conflicts: Int
        let bad: Int
    }

    let golden_status: String
    let nav_example: String
    let steps: [Step]

    static func load() throws -> GateVectors {
        try JSONDecoder().decode(GateVectors.self, from: Fixtures.data("gate_vectors.json"))
    }
}

func bytes(_ hex: String) -> [UInt8] {
    var out: [UInt8] = []
    var i = hex.startIndex
    while i < hex.endIndex {
        let j = hex.index(i, offsetBy: 2)
        out.append(UInt8(hex[i..<j], radix: 16)!)
        i = j
    }
    return out
}

extension VehicleGate.Verdict {
    var kind: String {
        switch self {
        case .usable: "usable"
        case .noStatus: "noStatus"
        case .notReady: "notReady"
        case .readyNotStable: "readyNotStable"
        case .navTooOld: "navTooOld"
        case .navTimeBackwards: "navTimeBackwards"
        case .notAligned: "notAligned"
        case .notFinite: "notFinite"
        }
    }

    /// The desktop's Verdict.text, which the .expected.json files record.
    var desktopText: String {
        switch self {
        case .usable: return "可用"
        case .noStatus: return "沒有最新的狀態封包 (0x05)"
        case let .notReady(state, inhibit):
            let name = Int(state) < DashboardState.names.count ? DashboardState.names[Int(state)] : "#\(state)"
            let bits = AIO.names(of: inhibit, in: StatusBits.inhibit).joined(separator: ", ")
            return "狀態不是 READY：\(name)（\(bits.isEmpty ? "—" : bits)）"
        case .readyNotStable: return "READY 尚未穩定"
        case .navTooOld: return "導航資料太舊 (0x04)"
        case .navTimeBackwards: return "導航時間沒有往前"
        case .notAligned: return "導航旗標未對準"
        case .notFinite: return "導航資料不是有限值"
        }
    }
}

// MARK: - Recordings (format of the desktop's src/aio_receiver/io/recording.py)

struct RecordedPacket {
    let t: Double
    let sender: String?
    let data: [UInt8]
}

enum RecordingFile {
    /// Inflates a .gz file (gzip header + raw DEFLATE, which Compression calls ZLIB).
    static func gunzip(_ gz: Data) throws -> [UInt8] {
        let b = [UInt8](gz)
        try #require(b.count > 18 && b[0] == 0x1F && b[1] == 0x8B && b[2] == 8)
        let flags = b[3]
        var i = 10
        if flags & 0x04 != 0 { i += 2 + (Int(b[i]) | Int(b[i + 1]) << 8) }      // FEXTRA
        if flags & 0x08 != 0 { while b[i] != 0 { i += 1 }; i += 1 }             // FNAME
        if flags & 0x10 != 0 { while b[i] != 0 { i += 1 }; i += 1 }             // FCOMMENT
        if flags & 0x02 != 0 { i += 2 }                                          // FHCRC
        let size = Int(ByteReader(b).u32(b.count - 4))
        var out = [UInt8](repeating: 0, count: size)
        let deflated = Array(b[i..<(b.count - 8)])
        let written = out.withUnsafeMutableBufferPointer { dst in
            deflated.withUnsafeBufferPointer { src in
                compression_decode_buffer(dst.baseAddress!, size, src.baseAddress!, src.count, nil, COMPRESSION_ZLIB)
            }
        }
        try #require(written == size)
        return out
    }

    /// v2: "AIONREC\0" u16 version u32 header_len header, then f64 t, u16 len, 4s IPv4, u16 port, bytes.
    /// v1: no header; f64 t, u16 len, bytes. A truncated or out-of-order tail is not a record.
    static func parse(_ b: [UInt8]) -> (packets: [RecordedPacket], hasSenders: Bool) {
        let r = ByteReader(b)
        let magic = Array("AIONREC".utf8) + [0]
        var i = 0
        var v2 = false
        if b.count >= 14 && Array(b[0..<8]) == magic {
            v2 = r.u16(8) == 2
            i = 14 + Int(r.u32(10))
        }
        let head = v2 ? 16 : 10
        var out: [RecordedPacket] = []
        var last = -Double.infinity
        while i + head <= b.count {
            let t = r.f64(i)
            let n = Int(r.u16(i + 8))
            guard i + head + n <= b.count, t.isFinite, t >= last else { break }
            last = t
            let sender = v2 ? b[(i + 10)..<(i + 14)].map(String.init).joined(separator: ".") : nil
            out.append(RecordedPacket(t: t, sender: sender, data: Array(b[(i + head)..<(i + head + n)])))
            i += head + n
        }
        return (out, v2)
    }
}

/// The desktop's core/monitor.py: judge at every packet and just after every gate deadline, so
/// transition times and the usable total do not depend on how often anyone looks.
struct ReplayMonitor {
    static let deadlineEpsilon = 1e-6

    var gate = VehicleGate()
    var verdict: VehicleGate.Verdict?
    var t = -Double.infinity
    var usableTotal = 0.0
    var transitions: [(t: Double, verdict: VehicleGate.Verdict)] = []
    var navCount = 0
    var statusCount = 0

    mutating func evaluate(at now: Double) {
        let v = gate.verdict(at: now)
        if verdict?.isUsable == true {
            usableTotal += now - t
        }
        t = now
        if v != verdict {
            verdict = v
            transitions.append((now, v))
        }
    }

    mutating func advance(to now: Double) {
        while let d = gate.nextDeadline(after: t), d + Self.deadlineEpsilon <= now {
            evaluate(at: d + Self.deadlineEpsilon)
        }
        if now >= t {
            evaluate(at: now)
        }
    }

    mutating func feed(_ data: [UInt8], at time: Double) {
        let now = max(time, t)
        advance(to: now)
        switch gate.feed(data, at: now) {
        case .nav: navCount += 1
        case .status: statusCount += 1
        case nil: break
        }
        evaluate(at: now)
    }
}

// MARK: - Tests

struct StatusPacketTests {

    @Test func decodesGoldenVector() throws {
        let packet = try GateVectors.load().golden_status
        #expect(packet.hasSuffix("5c"))                  // the checksum printed in the spec
        let s = try #require(StatusPacket(bytes: bytes(packet)))
        #expect(s.stateName == "READY")
        #expect(s.actionName == "NONE")
        #expect(s.gnssQualityName == "RTK float")
        #expect(s.sessionID == 0x1234_5678)
        #expect(s.sequence == 482)
        #expect(s.uptimeMs == 123_456_789)
        #expect(s.healthFlags == 0x10FFF)
        #expect(s.inhibitFlags == 0)
        #expect(s.navFlags == 0xE8)
        #expect(s.navRateHz == 100.0)
        #expect(s.navAgeMs == 12)
        #expect(s.healthNames.count == 13)
        #expect(s.healthNames.last == "NO_DUPLICATE_PROCESS")
    }

    @Test func rejectsBadChecksumVersionAndLength() throws {
        let good = bytes(try GateVectors.load().golden_status)
        var badSum = good
        badSum[20] ^= 0x01
        #expect(StatusPacket(bytes: badSum) == nil)

        var version2 = good
        version2[5] = 2
        version2[41] = version2[2..<41].reduce(UInt8(0)) { $0 &+ $1 }
        #expect(StatusPacket(bytes: version2) == nil)

        #expect(StatusPacket(bytes: Array(good.prefix(41))) == nil)
        #expect(StatusPacket(bytes: good + [0]) == nil)          // exact length only, like the desktop
        #expect(StatusPacket(bytes: good, messageID: 0x06) == nil)
    }
}

struct NavSolutionTests {

    @Test func decodesReferenceEncoderOutput() throws {
        let n = try #require(NavSolution(bytes: bytes(try GateVectors.load().nav_example)))
        #expect(abs(n.time - 345_678.123456) < 1e-9)
        #expect(n.latitude == 22.99690123)
        #expect(n.longitude == 120.22180456)
        #expect(n.height == 35.25)
        #expect(n.velocityNorth == 1.5 && n.velocityEast == -2.0 && n.velocityUp == 0.25)
        #expect(n.roll == 1.25 && n.pitch == -2.5)
        #expect(n.heading == -90)
        #expect(n.heading360 == 270)                     // negative headings show as 0…360
        #expect(n.groundSpeed == 2.5)
        #expect(n.positionNorthStd == 0.05 && n.headingStd == 0.3)
        #expect(n.gyroBias == [1.5, -0.7, 2.1])
        #expect(n.accelScale == [200, 150, -90])
        #expect(n.odometerScale == 1.01)
        #expect(n.mountYaw == -1.5)
        #expect(n.has(.zupt) && n.has(.gnss) && !n.has(.nhc))
        #expect(n.isAligned)
        #expect(n.isFinite)
    }

    @Test func flagsAreBitReversedOnTheWire() {
        #expect(AIO.reverseBits(0b0000_0001) == 0b1000_0000)
        #expect(AIO.reverseBits(0xE8) == 0x17)
        #expect(AIO.reverseBits(AIO.reverseBits(0x5A)) == 0x5A)
    }

    @Test func rejectsWrongLengthOrChecksum() throws {
        let good = bytes(try GateVectors.load().nav_example)
        #expect(NavSolution(bytes: Array(good.prefix(155))) == nil)
        #expect(NavSolution(bytes: good + [0]) == nil)
        var bad = good
        bad[155] &+= 1
        #expect(NavSolution(bytes: bad) == nil)
    }
}

struct VehicleGateTests {

    /// The shared contract: the same packet stream must give the desktop gate's verdict and
    /// counters at every step.
    @Test func matchesDesktopGateAtEveryStep() throws {
        let vectors = try GateVectors.load()
        #expect(vectors.steps.count > 400)
        var gate = VehicleGate()
        var nav = 0, status = 0
        for step in vectors.steps {
            for packet in step.packets {
                switch gate.feed(bytes(packet), at: step.t) {
                case .nav: nav += 1
                case .status: status += 1
                case nil: break
                }
            }
            let verdict = gate.verdict(at: step.t)
            #expect(verdict.kind == step.reason, "t=\(step.t)")
            #expect(verdict.isUsable == step.usable, "t=\(step.t)")
            #expect(nav == step.nav && status == step.status, "t=\(step.t)")
            #expect(gate.counters.lost == step.lost, "t=\(step.t)")
            #expect(gate.counters.reordered == step.reordered, "t=\(step.t)")
            #expect(gate.counters.twoSenders == step.conflicts, "t=\(step.t)")
            #expect(gate.counters.bad == step.bad, "t=\(step.t)")
        }
        #expect(gate.counters.twoSenders == 1)
    }

    @Test func secondSenderClearsAuthorisation() throws {
        let golden = bytes(try GateVectors.load().golden_status)
        let nav = bytes(try GateVectors.load().nav_example)
        var gate = VehicleGate()
        gate.feed(golden, at: 0)
        gate.feed(nav, at: 2.0)
        #expect(gate.verdict(at: 2.0) == .usable)
        // The same session going back 10: a second sender. Start over from that packet.
        var older = golden
        older[13] = 0xD8                              // sequence 472 = 0x1D8 (482 = 0x1E2)
        older[41] = older[2..<41].reduce(UInt8(0)) { $0 &+ $1 }
        #expect(StatusPacket(bytes: older)?.sequence == 472)
        gate.feed(older, at: 2.1)
        #expect(gate.counters.twoSenders == 1)
        #expect(gate.verdict(at: 2.1) == .readyNotStable)
        #expect(gate.verdict(at: 4.2) == .navTooOld)    // READY settled again; nav is old by now
    }

    @Test func singleLostStatusNeverBlocksButTimeoutDoes() throws {
        let golden = bytes(try GateVectors.load().golden_status)
        let nav = bytes(try GateVectors.load().nav_example)
        var gate = VehicleGate()
        gate.feed(golden, at: 0)
        #expect(gate.verdict(at: 1.9) == .readyNotStable)
        gate.feed(nav, at: 2.0)
        #expect(gate.verdict(at: 2.0) == .usable)
        // Status stops: still usable up to 3 s after the last one, then blocked.
        #expect(gate.verdict(at: 2.4) == .usable)
        #expect(gate.verdict(at: 2.6) == .navTooOld)    // nav is older than 0.5 s by now
        gate.feed(nav, at: 2.7)                           // same time stamp: not forward
        #expect(gate.verdict(at: 2.7) == .navTimeBackwards)
        #expect(gate.verdict(at: 3.01) == .noStatus)
        #expect(gate.nextDeadline(after: 2.7) == 3.0)
    }
}

/// The desktop's regression test (tests/test_regression.py) on the same real recordings.
struct RealRecordingTests {

    struct Expected: Decodable {
        let usable_s: Double
        let count: [String: Int]
        let transitions: [[Transition]]

        enum Transition: Decodable {
            case number(Double), flag(Bool), text(String)

            init(from decoder: Decoder) throws {
                let c = try decoder.singleValueContainer()
                if let b = try? c.decode(Bool.self) { self = .flag(b) }
                else if let d = try? c.decode(Double.self) { self = .number(d) }
                else { self = .text(try c.decode(String.self)) }
            }
        }
    }

    @Test(arguments: ["real_restart_v1", "real_ready_v2"])
    func matchesDesktopExpectations(name: String) throws {
        let recording = RecordingFile.parse(try RecordingFile.gunzip(Fixtures.data("\(name).bin.gz")))
        let expected = try JSONDecoder().decode(Expected.self, from: Fixtures.data("\(name).expected.json"))
        let packets = recording.packets
        try #require(!packets.isEmpty)

        var monitor = ReplayMonitor()
        monitor.advance(to: packets[0].t)
        for p in packets {
            monitor.feed(p.data, at: p.t)
        }
        monitor.advance(to: packets[packets.count - 1].t)

        #expect(monitor.transitions.count == expected.transitions.count)
        for (got, want) in zip(monitor.transitions, expected.transitions) {
            guard case let .number(t) = want[0], case let .flag(usable) = want[1], case let .text(text) = want[2] else {
                Issue.record("bad expected row \(want)")
                continue
            }
            #expect(abs(got.t - t) <= 1e-9, "t=\(t)")
            #expect(got.verdict.isUsable == usable, "t=\(t)")
            #expect(got.verdict.desktopText == text, "t=\(t)")
        }
        #expect(abs(monitor.usableTotal - expected.usable_s) <= 1e-6)
        let c = monitor.gate.counters
        #expect(monitor.navCount == expected.count["nav"])
        #expect(monitor.statusCount == expected.count["status"])
        #expect(c.lost == expected.count["lost"])
        #expect(c.reordered == expected.count["reordered"])
        #expect(c.twoSenders == expected.count["conflicts"])
        #expect(c.bad == expected.count["bad"])
        #expect(recording.hasSenders == (name == "real_ready_v2"))
    }
}

// MARK: - Language (the desktop's src/aio_receiver/i18n.py is the reference wording)

struct VocabularyTests {

    static let i18n: String = {
        let url = Fixtures.folder.deletingLastPathComponent().appendingPathComponent("src/aio_receiver/i18n.py")
        return (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    }()

    /// The source of one top-level table, e.g. `_STATES = {…}`, up to the next table or blank line.
    static func block(_ name: String) -> String {
        guard let start = i18n.range(of: "\n\(name) = ") else { return "" }
        let rest = i18n[start.upperBound...]
        let ends = ["\n\n", "\n_"].compactMap { rest.range(of: $0)?.lowerBound }
        return String(rest[..<(ends.min() ?? rest.endIndex)])
    }

    /// One Python string: adjacent literals, possibly on several lines, are one string ("a" "b" == "ab").
    static let literal = #""(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*"#
    static let pair = #"\(\s*("# + literal + #")\s*,\s*("# + literal + #")\s*\)"#

    /// The text of a matched `literal`: its pieces joined.
    static func joined(_ source: String) -> String {
        let piece = try! NSRegularExpression(pattern: #""((?:[^"\\]|\\.)*)""#)
        return piece.matches(in: source, range: NSRange(source.startIndex..., in: source))
            .map { String(source[Range($0.range(at: 1), in: source)!]) }.joined()
    }

    /// ("zh", "en") pairs in order.
    static func pairs(_ text: String) -> [[String]] {
        let re = try! NSRegularExpression(pattern: pair)
        return re.matches(in: text, range: NSRange(text.startIndex..., in: text)).map { m in
            (1...2).map { joined(String(text[Range(m.range(at: $0), in: text)!])) }
        }
    }

    /// "KEY": ("zh", "en") entries.
    static func keyed(_ text: String) -> [String: [String]] {
        let re = try! NSRegularExpression(pattern: #""([A-Za-z0-9_.]+)":\s*"# + pair)
        var out: [String: [String]] = [:]
        for m in re.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            let g = (1...3).map { String(text[Range(m.range(at: $0), in: text)!]) }
            out[g[0]] = [joined(g[1]), joined(g[2])]
        }
        return out
    }

    static func flat(_ table: [String: (String, String)]) -> [String: [String]] {
        table.mapValues { [$0.0, $0.1] }
    }

    @Test func wordingMatchesDesktop() throws {
        try #require(!Self.i18n.isEmpty, "src/aio_receiver/i18n.py not found")
        #expect(Self.keyed(Self.block("_STATES")) == Self.flat(Vocabulary.states))
        #expect(Self.keyed(Self.block("_ACTIONS")) == Self.flat(Vocabulary.actions))
        #expect(Self.keyed(Self.block("_LAMPS")) == Self.flat(Vocabulary.lamps))
        #expect(Self.pairs(Self.block("_GNSS_QUALITY")) == Vocabulary.gnssQuality.map { [$0.0, $0.1] })
        #expect(Self.pairs(Self.block("_HEALTH")) == Vocabulary.health.map { [$0.0, $0.1] })
        #expect(Self.pairs(Self.block("_INHIBIT")) == Vocabulary.inhibit.map { [$0.0, $0.1] })
        let desktop = Self.keyed(Self.i18n)              // _T has blank lines between its groups
        for (key, value) in Vocabulary.messages {
            #expect(desktop[key] == [value.0, value.1], "\(key)")
        }
    }

    @Test func tablesAreComplete() {
        #expect(Set(Vocabulary.states.keys) == Set(DashboardState.names))
        #expect(Set(Vocabulary.actions.keys) == Set(RequestedAction.names))
        #expect(Vocabulary.health.count == StatusBits.health.count)
        #expect(Vocabulary.inhibit.count == StatusBits.inhibit.count)
        #expect(Vocabulary.gnssQuality.count == StatusBits.gnssQuality.count)
    }

    /// One language at a time: no Chinese in English, no raw protocol codes in either.
    @Test func noMixedLanguages() throws {
        let cjk = try Regex(#"[\p{Han}]"#)
        let code = try Regex(#"\b[A-Z]{3,}_[A-Z_]+\b"#)       // KEEP_STILL_REQUIRED, NAV_STARTING …
        let words = Vocabulary.states.values.map { $0 } + Vocabulary.actions.values.map { $0 }
            + Vocabulary.lamps.values.map { $0 } + Vocabulary.gnssQuality + Vocabulary.health + Vocabulary.inhibit
            + Vocabulary.messages.values.map { $0 }
        for (zh, en) in words {
            #expect(en.firstMatch(of: cjk) == nil, "\(en)")
            #expect(zh.firstMatch(of: code) == nil && en.firstMatch(of: code) == nil, "\(zh) / \(en)")
        }
        let catalog = try JSONSerialization.jsonObject(
            with: Data(contentsOf: Fixtures.folder.deletingLastPathComponent().appendingPathComponent("ios/MyApp/Localizable.xcstrings"))
        ) as? [String: Any]
        let strings = try #require(catalog?["strings"] as? [String: [String: Any]])
        for (key, entry) in strings {
            #expect(key.firstMatch(of: cjk) == nil, "English key has Chinese: \(key)")
            let zh = ((entry["localizations"] as? [String: Any])?["zh-Hant"] as? [String: Any])
                .flatMap { $0["stringUnit"] as? [String: Any] }?["value"] as? String
            #expect(zh != nil, "no 繁中 for \(key)")
            #expect(zh?.firstMatch(of: code) == nil, "\(key)")
        }
    }

    @Test func reasonsReadInOneLanguage() {
        let notReady = VehicleGate.Verdict.notReady(state: 3, inhibit: 1 << 7 | 1 << 4)
        #expect(Vocabulary.reason(notReady, .zhHant) == "狀態不是就緒：保持靜止（GNSS 品質不足、需要保持靜止）")
        #expect(Vocabulary.reason(notReady, .en) == "Status is not ready: Keep still (GNSS quality too low, Must keep still)")
        #expect(Vocabulary.reason(.notReady(state: 6, inhibit: 0), .en) == "Status is not ready: Ready (—)")
        #expect(Vocabulary.reason(.readyNotStable, .zhHant) == "就緒尚未穩定")
        #expect(Vocabulary.word(usable: false, .en) == "Blocked")
        #expect(Vocabulary.actionText(1, .en) == "Keep the vehicle completely still")
        #expect(Vocabulary.lampName(.alignment, .zhHant) == "粗對準")
        #expect(Vocabulary.gnssQualityName(9, .en) == "#9")
    }

    @Test func systemErrorsAreWorded() {
        #expect(Vocabulary.bindError(port: 9000, code: EADDRINUSE, .zhHant) == "無法監聽 0.0.0.0:9000：這個連接埠已被其他程式使用")
        #expect(Vocabulary.bindError(port: 9000, code: EACCES, .en) == "Cannot listen on 0.0.0.0:9000: permission denied")
        #expect(Vocabulary.bindError(port: 1, code: EIO, .en).hasPrefix("Cannot listen on 0.0.0.0:1: system error \(EIO): "))
    }

    @Test func languageSettingResolves() {
        #expect(UILanguage.resolve("en") == .en)
        #expect(UILanguage.resolve("zh-Hant") == .zhHant)
        #expect(UILanguage.resolve(nil) == UILanguage.system)
        #expect(UILanguage.resolve("fr") == UILanguage.system)
        var a = MonitorSettings(), b = a
        b.language = "en"
        #expect(!a.needsRestart(comparedTo: b))         // switching language keeps listening
        a.navPort = 9001
        #expect(a.needsRestart(comparedTo: b))
    }
}

/// Texts the desktop's glossary test does not read: what iOS itself shows from Info.plist, and
/// Chinese written directly in Swift. docs/TERMINOLOGY.zh-TW.md lists the words not to use.
struct SystemTextTests {

    static let repo = Fixtures.folder.deletingLastPathComponent()

    static func read(_ path: String) throws -> String {
        try String(contentsOf: repo.appendingPathComponent(path), encoding: .utf8)
    }

    /// The glossary's 不使用的詞 table: each word not to use, with the words that replace it.
    static func bannedWords() throws -> [(word: String, replacements: [String])] {
        let glossary = try read("docs/TERMINOLOGY.zh-TW.md")
        let table = try #require(glossary.range(of: "## 不使用的詞")).upperBound
        return glossary[table...].split(separator: "\n")
            .filter { $0.hasPrefix("| ") && !$0.hasPrefix("| 不使用") && !$0.hasPrefix("|---") }
            .map { row in row.split(separator: "|", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) } }
            .filter { $0.count > 2 && !$0[1].isEmpty }
            .map { ($0[1], $0[2].components(separatedBy: "、")) }
    }

    static func count(_ word: String, in text: String) -> Int {
        text.components(separatedBy: word).count - 1
    }

    @Test func infoPlistTextIsOneLanguageAtATime() throws {
        let cjk = try Regex(#"[\p{Han}]"#)
        let project = try Self.read("ios/MyApp.xcodeproj/project.pbxproj")
        for line in project.split(separator: "\n") where line.contains("INFOPLIST_KEY_NS") {
            #expect(line.firstMatch(of: cjk) == nil, "Chinese belongs in InfoPlist.xcstrings: \(line)")
        }
        let catalog = try #require(JSONSerialization.jsonObject(
            with: Data(Self.read("ios/MyApp/InfoPlist.xcstrings").utf8)) as? [String: Any])
        let strings = try #require(catalog["strings"] as? [String: [String: Any]])
        #expect(strings["NSLocalNetworkUsageDescription"] != nil)
        for (key, entry) in strings {
            let localizations = entry["localizations"] as? [String: [String: [String: String]]]
            let en = try #require(localizations?["en"]?["stringUnit"]?["value"], "\(key) en")
            let zh = try #require(localizations?["zh-Hant"]?["stringUnit"]?["value"], "\(key) zh-Hant")
            #expect(en.firstMatch(of: cjk) == nil, "\(key)")
            #expect(zh.firstMatch(of: cjk) != nil, "\(key)")
        }
    }

    @Test func glossaryWordsNotUsedOutsideTheCatalog() throws {
        let banned = try Self.bannedWords()
        #expect(banned.contains { $0.word == "阻擋" } && banned.count >= 20)
        let swift = try FileManager.default.subpathsOfDirectory(atPath: Self.repo.appendingPathComponent("ios/MyApp").path)
            .filter { $0.hasSuffix(".swift") }.map { "ios/MyApp/\($0)" }
        for path in swift + ["ios/MyApp/InfoPlist.xcstrings"] {
            let text = try Self.read(path)
            for (word, replacements) in banned {
                // As the glossary says: a banned word inside its replacement (時間戳 in 時間戳記) is fine.
                let inside = replacements.filter { $0.contains(word) }.reduce(0) { $0 + Self.count($1, in: text) }
                #expect(Self.count(word, in: text) == inside, "\(path) uses \(word)")
            }
        }
    }
}

// MARK: - Presentation (the desktop's tests/test_presentation.py, case for case)

/// Packets as the desktop's tests/helpers.py builds them: encode_status with health 0 and
/// nav_age unknown, and the shared nav example with its time stamp changed.
enum Packets {
    static func status(_ seq: UInt32, state: UInt8 = 6, action: UInt8 = 0, inhibit: UInt32 = 0,
                       session: UInt32 = 1) -> [UInt8] {
        var p: [UInt8] = [0x55, 0xAA, 0x05, 36, 0, 1, state, action, 0]
        func le<T: FixedWidthInteger>(_ v: T) { p += withUnsafeBytes(of: v.littleEndian, Array.init) }
        le(session); le(seq); le(UInt64(0)); le(UInt32(0)); le(inhibit)
        p += [0, 0]; le(UInt16(0)); le(UInt16(0xFFFF)); le(UInt16(0))
        p.append(p[2...].reduce(UInt8(0)) { $0 &+ $1 })
        return p
    }

    static func nav(_ time: Double) throws -> [UInt8] {
        var p = Array(bytes(try GateVectors.load().nav_example).dropLast())
        let us = UInt64((time * 1e6).rounded())
        for i in 0..<8 { p[5 + i] = UInt8(truncatingIfNeeded: us >> (8 * UInt64(i))) }
        p.append(p[2...].reduce(UInt8(0)) { $0 &+ $1 })
        return p
    }
}

/// A monitor fed by hand, read the way the store reads it.
struct Feed {
    let engine = MonitorEngine(settings: MonitorSettings())

    /// ready_monitor: 0x05 in `state` (asking for `action`) at 2 Hz and 0x04 at 100 Hz from t=0.
    static func ready(_ seconds: Double = 3.0, state: UInt8 = 6, action: UInt8 = 0) throws -> Feed {
        let f = Feed()
        for i in 0..<Int(seconds * 100) {
            let t = Double(i) / 100
            if i % 50 == 0 {
                f.engine.ingest(Packets.status(UInt32(i / 50 + 1), state: state, action: action), from: "a", at: t)
            }
            f.engine.ingest(try Packets.nav(10 + t), from: "a", at: t)
        }
        return f
    }

    func screen(at now: Double, statusRate: Double = 2.0) -> Screen {
        Screen(snap: engine.snapshot(at: now), navRateHz: 100, statusRateHz: statusRate)
    }
}

struct PresentationTests {
    let zh = UILanguage.zhHant

    @Test func bandKinds() throws {
        #expect(Presentation.band(Feed().screen(at: 0), zh) == .init(kind: .idle, word: "不可用", headline: "還沒收到任何封包"))
        #expect(Presentation.band(try Feed.ready().screen(at: 2.99), zh).kind == .go)
        for (state, kind) in [("KEEP_STILL", SignalKind.wait), ("REFINING", .wait), ("BOOTING", .wait),
                              ("DEGRADED", .stop), ("FAULT", .stop), ("MAINTENANCE", .idle)] {
            let code = UInt8(DashboardState.names.firstIndex(of: state)!)
            #expect(Presentation.band(try Feed.ready(state: code).screen(at: 2.99), zh).kind == kind, "\(state)")
        }
        #expect(Presentation.band(try Feed.ready(1.5).screen(at: 1.49), zh)
                == .init(kind: .wait, word: "不可用", headline: "就緒確認中（需穩定 2 秒）"))
        let stale = Presentation.band(try Feed.ready().screen(at: 3.6), zh)
        #expect(stale.kind == .stop && stale.headline.contains("0x04 中斷"))
        let lost = Presentation.band(try Feed.ready().screen(at: 8.0), zh)
        #expect(lost.kind == .stop && lost.headline.contains("0x05 中斷超過 3 秒"))
        #expect(Presentation.band(try Feed.ready().screen(at: 2.99), .en).word == "Usable")
    }

    @Test func navWithoutStatus() throws {
        let f = Feed()
        f.engine.ingest(try Packets.nav(1.0), from: "a", at: 0)
        #expect(Presentation.band(f.screen(at: 0.1), zh) == .init(kind: .stop, word: "不可用", headline: "沒有狀態封包 0x05"))
    }

    @Test func rail() throws {
        let straight = Presentation.rail(try Feed.ready(state: 4).screen(at: 2.99), zh)
        #expect(straight.at == 2 && straight.mode == .progress)
        let done = Presentation.rail(try Feed.ready().screen(at: 2.99), zh)
        #expect(done.at == 4 && done.mode == .done)
        let settling = Presentation.rail(try Feed.ready(1.5).screen(at: 1.49), zh)
        #expect(settling.at == 4 && settling.mode == .progress && abs(settling.fraction - 0.745) < 0.01)
        let degraded = Presentation.rail(try Feed.ready(state: 7).screen(at: 2.99), zh)
        #expect(degraded.at == 4 && degraded.mode == .lost)
        let fault = Presentation.rail(try Feed.ready(state: 8).screen(at: 2.99), zh)
        #expect(fault.at == -1 && fault.mode == .fault)
        #expect(Presentation.rail(try Feed.ready().screen(at: 8.0), zh).mode == .none)      // 0x05 timed out
    }

    @Test func linksAndAges() throws {
        let s = try Feed.ready().screen(at: 2.99)
        let nav = Presentation.navLink(s, zh)
        #expect(nav.kind == .go && nav.text.contains("Hz"))
        #expect(Presentation.statusLink(s, zh) == .init(kind: .go, text: "2.0 Hz   0.5 秒前"))
        var gone = s
        gone.snap.navAge = (gone.snap.navAge ?? 0) + 75
        gone.snap.statusAge = (gone.snap.statusAge ?? 0) + 75
        #expect(Presentation.navLink(gone, zh) == .init(kind: .stop, text: "中斷 1 分 15 秒"))
        var noStatus = s
        noStatus.snap.status = nil
        #expect(Presentation.statusLink(noStatus, zh) == .init(kind: .idle, text: "沒有資料"))
        let f = Feed()
        f.engine.ingest(Packets.status(1), from: "a", at: 0)
        #expect(Presentation.navLink(f.screen(at: 0.1), zh) == .init(kind: .idle, text: "沒有資料"))
        #expect(Presentation.fmtAge(4000, zh) == "1 小時 6 分" && Presentation.fmtDur(3725) == "1:02:05")
        #expect(Presentation.fmtAge(75, .en) == "1 min 15 s")
    }

    @Test func guideTellsNeverFromLost() throws {
        #expect(Presentation.guide(Feed().screen(at: 0), zh) == nil)          // phone: setup help is in Settings
        let f = Feed()
        f.engine.ingest(try Packets.nav(1.0), from: "a", at: 0)
        let never = f.screen(at: 0.1)
        let g = try #require(Presentation.guide(never, zh))
        #expect(g.kind == .plate && g.title == "開啟儀表板的 0x05")
        #expect(Presentation.statusLink(never, zh) == .init(kind: .stop, text: "從未收到"))
        let lost = try #require(Presentation.guide(try Feed.ready().screen(at: 8.0), zh))
        #expect(lost.title == "檢查儀表板與網路" && lost.sub.contains("已中斷 5.5 秒") && lost.sub.contains("收到 6 包"))
        #expect(Presentation.guide(try Feed.ready().screen(at: 2.99), zh) == .init(kind: .quiet, title: "不需動作", sub: ""))
        #expect(Presentation.guide(try Feed.ready(state: 8, action: 4).screen(at: 2.99), zh)?.kind == .danger)
    }

    @Test func blockingConditions() throws {
        #expect(Presentation.blocking(try Feed.ready().screen(at: 8.0), zh) == nil)       // no current 0x05: unknown
        #expect(Presentation.blocking(try Feed.ready().screen(at: 2.99), zh) == [])
        let still: UInt32 = 1 << 7 | 1 << 9                 // KEEP_STILL_REQUIRED, FINE_ALIGNMENT_REQUIRED
        let f = Feed()
        f.engine.ingest(Packets.status(1, state: 3, inhibit: still), from: "a", at: 0)
        #expect(Presentation.blocking(f.screen(at: 0.1), zh)
                == [.init(text: "需要保持靜止", expected: true), .init(text: "需要精對準", expected: true)])
        f.engine.ingest(Packets.status(2, state: 7, inhibit: still | 1 << 12), from: "a", at: 0.2)
        #expect(Presentation.blocking(f.screen(at: 0.3), zh)?.map(\.expected) == [false, false, false])
    }

    @Test func conditionsUnmetFirst() throws {
        #expect(Presentation.conditions(Feed().screen(at: 0), zh).isEmpty)
        let rows = Presentation.conditions(try Feed.ready().screen(at: 2.99), zh)
        #expect(rows.count == StatusBits.health.count)
        let met = rows.map(\.met)
        #expect(met == met.sorted { !$0 && $1 })            // every unmet before every met
    }
}
