//
//  SettingsView.swift
//  MyApp
//

import Darwin
import SwiftUI

struct SettingsView: View {
    @Environment(MonitorStore.self) private var store
    @State private var draft = MonitorSettings()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if store.localAddresses.isEmpty {
                        Text("Not connected to a network.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(store.localAddresses) { address in
                        LabeledContent {
                            Text(verbatim: address.address)
                                .monospacedDigit()
                                .textSelection(.enabled)
                        } label: {
                            Text(verbatim: address.interface)
                        }
                    }
                    LabeledContent("Receiving") {
                        Text(store.isListening ? "Yes" : "No")
                            .foregroundStyle(store.isListening ? .green : .red)
                    }
                } header: {
                    Text("This iPhone")
                } footer: {
                    Text("On the device, open Maintenance → AIO NAV config, set output_udp to this iPhone's address and the 0x04 port, then restart AIO NAV. output_udp has only one destination, so the iPhone then replaces any other receiver.")
                }

                Section {
                    LabeledContent("0x04 port") {
                        TextField(value: $draft.navPort, format: .number.grouping(.never)) { Text(verbatim: "9000") }
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                    }
                    Toggle("Separate 0x05 port", isOn: Binding(
                        get: { draft.statusPort != nil },
                        set: { draft.statusPort = $0 ? draft.navPort &+ 1 : nil }))
                    if draft.statusPort != nil {
                        LabeledContent("0x05 port") {
                            TextField(value: Binding(get: { draft.statusPort ?? draft.navPort },
                                                     set: { draft.statusPort = $0 }),
                                      format: .number.grouping(.never)) { Text(verbatim: "9001") }
                                .keyboardType(.numberPad)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    Stepper(value: $draft.statusMessageID, in: 1...255) {
                        LabeledContent("0x05 message ID") {
                            Text(verbatim: String(format: "0x%02X", draft.statusMessageID))
                                .monospacedDigit()
                        }
                    }
                    LabeledContent("Accept only source IP") {
                        TextField("Any", text: $draft.allowedSourceIP)
                            .keyboardType(.numbersAndPunctuation)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .multilineTextAlignment(.trailing)
                    }
                } header: {
                    Text("Receiving")
                } footer: {
                    Text("UDP has no authentication: anyone who can reach this port can fake READY. Enter the device's IP so packets from other sources are only counted.")
                }

                Section {
                    secondsStepper("Status timeout", value: $draft.statusTimeout, range: 0.5...30, step: 0.5)
                    secondsStepper("READY stable time", value: $draft.readyStable, range: 0...30, step: 0.5)
                    secondsStepper("Max navigation age", value: $draft.navMaxAge, range: 0.1...5, step: 0.1)
                } header: {
                    Text("Rules")
                } footer: {
                    Text("Defaults are 3.0 s, 2.0 s and 0.5 s, the same as web_monitor's VehicleGate. Do not loosen them for real use.")
                }

                Section {
                    Toggle("Keep screen on", isOn: $draft.keepScreenOn)
                } header: {
                    Text("Display")
                } footer: {
                    Text("iOS pauses apps in the background, so monitoring only runs while this app is on screen.")
                }

                Section {
                    Button("Apply") {
                        store.apply(draft)
                    }
                    .disabled(draft == store.settings || !isValid)
                    Button("Restore defaults") {
                        draft = MonitorSettings()
                    }
                    Button("Clear charts and statistics", role: .destructive) {
                        store.reset()
                    }
                } footer: {
                    if !isValid {
                        Text("Check the ports and the source IP address.")
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                draft = store.settings
                store.refreshLocalAddresses()
            }
        }
    }

    private var isValid: Bool {
        guard draft.navPort > 0, draft.statusPort.map({ $0 > 0 }) ?? true else { return false }
        guard let ip = draft.allowedSource else { return true }
        var addr = in_addr()
        return inet_pton(AF_INET, ip, &addr) == 1
    }

    private func secondsStepper(_ title: LocalizedStringKey, value: Binding<Double>,
                                range: ClosedRange<Double>, step: Double) -> some View {
        Stepper(value: value, in: range, step: step) {
            LabeledContent(title) {
                Text(verbatim: Format.number(value.wrappedValue, 1, unit: "s"))
                    .monospacedDigit()
            }
        }
    }
}
