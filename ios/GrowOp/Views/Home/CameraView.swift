import SwiftUI
import UIKit

// MARK: - Live image (shared by the Home card and CameraView)

struct CameraImageView: View {
    let image: UIImage?
    let error: String?
    let at: Date?
    var showLive = true
    var muted = false

    private static let timeStyle = Date.FormatStyle(date: .omitted, time: .standard)

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Color.night
            if let image {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .saturation(muted ? 0.4 : 1)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: error == nil ? "video.fill" : "video.slash.fill")
                        .font(.system(size: 30, weight: .medium))
                    Text(error ?? "Waiting for the camera…")
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)
                }
                .foregroundStyle(Color.white.opacity(0.8))
                .padding(16)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if image != nil, showLive {
                HStack(spacing: 6) {
                    Circle().fill(error == nil ? Color.alertRed : Color.warn).frame(width: 6, height: 6)
                    Text(error == nil ? "live · \(at.map { Self.timeStyle.format($0) } ?? "")" : "reconnecting…")
                        .contentTransition(.numericText())
                }
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(Color.white)
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(Color.black.opacity(0.45), in: Capsule())
                .padding(8)
            }
        }
        .clipped()
    }
}

// MARK: - Home card

struct CameraCard: View {
    @Environment(AppState.self) private var app
    @Environment(\.scenePhase) private var scenePhase
    let camera: CameraInfo
    var muted = false

    private var error: String? {
        if let e = app.cameraError { return e }
        if camera.available == false { return camera.error ?? "Camera unavailable" }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Label("Tent camera", systemImage: "video.fill").font(.headline)
                Spacer()
                Text(camera.displayName).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
            }
            CameraImageView(image: app.cameraImage, error: error, at: app.cameraImageAt, muted: muted)
                .aspectRatio(16 / 9, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .card(padding: 16)
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            while !Task.isCancelled {
                await app.refreshCameraSnapshot()
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }
}

// MARK: - Full camera screen

struct CameraView: View {
    enum Mode: Hashable { case live, timelapse }

    @Environment(AppState.self) private var app
    @Environment(\.scenePhase) private var scenePhase
    @State private var mode: Mode
    @State private var zoom: CGFloat = 1
    @State private var lastZoom: CGFloat = 1
    @State private var showLook: Bool

    init(initialMode: Mode = .live, autoLook: Bool = false) {
        _mode = State(initialValue: initialMode)
        _showLook = State(initialValue: autoLook)
    }

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.spacing) {
                Picker("Mode", selection: $mode) {
                    Text("Live").tag(Mode.live)
                    Text("Timelapse").tag(Mode.timelapse)
                }
                .pickerStyle(.segmented)

                if mode == .live {
                    liveSection
                } else {
                    TimelapseView()
                }
            }
            .padding(Theme.spacing)
        }
        .background(Color.bg.ignoresSafeArea())
        .navigationTitle(app.status?.camera?.displayName ?? "Tent camera")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showLook) { CameraLookSheet() }
    }

    private var aspect: CGFloat {
        if let img = app.cameraImage, img.size.height > 0 { return img.size.width / img.size.height }
        return 16 / 9
    }

    private var liveSection: some View {
        VStack(spacing: Theme.spacing) {
            CameraImageView(image: app.cameraImage, error: app.cameraError, at: app.cameraImageAt)
                .scaleEffect(zoom)
                .aspectRatio(aspect, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .gesture(
                    MagnifyGesture()
                        .onChanged { v in zoom = min(4, max(1, lastZoom * v.magnification)) }
                        .onEnded { _ in lastZoom = zoom }
                )
                .onTapGesture(count: 2) {
                    withAnimation(.spring(duration: 0.3)) { zoom = 1; lastZoom = 1 }
                }
                .accessibilityLabel("Live tent camera")
            if zoom > 1 {
                Text("Double-tap to reset zoom").font(.caption).foregroundStyle(.tertiary)
            }

            Button { showLook = true } label: {
                Label("Ask the advisor to look now", systemImage: "sparkles")
            }
            .buttonStyle(BigButtonStyle())
            if let p = app.selectedPlant {
                Text("It takes a fresh snapshot and checks \(p.displayName).")
                    .font(.caption).foregroundStyle(.secondary)
            }

            if let cam = app.status?.camera {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Label(cam.available == false ? "Camera unavailable" : "Camera online",
                              systemImage: cam.available == false ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                            .foregroundStyle(cam.available == false ? Color.warn : Color.good)
                        Spacer()
                    }
                    .font(.subheadline.weight(.medium))
                    if let n = cam.frameCount {
                        Text("\(n) timelapse frames saved" + (cam.lastFrameAt.map { " · last \(Formatting.relative($0))" } ?? ""))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if let e = cam.error, !e.isEmpty {
                        Text(e).font(.caption).foregroundStyle(Color.warn)
                    }
                }
                .card(padding: 16)
            }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            while !Task.isCancelled {
                await app.refreshCameraSnapshot()
                try? await Task.sleep(for: .seconds(1))
            }
        }
    }
}

// MARK: - "Look now" sheet

struct CameraLookSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var photo: Photo?
    @State private var image: UIImage?
    @State private var errorText: String?

    private var plantName: String { app.selectedPlant?.displayName ?? "the tent" }

    var body: some View {
        NavigationStack {
            Group {
                if let photo {
                    ScrollView {
                        VStack(spacing: Theme.spacing) {
                            ZStack {
                                Color.night
                                if let image { Image(uiImage: image).resizable().scaledToFit() }
                                else { ProgressView().tint(.white) }
                            }
                            .aspectRatio(16 / 9, contentMode: .fit)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                            PhotoAnalysisView(analysis: photo.analysis)
                            Button("Done") { dismiss() }.buttonStyle(BigButtonStyle())
                        }
                        .padding(Theme.spacing)
                    }
                    .background(Color.bg.ignoresSafeArea())
                    .task { image = await app.fullImage(for: photo.id) }
                } else if let errorText {
                    VStack(spacing: 14) {
                        EmptyStateView(symbol: "video.slash.fill", title: "Couldn't look right now", message: errorText)
                        Button("Try again") { self.errorText = nil; Task { await run() } }.buttonStyle(BigButtonStyle())
                        Button("Close") { dismiss() }.buttonStyle(BigButtonStyle(filled: false))
                    }
                    .padding(Theme.spacing)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.bg.ignoresSafeArea())
                } else {
                    WorkingView(title: "The advisor is looking at the tent…",
                                subtitle: "Taking a fresh snapshot and checking \(plantName). This can take up to a minute.")
                        .background(Color.bg.ignoresSafeArea())
                }
            }
            .navigationTitle(photo == nil ? "Look now" : "What the advisor saw")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if photo != nil {
                    ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                }
            }
            .interactiveDismissDisabled(photo == nil && errorText == nil)
            .task { if photo == nil && errorText == nil { await run() } }
        }
    }

    private func run() async {
        do {
            photo = try await app.analyseCamera()
        } catch {
            errorText = error.localizedDescription
        }
    }
}

// MARK: - Timelapse

struct TimelapseView: View {
    @Environment(AppState.self) private var app
    @State private var days = 1
    @State private var frames: [CameraFrame] = []
    @State private var index: Double = 0
    @State private var image: UIImage?
    @State private var loading = false
    @State private var playing = false
    @State private var playTask: Task<Void, Never>?
    @State private var prefetchTask: Task<Void, Never>?

    private var currentIndex: Int { frames.isEmpty ? 0 : min(max(Int(index.rounded()), 0), frames.count - 1) }
    private var current: CameraFrame? { frames.isEmpty ? nil : frames[currentIndex] }

    var body: some View {
        VStack(spacing: 14) {
            Picker("Range", selection: $days) {
                Text("Last 24 h").tag(1)
                Text("7 days").tag(7)
            }
            .pickerStyle(.segmented)

            ZStack(alignment: .bottomLeading) {
                Color.night
                if let image {
                    Image(uiImage: image).resizable().scaledToFill()
                } else if loading || (!frames.isEmpty && image == nil) {
                    ProgressView().tint(.white)
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "film.stack").font(.system(size: 30))
                        Text("No frames yet").font(.caption)
                        Text("The camera saves a frame every half hour.").font(.caption2)
                    }
                    .foregroundStyle(Color.white.opacity(0.8))
                }
                if let f = current {
                    HStack(spacing: 6) {
                        Image(systemName: f.lightsOn == true ? "sun.max.fill" : "moon.fill")
                            .foregroundStyle(f.lightsOn == true ? Color.sun : Color.white.opacity(0.85))
                        Text(frameLabel(f)).contentTransition(.numericText())
                    }
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Color.white)
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(Color.black.opacity(0.45), in: Capsule())
                    .padding(10)
                }
            }
            .aspectRatio(16 / 9, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            HStack(spacing: 14) {
                Button(action: togglePlay) {
                    Image(systemName: playing ? "pause.fill" : "play.fill")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundStyle(Color.white)
                        .frame(width: 48, height: 48)
                        .background(Color.brand, in: Circle())
                }
                .disabled(frames.count < 2)
                .accessibilityLabel(playing ? "Pause" : "Play")
                Slider(value: $index, in: 0...Double(max(frames.count - 1, 1)), step: 1) { editing in
                    if editing { stopPlaying() }
                }
                .tint(.brand)
                .disabled(frames.count < 2)
            }
            HStack {
                Text(frames.isEmpty ? "" : "Frame \(currentIndex + 1) of \(frames.count)")
                Spacer()
                if let first = frames.first?.t, let last = frames.last?.t {
                    Text("\(Formatting.shortDateTime(first)) → \(Formatting.shortDateTime(last))").lineLimit(1).minimumScaleFactor(0.8)
                }
            }
            .font(.caption).foregroundStyle(.secondary)
        }
        .card(padding: 16)
        .sensoryFeedback(.selection, trigger: currentIndex)
        .task(id: days) { await load() }
        .onChange(of: currentIndex) { _, _ in
            if !playing { Task { await showCurrent() } }
        }
        .onDisappear {
            stopPlaying()
            prefetchTask?.cancel()
        }
    }

    private func frameLabel(_ f: CameraFrame) -> String {
        guard let d = Formatting.parseISO(f.t) else { return f.t ?? "" }
        return d.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute())
    }

    private func load() async {
        stopPlaying()
        prefetchTask?.cancel()
        loading = true
        image = nil
        frames = await app.cameraFrames(days: days)
        index = Double(max(frames.count - 1, 0))
        loading = false
        await showCurrent()
        prefetchAround(currentIndex)
    }

    private func showCurrent() async {
        guard let f = current else { image = nil; return }
        if let cached = app.cachedFrame(for: f.id) { image = cached; return }
        let id = f.id
        let img = await app.frame(for: id)
        if current?.id == id, let img { image = img }
    }

    /// Warm the cache around the current position so scrubbing feels instant.
    private func prefetchAround(_ center: Int) {
        prefetchTask?.cancel()
        let ids = frames.enumerated()
            .filter { abs($0.offset - center) <= 12 }
            .sorted { abs($0.offset - center) < abs($1.offset - center) }
            .map { $0.element.id }
        prefetchTask = Task {
            for id in ids {
                if Task.isCancelled { return }
                _ = await app.frame(for: id)
            }
        }
    }

    private func togglePlay() {
        if playing { stopPlaying(); return }
        guard frames.count > 1 else { return }
        playing = true
        if currentIndex >= frames.count - 1 { index = 0 }
        playTask = Task {
            while !Task.isCancelled {
                let next = currentIndex + 1
                if next >= frames.count { break }
                let f = frames[next]
                let img = await app.frame(for: f.id)
                if Task.isCancelled { break }
                index = Double(next)
                if let img { image = img }
                try? await Task.sleep(for: .milliseconds(165))   // ~6 fps
            }
            playing = false
        }
    }

    private func stopPlaying() {
        playTask?.cancel()
        playTask = nil
        playing = false
    }
}
