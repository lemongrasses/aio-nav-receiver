//
//  TrackMapView.swift
//  MyApp
//
//  Layout C track tab (docs/UI-PHONE-C.zh-TW.md §4.3, D3): Apple Maps stays; the track is solid
//  green where the output was usable and dashed grey where it was not.
//

import MapKit
import SwiftUI

struct TrackMapView: View {
    @Environment(MonitorStore.self) private var store
    @Environment(\.uiLanguage) private var lang
    @State private var position: MapCameraPosition = .automatic
    @State private var follow = true

    /// Runs of samples with the same verdict (and no gap); each starts at the previous run's last
    /// point, so the line has no holes where it changes style.
    static func runs(_ samples: [NavSample]) -> [(usable: Bool, points: [CLLocationCoordinate2D])] {
        var out: [(usable: Bool, points: [CLLocationCoordinate2D])] = []
        var lastRun: Int?
        for s in samples {
            let c = CLLocationCoordinate2D(latitude: s.latitude, longitude: s.longitude)
            if let last = out.last, last.usable == s.usable, lastRun == s.run {
                out[out.count - 1].points.append(c)
            } else {
                let joined = lastRun == s.run ? out.last?.points.last.map { [$0] } ?? [] : []
                out.append((s.usable, joined + [c]))
            }
            lastRun = s.run
        }
        return out.filter { $0.points.count > 1 }
    }

    var body: some View {
        let samples = store.navSamples
        let runs = Self.runs(samples)
        let snapshot = store.snapshot
        let kind = Presentation.band(store.screen, lang).kind
        let current = (snapshot.navAge ?? .infinity) < 1 ? snapshot.nav : nil
        NavigationStack {
            Map(position: $position) {
                ForEach(runs.indices, id: \.self) { i in
                    if runs[i].usable {
                        MapPolyline(coordinates: runs[i].points)
                            .stroke(Color.go, style: StrokeStyle(lineWidth: 7, lineCap: .round, lineJoin: .round))
                    } else {
                        MapPolyline(coordinates: runs[i].points)
                            .stroke(Color.blockedTrack, style: StrokeStyle(lineWidth: 4, lineCap: .round, dash: [9, 8]))
                    }
                }
                if let nav = current, nav.isFinite {
                    Annotation("Vehicle", coordinate: CLLocationCoordinate2D(latitude: nav.latitude, longitude: nav.longitude)) {
                        VehicleMarker(kind: kind, heading: nav.heading360)
                    }
                    .annotationTitles(.hidden)
                }
            }
            .mapStyle(.standard(elevation: .flat, pointsOfInterest: .excludingAll))
            .mapControls {
                MapCompass()
                MapScaleView()
            }
            .simultaneousGesture(DragGesture(minimumDistance: 10).onChanged { _ in follow = false })
            .onChange(of: store.navSamples.last?.id) {
                guard follow, let last = samples.last else { return }
                withAnimation(.easeInOut(duration: 0.4)) {
                    position = .camera(MapCamera(centerCoordinate: CLLocationCoordinate2D(latitude: last.latitude,
                                                                                          longitude: last.longitude),
                                                 distance: 800))
                }
            }
            .overlay(alignment: .topLeading) { TrackLegend().padding(12) }
            .safeAreaInset(edge: .bottom, spacing: 0) { PositionBar(nav: current) }
            .signHeader("Track", kind: kind)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        follow.toggle()
                        if follow, let last = samples.last {
                            position = .camera(MapCamera(centerCoordinate: CLLocationCoordinate2D(latitude: last.latitude,
                                                                                                  longitude: last.longitude),
                                                         distance: 800))
                        }
                    } label: {
                        Label("Follow vehicle", systemImage: follow ? "location.fill" : "location")
                    }
                    .tint(.white)
                    .accessibilityValue(follow ? Text("On") : Text("Off"))
                }
            }
        }
    }
}

/// A dark ring with the signal colour inside and the heading arrow.
private struct VehicleMarker: View {
    let kind: SignalKind
    let heading: Double

    var body: some View {
        ZStack {
            Circle().fill(Color.asphalt).frame(width: 36, height: 36)
            Circle().fill(kind.color).frame(width: 26, height: 26)
            Image(systemName: "location.north.fill")
                .font(.scaled(size: 13, weight: .bold))
                .foregroundStyle(kind == .wait ? Color.asphalt : .white)
                .rotationEffect(.degrees(heading))
        }
        .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(kind.accessibilityLabel)
    }
}

private struct TrackLegend: View {
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            entry(Vocabulary.t("track.usable", lang), color: .go, width: 5, dash: [])
            entry(Vocabulary.t("track.blocked", lang), color: .blockedTrack, width: 3, dash: [5, 4])
        }
        .font(.scaled(size: 13))
        .foregroundStyle(Color.text2)
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.white.opacity(0.94))
        .overlay(Rectangle().strokeBorder(Color.line, lineWidth: 1))
    }

    private func entry(_ text: String, color: Color, width: CGFloat, dash: [CGFloat]) -> some View {
        HStack(spacing: 6) {
            Path { p in p.move(to: CGPoint(x: 2, y: 4)); p.addLine(to: CGPoint(x: 22, y: 4)) }
                .stroke(color, style: StrokeStyle(lineWidth: width, lineCap: dash.isEmpty ? .round : .butt, dash: dash))
                .frame(width: 24, height: 8)
            Text(verbatim: text)
        }
    }
}

/// Position, heading and speed on asphalt at the bottom of the map.
private struct PositionBar: View {
    let nav: NavSolution?

    var body: some View {
        Group {
            if let nav {
                HStack {
                    Text(verbatim: Format.number(nav.latitude, 6) + ", " + Format.number(nav.longitude, 6))
                    Spacer()
                    Text(verbatim: Format.number(nav.heading360, 0) + "°")
                    Spacer()
                    Text(verbatim: Format.number(nav.groundSpeed * 3.6, 1, unit: "km/h"))
                }
                .font(.number(17, .semibold))
            } else {
                Text("No current position.")
                    .font(.scaled(size: 15))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .foregroundStyle(.white)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color.asphalt)
        .padding(.horizontal, 12)
        .padding(.bottom, 12)
    }
}
