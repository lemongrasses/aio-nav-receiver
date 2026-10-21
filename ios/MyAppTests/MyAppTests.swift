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
