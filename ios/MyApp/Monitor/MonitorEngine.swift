//
//  MonitorEngine.swift
//  MyApp
//
//  Owns the gate. The receiver thread feeds it every datagram as it arrives; the UI asks for
//  a snapshot ten times a second. A mutex keeps the two apart.
//

import Foundation
import Synchronization

nonisolated struct PacketCounts: Equatable, Sendable {
    var nav = 0
    var status = 0
    /// Datagrams from a source other than the allowed IP; counted, never used.
    var otherSource = 0
    var gate = VehicleGate.Counters()
}

nonisolated struct MonitorSnapshot: Sendable {
    var verdict: VehicleGate.Verdict = .noStatus
    var nav: NavSolution?
    var navAge: Double?
    var status: StatusPacket?
    var statusAge: Double?
    var counts = PacketCounts()
    var lastSender: String?
}

nonisolated final class MonitorEngine: Sendable {
    private struct Core {
        var gate: VehicleGate
        var allowedSource: String?
        var counts = PacketCounts()
        var lastSender: String?
    }

    private let core: Mutex<Core>

    init(settings: MonitorSettings) {
        let gate = VehicleGate(statusTimeout: settings.statusTimeout, statusStable: settings.readyStable,
                               navMaxAge: settings.navMaxAge, statusMessageID: settings.statusMessageID)
        core = Mutex(Core(gate: gate, allowedSource: settings.allowedSource))
    }

    func ingest(_ bytes: [UInt8], from sender: String, at arrival: Double) {
        core.withLock { c in
            if let allowed = c.allowedSource, sender != allowed {
                c.counts.otherSource += 1
                return
            }
            c.lastSender = sender
            switch c.gate.feed(bytes, at: arrival) {
            case .nav: c.counts.nav += 1
            case .status: c.counts.status += 1
            case nil: break
            }
        }
    }

    func snapshot(at now: Double) -> MonitorSnapshot {
        core.withLock { c in
            var counts = c.counts
            counts.gate = c.gate.counters
            return MonitorSnapshot(verdict: c.gate.verdict(at: now),
                                   nav: c.gate.nav, navAge: c.gate.navAt.map { now - $0 },
                                   status: c.gate.status, statusAge: c.gate.statusAt.map { now - $0 },
                                   counts: counts, lastSender: c.lastSender)
        }
    }
}
