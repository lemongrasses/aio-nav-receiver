//
//  VehicleGate.swift
//  MyApp
//
//  When may the 0x04 navigation data be used? The same rules as the desktop app's
//  src/aio_receiver/core/gate.py (the spec); fixtures/gate_vectors.json holds both to it.
//
//  1. Blocked by default. A valid 0x05 must have arrived within statusTimeout; a bad checksum,
//     an unknown version or a new session_id clears the authorisation at once.
//  2. The status must say READY with inhibit_flags == 0 continuously for statusStable, in the
//     same session.
//  3. The newest 0x04 must be at most navMaxAge old, carry the ALIGN, HEADING and FINE flags,
//     have a time stamp that moves forward, and only finite values.
//  4. Sequence numbers count lost and reordered status packets; one lost packet never blocks.
//     A sequence more than `reorderWindow` behind means two senders in one session: clear,
//     and start over from that packet. (web_monitor's VehicleGate only ignores it.)
//
//  Pure: feed datagrams with their arrival time (a monotonic clock), ask verdict(at:).
//

import Foundation

nonisolated struct VehicleGate: Sendable {
    nonisolated enum PacketKind: Sendable {
        case status, nav
    }

    nonisolated enum Verdict: Equatable, Sendable {
        case usable
        case noStatus
        case notReady(state: UInt8, inhibit: UInt32)
        case readyNotStable
        case navTooOld
        case navTimeBackwards
        case notAligned
        case notFinite

        var isUsable: Bool { self == .usable }
    }

    nonisolated struct Counters: Equatable, Sendable {
        var lost = 0
        /// Older or duplicate status packets within the reorder window; content ignored.
        var reordered = 0
        /// Status packets more than `reorderWindow` behind: a second sender in the same
        /// session. Each one clears the authorisation.
        var twoSenders = 0
        var bad = 0
    }

    /// Sequence numbers at most this far back count as reordered, beyond it as a second sender.
    static let reorderWindow: UInt32 = 5

    var statusTimeout: Double = 3.0
    var statusStable: Double = 2.0
    var navMaxAge: Double = 0.5
    var statusMessageID: UInt8 = AIO.defaultStatusMessageID

    private(set) var status: StatusPacket?
    private(set) var statusAt: Double?
    private(set) var readySince: Double?
    private(set) var session: UInt32?
    private(set) var nav: NavSolution?
    private(set) var navAt: Double?
    private(set) var navTimeBackwards = false
    private(set) var counters = Counters()

    init(statusTimeout: Double = 3.0, statusStable: Double = 2.0, navMaxAge: Double = 0.5,
         statusMessageID: UInt8 = AIO.defaultStatusMessageID) {
        self.statusTimeout = statusTimeout
        self.statusStable = statusStable
        self.navMaxAge = navMaxAge
        self.statusMessageID = statusMessageID
    }

    /// Takes one datagram. Returns what it was, or nil when it is not a valid packet.
    @discardableResult
    mutating func feed(_ data: [UInt8], at now: Double) -> PacketKind? {
        if AIO.isFrame(data, id: statusMessageID) {
            guard let s = StatusPacket(bytes: data, messageID: statusMessageID) else {
                counters.bad += 1
                clear()                                   // broken or unknown status: stop trusting
                return nil
            }
            if let session, s.sessionID != session {
                clear()                                   // the dashboard restarted: start over
            } else if let previous = status {
                let gap = s.sequence &- previous.sequence
                if gap == 0 || gap > 0x7FFF_FFFF {
                    if previous.sequence &- s.sequence <= Self.reorderWindow {
                        counters.reordered += 1
                        return .status                    // old or duplicate: ignore its content
                    }
                    counters.twoSenders += 1
                    clear()                               // two senders in one session: start over from this one
                } else {
                    counters.lost += Int(gap - 1)
                }
            }
            session = s.sessionID
            status = s
            statusAt = now
            if s.state == DashboardState.ready.rawValue && s.inhibitFlags == 0 {
                if readySince == nil {
                    readySince = now
                }
            } else {
                readySince = nil
            }
            return .status
        }
        if AIO.isFrame(data, id: AIO.navMessageID) {
            guard let n = NavSolution(bytes: data) else {
                counters.bad += 1
                return nil
            }
            navTimeBackwards = nav.map { n.time <= $0.time } ?? false
            nav = n
            navAt = now
            return .nav
        }
        counters.bad += 1
        return nil
    }

    func verdict(at now: Double) -> Verdict {
        guard let status, let statusAt, now - statusAt <= statusTimeout else { return .noStatus }
        guard let readySince else { return .notReady(state: status.state, inhibit: status.inhibitFlags) }
        if now - readySince < statusStable { return .readyNotStable }
        guard let nav, let navAt, now - navAt <= navMaxAge else { return .navTooOld }
        if navTimeBackwards { return .navTimeBackwards }
        if !nav.isAligned { return .notAligned }
        if !nav.isFinite { return .notFinite }
        return .usable
    }

    /// The earliest time after `after` at which the verdict can change without a new packet
    /// (a timeout or the READY settling time running out).
    func nextDeadline(after: Double) -> Double? {
        var times: [Double] = []
        if status != nil, let statusAt {
            times.append(statusAt + statusTimeout)
            if let readySince {
                times.append(readySince + statusStable)
            }
        }
        if nav != nil, let navAt {
            times.append(navAt + navMaxAge)
        }
        return times.filter { $0 > after }.min()
    }

    private mutating func clear() {
        status = nil
        statusAt = nil
        readySince = nil
        session = nil
    }
}
