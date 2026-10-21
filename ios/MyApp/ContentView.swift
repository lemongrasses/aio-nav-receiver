//
//  ContentView.swift
//  MyApp
//

import SwiftUI

struct ContentView: View {
    @Environment(\.uiLanguage) private var lang

    var body: some View {
        // `.id(lang)` rebuilds a tab when the language changes: the navigation bar keeps its
        // title text otherwise, since the localization key itself does not change.
        TabView {
            Tab("Status", systemImage: "gauge.with.dots.needle.67percent") {
                StatusView().id(lang)
            }
            Tab("Charts", systemImage: "chart.xyaxis.line") {
                ChartsView().id(lang)
            }
            Tab("Track", systemImage: "map") {
                TrackMapView().id(lang)
            }
            Tab("Settings", systemImage: "gearshape") {
                SettingsView().id(lang)
            }
        }
    }
}

#Preview {
    ContentView()
        .environment(MonitorStore())
}
