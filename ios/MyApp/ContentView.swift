//
//  ContentView.swift
//  MyApp
//

import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            Tab("Status", systemImage: "gauge.with.dots.needle.67percent") {
                StatusView()
            }
            Tab("Charts", systemImage: "chart.xyaxis.line") {
                ChartsView()
            }
            Tab("Track", systemImage: "map") {
                TrackMapView()
            }
            Tab("Settings", systemImage: "gearshape") {
                SettingsView()
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(MonitorStore())
}
