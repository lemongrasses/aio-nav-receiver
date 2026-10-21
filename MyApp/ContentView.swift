//
//  ContentView.swift
//  MyApp
//

import SwiftUI

struct ContentView: View {
    @State private var count = 0

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "swift")
                .font(.system(size: 64))
                .foregroundStyle(.tint)

            Text("Hello, MyApp!")
                .font(.largeTitle.bold())

            Text("Tapped \(count) times")
                .font(.title3)
                .monospacedDigit()
                .contentTransition(.numericText())

            Button("Tap me") {
                withAnimation { count += 1 }
            }
            .buttonStyle(.glassProminent)
            .controlSize(.large)
        }
        .padding()
    }
}

#Preview {
    ContentView()
}
