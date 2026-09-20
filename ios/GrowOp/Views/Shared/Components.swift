import SwiftUI

// MARK: - Alerts

struct AlertMessage: Identifiable {
    let id = UUID()
    var title: String = "Something went wrong"
    var message: String
}

extension View {
    /// Presents a simple OK alert bound to an optional AlertMessage.
    func errorAlert(_ item: Binding<AlertMessage?>) -> some View {
        alert(item: item) { a in
            Alert(title: Text(a.title), message: Text(a.message), dismissButton: .default(Text("OK")))
        }
    }
}

// MARK: - Colors for levels / severities

enum LevelColor {
    static func color(for level: String?) -> Color {
        switch (level ?? "").lowercased() {
        case "good", "ok", "info": return .green
        case "warn", "warning", "attention": return .orange
        case "alert", "urgent", "error": return .red
        default: return .gray
        }
    }

    static func infoColor(for level: String?) -> Color {
        // For finding severities / urgencies where "info" is neutral rather than good.
        switch (level ?? "").lowercased() {
        case "info": return .blue
        case "warn", "warning", "attention": return .orange
        case "alert", "urgent", "error": return .red
        default: return .gray
        }
    }

    static func symbol(for level: String?) -> String {
        switch (level ?? "").lowercased() {
        case "good", "ok": return "checkmark.circle.fill"
        case "warn", "warning", "attention": return "exclamationmark.triangle.fill"
        case "alert", "urgent", "error": return "exclamationmark.octagon.fill"
        default: return "info.circle.fill"
        }
    }
}

// MARK: - Card container

struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

extension View {
    func card() -> some View { modifier(CardBackground()) }
}

struct SectionTitle: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.headline)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Bullet list

struct BulletList: View {
    let items: [String]
    var symbol: String = "circle.fill"
    var color: Color = .accentColor

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: symbol)
                        .font(.system(size: symbol == "circle.fill" ? 7 : 14))
                        .foregroundStyle(color)
                        .padding(.top, symbol == "circle.fill" ? 2 : 0)
                    Text(item)
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

// MARK: - Big action button

struct BigButtonStyle: ButtonStyle {
    var color: Color = .accentColor
    var filled: Bool = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundStyle(filled ? Color.white : color)
            .background(filled ? color : color.opacity(0.15), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}

// MARK: - Created items (tasks / photo requests returned with advice)

struct CreatedItemsView: View {
    var tasks: [TaskItem]?
    var photoRequests: [PhotoRequest]?

    var body: some View {
        if let tasks, !tasks.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label("Added to your tasks", systemImage: "checklist")
                    .font(.subheadline.weight(.semibold))
                ForEach(tasks) { t in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "circle").foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(t.title ?? "Task")
                            if let due = t.due, !due.isEmpty {
                                Text("Due \(Formatting.friendlyDay(due))").font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .card()
        }
        if let reqs = photoRequests, !reqs.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Label("The advisor would like a photo", systemImage: "camera")
                    .font(.subheadline.weight(.semibold))
                ForEach(reqs) { r in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.title ?? "Photo").fontWeight(.medium)
                        if let i = r.instructions, !i.isEmpty {
                            Text(i).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                }
                Text("Find it in the Photos tab.").font(.caption).foregroundStyle(.secondary)
            }
            .card()
        }
    }
}

// MARK: - Loading overlay

struct WorkingView: View {
    var title: String
    var subtitle: String? = nil
    var body: some View {
        VStack(spacing: 14) {
            ProgressView().controlSize(.large)
            Text(title).font(.headline)
            if let subtitle {
                Text(subtitle).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Empty state

struct EmptyStateView: View {
    var symbol: String
    var title: String
    var message: String
    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: symbol).font(.system(size: 40)).foregroundStyle(.secondary)
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 30)
    }
}

// MARK: - Thumbnail loader (needs auth header, so goes via APIClient)

struct PhotoThumbnail: View {
    @Environment(AppState.self) private var app
    let photoID: Int
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            Color(.tertiarySystemFill)
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else if failed {
                Image(systemName: "photo").foregroundStyle(.secondary)
            } else {
                ProgressView()
            }
        }
        .clipped()
        .task(id: photoID) {
            image = await app.thumbnail(for: photoID)
            if image == nil { failed = true }
        }
    }
}

// MARK: - Score / level chip

struct LevelChip: View {
    var text: String
    var color: Color
    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.18), in: Capsule())
            .foregroundStyle(color)
    }
}
