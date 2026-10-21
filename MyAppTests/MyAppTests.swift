//
//  MyAppTests.swift
//  MyAppTests
//
//  Fixtures/gate_vectors.json comes from tools/make_gate_vectors.py, which builds the packets
//  with web_monitor's own encoders and records what its reference VehicleGate decided.
//

import Foundation
import Testing
@testable import MyApp

private final class BundleToken {}

struct GateVectors: Decodable {
    struct Step: Decodable {
        let t: Double
        let packets: [String]
        let usable: Bool
        let reason: String
        let lost: Int
        let reordered: Int
        let bad: Int
    }

    let golden_status: String
    let nav_example: String
    let steps: [Step]

    static func load() throws -> GateVectors {
        let url = try #require(Bundle(for: BundleToken.self).url(forResource: "gate_vectors", withExtension: "json"))
        return try JSONDecoder().decode(GateVectors.self, from: Data(contentsOf: url))
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
}

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
        var bad = good
        bad[155] &+= 1
        #expect(NavSolution(bytes: bad) == nil)
    }
}

struct VehicleGateTests {

    /// The spec's acceptance test: the same packet stream must give the same verdict as
    /// web_monitor's VehicleGate at every step.
    @Test func matchesReferenceGateAtEveryStep() throws {
        let vectors = try GateVectors.load()
        #expect(vectors.steps.count > 400)
        var gate = VehicleGate()
        for step in vectors.steps {
            for packet in step.packets {
                gate.feed(bytes(packet), at: step.t)
            }
            let verdict = gate.verdict(at: step.t)
            #expect(verdict.kind == step.reason, "t=\(step.t)")
            #expect(verdict.isUsable == step.usable, "t=\(step.t)")
            #expect(gate.counters.lost == step.lost, "t=\(step.t)")
            #expect(gate.counters.reordered + gate.counters.twoSenders == step.reordered, "t=\(step.t)")
            #expect(gate.counters.bad == step.bad, "t=\(step.t)")
        }
        #expect(gate.counters.twoSenders == 1)
    }

    @Test func blockedUntilStatusArrives() {
        let gate = VehicleGate()
        #expect(gate.verdict(at: 100) == .noStatus)
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
    }
}
