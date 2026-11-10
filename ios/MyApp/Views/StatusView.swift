//
//  StatusView.swift
//  MyApp
//
//  Layout C status tab (docs/UI-PHONE-C.zh-TW.md §4.1): the verdict, what to do, where the
//  alignment stands and both packet streams fit on the first screen; the detail opens below.
//

import SwiftUI

extension UILanguage {
    /// A catalog string in this language (for text assembled in code).
    func text(_ key: String.LocalizationValue) -> String {
        String(localized: LocalizedStringResource(key, locale: locale))
    }
}

struct StatusView: View {
    @Environment(MonitorStore.self) private var store
    @Environment(\.uiLanguage) private var lang
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var open: Section?
    @State private var dimmed = false
    @State private var lastKind: SignalKind?

    enum Section { case nav, status, stats }

    var body: some View {
        let screen = store.screen
        let band = Presentation.band(screen, lang)
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    VerdictBand(band: band, dimmed: dimmed)
                    if let failure = store.listenFailure {
                        ListenErrorBox(failure: failure)
                    }
                    GuidanceArea(screen: screen)
                    HStack(spacing: 1) {
                        StreamCell(label: "0x04", link: Presentation.navLink(screen, lang))
                        StreamCell(label: "0x05", link: Presentation.statusLink(screen, lang))
                    }
                    .background(Color.line)
                    .padding(.top, 1)
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(Text("Packets"))
                    NavigationRow(screen: screen, expanded: open == .nav) { toggle(.nav) }
                    StatusPacketRow(screen: screen, expanded: open == .status) { toggle(.status) }
                    StatisticsRow(screen: screen, usableSeconds: store.usableSeconds, expanded: open == .stats) {
                        toggle(.stats)
                    }
                    Rectangle().fill(Color.line).frame(height: 1)
                    ListeningFooter()
                }
            }
            .background(Color.kerb)
            .scrollContentBackground(.hidden)
            // The band is the header: its colour runs up under the status bar.
            .toolbarBackground(band.kind.color, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(band.kind == .wait ? .light : .dark, for: .navigationBar)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Text("AIO NAV Receiver")
                        .font(.scaled(size: 13, weight: .semibold))
                        .foregroundStyle(band.kind.ink)
                        .fixedSize()
                }
                .sharedBackgroundVisibility(.hidden)
                ToolbarItem(placement: .principal) { EmptyView() }
                ToolbarItem(placement: .topBarTrailing) {
                    Text(verbatim: Vocabulary.t("band.since", lang, ["age": Presentation.fmtAge(store.verdictFor, lang)]))
                        .font(.number(16, .semibold))
                        .foregroundStyle(band.kind.ink)
                        .fixedSize()
                }
                .sharedBackgroundVisibility(.hidden)
            }
        }
        .onChange(of: band.kind) { old, new in
            if old == .go && new != .go {
                flash()
            }
        }
    }

    private func toggle(_ section: Section) {
        open = open == section ? nil : section
    }

    /// The lit lamp blinks three times when usable ends (not with Reduce Motion).
    private func flash() {
        guard !reduceMotion else { return }
        Task {
            for _ in 0..<3 {
                dimmed = true
                try? await Task.sleep(for: .milliseconds(160))
                dimmed = false
                try? await Task.sleep(for: .milliseconds(160))
            }
        }
    }
}

// MARK: - ① The verdict band

struct VerdictBand: View {
    let band: Presentation.Band
    let dimmed: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            SignalMast(kind: band.kind, lamp: 20, dimmed: dimmed)
            VStack(alignment: .leading, spacing: 4) {
                Text(verbatim: band.word)
                    .font(.scaled(size: 34, weight: .bold))
                Text(verbatim: band.headline)
                    .font(.scaled(size: 16, weight: .semibold))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(band.kind.ink)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16)
        .padding(.top, 4)
        .padding(.bottom, 14)
        .background(band.kind.color)
        .accessibilityElement(children: .combine)
    }
}

struct ListenErrorBox: View {
    let failure: UDPReceiver.BindError
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Cannot listen")
                .font(.scaled(size: 16, weight: .bold))
                .foregroundStyle(Color.stop)
            Text(verbatim: Vocabulary.bindError(port: failure.port, code: failure.code, lang))
                .font(.scaled(size: 14))
                .foregroundStyle(Color.asphalt)
            Text("Another app may be using this port. Change the port in Settings.")
                .font(.scaled(size: 13))
                .foregroundStyle(Color.muted)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(Rectangle().strokeBorder(Color.stop, lineWidth: 2))
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.panel)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isStaticText)
    }
}

// MARK: - ② What to do, ③ where the alignment stands

struct GuidanceArea: View {
    let screen: Screen
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        if !screen.nothingReceived {
            VStack(alignment: .leading, spacing: 12) {
                if let guide = Presentation.guide(screen, lang) {
                    InstructionPlate(guide: guide)
                }
                let rail = Presentation.rail(screen, lang)
                StationRail(rail: rail)
                underRail(rail)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.panel)
        }
    }

    /// Under the route, only one thing: real problems, else the steps left, else the note.
    @ViewBuilder
    private func underRail(_ rail: Presentation.Rail) -> some View {
        let chips = Presentation.blocking(screen, lang) ?? []
        let problems = chips.filter { !$0.expected }
        if !problems.isEmpty {
            FlowLayout {
                ForEach(problems.indices, id: \.self) { SignChip(text: problems[$0].text, expected: false) }
            }
        } else if !chips.isEmpty {
            Text("Alignment in progress, \(chips.count) steps to go")
                .font(.scaled(size: 14, weight: .semibold))
                .foregroundStyle(Color.amberText)
        } else if rail.at == 4 && rail.mode == .progress && rail.fraction > 0 {
            Text(verbatim: Vocabulary.t("station.confirming", lang,
                                        ["x": rail.fraction * screen.readyStable, "y": screen.readyStable]))
                .font(.number(14, .semibold))
                .foregroundStyle(Color.asphalt)
        } else if !rail.note.isEmpty {
            Text(verbatim: rail.note)
                .font(.scaled(size: 14, weight: [.fault, .lost].contains(rail.mode) ? .semibold : .regular))
                .foregroundStyle([.fault, .lost].contains(rail.mode) ? Color.stop : .muted)
        }
    }
}

// MARK: - ⑤ Navigation 0x04

struct NavigationRow: View {
    let screen: Screen
    let expanded: Bool
    let toggle: () -> Void
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        let nav = screen.snap.nav
        let stale = (screen.snap.navAge ?? .infinity) > screen.navMaxAge
        ExpandRow(title: "Navigation 0x04", expanded: expanded, toggle: toggle) {
            if let n = nav {
                let sigma = [n.positionNorthStd, n.positionEastStd, n.heightStd]
                    .map { Format.number(Double($0), 2) }.joined(separator: "/")
                Group {
                    if n.isAligned {
                        Text("Aligned, σ \(sigma)\u{00A0}m")
                    } else {
                        Text("Not aligned, σ \(sigma)\u{00A0}m")
                    }
                }
                .foregroundStyle(stale ? Color.faint : .muted)
            } else {
                Text("No 0x04 navigation packets yet.").foregroundStyle(Color.muted)
            }
        } content: {
            if let n = nav {
                VStack(alignment: .leading, spacing: 10) {
                    FieldGrid(fields: [
                        ("Data age", screen.snap.navAge.map { Format.number($0 * 1000, 0, unit: "ms") } ?? "—"),
                        ("Receive rate", Format.number(screen.navRateHz, 1, unit: "Hz")),
                        ("Position σ N / E / D", [n.positionNorthStd, n.positionEastStd, n.heightStd]
                            .map { Format.number(Double($0), 3) }.joined(separator: " / ") + " m"),
                        ("Heading σ", Format.number(Double(n.headingStd), 3, unit: "°")),
                        ("Latitude", Format.number(n.latitude, 8, unit: "°")),
                        ("Longitude", Format.number(n.longitude, 8, unit: "°")),
                        ("Height", Format.number(Double(n.height), 2, unit: "m")),
                        ("Heading", Format.number(n.heading360, 1, unit: "°")),
                        ("Ground speed", Format.number(n.groundSpeed, 2, unit: "m/s") + "  ("
                            + Format.number(n.groundSpeed * 3.6, 1, unit: "km/h") + ")"),
                        ("Roll / pitch", Format.number(Double(n.roll), 2) + " / " + Format.number(Double(n.pitch), 2, unit: "°")),
                    ], faint: stale)
                    Text("Alignment").font(.scaled(size: 12)).foregroundStyle(Color.muted)
                    FlowLayout(spacing: 14) {
                        ForEach([NavFlag.alignment, .headingValid, .fineAlignment], id: \.self) { flag in
                            DotLabel(text: Vocabulary.lampName(flag, lang), on: n.has(flag), faint: stale)
                        }
                    }
                    Text("Aiding this epoch").font(.scaled(size: 12)).foregroundStyle(Color.muted)
                    FlowLayout(spacing: 4) {
                        ForEach([NavFlag.gnss, .zupt, .zihr, .nhc, .vupt], id: \.self) { flag in
                            FlagChip(text: flag.name, on: n.has(flag), faint: stale)
                        }
                    }
                }
            } else {
                Text("No 0x04 navigation packets yet.").font(.scaled(size: 14)).foregroundStyle(Color.muted)
            }
        }
    }
}

// MARK: - ⑤ Status 0x05

struct StatusPacketRow: View {
    let screen: Screen
    let expanded: Bool
    let toggle: () -> Void
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        let status = screen.snap.status
        let stale = !screen.statusFresh
        let rows = Presentation.conditions(screen, lang)
        ExpandRow(title: "Status 0x05", expanded: expanded, toggle: toggle) {
            if let s = status {
                let name = Vocabulary.stateName(s.state, lang)
                if stale {
                    Text("Out of date, last: \(name)").foregroundStyle(Color.stop)
                } else {
                    Text("\(name), \(rows.filter { !$0.met }.count) / \(rows.count) unmet").foregroundStyle(Color.muted)
                }
            } else {
                Text("No valid 0x05 status packet.").foregroundStyle(Color.muted)
            }
        } content: {
            if let s = status {
                VStack(alignment: .leading, spacing: 10) {
                    FieldGrid(fields: [
                        ("State", Vocabulary.stateName(s.state, lang)),
                        ("Requested action", Vocabulary.actionText(s.requestedAction, lang)),
                        ("GNSS quality", Vocabulary.gnssQualityName(s.gnssQuality, lang)),
                        ("Session", String(format: "0x%08X", s.sessionID)),
                        ("Sequence", "\(s.sequence)"),
                        ("Dashboard uptime", Format.duration(Double(s.uptimeMs) / 1000)),
                        ("Navigation rate", Format.number(s.navRateHz, 1, unit: "Hz")),
                        ("0x04 age", s.navAgeMs == 0xFFFF ? "—" : "\(s.navAgeMs) ms"),
                        ("Status age", screen.snap.statusAge.map { Format.number($0, 1, unit: "s") } ?? "—"),
                    ], faint: stale)
                    Text(verbatim: Vocabulary.t("block.title", lang)).font(.scaled(size: 12)).foregroundStyle(Color.muted)
                    if let chips = Presentation.blocking(screen, lang) {
                        if chips.isEmpty {
                            Text(verbatim: Vocabulary.t("none", lang))
                                .font(.scaled(size: 14, weight: .semibold))
                                .foregroundStyle(Color.go)
                        } else {
                            FlowLayout {
                                ForEach(chips.indices, id: \.self) { SignChip(text: chips[$0].text, expected: chips[$0].expected) }
                            }
                            if chips.allSatisfy(\.expected) {
                                Text(verbatim: Vocabulary.t("block.expected", lang))
                                    .font(.scaled(size: 13)).foregroundStyle(Color.muted)
                            }
                        }
                    } else {
                        Text(verbatim: Vocabulary.t("block.unknown", lang))
                            .font(.scaled(size: 14)).foregroundStyle(Color.faint)
                    }
                    HStack {
                        Text(verbatim: Vocabulary.t("status.health", lang) + (stale ? Vocabulary.t("status.out_of_date", lang) : ""))
                        Spacer()
                        Text(verbatim: Vocabulary.t("status.met", lang, ["n": rows.filter(\.met).count, "total": rows.count]))
                            .font(.number(12))
                    }
                    .font(.scaled(size: 12))
                    .foregroundStyle(Color.muted)
                    LazyVGrid(columns: [GridItem(.flexible(), alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                              alignment: .leading, spacing: 4) {
                        ForEach(rows.indices, id: \.self) { i in
                            DotLabel(text: rows[i].name, on: rows[i].met, faint: stale)
                        }
                    }
                }
            } else {
                Text("No valid 0x05 status packet.").font(.scaled(size: 14)).foregroundStyle(Color.muted)
            }
        }
    }
}

// MARK: - ⑤ Statistics

struct StatisticsRow: View {
    let screen: Screen
    let usableSeconds: Double
    let expanded: Bool
    let toggle: () -> Void
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        let c = screen.snap.counts
        ExpandRow(title: "Statistics", expanded: expanded, toggle: toggle) {
            Text(summary(c))
        } content: {
            FieldGrid(fields: [
                ("0x04 packets", "\(c.nav)"),
                ("0x05 packets", "\(c.status)"),
                ("Lost 0x05", "\(c.gate.lost)"),
                ("Out of order", "\(c.gate.reordered)"),
                ("Two senders", "\(c.gate.twoSenders)"),
                ("Invalid", "\(c.gate.bad)"),
                ("Other senders", "\(c.otherSource)"),
                ("Usable total", Format.duration(usableSeconds)),
                ("Last sender", screen.snap.lastSender ?? "—"),
            ])
        }
    }

    /// The non-zero problem counters (lost and out of order in amber, the rest in red), then the
    /// usable total; "no problems" when they are all zero.
    private func summary(_ c: PacketCounts) -> AttributedString {
        let items: [(String.LocalizationValue, Int, Color)] = [
            ("Lost 0x05", c.gate.lost, .amber), ("Out of order", c.gate.reordered, .amber),
            ("Two senders", c.gate.twoSenders, .stop), ("Invalid", c.gate.bad, .stop),
            ("Other senders", c.otherSource, .stop),
        ]
        var out = AttributedString()
        let problems = items.filter { $0.1 > 0 }
        if problems.isEmpty {
            var ok = AttributedString(lang.text("No problems"))
            ok.foregroundColor = .muted
            out += ok
        }
        for (i, item) in problems.enumerated() {
            var part = AttributedString((i > 0 ? lang.pick(("、", ", ")) : "") + "\(lang.text(item.0)) \(item.1)")
            part.foregroundColor = item.2
            out += part
        }
        var total = AttributedString("　" + Vocabulary.t("band.total", lang) + " " + Format.duration(usableSeconds))
        total.foregroundColor = .muted
        out += total
        return out
    }
}

// MARK: - ⑥ Where we listen

struct ListeningFooter: View {
    @Environment(MonitorStore.self) private var store
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        var parts: [String] = []
        if store.isListening {
            parts.append(lang.text("Listening on UDP port") + " "
                         + Set(store.settings.ports).sorted().map(String.init).joined(separator: ", "))
        }
        if let a = store.localAddresses.first {
            parts.append(lang.text("This iPhone") + " " + a.address + lang.pick(("（\(a.interface)）", " (\(a.interface))")))
        }
        return Text(verbatim: parts.joined(separator: "　"))
            .font(.scaled(size: 12))
            .foregroundStyle(Color.muted)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
    }
}
