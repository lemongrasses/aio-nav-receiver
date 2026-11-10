//
//  Presentation.swift
//  MyApp
//
//  What the screen says, as pure functions of a snapshot: a port of the desktop's
//  src/aio_receiver/ui/presentation.py (layout C). PresentationTests repeats its test cases.
//
//  Colour carries meaning only:
//    go    可用 - the output may be used
//    wait  不可用, but as expected: alignment in progress or ready still settling; follow the instruction
//    stop  不可用 because something is wrong: data lost, fault, stale, flags
//    idle  不可用 with nothing to judge yet, or AIO NAV stopped on purpose
//

import Foundation

nonisolated enum SignalKind: String, Sendable {
    case go, wait, stop, idle
}

/// Everything the presentation functions read: the gate's snapshot, the measured rates and the
/// rule thresholds in use.
nonisolated struct Screen: Sendable {
    var snap = MonitorSnapshot()
    var navRateHz = 0.0
    var statusRateHz = 0.0
    var statusTimeout = 3.0
    var readyStable = 2.0
    var navMaxAge = 0.5

    var nothingReceived: Bool { snap.counts.nav == 0 && snap.counts.status == 0 }
    var statusFresh: Bool { snap.status != nil && (snap.statusAge ?? .infinity) <= statusTimeout }
    var stateName: String? { snap.status.map(\.stateName) }
}

nonisolated enum Presentation {
    static let startup: Set<String> = ["BOOTING", "CHECKING", "NAV_STARTING"]
    static let aligning: Set<String> = ["KEEP_STILL", "MOVE_STRAIGHT", "REFINING"]
    /// Blocking conditions that are simply the next alignment steps while AIO NAV starts or aligns.
    static let stepBits: Set<String> = ["BOOT_IN_PROGRESS", "KEEP_STILL_REQUIRED", "MOVE_STRAIGHT_REQUIRED",
                                        "FINE_ALIGNMENT_REQUIRED"]
    static let dangerActions: Set<String> = ["SAFE_STOP", "SERVICE_REQUIRED"]
    /// The alignment as a route: (label key, states at that station). The last station is READY.
    static let stations: [(key: String, states: Set<String>)] = [
        ("station.start", startup), ("station.still", ["KEEP_STILL"]), ("station.straight", ["MOVE_STRAIGHT"]),
        ("station.fine", ["REFINING"]), ("station.usable", ["READY"]),
    ]
    static let stateHeadline = [
        "BOOTING": "band.startup", "CHECKING": "band.startup", "NAV_STARTING": "band.startup",
        "KEEP_STILL": "band.stage1", "MOVE_STRAIGHT": "band.stage2", "REFINING": "band.stage3",
        "READY": "band.ready_inhibit", "DEGRADED": "band.degraded", "FAULT": "band.fault",
        "MAINTENANCE": "band.maintenance",
    ]

    // MARK: Band

    struct Band: Equatable, Sendable {
        let kind: SignalKind
        let word: String        // 可用 | 不可用
        let headline: String    // one short line: why, in the operator's words
    }

    static func band(_ s: Screen, _ lang: UILanguage) -> Band {
        let blocked = Vocabulary.word(usable: false, lang)
        func stop(_ key: String, _ args: [String: Any] = [:]) -> Band {
            Band(kind: .stop, word: blocked, headline: Vocabulary.t(key, lang, args))
        }
        switch s.snap.verdict {
        case .usable:
            return Band(kind: .go, word: Vocabulary.word(usable: true, lang), headline: Vocabulary.t("band.usable", lang))
        case .noStatus:
            if s.nothingReceived {
                return Band(kind: .idle, word: blocked, headline: Vocabulary.t("band.nothing", lang))
            }
            if s.snap.counts.status == 0 {
                return stop("band.no_status")
            }
            return stop("band.status_lost", ["s": s.statusTimeout])
        case let .notReady(code, _):
            let name = DashboardState.name(of: code)
            let headline = stateHeadline[name].map { Vocabulary.t($0, lang) }
                ?? Vocabulary.t("band.state", lang, ["state": name])
            let kind: SignalKind = name == "MAINTENANCE" ? .idle
                : (startup.contains(name) || aligning.contains(name)) ? .wait : .stop
            return Band(kind: kind, word: blocked, headline: headline)
        case .readyNotStable:
            return Band(kind: .wait, word: blocked, headline: Vocabulary.t("band.settling", lang, ["s": s.readyStable]))
        case .navTooOld:
            return s.snap.nav == nil ? stop("band.no_nav") : stop("band.nav_lost", ["s": s.navMaxAge])
        case .navTimeBackwards:
            return stop("band.nav_backwards")
        case .notAligned:
            return stop("band.not_aligned")
        case .notFinite:
            return stop("band.not_finite")
        }
    }

    // MARK: Route

    enum RailMode: String, Sendable {
        case progress, done, lost, fault, stopped, none
    }

    /// Where the alignment stands. `at` is the current station (-1 = off the route).
    struct Rail: Equatable, Sendable {
        let at: Int
        let mode: RailMode
        let fraction: Double    // ready settling: 0...1 of the stability time
        let note: String        // shown under the route
    }

    static func rail(_ s: Screen, _ lang: UILanguage) -> Rail {
        guard s.statusFresh, let name = s.stateName else {
            return Rail(at: -1, mode: .none, fraction: 0, note: s.nothingReceived ? "" : Vocabulary.t("rail.no_status", lang))
        }
        if name == "READY" {
            guard let held = s.snap.readyFor else {
                return Rail(at: 4, mode: .progress, fraction: 0, note: Vocabulary.t("rail.ready_inhibit", lang))
            }
            let f = s.readyStable <= 0 ? 1 : max(0, min(held / s.readyStable, 1))
            return Rail(at: 4, mode: f >= 1 ? .done : .progress, fraction: f, note: "")
        }
        if let i = stations.firstIndex(where: { $0.states.contains(name) }) {
            return Rail(at: i, mode: .progress, fraction: 0, note: "")
        }
        switch name {
        case "DEGRADED": return Rail(at: 4, mode: .lost, fraction: 0, note: Vocabulary.t("rail.degraded", lang))
        case "FAULT": return Rail(at: -1, mode: .fault, fraction: 0, note: Vocabulary.t("rail.fault", lang))
        case "MAINTENANCE": return Rail(at: -1, mode: .stopped, fraction: 0, note: Vocabulary.t("rail.stopped", lang))
        default: return Rail(at: -1, mode: .none, fraction: 0, note: Vocabulary.t("rail.unknown", lang, ["state": name]))
        }
    }

    // MARK: Guidance

    enum GuideKind: String, Sendable {
        case plate      // the blue instruction sign
        case danger     // the same sign in red
        case quiet      // nothing to do: one line of grey text, no sign
    }

    struct Guide: Equatable, Sendable {
        let kind: GuideKind
        let title: String
        let sub: String
    }

    /// The one thing the operator does now, under the verdict; nil before anything arrives (the
    /// setup help lives in Settings on the phone).
    static func guide(_ s: Screen, _ lang: UILanguage) -> Guide? {
        if s.nothingReceived {
            return nil
        }
        guard s.statusFresh, let status = s.snap.status else {
            if s.snap.counts.status == 0 || s.snap.status == nil {
                return Guide(kind: .plate, title: Vocabulary.t("guide.no_status", lang),
                             sub: Vocabulary.t("guide.no_status_sub", lang))
            }
            return Guide(kind: .plate, title: Vocabulary.t("guide.status_lost", lang),
                         sub: Vocabulary.t("guide.status_lost_sub", lang,
                                           ["age": fmtAge(s.snap.statusAge ?? 0, lang), "n": s.snap.counts.status]))
        }
        let action = status.actionName
        let text = Vocabulary.actionText(status.requestedAction, lang)
        if action == "NONE" {
            return Guide(kind: .quiet, title: text, sub: "")
        }
        return Guide(kind: dangerActions.contains(action) ? .danger : .plate, title: text, sub: "")
    }

    // MARK: Blocking conditions and conditions met

    struct Chip: Equatable, Sendable {
        let text: String
        let expected: Bool      // a normal alignment step (amber), not a problem (red)
    }

    /// The 0x05 blocking conditions, or nil when there is no current 0x05 to say.
    static func blocking(_ s: Screen, _ lang: UILanguage) -> [Chip]? {
        guard s.statusFresh, let status = s.snap.status else { return nil }
        let stepping = startup.contains(status.stateName) || aligning.contains(status.stateName)
        return StatusBits.inhibit.indices.filter { status.inhibitFlags >> UInt32($0) & 1 == 1 }.map { bit in
            Chip(text: lang.pick(Vocabulary.inhibit[bit]),
                 expected: stepping && stepBits.contains(StatusBits.inhibit[bit]))
        }
    }

    /// (condition, met) for every 0x05 health flag, the unmet first; empty before any 0x05.
    static func conditions(_ s: Screen, _ lang: UILanguage) -> [(name: String, met: Bool)] {
        guard let status = s.snap.status else { return [] }
        let rows = Vocabulary.health.indices.map { bit in
            (name: lang.pick(Vocabulary.health[bit]), met: status.healthFlags >> UInt32(bit) & 1 == 1)
        }
        return rows.filter { !$0.met } + rows.filter(\.met)     // bit order kept within each group
    }

    // MARK: Streams

    struct Link: Equatable, Sendable {
        let kind: SignalKind    // go | stop | idle
        let text: String
    }

    static func navLink(_ s: Screen, _ lang: UILanguage) -> Link {
        guard s.snap.nav != nil, let age = s.snap.navAge else {
            return Link(kind: .idle, text: Vocabulary.t("link.none", lang))
        }
        if age > s.navMaxAge {
            return Link(kind: .stop, text: Vocabulary.t("link.lost", lang, ["age": fmtAge(age, lang)]))
        }
        return Link(kind: .go, text: Vocabulary.t("link.nav", lang, ["rate": s.navRateHz, "ms": age * 1000]))
    }

    static func statusLink(_ s: Screen, _ lang: UILanguage) -> Link {
        guard s.snap.status != nil, let age = s.snap.statusAge else {
            if s.snap.nav != nil && s.snap.counts.status == 0 {      // 0x04 arrives, 0x05 never has
                return Link(kind: .stop, text: Vocabulary.t("link.never", lang))
            }
            return Link(kind: .idle, text: Vocabulary.t("link.none", lang))
        }
        if age > s.statusTimeout {
            return Link(kind: .stop, text: Vocabulary.t("link.lost", lang, ["age": fmtAge(age, lang)]))
        }
        return Link(kind: .go, text: Vocabulary.t("link.status", lang, ["rate": s.statusRateHz, "s": age]))
    }

    // MARK: Times

    static func fmtAge(_ seconds: Double, _ lang: UILanguage) -> String {
        if seconds < 60 {
            return Vocabulary.t("age.s", lang, ["s": seconds])
        }
        if seconds < 3600 {
            return Vocabulary.t("age.ms", lang, ["m": Int(seconds / 60), "s": Int(seconds.truncatingRemainder(dividingBy: 60))])
        }
        return Vocabulary.t("age.hm", lang, ["h": Int(seconds / 3600),
                                              "m": Int(seconds.truncatingRemainder(dividingBy: 3600) / 60)])
    }

    static func fmtDur(_ seconds: Double) -> String {
        let s = Int(max(seconds, 0))
        return String(format: "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
    }
}
