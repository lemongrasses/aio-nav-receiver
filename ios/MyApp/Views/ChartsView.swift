//
//  ChartsView.swift
//  MyApp
//
//  Layout C charts tab (docs/UI-PHONE-C.zh-TW.md §4.2): the signal history over the last 1, 5 or
//  10 minutes, then the navigation quality and the vehicle's motion. Not interactive; redrawn
//  every 0.5 s.
//

import Charts
import SwiftUI

struct ChartsView: View {
    @Environment(MonitorStore.self) private var store
    @Environment(\.uiLanguage) private var lang
    @AppStorage("chartWindowMinutes") private var windowMinutes = 5

    var body: some View {
        let kind = Presentation.band(store.screen, lang).kind
        NavigationStack {
            // Redrawn every 0.5 s so the time axis keeps moving even when nothing arrives.
            TimelineView(.periodic(from: .now, by: MonitorStore.sampleInterval)) { context in
                let window = context.date.addingTimeInterval(-Double(windowMinutes) * 60)...context.date
                let nav = store.navSamples.filter { $0.date >= window.lowerBound }
                let link = store.linkSamples.filter { $0.date >= window.lowerBound }
                ScrollView {
                    VStack(spacing: 10) {
                        SignalHistory(segments: store.timeline, window: window, minutes: windowMinutes)
                        GroupTitle("Navigation quality")
                        MetricCard(title: "Position σ", unit: "m", samples: nav, window: window,
                                   now: nav.last.map { [$0.sigmaNorth, $0.sigmaEast, $0.sigmaDown]
                                       .map { Format.number($0, 2) }.joined(separator: " / ") },
                                   series: [.init("N", \.sigmaNorth, .info),
                                            .init("E", \.sigmaEast, Color(hex: 0xC25E00), dash: [6, 3]),
                                            .init("D", \.sigmaDown, Color(hex: 0x6A3DAD), dash: [2, 3])])
                        MetricCard(title: "Heading σ", unit: "°", samples: nav, window: window,
                                   now: nav.last.map { Format.number($0.sigmaHeading, 2) },
                                   series: [.init("σ", \.sigmaHeading, .info)])
                        DataAgeCard(samples: link, window: window, limitMs: store.settings.navMaxAge * 1000)
                        ReceiveRateCard(samples: link, window: window)
                        GroupTitle("Motion")
                        MetricCard(title: "Speed", unit: "m/s", samples: nav, window: window,
                                   now: nav.last.map { Format.number($0.speed, 2) },
                                   series: [.init("Speed", \.speed, .info)])
                        MetricCard(title: "Heading", unit: "°", samples: nav, window: window,
                                   now: nav.last.map { Format.number($0.heading, 1) },
                                   series: [.init("Heading", \.heading, .info)], yDomain: 0...360, points: true)
                        MetricCard(title: "Height", unit: "m", samples: nav, window: window,
                                   now: nav.last.map { Format.number($0.height, 2) },
                                   series: [.init("Height", \.height, .info)])
                    }
                    .padding(.vertical, 10)
                }
            }
            .background(Color.kerb)
            .safeAreaInset(edge: .top, spacing: 0) {
                WindowPicker(minutes: $windowMinutes)
            }
            .signHeader("Charts", kind: kind)
        }
    }
}

/// 1 / 5 / 10 minutes, in the lower half of the dark header.
private struct WindowPicker: View {
    @Binding var minutes: Int

    var body: some View {
        HStack(spacing: 0) {
            ForEach([1, 5, 10], id: \.self) { m in
                let on = m == minutes
                Button {
                    minutes = m
                } label: {
                    Group {
                        switch m {
                        case 1: Text("1 min")
                        case 5: Text("5 min")
                        default: Text("10 min")
                        }
                    }
                    .font(.scaled(size: 14, weight: .semibold))
                    .foregroundStyle(on ? Color.asphalt : Color(hex: 0xC9D0D6))
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .background(on ? Color.white : .clear)
                    .overlay(Rectangle().strokeBorder(on ? Color.white : Color.lampRingOff, lineWidth: 1.5))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 12)
        .background(Color.asphalt)
    }
}

private struct GroupTitle: View {
    let title: LocalizedStringKey

    init(_ title: LocalizedStringKey) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.scaled(size: 13, weight: .bold))
            .foregroundStyle(Color.muted)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.top, 4)
    }
}

private struct EmptyChartText: View {
    var body: some View {
        Text("No data in this window.")
            .font(.scaled(size: 13))
            .foregroundStyle(Color.muted)
            .frame(maxWidth: .infinity, minHeight: 90)
    }
}

// MARK: - Signal history

/// One row per lamp (problem / wait / usable): the times it was lit are filled in, so colour is
/// not needed to read it. A fourth row keeps the dashboard state colours.
struct SignalHistory: View {
    let segments: [TimelineSegment]
    let window: ClosedRange<Date>
    let minutes: Int
    @Environment(\.uiLanguage) private var lang

    struct Swatch: Identifiable {
        let name: String
        let color: Color
        var id: String { name }
    }

    static let swatches = [
        Swatch(name: "NO_STATUS", color: .stationFuture), Swatch(name: "BOOTING", color: .indigo),
        Swatch(name: "CHECKING", color: .purple), Swatch(name: "NAV_STARTING", color: .blue),
        Swatch(name: "KEEP_STILL", color: .cyan), Swatch(name: "MOVE_STRAIGHT", color: .teal),
        Swatch(name: "REFINING", color: .mint), Swatch(name: "READY", color: .go),
        Swatch(name: "DEGRADED", color: .yellow), Swatch(name: "FAULT", color: .stop),
        Swatch(name: "MAINTENANCE", color: .brown),
    ]

    private func label(_ state: String) -> String {
        state == "NO_STATUS" ? Vocabulary.t("band.no_status", lang) : (Vocabulary.states[state].map(lang.pick) ?? state)
    }

    var body: some View {
        let visible = segments.filter { $0.end >= window.lowerBound }
        let lamps: [(String, SignalKind, Color)] = [("mast.stop", .stop, .stop), ("mast.wait", .wait, .wait),
                                                    ("mast.go", .go, .go)]
        VStack(alignment: .leading, spacing: 6) {
            Text("Signal history").font(.scaled(size: 15, weight: .bold))
            Text("Each row is one lamp; the times it was lit are filled in, so colour is not needed to read it.")
                .font(.scaled(size: 12.5))
                .foregroundStyle(Color.muted)
                .fixedSize(horizontal: false, vertical: true)
            VStack(spacing: 4) {
                ForEach(lamps, id: \.0) { key, kind, color in
                    lane(Vocabulary.t(key, lang), runs: visible.filter { $0.kind == kind }.map { ($0.start, $0.end, color) },
                         empty: Color(hex: 0xF1F3F5))
                }
                lane(Vocabulary.t("status.state", lang), runs: visible.map { segment in
                    (segment.start, segment.end, Self.swatches.first { $0.name == segment.state }?.color ?? .stationFuture)
                }, empty: .clear)
                HStack(spacing: 8) {
                    Spacer().frame(width: 46)
                    Text("\(minutes) min ago")
                    Spacer()
                    Text("Now")
                }
                .font(.number(12))
                .foregroundStyle(Color.muted)
            }
            .padding(.top, 4)
            let shown = Set(visible.map(\.state))
            FlowLayout(spacing: 12) {
                ForEach(Self.swatches.filter { shown.contains($0.name) }) { swatch in
                    HStack(spacing: 5) {
                        Rectangle().fill(swatch.color).frame(width: 12, height: 10)
                        Text(verbatim: label(swatch.name)).font(.scaled(size: 12.5)).foregroundStyle(Color.text2)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.panel)
        .accessibilityElement(children: .combine)
    }

    /// A bar over the window with the given runs filled in.
    private func lane(_ title: String, runs: [(Date, Date, Color)], empty: Color) -> some View {
        HStack(spacing: 8) {
            Text(verbatim: title)
                .font(.scaled(size: 12.5))
                .foregroundStyle(Color.text2)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(width: 46, alignment: .leading)
            Canvas { ctx, size in
                ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(empty))
                let span = window.upperBound.timeIntervalSince(window.lowerBound)
                guard span > 0 else { return }
                for (start, end, color) in runs {
                    let x0 = max(0, start.timeIntervalSince(window.lowerBound) / span) * size.width
                    let x1 = min(1, end.timeIntervalSince(window.lowerBound) / span) * size.width
                    if x1 > x0 {
                        ctx.fill(Path(CGRect(x: x0, y: 0, width: max(x1 - x0, 1), height: size.height)), with: .color(color))
                    }
                }
            }
            .frame(height: 16)
        }
    }
}

// MARK: - Chart cards

private struct ChartCard<Content: View>: View {
    let title: LocalizedStringKey
    let unit: String
    let now: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                HStack(spacing: 4) {
                    Text(title).font(.scaled(size: 14, weight: .semibold))
                    Text(verbatim: unit).font(.scaled(size: 14, weight: .medium)).foregroundStyle(Color.muted)
                }
                Spacer()
                if let now {
                    Text(verbatim: now).font(.number(20, .bold))
                }
            }
            content
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.panel)
    }
}

struct MetricSeries {
    let name: String
    let value: KeyPath<NavSample, Double>
    let color: Color
    let dash: [CGFloat]

    init(_ name: String, _ value: KeyPath<NavSample, Double>, _ color: Color, dash: [CGFloat] = []) {
        self.name = name
        self.value = value
        self.color = color
        self.dash = dash
    }
}

/// Lines told apart by their dash pattern as well as their colour.
private struct MetricCard: View {
    let title: LocalizedStringKey
    let unit: String
    let samples: [NavSample]
    let window: ClosedRange<Date>
    let now: String?
    let series: [MetricSeries]
    var yDomain: ClosedRange<Double>?
    var points = false

    var body: some View {
        ChartCard(title: title, unit: unit, now: now) {
            if samples.isEmpty {
                EmptyChartText()
            } else {
                let chart = Chart {
                    ForEach(series.indices, id: \.self) { i in
                        let s = series[i]
                        ForEach(samples) { p in
                            if points {
                                PointMark(x: .value("Time", p.date), y: .value(unit, p[keyPath: s.value]))
                                    .symbolSize(10)
                                    .foregroundStyle(s.color)
                            } else {
                                LineMark(x: .value("Time", p.date), y: .value(unit, p[keyPath: s.value]),
                                         series: .value("Run", "\(s.name)-\(p.run)"))
                                    .foregroundStyle(s.color)
                                    .lineStyle(StrokeStyle(lineWidth: 2.2, lineJoin: .round, dash: s.dash))
                            }
                        }
                    }
                }
                .chartXScale(domain: window)
                .chartXAxis(.hidden)
                .frame(height: 110)
                Group {
                    if let yDomain {
                        chart.chartYScale(domain: yDomain).chartYAxis { AxisMarks(values: [0, 90, 180, 270, 360]) }
                    } else {
                        chart
                    }
                }
                if series.count > 1 {
                    HStack(spacing: 14) {
                        ForEach(series.indices, id: \.self) { i in
                            HStack(spacing: 5) {
                                Path { p in p.move(to: CGPoint(x: 1, y: 3)); p.addLine(to: CGPoint(x: 21, y: 3)) }
                                    .stroke(series[i].color, style: StrokeStyle(lineWidth: 2.5, dash: series[i].dash))
                                    .frame(width: 22, height: 6)
                                Text(verbatim: series[i].name)
                            }
                        }
                    }
                    .font(.scaled(size: 12.5))
                    .foregroundStyle(Color.text2)
                }
            }
        }
    }
}

private struct DataAgeCard: View {
    let samples: [LinkSample]
    let window: ClosedRange<Date>
    let limitMs: Double

    var body: some View {
        let ages = samples.filter { $0.navAgeMs != nil }
        ChartCard(title: "0x04 data age", unit: "ms", now: ages.last?.navAgeMs.map { Format.number($0, 0) }) {
            if ages.isEmpty {
                EmptyChartText()
            } else {
                Chart {
                    ForEach(ages) { s in
                        AreaMark(x: .value("Time", s.date), y: .value("ms", s.navAgeMs ?? 0))
                            .foregroundStyle(Color(hex: 0xFCE3CF))
                        LineMark(x: .value("Time", s.date), y: .value("ms", s.navAgeMs ?? 0))
                            .foregroundStyle(Color(hex: 0xC25E00))
                            .lineStyle(StrokeStyle(lineWidth: 2))
                    }
                    RuleMark(y: .value("Limit", limitMs))
                        .foregroundStyle(Color.stop)
                        .lineStyle(StrokeStyle(lineWidth: 1.8, dash: [6, 4]))
                        .annotation(position: .top, alignment: .trailing) {
                            Text("Limit \(Format.number(limitMs, 0)) ms")
                                .font(.scaled(size: 11.5, weight: .bold))
                                .foregroundStyle(Color.stop)
                        }
                }
                .chartXScale(domain: window)
                .chartXAxis(.hidden)
                .frame(height: 110)
            }
        }
    }
}

private struct ReceiveRateCard: View {
    let samples: [LinkSample]
    let window: ClosedRange<Date>

    var body: some View {
        ChartCard(title: "Receive rate", unit: "Hz", now: samples.last.map { Format.number($0.rateHz, 1) }) {
            if samples.isEmpty {
                EmptyChartText()
            } else {
                Chart(samples) { s in
                    LineMark(x: .value("Time", s.date), y: .value("Hz", s.rateHz))
                        .foregroundStyle(Color.info)
                        .interpolationMethod(.stepEnd)
                }
                .chartXScale(domain: window)
                .chartXAxis(.hidden)
                .frame(height: 110)
            }
        }
    }
}
