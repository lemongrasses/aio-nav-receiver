//
//  MonitorSettings.swift
//  MyApp
//

import Foundation

/// Receiver settings (spec "設定"); stored as JSON in UserDefaults.
nonisolated struct MonitorSettings: Codable, Equatable, Sendable {
    /// Must match the port of `output_udp` in aio_nav.yaml.
    var navPort: UInt16 = 9000
    /// Only when `status_udp.destination` points at another port; nil = same as navPort.
    var statusPort: UInt16?
    /// `status_udp.message_id`.
    var statusMessageID: UInt8 = AIO.defaultStatusMessageID
    /// Only packets from this IPv4 address are used; others are only counted. Empty = any.
    var allowedSourceIP = ""
    var statusTimeout = 3.0
    var readyStable = 2.0
    var navMaxAge = 0.5
    var keepScreenOn = true

    var ports: [UInt16] { [navPort, statusPort ?? navPort] }
    var allowedSource: String? {
        let ip = allowedSourceIP.trimmingCharacters(in: .whitespaces)
        return ip.isEmpty ? nil : ip
    }

    /// Settings whose change needs a new receiver and gate (and so clears the history).
    func needsRestart(comparedTo other: MonitorSettings) -> Bool {
        var a = self, b = other
        a.keepScreenOn = false
        b.keepScreenOn = false
        return a != b
    }

    private static let key = "monitorSettings"

    static func load() -> MonitorSettings {
        guard let data = UserDefaults.standard.data(forKey: key),
              let settings = try? JSONDecoder().decode(MonitorSettings.self, from: data) else { return MonitorSettings() }
        return settings
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: Self.key)
        }
    }
}
