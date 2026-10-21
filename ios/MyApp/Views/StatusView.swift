//
//  StatusView.swift
//  MyApp
//

import SwiftUI

struct StatusView: View {
    @Environment(MonitorStore.self) private var store

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    VerdictBanner(snapshot: store.snapshot)
                    if let failure = store.listenFailure {
                        ListenErrorCard(failure: failure)
                    }
                    NavigationCard(snapshot: store.snapshot, rateHz: store.receiveRateHz)
                    StatusPacketCard(snapshot: store.snapshot)
                    StatisticsCard(counts: store.snapshot.counts, usableSeconds: store.usableSeconds)
                    ListeningFooter()
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("AIO NAV Receiver")
        }
    }
}

struct VerdictBanner: View {
    let snapshot: MonitorSnapshot
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        let usable = snapshot.verdict.isUsable
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center) {
                Image(systemName: usable ? "checkmark.shield.fill" : "xmark.octagon.fill")
                    .font(.system(size: 40))
                    .contentTransition(.symbolEffect(.replace))
                Text(verbatim: Vocabulary.word(usable: usable, lang))
                    .font(.largeTitle.bold())
                Spacer()
                if let status = snapshot.status {
                    Text(verbatim: Vocabulary.stateName(status.state, lang))
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(.white.opacity(0.22), in: Capsule())
                }
            }
            if !usable {
                Text(verbatim: Vocabulary.reason(snapshot.verdict, lang))
                    .font(.title3.weight(.semibold))
            }
            if let status = snapshot.status, status.requestedAction != RequestedAction.none.rawValue {
                Label {
                    Text(verbatim: Vocabulary.actionText(status.requestedAction, lang))
                } icon: {
                    Image(systemName: "person.wave.2.fill")
                }
                .font(.headline)
                .padding(.top, 4)
            }
        }
        .foregroundStyle(.white)
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(usable ? Color.green.gradient : Color.red.gradient, in: .rect(cornerRadius: 24))
        .animation(.snappy, value: usable)
        .accessibilityElement(children: .combine)
    }
}

struct ListenErrorCard: View {
    let failure: UDPReceiver.BindError
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        Card(title: "Cannot listen", systemImage: "exclamationmark.triangle.fill") {
            Text(verbatim: Vocabulary.bindError(port: failure.port, code: failure.code, lang))
                .font(.callout)
            Text("Another app may be using this port. Change the port in Settings.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .foregroundStyle(.orange)
    }
}

struct NavigationCard: View {
    let snapshot: MonitorSnapshot
    let rateHz: Double
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        Card(title: "Navigation 0x04", systemImage: "location.north.circle") {
            if let n = snapshot.nav {
                InfoRow("Latitude", Format.number(n.latitude, 8, unit: "°"))
                InfoRow("Longitude", Format.number(n.longitude, 8, unit: "°"))
                InfoRow("Height", Format.number(Double(n.height), 2, unit: "m"))
                InfoRow("Heading", Format.number(n.heading360, 1, unit: "°"))
                InfoRow("Ground speed", Format.number(n.groundSpeed, 2, unit: "m/s") + "  ("
                        + Format.number(n.groundSpeed * 3.6, 1, unit: "km/h") + ")")
                InfoRow("Roll / pitch", Format.number(Double(n.roll), 2) + " / " + Format.number(Double(n.pitch), 2, unit: "°"))
                InfoRow("Position σ N / E / D", [n.positionNorthStd, n.positionEastStd, n.heightStd]
                    .map { Format.number(Double($0), 3) }.joined(separator: " / ") + " m")
                InfoRow("Heading σ", Format.number(Double(n.headingStd), 3, unit: "°"))
                InfoRow("Data age", snapshot.navAge.map { Format.number($0 * 1000, 0, unit: "ms") } ?? "—")
                InfoRow("Receive rate", Format.number(rateHz, 1, unit: "Hz"))
                Divider()
                Text("Alignment")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                FlowLayout {
                    ForEach([NavFlag.alignment, .headingValid, .fineAlignment], id: \.self) { flag in
                        Chip(text: Vocabulary.lampName(flag, lang), isOn: n.has(flag))
                    }
                }
                Text("Aiding this epoch")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                FlowLayout {
                    ForEach([NavFlag.gnss, .zupt, .zihr, .nhc, .vupt], id: \.self) { flag in
                        Chip(text: flag.name, tint: .blue, isOn: n.has(flag))
                    }
                }
            } else {
                Text("No 0x04 navigation packets yet.")
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct StatusPacketCard: View {
    let snapshot: MonitorSnapshot
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        Card(title: "Status 0x05", systemImage: "list.bullet.rectangle") {
            if let s = snapshot.status {
                InfoRow("State", Vocabulary.stateName(s.state, lang))
                InfoRow("Requested action", Vocabulary.actionText(s.requestedAction, lang))
                InfoRow("GNSS quality", Vocabulary.gnssQualityName(s.gnssQuality, lang))
                InfoRow("Session", String(format: "0x%08X", s.sessionID))
                InfoRow("Sequence", "\(s.sequence)")
                InfoRow("Dashboard uptime", Format.duration(Double(s.uptimeMs) / 1000))
                InfoRow("Navigation rate", Format.number(s.navRateHz, 1, unit: "Hz"))
                InfoRow("0x04 age", s.navAgeMs == 0xFFFF ? "—" : "\(s.navAgeMs) ms")
                InfoRow("Status age", snapshot.statusAge.map { Format.number($0, 1, unit: "s") } ?? "—")
                Divider()
                Text("Blocking conditions")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                let inhibit = Vocabulary.inhibitNames(s.inhibitFlags, lang)
                if inhibit.isEmpty {
                    Text(verbatim: Vocabulary.t("none", lang))
                } else {
                    FlowLayout {
                        ForEach(inhibit, id: \.self) { Chip(text: $0, tint: .red) }
                    }
                }
                Text("Conditions met")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                FlowLayout {
                    ForEach(Vocabulary.healthNames(s.healthFlags, lang), id: \.self) { Chip(text: $0) }
                }
            } else {
                Text("No valid 0x05 status packet.")
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct StatisticsCard: View {
    let counts: PacketCounts
    let usableSeconds: Double

    var body: some View {
        Card(title: "Statistics", systemImage: "number") {
            InfoRow("0x04 packets", "\(counts.nav)")
            InfoRow("0x05 packets", "\(counts.status)")
            InfoRow("Lost 0x05", "\(counts.gate.lost)")
            InfoRow("Out of order", "\(counts.gate.reordered)")
            InfoRow("Two senders", "\(counts.gate.twoSenders)")
            InfoRow("Invalid", "\(counts.gate.bad)")
            InfoRow("Other senders", "\(counts.otherSource)")
            InfoRow("Usable total", Format.duration(usableSeconds))
        }
    }
}

struct ListeningFooter: View {
    @Environment(MonitorStore.self) private var store

    var body: some View {
        VStack(spacing: 4) {
            if store.isListening {
                HStack(spacing: 4) {
                    Text("Listening on UDP port")
                    Text(verbatim: Set(store.settings.ports).sorted().map(String.init).joined(separator: ", "))
                }
            }
            if let address = store.localAddresses.first {
                HStack(spacing: 4) {
                    Text("This iPhone")
                    Text(verbatim: "\(address.address) (\(address.interface))")
                }
            }
            if let sender = store.snapshot.lastSender {
                HStack(spacing: 4) {
                    Text("Last sender")
                    Text(verbatim: sender)
                }
            }
        }
        .font(.footnote)
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity)
    }
}
