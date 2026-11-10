//
//  SettingsView.swift
//  MyApp
//
//  Layout C settings tab (docs/UI-PHONE-C.zh-TW.md §4.4). The draft-and-apply behaviour, the
//  ranges, steps and validation are unchanged; only the grouping and the look are new.
//

import Darwin
import SwiftUI

struct SettingsView: View {
    @Environment(MonitorStore.self) private var store
    @Environment(\.uiLanguage) private var lang
    @State private var draft = MonitorSettings()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    everyday
                    advanced
                    actions
                }
                .padding(.bottom, 16)
            }
            .background(Color.kerb)
            .safeAreaInset(edge: .bottom, spacing: 0) { applyBar }
            .signHeader("Settings", kind: nil)
            .onAppear {
                draft = store.settings
                store.refreshLocalAddresses()
            }
        }
    }

    // MARK: Everyday

    private var everyday: some View {
        Group {
            GroupHeader(title: Vocabulary.t("set.sec_everyday", lang), sub: "Changing these never changes the verdict")
            SettingsBlock {
                if store.localAddresses.isEmpty {
                    SettingRow { Text("Not connected to a network.").foregroundStyle(Color.muted) }
                }
                ForEach(store.localAddresses) { address in
                    SettingRow {
                        Text(verbatim: lang.text("This iPhone") + " " + address.interface)
                        Spacer()
                        Text(verbatim: address.address)
                            .font(.number(17, .semibold))
                            .fixedSize()                // an address is never split; the label wraps instead
                            .textSelection(.enabled)
                    }
                }
                SettingRow {
                    Text("Receiving")
                    Spacer()
                    Text(store.isListening ? "● Yes" : "● No")
                        .font(.scaled(size: 15, weight: .bold))
                        .foregroundStyle(store.isListening ? Color.go : .stop)
                }
                SettingRow {
                    Text("Version")
                    Spacer()
                    Text(verbatim: Self.version).font(.number(15, .semibold))
                }
                Footnote("On the device, open Maintenance → AIO NAV config, set output_udp to this iPhone's address and the 0x04 port, then restart AIO NAV. output_udp has only one destination, so the iPhone then replaces any other receiver.")
                SettingRow {
                    let label = VStack(alignment: .leading, spacing: 2) {
                        Text("Language")
                        Text("Applies at once, no Apply needed").font(.scaled(size: 12.5)).foregroundStyle(Color.muted)
                    }
                    let buttons = LanguageButtons(selection: store.settings.language) { code in
                        draft.language = code
                        store.setLanguage(code)         // applies at once, like the desktop; listening carries on
                    }
                    // The buttons never shorten their words: they go under the label when they do not fit beside it.
                    ViewThatFits(in: .horizontal) {
                        HStack { label; Spacer(minLength: 8); buttons }
                        VStack(alignment: .leading, spacing: 8) { label; buttons }
                            .padding(.vertical, 8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                SettingRow {
                    Toggle("Keep screen on", isOn: $draft.keepScreenOn).tint(.asphalt)
                }
                Footnote("iOS pauses apps in the background, so monitoring only runs while this app is on screen.")
            }
        }
    }

    // MARK: Advanced

    private var advanced: some View {
        Group {
            GroupHeader(title: Vocabulary.t("set.sec_advanced", lang), sub: nil,
                        subText: Vocabulary.t("set.advanced_sub", lang))
            SettingsBlock {
                SettingRow {
                    Text("0x04 port")
                    Spacer()
                    NumberField(value: $draft.navPort, placeholder: "9000", invalid: draft.navPort == 0)
                }
                SettingRow {
                    Toggle("Separate 0x05 port", isOn: Binding(
                        get: { draft.statusPort != nil },
                        set: { draft.statusPort = $0 ? draft.navPort &+ 1 : nil }))
                        .tint(.asphalt)
                }
                if draft.statusPort != nil {
                    SettingRow {
                        Text("0x05 port")
                        Spacer()
                        NumberField(value: Binding(get: { draft.statusPort ?? draft.navPort }, set: { draft.statusPort = $0 }),
                                    placeholder: "9001", invalid: draft.statusPort == 0)
                    }
                }
                SettingRow {
                    Text("0x05 message ID")
                    Spacer()
                    SignStepper(text: String(format: "0x%02X", draft.statusMessageID),
                                down: draft.statusMessageID > 1 ? { draft.statusMessageID -= 1 } : nil,
                                up: draft.statusMessageID < 255 ? { draft.statusMessageID += 1 } : nil)
                }
                SettingRow {
                    Text("Accept only from IP")
                    Spacer()
                    TextField("Any", text: $draft.allowedSourceIP)
                        .keyboardType(.numbersAndPunctuation)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .multilineTextAlignment(.trailing)
                        .font(.number(17, .semibold))
                        .fieldBox(width: 160, invalid: !ipValid)
                }
                Footnote("UDP has no authentication: anyone who can reach this port can fake the ready status. Enter the device's IP so packets from other senders are only counted.")
                VStack(alignment: .leading, spacing: 0) {
                    Text("Rules: do not loosen them for real use")
                        .font(.scaled(size: 14, weight: .bold))
                        .foregroundStyle(Color.stop)
                        .padding(.top, 4)
                        .padding(.bottom, 2)
                    secondsRow("Status timeout", value: $draft.statusTimeout, range: 0.5...30, step: 0.5)
                    secondsRow("Ready hold time", value: $draft.readyStable, range: 0...30, step: 0.5)
                    secondsRow("Navigation max age", value: $draft.navMaxAge, range: 0.1...5, step: 0.1)
                    Footnote("Defaults are 3.0, 2.0 and 0.5 s, the same as the desktop app.")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .overlay(Rectangle().strokeBorder(Color.stop, lineWidth: 2))
                .padding(.top, 12)
            }
        }
    }

    // MARK: Restore, clear

    private var actions: some View {
        SettingsBlock {
            HStack(spacing: 12) {
                Text("Puts this page's fields back to the defaults. They take effect when you tap Apply.")
                    .font(.scaled(size: 14)).foregroundStyle(Color.text2)
                Spacer(minLength: 8)
                Button("Restore defaults") {
                    let language = draft.language
                    draft = MonitorSettings()
                    draft.language = language
                }
                .buttonStyle(OutlineButton(color: .asphalt))
            }
            .padding(.vertical, 6)
            Rectangle().fill(Color.rowRule).frame(height: 1)
            HStack(spacing: 12) {
                Text("Clears the charts, the track and the packet counts, at once.")
                    .font(.scaled(size: 14)).foregroundStyle(Color.text2)
                Spacer(minLength: 8)
                Button("Clear charts and statistics") {
                    store.reset()
                }
                .buttonStyle(OutlineButton(color: .stop))
            }
            .padding(.vertical, 6)
        }
        .padding(.top, 12)
    }

    // MARK: Apply bar

    /// The fields that differ from what is in use (the language applies at once, so never pending).
    private var pending: [String] {
        let s = store.settings
        var out: [(Bool, String.LocalizationValue)] = [
            (draft.navPort != s.navPort, "0x04 port"),
            (draft.statusPort != s.statusPort, "0x05 port"),
            (draft.statusMessageID != s.statusMessageID, "0x05 message ID"),
            (draft.allowedSourceIP.trimmingCharacters(in: .whitespaces) != s.allowedSourceIP.trimmingCharacters(in: .whitespaces),
             "Accept only from IP"),
            (draft.statusTimeout != s.statusTimeout, "Status timeout"),
            (draft.readyStable != s.readyStable, "Ready hold time"),
            (draft.navMaxAge != s.navMaxAge, "Navigation max age"),
            (draft.keepScreenOn != s.keepScreenOn, "Keep screen on"),
        ]
        out = out.filter(\.0)
        return out.map { lang.text($0.1) }
    }

    @ViewBuilder
    private var applyBar: some View {
        let changed = pending
        if !changed.isEmpty {
            HStack(spacing: 12) {
                if isValid {
                    Text("\(changed.count) changes not applied: \(Vocabulary.joined(changed, lang))")
                        .font(.scaled(size: 14))
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text("Check the ports and the source IP address.")
                        .font(.scaled(size: 14, weight: .semibold))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Button {
                    var new = draft
                    new.language = store.settings.language
                    store.apply(new)
                } label: {
                    Text("Apply")
                        .font(.scaled(size: 15, weight: .bold))
                        .foregroundStyle(isValid ? Color.info : .faint)
                        .padding(.horizontal, 22)
                        .frame(minHeight: 44)
                        .background(Color.white, in: .rect(cornerRadius: 4))
                }
                .buttonStyle(.plain)
                .disabled(!isValid)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(isValid ? Color.info : .stop)
        }
    }

    // MARK: Helpers

    static let version: String = {
        let info = Bundle.main.infoDictionary ?? [:]
        let short = info["CFBundleShortVersionString"] as? String ?? "?"
        let build = info["CFBundleVersion"] as? String ?? "?"
        return "\(short) (\(build))"
    }()

    private var ipValid: Bool {
        guard let ip = draft.allowedSource else { return true }
        var addr = in_addr()
        return inet_pton(AF_INET, ip, &addr) == 1
    }

    private var isValid: Bool {
        draft.navPort > 0 && (draft.statusPort.map { $0 > 0 } ?? true) && ipValid
    }

    private func secondsRow(_ title: LocalizedStringKey, value: Binding<Double>,
                            range: ClosedRange<Double>, step: Double) -> some View {
        SettingRow {
            Text(title)
            Spacer()
            SignStepper(text: Format.number(value.wrappedValue, 1, unit: "s"),
                        down: value.wrappedValue - step >= range.lowerBound - 1e-9
                            ? { value.wrappedValue = max(range.lowerBound, ((value.wrappedValue - step) * 10).rounded() / 10) } : nil,
                        up: value.wrappedValue + step <= range.upperBound + 1e-9
                            ? { value.wrappedValue = min(range.upperBound, ((value.wrappedValue + step) * 10).rounded() / 10) } : nil)
        }
    }
}

// MARK: - Pieces

private struct GroupHeader: View {
    let title: String
    let sub: LocalizedStringKey?
    var subText: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(verbatim: title).font(.scaled(size: 17, weight: .bold))
            if let sub {
                Text(sub).font(.scaled(size: 13)).foregroundStyle(Color.muted)
            } else if let subText {
                Text(verbatim: subText).font(.scaled(size: 13)).foregroundStyle(Color.muted)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 18)
        .padding(.bottom, 8)
    }
}

private struct SettingsBlock<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) { content }
            .padding(.horizontal, 16)
            .padding(.top, 4)
            .padding(.bottom, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.panel)
    }
}

/// At least 50 high, a hairline above.
private struct SettingRow<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Color.rowRule).frame(height: 1)
            HStack(spacing: 12) { content }
                .font(.scaled(size: 15))
                .foregroundStyle(Color.asphalt)
                .frame(minHeight: 50)
        }
    }
}

private struct Footnote: View {
    let text: LocalizedStringKey

    init(_ text: LocalizedStringKey) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .font(.scaled(size: 13))
            .foregroundStyle(Color.muted)
            .lineSpacing(2)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.vertical, 6)
    }
}

private struct NumberField: View {
    @Binding var value: UInt16
    let placeholder: String
    let invalid: Bool

    var body: some View {
        TextField(value: $value, format: .number.grouping(.never)) { Text(verbatim: placeholder) }
            .keyboardType(.numberPad)
            .multilineTextAlignment(.trailing)
            .font(.number(17, .semibold))
            .fieldBox(width: 120, invalid: invalid)
    }
}

extension View {
    /// The settings input box: a grey outline, red when the value is not valid.
    func fieldBox(width: CGFloat, invalid: Bool) -> some View {
        self
            .padding(.horizontal, 10)
            .frame(width: width, height: 42)
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(invalid ? Color.stop : .fieldBorder,
                                                                    lineWidth: invalid ? 2 : 1.5))
    }
}

/// − value +, 44 × 44 buttons outlined in asphalt.
private struct SignStepper: View {
    let text: String
    let down: (() -> Void)?
    let up: (() -> Void)?

    var body: some View {
        HStack(spacing: 6) {
            button("−", label: "Decrease", action: down)
            Text(verbatim: text).font(.number(17, .semibold)).frame(minWidth: 58)
            button("+", label: "Increase", action: up)
        }
        .accessibilityElement(children: .contain)
    }

    private func button(_ symbol: String, label: LocalizedStringKey, action: (() -> Void)?) -> some View {
        Button {
            action?()
        } label: {
            Text(verbatim: symbol)
                .font(.scaled(size: 22, weight: .bold))
                .foregroundStyle(action == nil ? Color.faint : .asphalt)
                .frame(width: 44, height: 44)
                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(action == nil ? Color.line : .asphalt, lineWidth: 1.5))
        }
        .buttonStyle(.plain)
        .disabled(action == nil)
        .accessibilityLabel(label)
    }
}

/// Follow system / 繁體中文 / English as three joined buttons.
private struct LanguageButtons: View {
    let selection: String?
    let pick: (String?) -> Void

    var body: some View {
        HStack(spacing: 0) {
            option(nil) { Text("Follow system") }
            ForEach(UILanguage.allCases, id: \.rawValue) { lang in
                option(lang.rawValue) { Text(verbatim: lang.nativeName) }
            }
        }
        .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(Color.asphalt, lineWidth: 1.5))
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Language"))
    }

    private func option(_ code: String?, @ViewBuilder label: () -> Text) -> some View {
        let on = selection == code
        return Button {
            pick(code)
        } label: {
            label()
                .font(.scaled(size: 13.5, weight: .semibold))
                .fixedSize()
                .foregroundStyle(on ? Color.white : .asphalt)
                .padding(.horizontal, 9)
                .frame(minHeight: 40)
                .background(on ? Color.asphalt : .white)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isSelected, .isButton] : .isButton)
    }
}

private struct OutlineButton: ButtonStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.scaled(size: 14, weight: .semibold))
            .foregroundStyle(color)
            .lineLimit(2)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 12)
            .frame(minHeight: 44)
            .background(configuration.isPressed ? Color.kerb : .white, in: .rect(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(color, lineWidth: 1.5))
    }
}
