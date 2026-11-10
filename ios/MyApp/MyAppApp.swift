//
//  MyAppApp.swift
//  MyApp
//

import SwiftUI

@main
struct MyAppApp: App {
    @State private var store = MonitorStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(store)
                .environment(\.uiLanguage, store.language)
                .environment(\.locale, store.language.locale)
                .preferredColorScheme(.light)       // the signal colours are tuned for a white page (D2)
        }
        .onChange(of: scenePhase, initial: true) {
            // iOS suspends apps in the background; release the port and pick up again on return.
            if scenePhase == .active {
                store.start()
            } else if scenePhase == .background {
                store.stop()
            }
        }
    }
}
