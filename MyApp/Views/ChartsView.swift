//
//  ChartsView.swift
//  MyApp
//
//  Live charts over the last 1, 5 or 10 minutes: when and why the gate changed, the
//  navigation quality and the vehicle's motion.
//

import Charts
import SwiftUI

struct ChartsView: View {
    @Environment(MonitorStore.self) private var store
    @AppStorage("chartWindowMinutes") private var windowMinutes = 5

    var body: some View {
        NavigationStack {
            // Redrawn every 0.5 s so the time axis keeps moving even when nothing arrives.
            TimelineView(.periodic(from: .now, by: MonitorStore.sampleInterval)) { context in
                let window = context.date.addingTimeInterval(-Double(windowMinutes) * 60)...context.date
                let nav = store.navSamples.filter { $0.date >= window.lowerBound }
                let link = store.linkSamples.filter { $0.date >= window.lowerBound }
                ScrollView {
                    VStack(spacing: 16) {
                        Picker("Window", selection: $windowMinutes) {
                            Text("1 min").tag(1)
                            Text("5 min").tag(5)
                            Text("10 min").tag(10)
                        }
                        .pickerStyle(.segmented)

                        StatusTimelineChart(segments: store.timeline, window: window)

                        SectionTitle("Navigation quality")
                        NavMetricChart(title: "Position σ", unit: "m", samples: nav, window: window, series: [
                            .init("N", \.sigmaNorth), .init("E", \.sigmaEast), .init("D", \.sigmaDown),
                        ])
                        NavMetricChart(title: "Heading σ", unit: "°", samples: nav, window: window, series: [
                            .init("σ", \.sigmaHeading),
                        ])
                        DataAgeChart(samples: link, window: window, limitMs: store.settings.navMaxAge * 1000)
                        ReceiveRateChart(samples: link, window: window)

                        SectionTitle("Motion")
                        NavMetricChart(title: "Speed", unit: "m/s", samples: nav, window: window, series: [
                            .init("Speed", \.speed),
                        ])
                        NavMetricChart(title: "Heading", unit: "°", samples: nav, window: window, series: [
                            .init("Heading", \.heading),
                        ], yDomain: 0...360, points: true)
                        NavMetricChart(title: "Height", unit: "m", samples: nav, window: window, series: [
                            .init("Height", \.height),
                        ])
                    }
                    .padding()
                }
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Charts")
        }
    }
}

private struct SectionTitle: View {
    let title: LocalizedStringKey

    init(_ title: LocalizedStringKey) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.title3.bold())
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 8)
    }
}

private struct ChartCard<Content: View>: View {
    let title: LocalizedStringKey
    let unit: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.headline)
                if !unit.isEmpty {
                    Text(verbatim: "(\(unit))")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            content
                .frame(height: 150)
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 20))
    }
}

private struct EmptyChartText: View {
    var body: some View {
        Text("No data in this window.")
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Two lanes: the gate verdict (green / red) and the dashboard state.
struct StatusTimelineChart: View {
    let segments: [TimelineSegment]
    let window: ClosedRange<Date>

    struct Swatch: Identifiable {
        let name: String
        let color: Color
        var id: String { name }
    }

    static let swatches = [
        Swatch(name: "USABLE", color: .green), Swatch(name: "BLOCKED", color: .red),
        Swatch(name: "NO_STATUS", color: .gray), Swatch(name: "BOOTING", color: .indigo),
        Swatch(name: "CHECKING", color: .purple), Swatch(name: "NAV_STARTING", color: .blue),
        Swatch(name: "KEEP_STILL", color: .cyan), Swatch(name: "MOVE_STRAIGHT", color: .teal),
        Swatch(name: "REFINING", color: .mint), Swatch(name: "READY", color: .green),
        Swatch(name: "DEGRADED", color: .yellow), Swatch(name: "FAULT", color: .red),
        Swatch(name: "MAINTENANCE", color: .brown),
    ]

    /// Joins neighbouring segments with the same key into one bar.
    static func merged(_ segments: [TimelineSegment], by key: (TimelineSegment) -> String)
        -> [(key: String, start: Date, end: Date)] {
        var runs: [(key: String, start: Date, end: Date)] = []
        for segment in segments {
            let k = key(segment)
            if let last = runs.last, last.key == k {
                runs[runs.count - 1].end = segment.end
            } else {
                runs.append((k, segment.start, segment.end))
            }
        }
        return runs
    }

    var body: some View {
        let visible = segments.filter { $0.end >= window.lowerBound }
        let gate = String(localized: "Gate")
        let state = String(localized: "State")
        VStack(alignment: .leading, spacing: 8) {
            Text("Status timeline")
                .font(.headline)
            Chart {
                ForEach(Self.merged(visible) { $0.usable ? "USABLE" : "BLOCKED" }, id: \.start) { run in
                    RectangleMark(xStart: .value("Start", max(run.start, window.lowerBound)), xEnd: .value("End", run.end),
                                  y: .value("Lane", gate), height: .ratio(0.7))
                        .foregroundStyle(by: .value("Value", run.key))
                }
                ForEach(Self.merged(visible) { $0.state }, id: \.start) { run in
                    RectangleMark(xStart: .value("Start", max(run.start, window.lowerBound)), xEnd: .value("End", run.end),
                                  y: .value("Lane", state), height: .ratio(0.7))
                        .foregroundStyle(by: .value("Value", run.key))
                }
            }
            .chartForegroundStyleScale(domain: Self.swatches.map(\.name), range: Self.swatches.map(\.color))
            .chartLegend(.hidden)
            .chartXScale(domain: window)
            .chartYScale(domain: [gate, state])
            .frame(height: 90)

            let shown = Set(visible.map(\.state))
            FlowLayout(spacing: 10) {
                ForEach(Self.swatches.filter { shown.contains($0.name) || $0.name == "USABLE" || $0.name == "BLOCKED" }) { swatch in
                    HStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 2).fill(swatch.color).frame(width: 10, height: 10)
                        Text(verbatim: swatch.name).font(.caption2.monospaced())
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 20))
    }
}

struct MetricSeries {
    let name: String
    let value: KeyPath<NavSample, Double>

    init(_ name: String, _ value: KeyPath<NavSample, Double>) {
        self.name = name
        self.value = value
    }
}

struct NavMetricChart: View {
    let title: LocalizedStringKey
    let unit: String
    let samples: [NavSample]
    let window: ClosedRange<Date>
    let series: [MetricSeries]
    var yDomain: ClosedRange<Double>?
    var points = false

    var body: some View {
        ChartCard(title: title, unit: unit) {
            if samples.isEmpty {
                EmptyChartText()
            } else {
                let chart = Chart {
                    ForEach(series, id: \.name) { s in
                        ForEach(samples) { p in
                            if points {
                                PointMark(x: .value("Time", p.date), y: .value(unit, p[keyPath: s.value]))
                                    .symbolSize(12)
                                    .foregroundStyle(by: .value("Series", s.name))
                            } else {
                                LineMark(x: .value("Time", p.date), y: .value(unit, p[keyPath: s.value]),
                                         series: .value("Run", "\(s.name)-\(p.run)"))
                                    .foregroundStyle(by: .value("Series", s.name))
                            }
                        }
                    }
                }
                .chartXScale(domain: window)
                .chartLegend(series.count > 1 ? .visible : .hidden)
                if let yDomain {
                    chart
                        .chartYScale(domain: yDomain)
                        .chartYAxis { AxisMarks(values: [0, 90, 180, 270, 360]) }
                } else {
                    chart
                }
            }
        }
    }
}

struct DataAgeChart: View {
    let samples: [LinkSample]
    let window: ClosedRange<Date>
    let limitMs: Double

    var body: some View {
        let ages = samples.filter { $0.navAgeMs != nil }
        ChartCard(title: "0x04 data age", unit: "ms") {
            if ages.isEmpty {
                EmptyChartText()
            } else {
                Chart {
                    ForEach(ages) { s in
                        AreaMark(x: .value("Time", s.date), y: .value("ms", s.navAgeMs ?? 0))
                            .foregroundStyle(.orange.opacity(0.25))
                        LineMark(x: .value("Time", s.date), y: .value("ms", s.navAgeMs ?? 0))
                            .foregroundStyle(.orange)
                    }
                    RuleMark(y: .value("Limit", limitMs))
                        .foregroundStyle(.red)
                        .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
                        .annotation(position: .top, alignment: .leading) {
                            Text("Limit").font(.caption2).foregroundStyle(.red)
                        }
                }
                .chartXScale(domain: window)
            }
        }
    }
}

struct ReceiveRateChart: View {
    let samples: [LinkSample]
    let window: ClosedRange<Date>

    var body: some View {
        ChartCard(title: "Receive rate", unit: "Hz") {
            if samples.isEmpty {
                EmptyChartText()
            } else {
                Chart(samples) { s in
                    LineMark(x: .value("Time", s.date), y: .value("Hz", s.rateHz))
                        .foregroundStyle(.blue)
                        .interpolationMethod(.stepEnd)
                }
                .chartXScale(domain: window)
            }
        }
    }
}
