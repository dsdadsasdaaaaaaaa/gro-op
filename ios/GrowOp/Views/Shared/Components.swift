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

// MARK: - Section title

struct SectionTitle: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.headline)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Lists

struct BulletList: View {
    let items: [String]
    var symbol: String = "circle.fill"
    var color: Color = .brand

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: symbol)
                        .font(.system(size: symbol == "circle.fill" ? 7 : 15))
                        .foregroundStyle(color)
                    Text(item)
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

/// Numbered steps with check circles.
struct NumberedList: View {
    let items: [String]
    var color: Color = .brand

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(items.enumerated()), id: \.offset) { idx, item in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    ZStack {
                        Circle().stroke(color, lineWidth: 1.5).frame(width: 26, height: 26)
                        Text("\(idx + 1)").font(.caption.weight(.bold)).foregroundStyle(color)
                    }
                    Text(item).font(.body).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

// MARK: - Created items (tasks / photo requests returned with advice)

struct CreatedItemsView: View {
    var tasks: [TaskItem]?
    var photoRequests: [PhotoRequest]?

    var body: some View {
        let t = tasks ?? []
        let r = photoRequests ?? []
        if !t.isEmpty || !r.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Added for you").font(.subheadline.weight(.semibold)).foregroundStyle(.secondary)
                FlowChips {
                    ForEach(t) { task in
                        PillChip(text: task.title ?? "Task", symbol: "checklist", tint: .brand)
                    }
                    ForEach(r) { req in
                        PillChip(text: req.title ?? "Photo", symbol: "camera.fill", tint: .night)
                    }
                }
                if !r.isEmpty {
                    Text("Photo requests are waiting in the Photos tab.").font(.caption).foregroundStyle(.secondary)
                }
            }
            .card()
        }
    }
}

/// Simple wrapping chip container.
struct FlowChips<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) { content }
        }
    }
}

// MARK: - Loading / empty

struct WorkingView: View {
    var title: String
    var subtitle: String? = nil
    var body: some View {
        VStack(spacing: 14) {
            ProgressView().controlSize(.large).tint(.brand)
            Text(title).font(.headline)
            if let subtitle {
                Text(subtitle).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct EmptyStateView: View {
    var symbol: String
    var title: String
    var message: String
    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle().fill(Color.brand.opacity(0.10)).frame(width: 84, height: 84)
                Image(systemName: symbol).font(.system(size: 36, weight: .medium)).foregroundStyle(Color.brand)
            }
            Text(title).font(.title3.weight(.semibold))
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
            Color.track
            if let image {
                Color.clear
                    .overlay(Image(uiImage: image).resizable().scaledToFill())
                    .clipped()
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
