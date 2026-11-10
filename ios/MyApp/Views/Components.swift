//
//  Components.swift
//  MyApp
//
//  Layout C: road-signage colours that only ever carry meaning (the desktop's ui/theme.py is the
//  same set), the signal mast, the alignment route and the other shared pieces.
//

import SwiftUI

extension EnvironmentValues {
    /// The one language the app shows (Settings → Language). Text with a localized key follows
    /// `locale`, which the app sets to match; code-built text uses this.
    @Entry var uiLanguage: UILanguage = .en
}

// MARK: - Tokens (docs/UI-PHONE-C.zh-TW.md §1.1)

extension Color {
    init(hex: UInt32) {
        self.init(red: Double(hex >> 16 & 0xFF) / 255, green: Double(hex >> 8 & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }

    static let asphalt = Color(hex: 0x1D252C)       // text, the mast, tab bar, headers
    static let kerb = Color(hex: 0xE9ECEE)          // page background
    static let panel = Color.white
    static let text2 = Color(hex: 0x3B454E)
    static let muted = Color(hex: 0x56616B)         // labels and hints
    static let faint = Color(hex: 0x6B757E)         // not received yet, future stations, out-of-date values
    static let line = Color(hex: 0xD5DADF)          // rules and outlines, never text
    static let rowRule = Color(hex: 0xEEF0F2)
    static let go = Color(hex: 0x1E7B45)
    static let wait = Color(hex: 0xF2B705)          // dark text on it
    static let stop = Color(hex: 0xB3261E)
    static let idle = Color(hex: 0x5F6A73)
    static let info = Color(hex: 0x1B4F9C)          // the blue instruction sign, the apply bar
    static let infoInk = Color(hex: 0xE3ECF9)
    static let lampOff = Color(hex: 0x2B353D)
    static let lampRingOff = Color(hex: 0x46525C)
    static let lampTextOff = Color(hex: 0x9AA4AC)
    static let goTint = Color(hex: 0xDDEFE3)
    static let goInk = Color(hex: 0x145A32)
    static let amber = Color(hex: 0x8A5A00)         // counters worth a look
    static let amberText = Color(hex: 0x6B4600)
    static let tabInactive = Color(hex: 0xAEB6BD)
    static let stationFuture = Color(hex: 0xAEB6BD)
    static let fieldBorder = Color(hex: 0x8A949C)
    static let blockedTrack = Color(hex: 0x7B858E)
}

extension SignalKind {
    /// The lamp and band colour.
    var color: Color {
        switch self {
        case .go: .go
        case .wait: .wait
        case .stop: .stop
        case .idle: .idle
        }
    }

    /// Text on the band: yellow needs dark ink.
    var ink: Color { self == .wait ? .asphalt : .white }

    /// The big word on white: yellow text would not read.
    var wordColor: Color {
        switch self {
        case .go: .go
        case .wait: .asphalt
        case .stop: .stop
        case .idle: .idle
        }
    }

    /// Which lamp is lit, top to bottom; nil = all dark.
    var lamp: Int? {
        switch self {
        case .stop: 0
        case .wait: 1
        case .go: 2
        case .idle: nil
        }
    }

    var accessibilityLabel: LocalizedStringKey {
        switch self {
        case .go: "Signal: green, usable"
        case .wait: "Signal: yellow, wait"
        case .stop: "Signal: red, problem"
        case .idle: "Signal: off, no data"
        }
    }

    /// The word beside the small mast in a header.
    func word(_ lang: UILanguage) -> String {
        switch self {
        case .go: Vocabulary.t("mast.go", lang)
        case .wait: Vocabulary.t("mast.wait", lang)
        case .stop: Vocabulary.t("mast.stop", lang)
        case .idle: Vocabulary.t("link.none", lang)
        }
    }
}

extension Font {
    /// The system font at a layout C size (§1.2) that grows with the system text size, up to the
    /// first accessibility size so the screens stay usable. ContentView rebuilds the tabs when the
    /// text size changes.
    static func scaled(size: CGFloat, weight: Font.Weight = .regular, design: Font.Design? = nil) -> Font {
        .system(size: scaledSize(size), weight: weight, design: design)
    }

    static func scaledSize(_ size: CGFloat) -> CGFloat {
        let current = UIApplication.shared.preferredContentSizeCategory
        let category = current > .accessibilityMedium ? .accessibilityMedium : current
        return UIFontMetrics.default.scaledValue(for: size, compatibleWith: UITraitCollection(preferredContentSizeCategory: category))
    }

    /// Numbers: the system font with tabular digits (D5).
    static func number(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
        .scaled(size: size, weight: weight).monospacedDigit()
    }
}

enum Format {
    static func number(_ value: Double, _ digits: Int, unit: String = "") -> String {
        guard value.isFinite else { return "—" }
        return String(format: "%.\(digits)f", value) + (unit.isEmpty ? "" : " " + unit)
    }

    static func duration(_ seconds: Double) -> String {
        Presentation.fmtDur(seconds)
    }
}

// MARK: - Signal mast (§1.3)

/// Three lamps, red on top, yellow in the middle, green at the bottom: the position says the
/// meaning, so it reads without colour. `dimmed` turns the lit lamp off (the flash on loss).
struct SignalMast: View {
    let kind: SignalKind
    var vertical = true
    var lamp: CGFloat = 20
    var showsWord = false
    var dimmed = false
    @Environment(\.uiLanguage) private var lang

    private static let colors: [Color] = [.stop, .wait, .go]

    var body: some View {
        let lamps = ForEach(0..<3, id: \.self) { i in lampView(i) }
        Group {
            if vertical {
                VStack(spacing: 5) { lamps }
                    .padding(6)
                    .background(Color.asphalt, in: .rect(cornerRadius: lamp / 2 + 6))
            } else {
                HStack(spacing: 6) {
                    lamps
                    if showsWord {
                        Text(verbatim: kind.word(lang))
                            .font(.scaled(size: 13, weight: .semibold))
                            .foregroundStyle(.white)
                            .padding(.leading, 2)
                    }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(kind.accessibilityLabel)
    }

    private func lampView(_ i: Int) -> some View {
        let lit = kind.lamp == i && !dimmed
        return Circle()
            .fill(lit ? Self.colors[i] : .lampOff)
            .overlay(Circle().strokeBorder(lit ? Color.white : .lampRingOff, lineWidth: 2))
            .overlay {
                if lit && lamp >= 34 {
                    Image(systemName: ["exclamationmark", "clock", "checkmark"][i])
                        .font(.scaled(size: lamp * 0.45, weight: .heavy))
                        .foregroundStyle(i == 1 ? Color.asphalt : .white)
                }
            }
            .frame(width: lamp, height: lamp)
    }
}

// MARK: - Alignment route (§2.3, §4.1 ③)

struct StationRail: View {
    let rail: Presentation.Rail
    @Environment(\.uiLanguage) private var lang

    private static let size: CGFloat = 30

    private enum Look { case done, now, go, lost, future }

    var body: some View {
        let n = Presentation.stations.count
        VStack(spacing: 6) {
            GeometryReader { geo in
                let half = Self.size / 2
                let x0 = half, x1 = geo.size.width - half
                let xs = (0..<n).map { x0 + (x1 - x0) * CGFloat($0) / CGFloat(n - 1) }
                ZStack(alignment: .topLeading) {
                    Capsule().fill(Color.line)
                        .frame(width: x1 - x0, height: 10)
                        .offset(x: x0, y: half - 5)
                    if rail.at > 0 {
                        Capsule().fill(Color.asphalt)
                            .frame(width: xs[rail.at] - x0, height: 10)
                            .offset(x: x0, y: half - 5)
                    }
                    ForEach(0..<n, id: \.self) { i in
                        station(i, last: i == n - 1)
                            .position(x: xs[i], y: half)
                    }
                }
            }
            .frame(height: Self.size)
            HStack(spacing: 0) {
                ForEach(0..<n, id: \.self) { i in
                    let look = look(i)
                    Text(verbatim: Vocabulary.t(Presentation.stations[i].key, lang))
                        .font(.scaled(size: 12, weight: [.now, .go, .lost].contains(look) ? .bold : .regular))
                        .foregroundStyle(look == .future ? Color.faint : .asphalt)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, alignment: i == 0 ? .leading : (i == n - 1 ? .trailing : .center))
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func look(_ i: Int) -> Look {
        if rail.at >= 0 && i < rail.at { return .done }
        if i == rail.at {
            switch rail.mode {
            case .done: return .go
            case .lost: return .lost
            default: return .now
            }
        }
        return .future
    }

    @ViewBuilder
    private func station(_ i: Int, last: Bool) -> some View {
        let look = look(i)
        let (fill, ink, outline): (Color, Color, Color) = switch look {
        case .done: (.asphalt, .white, .asphalt)
        case .now: (.wait, .asphalt, .asphalt)
        case .go: (.go, .white, .go)
        case .lost: (.stop, .white, .stop)
        case .future: (.panel, .faint, .stationFuture)
        }
        let s = Self.size
        if last {
            let shape = RoundedRectangle(cornerRadius: 5)
            ZStack {
                if look == .now {                       // ready settling: the plate fills up from below
                    shape.fill(Color.panel)
                    VStack(spacing: 0) {
                        Spacer(minLength: 0)
                        Rectangle().fill(Color.wait).frame(height: (s - 5) * rail.fraction)
                    }
                    .padding(2.5)
                } else {
                    shape.fill(fill)
                }
                shape.strokeBorder(outline, lineWidth: 2.5)
                if look == .go {
                    Image(systemName: "checkmark").font(.scaled(size: 14, weight: .heavy)).foregroundStyle(ink)
                } else if look == .lost {
                    Text(verbatim: "!").font(.number(16, .heavy)).foregroundStyle(ink)
                }
            }
            .frame(width: s, height: s)
        } else {
            ZStack {
                Circle().fill(fill)
                Circle().strokeBorder(outline, lineWidth: 2.5)
                if i > 0 {                              // start is a marker, not a step
                    Text(verbatim: "\(i)").font(.number(14, .bold)).foregroundStyle(ink)
                }
            }
            .frame(width: s, height: s)
        }
    }
}

// MARK: - Instruction sign (§4.1 ②)

struct InstructionPlate: View {
    let guide: Presentation.Guide

    var body: some View {
        if guide.kind == .quiet {
            Text(verbatim: guide.title)
                .font(.scaled(size: 15))
                .foregroundStyle(Color.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            let color: Color = guide.kind == .danger ? .stop : .info
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: "person.fill")
                    .font(.scaled(size: 22))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text(verbatim: guide.title)
                        .font(.scaled(size: guide.sub.isEmpty ? 21 : 18, weight: .bold))
                    if !guide.sub.isEmpty {
                        Text(verbatim: guide.sub)
                            .font(.scaled(size: 13))
                            .foregroundStyle(Color.infoInk)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(color, in: .rect(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(.white, lineWidth: 3))
            .padding(2)
            .background(color, in: .rect(cornerRadius: 8))
            .accessibilityElement(children: .combine)
        }
    }
}

// MARK: - Chips

/// A blocking condition: amber when it is a normal alignment step, red when it is a problem.
struct SignChip: View {
    let text: String
    let expected: Bool

    var body: some View {
        let (bg, ink, border): (Color, Color, Color) = expected
            ? (Color(hex: 0xFFF1BF), .amberText, Color(hex: 0xE5C44D))
            : (Color(hex: 0xFBE4E2), .stop, Color(hex: 0xE6A39E))
        Text(verbatim: text)
            .font(.scaled(size: 14, weight: .semibold))
            .foregroundStyle(ink)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(bg, in: .rect(cornerRadius: 4))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(border, lineWidth: 1.5))
    }
}

/// An aiding flag: tinted when it appeared this epoch.
struct FlagChip: View {
    let text: String
    let on: Bool
    var faint = false

    var body: some View {
        Text(verbatim: text)
            .font(.number(13))
            .foregroundStyle(on && !faint ? Color.goInk : .faint)
            .padding(.horizontal, 7)
            .padding(.vertical, 1)
            .background(on && !faint ? Color.goTint : .panel, in: .rect(cornerRadius: 3))
            .overlay(RoundedRectangle(cornerRadius: 3)
                .strokeBorder(on && !faint ? Color(hex: 0xBFDCC9) : .line, lineWidth: 1))
    }
}

/// A lamp with its name: the alignment flags, the conditions met.
struct DotLabel: View {
    let text: String
    let on: Bool
    var faint = false

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(on && !faint ? Color.go : .clear)
                .overlay(Circle().strokeBorder(on && !faint ? Color.clear : .fieldBorder, lineWidth: 1.5))
                .frame(width: 9, height: 9)
            Text(verbatim: text)
                .font(.scaled(size: 13, weight: on ? .regular : .semibold))
                .foregroundStyle(faint ? Color.faint : .asphalt)
                .lineLimit(2)
        }
    }
}

// MARK: - Streams (§4.1 ④)

struct StreamCell: View {
    let label: String
    let link: Presentation.Link

    var body: some View {
        let lost = link.kind == .stop
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Circle()
                    .fill(link.kind == .go ? Color.go : (lost ? Color.stop : Color.faint))
                    .frame(width: 10, height: 10)
                Text(verbatim: label).font(.scaled(size: 12)).foregroundStyle(Color.muted)
            }
            Text(verbatim: link.text)
                .font(.number(14, .semibold))
                .foregroundStyle(lost ? Color.stop : .asphalt)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.panel)
        .overlay { if lost { Rectangle().strokeBorder(Color.stop, lineWidth: 2) } }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Expandable summary rows (§4.1 ⑤)

struct ExpandRow<Summary: View, Content: View>: View {
    let title: LocalizedStringKey
    let expanded: Bool
    let toggle: () -> Void
    @ViewBuilder var summary: Summary
    @ViewBuilder var content: Content

    var body: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Color.line).frame(height: 1)
            Button(action: toggle) {
                HStack(spacing: 10) {
                    Text(title)
                        .font(.scaled(size: 15, weight: .semibold))
                        .foregroundStyle(Color.asphalt)
                        .fixedSize()
                    Spacer(minLength: 8)
                    summary
                        .font(.scaled(size: 13))
                        .multilineTextAlignment(.trailing)    // wraps under large text instead of cutting off
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.scaled(size: 13, weight: .semibold))
                        .foregroundStyle(Color.muted)
                }
                .padding(.horizontal, 16)
                .frame(minHeight: 48)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityValue(expanded ? Text("Expanded") : Text("Collapsed"))
            if expanded {
                content
                    .padding(.horizontal, 16)
                    .padding(.bottom, 14)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Color.panel)
    }
}

/// Two columns of label (12, muted) over value (14).
struct FieldGrid: View {
    let fields: [(label: LocalizedStringKey, value: String)]
    var faint = false

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible(), alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                  alignment: .leading, spacing: 8) {
            ForEach(fields.indices, id: \.self) { i in
                VStack(alignment: .leading, spacing: 1) {
                    Text(fields[i].label).font(.scaled(size: 12)).foregroundStyle(Color.muted)
                    Text(verbatim: fields[i].value)
                        .font(.number(14))
                        .foregroundStyle(faint ? Color.faint : .asphalt)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

// MARK: - Headers (§4.0)

extension View {
    /// The dark header of the charts, track and settings tabs: white title on the left, the
    /// small mast with its word on the right.
    func signHeader(_ title: LocalizedStringKey, kind: SignalKind?) -> some View {
        self
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color.asphalt, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Text(title)
                        .font(.scaled(size: 18, weight: .bold))
                        .foregroundStyle(.white)
                        .fixedSize()
                        .accessibilityAddTraits(.isHeader)
                }
                .sharedBackgroundVisibility(.hidden)
                if let kind {
                    ToolbarItem(placement: .topBarTrailing) {
                        SignalMast(kind: kind, vertical: false, lamp: 14, showsWord: true)
                    }
                    .sharedBackgroundVisibility(.hidden)
                }
            }
    }
}

/// Lays children out left to right, wrapping onto new lines.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = arrange(subviews, width: width)
        let height = rows.last.map { $0.y + $0.height } ?? 0
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for row in arrange(subviews, width: bounds.width) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: bounds.minY + row.y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
        }
    }

    private struct Row {
        var indices: [Int] = []
        var y: CGFloat = 0
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if !row.indices.isEmpty && row.width + spacing + size.width > width {
                rows.append(row)
                row = Row(y: row.y + row.height + spacing)
            }
            row.width += (row.indices.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.indices.append(index)
        }
        if !row.indices.isEmpty {
            rows.append(row)
        }
        return rows
    }
}
