import SwiftUI

// MARK: - Palette (asset catalog colours with light/dark variants)

extension Color {
    static let bg = Color("Bg")
    static let card = Color("Card")
    /// Deep green brand colour (asset "Primary"; named `brand` here to avoid SwiftUI's `Color.primary`).
    static let brand = Color("Primary")
    static let leaf = Color("Leaf")
    static let good = Color("Good")
    static let warn = Color("Warn")
    static let alertRed = Color("Alert")
    static let sun = Color("Sun")
    static let night = Color("Night")
    /// Subtle track / separator colour that adapts to the label colour.
    static let track = Color.primary.opacity(0.08)
}

enum Theme {
    static let radius: CGFloat = 20
    static let chipRadius: CGFloat = 16
    static let spacing: CGFloat = 16
    static let sectionSpacing: CGFloat = 24
}

extension Font {
    /// Big rounded numbers.
    static func hero(_ size: CGFloat, weight: Font.Weight = .bold) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }
}

// MARK: - Card surface

struct CardSurface: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    var padding: CGFloat
    var radius: CGFloat

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .shadow(color: scheme == .dark ? .clear : Color.black.opacity(0.06), radius: 14, y: 5)
    }
}

struct SoftShadow: ViewModifier {
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        content.shadow(color: scheme == .dark ? .clear : Color.black.opacity(0.06), radius: 14, y: 5)
    }
}

extension View {
    /// The light-mode-only card shadow, for surfaces that draw their own background.
    func softShadow() -> some View { modifier(SoftShadow()) }

    /// The standard card: 20pt radius, generous padding, soft shadow in light mode only.
    func card(padding: CGFloat = 20, radius: CGFloat = Theme.radius) -> some View {
        modifier(CardSurface(padding: padding, radius: radius))
    }

    /// Smaller surface for chips and grid cells.
    func chipSurface() -> some View {
        modifier(CardSurface(padding: 12, radius: Theme.chipRadius))
    }
}

// MARK: - Level → colour / symbol

enum LevelColor {
    /// Good / warn / alert (used for assessment, alerts, urgencies).
    static func color(for level: String?) -> Color {
        switch (level ?? "").lowercased() {
        case "good", "ok": return .good
        case "warn", "warning", "attention": return .warn
        case "alert", "urgent", "error": return .alertRed
        case "standby": return .secondary
        default: return .secondary
        }
    }

    /// Same, but "info" is neutral (findings / urgencies).
    static func infoColor(for level: String?) -> Color {
        switch (level ?? "").lowercased() {
        case "info": return .brand
        case "warn", "warning", "attention": return .warn
        case "alert", "urgent", "error": return .alertRed
        default: return .secondary
        }
    }

    static func symbol(for level: String?) -> String {
        switch (level ?? "").lowercased() {
        case "good", "ok": return "checkmark.circle.fill"
        case "warn", "warning", "attention": return "exclamationmark.triangle.fill"
        case "alert", "urgent", "error": return "exclamationmark.octagon.fill"
        case "standby": return "moon.zzz.fill"
        default: return "info.circle.fill"
        }
    }
}

// MARK: - Buttons

struct BigButtonStyle: ButtonStyle {
    var color: Color = .brand
    var filled: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity, minHeight: 52)
            .foregroundStyle(filled ? Color.white : color)
            .background(filled ? color : color.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.spring(duration: 0.25), value: configuration.isPressed)
    }
}

/// Pill chip used for badges, filters and small actions.
struct PillChip: View {
    var text: String
    var symbol: String? = nil
    var tint: Color = .brand
    var filled: Bool = false

    var body: some View {
        HStack(spacing: 6) {
            if let symbol { Image(systemName: symbol) }
            Text(text)
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(filled ? Color.white : tint)
        .padding(.horizontal, 14).padding(.vertical, 9)
        .background(filled ? tint : tint.opacity(0.14), in: Capsule())
    }
}

/// Tiny capsule label (status chips).
struct LevelChip: View {
    var text: String
    var color: Color
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }
}

/// A one-line notice with an icon on a tinted background.
struct InlineNotice: View {
    var symbol: String
    var text: String
    var tint: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(tint)
            Text(text).font(.subheadline.weight(.medium)).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
