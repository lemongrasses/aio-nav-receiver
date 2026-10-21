//
//  Components.swift
//  MyApp
//

import SwiftUI

extension VehicleGate.Verdict {
    /// Reason shown when blocked, in the order the rules are checked.
    var title: LocalizedStringResource {
        switch self {
        case .usable: "Usable"
        case .noStatus: "No current status packet"
        case .notReady: "Status not READY"
        case .readyNotStable: "READY not yet stable"
        case .navTooOld: "Navigation data too old"
        case .navTimeBackwards: "Navigation time did not move forward"
        case .notAligned: "Navigation flags not aligned"
        case .notFinite: "Navigation data not finite"
        }
    }

    /// For "not READY": the state and the inhibit bit names.
    var detail: String? {
        guard case let .notReady(state, inhibit) = self else { return nil }
        let names = AIO.names(of: inhibit, in: StatusBits.inhibit)
        return DashboardState.name(of: state) + " · inhibit " + (names.isEmpty ? "0" : names.joined(separator: ", "))
    }
}

enum Format {
    static func number(_ value: Double, _ digits: Int, unit: String = "") -> String {
        guard value.isFinite else { return "—" }
        return String(format: "%.\(digits)f", value) + (unit.isEmpty ? "" : " " + unit)
    }

    static func duration(_ seconds: Double) -> String {
        let s = Int(seconds.rounded(.down))
        return String(format: "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
    }
}

/// A rounded section on the status page.
struct Card<Content: View>: View {
    let title: LocalizedStringKey
    let systemImage: String
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(title, systemImage: systemImage)
                .font(.headline)
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemGroupedBackground), in: .rect(cornerRadius: 20))
    }
}

struct InfoRow: View {
    let label: LocalizedStringKey
    let value: String

    init(_ label: LocalizedStringKey, _ value: String) {
        self.label = label
        self.value = value
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text(verbatim: value)
                .monospacedDigit()
                .multilineTextAlignment(.trailing)
        }
        .font(.subheadline)
    }
}

/// A flag or bit name; dimmed when off.
struct Chip: View {
    let text: String
    var tint: Color = .green
    var isOn = true

    var body: some View {
        Text(verbatim: text)
            .font(.caption.monospaced().weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .foregroundStyle(isOn ? .white : .secondary)
            .background(isOn ? tint : Color(.tertiarySystemFill), in: Capsule())
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
