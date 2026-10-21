//
//  TrackMapView.swift
//  MyApp
//

import MapKit
import SwiftUI

struct TrackMapView: View {
    @Environment(MonitorStore.self) private var store
    @State private var position: MapCameraPosition = .automatic
    @State private var follow = true

    var body: some View {
        let track = store.navSamples.map { CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude) }
        let snapshot = store.snapshot
        let current = (snapshot.navAge ?? .infinity) < 1 ? snapshot.nav : nil
        NavigationStack {
            Map(position: $position) {
                if track.count > 1 {
                    MapPolyline(coordinates: track)
                        .stroke(.blue, lineWidth: 4)
                }
                if let nav = current, nav.isFinite {
                    Annotation("Vehicle", coordinate: CLLocationCoordinate2D(latitude: nav.latitude, longitude: nav.longitude)) {
                        Image(systemName: "location.north.fill")
                            .font(.title3)
                            .rotationEffect(.degrees(nav.heading360))
                            .foregroundStyle(.white)
                            .padding(8)
                            .background(snapshot.verdict.isUsable ? Color.green : Color.red, in: Circle())
                            .shadow(radius: 3)
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
                guard follow, let last = track.last else { return }
                withAnimation(.easeInOut(duration: 0.4)) {
                    position = .camera(MapCamera(centerCoordinate: last, distance: 800))
                }
            }
            .safeAreaInset(edge: .bottom) {
                if let nav = current {
                    HStack(spacing: 16) {
                        Text(verbatim: Format.number(nav.latitude, 6) + ", " + Format.number(nav.longitude, 6))
                        Text(verbatim: Format.number(nav.heading360, 0, unit: "°"))
                        Text(verbatim: Format.number(nav.groundSpeed * 3.6, 1, unit: "km/h"))
                    }
                    .font(.footnote.monospacedDigit())
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .glassEffect()
                    .padding(.bottom, 8)
                } else {
                    Text("No current position.")
                        .font(.footnote)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .glassEffect()
                        .padding(.bottom, 8)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        follow.toggle()
                        if follow, let last = track.last {
                            position = .camera(MapCamera(centerCoordinate: last, distance: 800))
                        }
                    } label: {
                        Label("Follow vehicle", systemImage: follow ? "location.fill" : "location")
                    }
                }
            }
            .navigationTitle("Track")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
