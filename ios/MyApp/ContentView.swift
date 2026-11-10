//
//  ContentView.swift
//  MyApp
//

import SwiftUI

enum AppTab: Hashable, CaseIterable {
    case status, charts, track, settings

    var title: LocalizedStringKey {
        switch self {
        case .status: "Status"
        case .charts: "Charts"
        case .track: "Track"
        case .settings: "Settings"
        }
    }

    var icon: Image {
        switch self {
        case .status: Image("SignalTab")
        case .charts: Image(systemName: "chart.xyaxis.line")
        case .track: Image(systemName: "mappin.and.ellipse")
        case .settings: Image(systemName: "gearshape")
        }
    }
}

struct ContentView: View {
    @Environment(\.uiLanguage) private var lang
    @Environment(\.dynamicTypeSize) private var textSize
    @State private var tab = AppTab.status

    var body: some View {
        // The system tab bar floats as glass on iOS 26 and ignores a background colour, and a
        // TabView does not pass a bottom inset on to its tabs, so the layout C bar (asphalt, §4.0)
        // sits under a stack that keeps every tab alive (and its state) and shows one.
        // `.id(lang)` rebuilds a tab when the language changes: the navigation bar keeps its
        // title text otherwise, since the localization key itself does not change.
        VStack(spacing: 0) {
            ZStack {
                page(.status) { StatusView() }
                page(.charts) { ChartsView() }
                page(.track) { TrackMapView() }
                page(.settings) { SettingsView() }
            }
            SignTabBar(selection: $tab)
                .id(textSize)
        }
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
    }

    private func page(_ value: AppTab, @ViewBuilder _ content: () -> some View) -> some View {
        let on = tab == value
        return content()
            .id([lang.rawValue, "\(textSize)"])     // Font.scaled reads the text size when built
            .opacity(on ? 1 : 0)
            .allowsHitTesting(on)
            .accessibilityHidden(!on)
    }
}

/// Asphalt, white for the selected tab, grey for the others.
struct SignTabBar: View {
    @Binding var selection: AppTab

    var body: some View {
        HStack(spacing: 0) {
            ForEach(AppTab.allCases, id: \.self) { tab in
                let on = tab == selection
                Button {
                    selection = tab
                } label: {
                    VStack(spacing: 4) {
                        tab.icon
                            .renderingMode(.template)
                            .font(.system(size: 20, weight: .medium))
                            .frame(height: 24)
                        Text(tab.title)
                            .font(.scaled(size: 12, weight: on ? .bold : .regular))
                    }
                    .foregroundStyle(on ? Color.white : .tabInactive)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
            }
        }
        .padding(.top, 6)
        .background(Color.asphalt.ignoresSafeArea(edges: .bottom))
    }
}

#Preview {
    ContentView()
        .environment(MonitorStore())
}
