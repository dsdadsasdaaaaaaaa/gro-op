import SwiftUI
import PhotosUI

/// A picked image waiting to be sent, optionally answering a request.
struct PendingPhoto: Identifiable {
    let id = UUID()
    var image: UIImage
    var request: PhotoRequest?
}

struct PhotosView: View {
    @Environment(AppState.self) private var app
    @State private var cameraTarget: PhotoRequest?
    @State private var showCamera = false
    @State private var libraryTarget: PhotoRequest?
    @State private var showLibrary = false
    @State private var librarySelection: PhotosPickerItem?
    @State private var pending: PendingPhoto?
    @State private var alert: AlertMessage?
    @State private var skipping: Int?

    private let gridColumns = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    PlantSwitcher()
                    if !app.openRequestsForSelected.isEmpty {
                        SectionTitle(text: "The advisor wants to see")
                        ForEach(app.openRequestsForSelected) { r in
                            PhotoRequestCard(request: r,
                                             onTake: { startCamera(for: r) },
                                             onChoose: { startLibrary(for: r) },
                                             onSkip: { Task { await skip(r) } },
                                             busy: skipping == r.id)
                        }
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        Label("Send a photo", systemImage: "camera.viewfinder").font(.title3.weight(.semibold))
                        Text("Any photo of your plants — the advisor will check it over.")
                            .font(.subheadline).foregroundStyle(.secondary)
                        HStack(spacing: 10) {
                            Button { startCamera(for: nil) } label: { Label("Take photo", systemImage: "camera.fill") }
                                .buttonStyle(BigButtonStyle())
                            Button { startLibrary(for: nil) } label: { Label("Choose", systemImage: "photo.on.rectangle") }
                                .buttonStyle(BigButtonStyle(filled: false))
                        }
                    }
                    .card()

                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(text: "Past photos")
                        if app.photosForSelected.isEmpty {
                            Text("No photos yet.").font(.subheadline).foregroundStyle(.secondary)
                        } else {
                            LazyVGrid(columns: gridColumns, spacing: 6) {
                                ForEach(app.photosForSelected) { p in
                                    NavigationLink(value: p.id) {
                                        PhotoGridCell(photo: p)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
                .padding(Theme.spacing)
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("Photos")
            .navigationDestination(for: Int.self) { id in
                if let p = app.photos.first(where: { $0.id == id }) {
                    PhotoDetailView(photo: p)
                } else {
                    Text("Photo not found")
                }
            }
            .refreshable {
                await app.loadPhotoRequests()
                await app.loadPhotos()
            }
            .task {
                await app.loadPhotoRequests()
                await app.loadPhotos()
            }
            .fullScreenCover(isPresented: $showCamera) {
                CameraPicker { img in
                    showCamera = false
                    if let img { pending = PendingPhoto(image: img, request: cameraTarget) }
                    cameraTarget = nil
                }
                .ignoresSafeArea()
            }
            .photosPicker(isPresented: $showLibrary, selection: $librarySelection, matching: .images)
            .onChange(of: librarySelection) { _, item in
                guard let item else { return }
                Task {
                    defer { librarySelection = nil }
                    if let data = try? await item.loadTransferable(type: Data.self), let img = UIImage(data: data) {
                        pending = PendingPhoto(image: img, request: libraryTarget)
                    } else {
                        alert = AlertMessage(message: "Couldn't load that photo.")
                    }
                    libraryTarget = nil
                }
            }
            .sheet(item: $pending) { p in
                PhotoSubmitSheet(pending: p)
            }
            .errorAlert($alert)
        }
    }

    private func startCamera(for request: PhotoRequest?) {
        guard CameraPicker.isAvailable else {
            alert = AlertMessage(title: "No camera", message: "This device has no camera available. Use \"Choose\" to pick a photo instead.")
            return
        }
        cameraTarget = request
        showCamera = true
    }

    private func startLibrary(for request: PhotoRequest?) {
        libraryTarget = request
        showLibrary = true
    }

    private func skip(_ r: PhotoRequest) async {
        skipping = r.id
        defer { skipping = nil }
        do { try await app.skipPhotoRequest(id: r.id) }
        catch { alert = AlertMessage(message: error.localizedDescription) }
    }
}

// MARK: - Request card

struct PhotoRequestCard: View {
    let request: PhotoRequest
    var onTake: () -> Void
    var onChoose: () -> Void
    var onSkip: () -> Void
    var busy: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.night.opacity(0.14))
                    Image(systemName: "camera.fill").font(.system(size: 14, weight: .semibold)).foregroundStyle(Color.night)
                }
                .frame(width: 30, height: 30)
                Text(request.title ?? "Photo request").font(.title3.weight(.semibold))
                Spacer()
                Text(Formatting.relative(request.createdAt)).font(.caption).foregroundStyle(.tertiary)
            }
            if let i = request.instructions, !i.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    RoundedRectangle(cornerRadius: 2).fill(Color.brand).frame(width: 4)
                    Text(i)
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.brand.opacity(0.08), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            if let r = request.reason, !r.isEmpty {
                Label(r, systemImage: "questionmark.circle").font(.footnote).foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
                Button(action: onTake) { Label("Take photo", systemImage: "camera.fill") }
                    .buttonStyle(BigButtonStyle())
                Button(action: onChoose) { Label("Choose", systemImage: "photo.on.rectangle") }
                    .buttonStyle(BigButtonStyle(filled: false))
            }
            Button(action: onSkip) {
                HStack { if busy { ProgressView().controlSize(.small) }; Text("Skip this one") }
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
            .disabled(busy)
        }
        .card()
    }
}

// MARK: - Grid cell

struct PhotoGridCell: View {
    let photo: Photo

    private func scoreColor(_ s: Double) -> Color {
        if s >= 8 { return .good }
        if s >= 5 { return .warn }
        return .alertRed
    }

    var body: some View {
        Color.clear
            .aspectRatio(1, contentMode: .fit)
            .overlay(PhotoThumbnail(photoID: photo.id))
            .overlay(alignment: .topLeading) {
                if photo.isFromCamera {
                    Image(systemName: "video.fill")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.white)
                        .padding(5)
                        .background(Color.night.opacity(0.85), in: Circle())
                        .padding(6)
                }
            }
            .overlay(alignment: .bottomLeading) {
                if let score = photo.analysis?.healthScore, score > 0 {
                    Text("\(Formatting.number(score))/10")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(Color.white)
                        .padding(.horizontal, 7).padding(.vertical, 3)
                        .background(scoreColor(score), in: Capsule())
                        .padding(6)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

// MARK: - Submit sheet

struct PhotoSubmitSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    let pending: PendingPhoto

    @State private var note = ""
    @State private var sending = false
    @State private var result: Photo?
    @State private var alert: AlertMessage?

    var body: some View {
        NavigationStack {
            Group {
                if sending {
                    WorkingView(title: "Analyzing your photo…", subtitle: "The advisor is looking closely. This can take up to a minute.")
                } else if let result {
                    ScrollView {
                        VStack(spacing: 16) {
                            Image(uiImage: pending.image)
                                .resizable().scaledToFit()
                                .frame(maxHeight: 220)
                                .clipShape(RoundedRectangle(cornerRadius: 14))
                            PhotoAnalysisView(analysis: result.analysis)
                            Button("Done") { dismiss() }.buttonStyle(BigButtonStyle())
                        }
                        .padding()
                    }
                    .background(Color.bg.ignoresSafeArea())
                } else {
                    form
                }
            }
            .navigationTitle(result == nil ? "Send photo" : "Analysis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if result == nil && !sending {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                }
            }
            .errorAlert($alert)
            .interactiveDismissDisabled(sending)
        }
    }

    private var form: some View {
        ScrollView {
            VStack(spacing: 16) {
                Image(uiImage: pending.image)
                    .resizable().scaledToFit()
                    .frame(maxHeight: 320)
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                if let r = pending.request {
                    VStack(alignment: .leading, spacing: 6) {
                        Label(r.title ?? "Photo request", systemImage: "camera.badge.ellipsis").font(.headline)
                        if let i = r.instructions, !i.isEmpty {
                            Text(i).font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    .card()
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Note (optional)").font(.subheadline.weight(.semibold))
                    TextField("Anything the advisor should know about this photo", text: $note, axis: .vertical)
                        .lineLimit(2...5)
                        .padding(10)
                        .background(Color.track, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .card()

                Button {
                    Task { await send() }
                } label: { Label("Send for analysis", systemImage: "paperplane.fill") }
                    .buttonStyle(BigButtonStyle())
            }
            .padding()
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Color.bg.ignoresSafeArea())
    }

    private func send() async {
        sending = true
        defer { sending = false }
        do {
            let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
            result = try await app.uploadPhoto(image: pending.image, requestId: pending.request?.id, note: trimmed.isEmpty ? nil : trimmed,
                                               plantId: pending.request?.plantId ?? app.selectedPlantId)
        } catch {
            alert = AlertMessage(title: "Couldn't send the photo", message: error.localizedDescription)
        }
    }
}

// MARK: - Analysis

struct PhotoAnalysisView: View {
    let analysis: PhotoAnalysis?

    private func scoreColor(_ s: Double) -> Color {
        if s >= 8 { return .good }
        if s >= 5 { return .warn }
        return .alertRed
    }

    var body: some View {
        if let a = analysis {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .center, spacing: 14) {
                    if let s = a.healthScore, s > 0 {
                        VStack(spacing: 0) {
                            Text(Formatting.number(s)).font(.system(size: 34, weight: .bold, design: .rounded))
                            Text("out of 10").font(.caption2)
                        }
                        .foregroundStyle(scoreColor(s))
                        .frame(width: 74, height: 74)
                        .background(scoreColor(s).opacity(0.15), in: Circle())
                    }
                    Text(a.summary ?? "No summary.").font(.body).fixedSize(horizontal: false, vertical: true)
                }
            }
            .card()

            if let f = a.findings, !f.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("What the advisor saw").font(.subheadline.weight(.semibold))
                    ForEach(f) { finding in
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: LevelColor.symbol(for: finding.severity))
                                .foregroundStyle(LevelColor.infoColor(for: finding.severity))
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(finding.title ?? "").fontWeight(.medium)
                                    if let sev = finding.severity {
                                        LevelChip(text: sev.capitalized, color: LevelColor.infoColor(for: sev))
                                    }
                                }
                                if let d = finding.detail, !d.isEmpty {
                                    Text(d).font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                }
                .card()
            }

            if let actions = a.actions, !actions.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("What to do").font(.subheadline.weight(.semibold))
                    NumberedList(items: actions, color: .brand)
                }
                .card()
            }

            CreatedItemsView(tasks: a.tasks, photoRequests: a.photoRequests)
        } else {
            Text("No analysis available for this photo.").foregroundStyle(.secondary).card()
        }
    }
}

// MARK: - Detail

struct PhotoDetailView: View {
    @Environment(AppState.self) private var app
    let photo: Photo
    @State private var image: UIImage?

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                ZStack {
                    Color.track
                    if let image {
                        Image(uiImage: image).resizable().scaledToFit()
                    } else {
                        PhotoThumbnail(photoID: photo.id)
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: 200)
                .clipShape(RoundedRectangle(cornerRadius: 14))

                HStack {
                    Text(Formatting.shortDateTime(photo.createdAt)).font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if photo.isFromCamera {
                        LevelChip(text: "Tent camera", color: .night)
                    } else if photo.requestId != nil {
                        LevelChip(text: "Requested by advisor", color: .night)
                    }
                }
                if let n = photo.note, !n.isEmpty {
                    Text("Your note: \(n)").font(.subheadline).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                PhotoAnalysisView(analysis: photo.analysis)
            }
            .padding()
        }
        .background(Color.bg.ignoresSafeArea())
        .navigationTitle("Photo")
        .navigationBarTitleDisplayMode(.inline)
        .task { image = await app.fullImage(for: photo.id) }
    }
}
