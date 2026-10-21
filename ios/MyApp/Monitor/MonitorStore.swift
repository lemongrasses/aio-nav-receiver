//
//  MonitorStore.swift
//  MyApp
//
//  The UI's view of the monitor: a snapshot every 100 ms (spec: recompute the verdict every
//  100 ms) plus the last ten minutes of history for the charts and the map.
//

import Foundation
import Observation
import UIKit

struct TimelineSegment: Identifiable {
    let id: Int
    var start: Date
    var end: Date
    let usable: Bool
    /// Dashboard state name, or "NO_STATUS" while there is no current 0x05.
    let state: String
}

/// Navigation values sampled at 2 Hz while 0x04 is arriving.
struct NavSample: Identifiable {
    let id: Int
    let date: Date
    /// Increases after a gap so chart lines break instead of bridging it.
    let run: Int
    let latitude: Double
    let longitude: Double
    let height: Double
    let speed: Double
    let heading: Double
    let sigmaNorth: Double
    let sigmaEast: Double
    let sigmaDown: Double
    let sigmaHeading: Double
}

/// Link health sampled at 2 Hz whether or not anything arrives.
struct LinkSample: Identifiable {
    let id: Int
    let date: Date
    let rateHz: Double
    let navAgeMs: Double?
}

struct LocalAddress: Hashable, Identifiable {
    let interface: String
    let address: String
    var id: String { interface + address }
}

@Observable
final class MonitorStore {
    static let historyLimit: TimeInterval = 10 * 60
    static let sampleInterval = 0.5

    private(set) var settings: MonitorSettings
    private(set) var snapshot = MonitorSnapshot()
    private(set) var receiveRateHz = 0.0
    private(set) var usableSeconds = 0.0
    private(set) var isListening = false
    private(set) var listenFailure: UDPReceiver.BindError?
    private(set) var localAddresses: [LocalAddress] = []
    private(set) var timeline: [TimelineSegment] = []
    private(set) var navSamples: [NavSample] = []
    private(set) var linkSamples: [LinkSample] = []

    private var engine: MonitorEngine
    private var receiver: UDPReceiver?
    private var tickTask: Task<Void, Never>?
    private var lastTick: Double?
    private var lastSampleAt = 0.0
    private var rateWindow: [(time: Double, count: Int)] = []
    private var nextID = 0
    private var run = 0

    init() {
        let saved = MonitorSettings.load()
        settings = saved
        engine = MonitorEngine(settings: saved)
    }

    func start() {
        guard tickTask == nil else { return }
        do {
            receiver = try UDPReceiver(ports: settings.ports, handler: Self.handler(for: engine))
            isListening = true
            listenFailure = nil
        } catch {
            isListening = false
            listenFailure = error as? UDPReceiver.BindError ?? UDPReceiver.BindError(port: settings.navPort, code: EIO)
        }
        refreshLocalAddresses()
        tickTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(100))
                self?.tick()
            }
        }
        updateIdleTimer()
    }

    func stop() {
        receiver?.stop()
        receiver = nil
        tickTask?.cancel()
        tickTask = nil
        isListening = false
        lastTick = nil
        rateWindow = []
        updateIdleTimer()
    }

    /// Saves new settings; a change to ports, ids, source or rules restarts with a fresh gate.
    func apply(_ new: MonitorSettings) {
        let restart = new.needsRestart(comparedTo: settings)
        settings = new
        new.save()
        if restart {
            reset()
        } else {
            updateIdleTimer()
        }
    }

    /// The language shown now: the setting, or the iPhone's language.
    var language: UILanguage { UILanguage.resolve(settings.language) }

    /// Switches the language at once; listening carries on.
    func setLanguage(_ code: String?) {
        var new = settings
        new.language = code
        apply(new)
    }

    /// Starts over with a fresh gate, statistics and history.
    func reset() {
        stop()
        engine = MonitorEngine(settings: settings)
        clearHistory()
        start()
    }

    func clearHistory() {
        timeline = []
        navSamples = []
        linkSamples = []
        usableSeconds = 0
        run += 1
    }

    func refreshLocalAddresses() {
        localAddresses = UDPReceiver.localAddresses().map { LocalAddress(interface: $0.interface, address: $0.address) }
    }

    /// Built outside the main actor: the receiver thread calls it.
    nonisolated private static func handler(for engine: MonitorEngine) -> UDPReceiver.Handler {
        { bytes, sender, arrival in engine.ingest(bytes, from: sender, at: arrival) }
    }

    private func updateIdleTimer() {
        UIApplication.shared.isIdleTimerDisabled = settings.keepScreenOn && tickTask != nil
    }

    private func makeID() -> Int {
        nextID += 1
        return nextID
    }

    private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let date = Date()
        let snap = engine.snapshot(at: now)
        if let lastTick, snap.verdict.isUsable {
            usableSeconds += now - lastTick
        }
        lastTick = now
        snapshot = snap

        rateWindow.append((now, snap.counts.nav))
        rateWindow.removeAll { now - $0.time > 1.0 }
        if let first = rateWindow.first, now - first.time > 0.05 {
            receiveRateHz = Double(snap.counts.nav - first.count) / (now - first.time)
        }

        recordTimeline(snap, at: date)
        if now - lastSampleAt >= Self.sampleInterval {
            lastSampleAt = now
            recordSamples(snap, at: date)
            trimHistory(before: date.addingTimeInterval(-Self.historyLimit))
        }
    }

    private func recordTimeline(_ snap: MonitorSnapshot, at date: Date) {
        let usable = snap.verdict.isUsable
        let state = snap.verdict == .noStatus ? "NO_STATUS" : (snap.status?.stateName ?? "NO_STATUS")
        if let last = timeline.last, last.usable == usable, last.state == state {
            timeline[timeline.count - 1].end = date
        } else {
            let start = timeline.last?.end ?? date
            timeline.append(TimelineSegment(id: makeID(), start: start, end: date, usable: usable, state: state))
        }
    }

    private func recordSamples(_ snap: MonitorSnapshot, at date: Date) {
        linkSamples.append(LinkSample(id: makeID(), date: date, rateHz: receiveRateHz,
                                      navAgeMs: snap.navAge.map { min($0 * 1000, 5000) }))
        guard let n = snap.nav, let age = snap.navAge, age < 1.0, n.isFinite,
              abs(n.latitude) <= 90, abs(n.longitude) <= 180 else { return }
        if let last = navSamples.last, date.timeIntervalSince(last.date) > 3 * Self.sampleInterval {
            run += 1
        }
        navSamples.append(NavSample(id: makeID(), date: date, run: run,
                                    latitude: n.latitude, longitude: n.longitude, height: Double(n.height),
                                    speed: n.groundSpeed, heading: n.heading360,
                                    sigmaNorth: Double(n.positionNorthStd), sigmaEast: Double(n.positionEastStd),
                                    sigmaDown: Double(n.heightStd), sigmaHeading: Double(n.headingStd)))
    }

    private func trimHistory(before cutoff: Date) {
        timeline.removeAll { $0.end < cutoff }
        navSamples.removeAll { $0.date < cutoff }
        linkSamples.removeAll { $0.date < cutoff }
    }
}
