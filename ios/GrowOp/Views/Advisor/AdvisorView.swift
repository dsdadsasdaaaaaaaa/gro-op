import SwiftUI

struct AdvisorView: View {
    @Environment(AppState.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var runningBrief = false
    @State private var alert: AlertMessage?
    @State private var confirmClear = false
    @State private var aboutPlantId: Int?          // nil = the whole tent
    @State private var aboutChosen = false
    @State private var followBottom = false        // only scroll to the end after this person sends something
    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: Theme.spacing) {
                            briefSection
                            HStack {
                                Text("Ask the advisor").font(.headline)
                                Spacer()
                            }
                            .padding(.top, 8)
                            if app.chatMessages.isEmpty && !sending {
                                Text("Anything about your plant — watering, feeding, what a leaf looks like, when to flip to flower…")
                                    .font(.subheadline).foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            ForEach(app.chatMessages) { m in
                                ChatBubble(message: m, mine: isMine(m)).id(m.id)
                            }
                            if sending {
                                HStack(spacing: 10) {
                                    LeafGlyph()
                                    ProgressView().controlSize(.small)
                                    Text("Thinking…").font(.subheadline).foregroundStyle(.secondary)
                                    Spacer()
                                }
                                .id("typing")
                            }
                            Color.clear.frame(height: 1).id("bottom")
                        }
                        .padding(Theme.spacing)
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: app.chatMessages.count) { _, _ in
                        if followBottom { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
                    }
                    .onChange(of: sending) { _, _ in
                        if followBottom { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
                    }
                    .onChange(of: inputFocused) { _, focused in
                        if focused {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
                            }
                        }
                    }
                }
                inputBar
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("Advisor")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { Task { await app.loadChat(); await app.loadBrief() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        Button(role: .destructive) { confirmClear = true } label: { Label("Clear chat", systemImage: "trash") }
                    } label: { Image(systemName: "ellipsis.circle").foregroundStyle(.secondary) }
                }
            }
            .confirmationDialog("Clear the chat for both of you?", isPresented: $confirmClear, titleVisibility: .visible) {
                Button("Clear it", role: .destructive) {
                    Task {
                        do { try await app.clearChat() } catch { alert = AlertMessage(message: error.localizedDescription) }
                    }
                }
            }
            .errorAlert($alert)
            .task {
                await app.loadBrief()
                await app.loadChat()
                await app.markBriefRead()
            }
            .onChange(of: app.brief?.id) { _, _ in
                Task { await app.markBriefRead() }
            }
        }
    }

    // MARK: Brief

    @ViewBuilder
    private var briefSection: some View {
        if let b = app.brief {
            BriefCard(brief: b)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Image(systemName: "sparkles").foregroundStyle(Color.night)
                    Text("No daily brief yet").font(.headline)
                }
                Text("The advisor writes a short report each morning. You can ask for one now.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            .card()
        }
        Button {
            Task { await runBrief() }
        } label: {
            HStack(spacing: 8) {
                if runningBrief { ProgressView().tint(Color.brand) } else { Image(systemName: "sparkles") }
                Text(runningBrief ? "Writing your brief… (up to a minute)" : "Write a brief now (≈ $0.10)")
            }
        }
        .buttonStyle(BigButtonStyle(color: .brand, filled: false))
        .disabled(runningBrief)
    }

    private func runBrief() async {
        runningBrief = true
        defer { runningBrief = false }
        do {
            try await app.runBrief()
            await app.markBriefRead()
        } catch {
            alert = AlertMessage(title: "Couldn't run the brief", message: error.localizedDescription)
        }
    }

    // MARK: Input

    private var inputBar: some View {
        VStack(alignment: .leading, spacing: 6) {
        if !app.plants.isEmpty {
            Menu {
                Button { aboutPlantId = nil; aboutChosen = true } label: { Label("The whole tent", systemImage: "house.fill") }
                ForEach(app.plants) { p in
                    Button { aboutPlantId = p.id; aboutChosen = true } label: { Label(p.displayName, systemImage: "leaf.fill") }
                }
            } label: {
                Label("About: \(aboutName)", systemImage: aboutPlantId == nil ? "house.fill" : "leaf.fill")
                    .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
            }
        }
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask the advisor…", text: $draft, axis: .vertical)
                .lineLimit(1...5)
                .padding(.horizontal, 16).padding(.vertical, 11)
                .background(Color.card, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(Color.track, lineWidth: 1))
                .focused($inputFocused)
                .disabled(sending)
            Button {
                Task { await send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(canSend ? Color.brand : Color.secondary.opacity(0.4))
            }
            .disabled(!canSend)
            .accessibilityLabel("Send")
        }
        }
        .padding(.horizontal, Theme.spacing).padding(.vertical, 10)
        .background(Color.bg)
    }

    private var aboutName: String {
        guard let id = currentAbout else { return "the whole tent" }
        return app.plants.first { $0.id == id }?.displayName ?? "the whole tent"
    }
    /// Until the person picks, a question is about the plant they're looking at.
    private var currentAbout: Int? { aboutChosen ? aboutPlantId : app.selectedPlantId }

    private func isMine(_ m: ChatMessage) -> Bool {
        guard m.isUser else { return false }
        guard let author = m.author, !author.isEmpty, let me = app.myPlant?.owner, !me.isEmpty else { return true }
        return author.caseInsensitiveCompare(me) == .orderedSame
    }

    private var canSend: Bool {
        !sending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        followBottom = true
        sending = true
        defer { sending = false }
        do {
            try await app.sendChat(text, plantId: currentAbout)
        } catch {
            draft = text
            alert = AlertMessage(title: "Message not sent", message: error.localizedDescription)
        }
    }
}

// MARK: - Brief card

struct BriefCard: View {
    let brief: Brief
    @State private var showConcerns = true
    @State private var showActions = true
    @State private var showTargets = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Daily brief", systemImage: "sparkles")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(Color.night)
                Spacer()
                Text(Formatting.shortDateTime(brief.createdAt)).font(.caption).foregroundStyle(.tertiary)
            }
            if let h = brief.headline, !h.isEmpty {
                Text(h).font(.title2.bold()).fixedSize(horizontal: false, vertical: true)
            }
            if let t = brief.cameraFrameAt, let d = Formatting.parseISO(t) {
                Label("Included the tent camera frame from \(d.formatted(date: .abbreviated, time: .shortened))", systemImage: "video.fill")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let s = brief.summary, !s.isEmpty {
                Text(s).font(.body).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if let per = brief.perPlant, !per.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(per) { pp in
                        HStack(alignment: .top, spacing: 10) {
                            LeafGlyph()
                            VStack(alignment: .leading, spacing: 2) {
                                Text(pp.name ?? "Plant").font(.caption.weight(.semibold)).foregroundStyle(Color.brand)
                                if let h = pp.headline, !h.isEmpty { Text(h).font(.subheadline.weight(.semibold)) }
                                if let sm = pp.summary, !sm.isEmpty { Text(sm).font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
                            }
                        }
                    }
                }
                .padding(.top, 2)
            }
            if let c = brief.concerns, !c.isEmpty {
                CollapsibleSection(title: "Concerns", symbol: "exclamationmark.triangle.fill", tint: .warn, count: c.count, isOpen: $showConcerns) {
                    BulletList(items: c, symbol: "exclamationmark.triangle.fill", color: .warn)
                }
            }
            if let a = brief.actions, !a.isEmpty {
                CollapsibleSection(title: "Do today", symbol: "checkmark.circle.fill", tint: .brand, count: a.count, isOpen: $showActions) {
                    NumberedList(items: a, color: .brand)
                }
            }
            if let tc = brief.targetChanges, !tc.isEmpty {
                CollapsibleSection(title: "Targets changed", symbol: "slider.horizontal.3", tint: .night, count: tc.count, isOpen: $showTargets) {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(tc) { c in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 6) {
                                    Text(prettyField(c.field)).fontWeight(.medium)
                                    Text("\(c.from?.description ?? "—") → \(c.to?.description ?? "—")").foregroundStyle(Color.night)
                                }
                                .font(.subheadline)
                                if let r = c.reason, !r.isEmpty {
                                    Text(r).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            CreatedItemsView(tasks: brief.tasks, photoRequests: brief.photoRequests)
        }
        .card()
    }

    private func prettyField(_ f: String?) -> String {
        guard let f else { return "" }
        return f.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

struct CollapsibleSection<Content: View>: View {
    let title: String
    let symbol: String
    let tint: Color
    let count: Int
    @Binding var isOpen: Bool
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button {
                withAnimation(.snappy) { isOpen.toggle() }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: symbol).foregroundStyle(tint)
                    Text(title).font(.subheadline.weight(.semibold))
                    LevelChip(text: "\(count)", color: tint)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(isOpen ? 180 : 0))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if isOpen { content }
        }
        .padding(.top, 4)
    }
}

// MARK: - Chat bubble

struct LeafGlyph: View {
    var body: some View {
        ZStack {
            Circle().fill(Color.brand.opacity(0.14))
            Image(systemName: "leaf.fill").font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.brand)
        }
        .frame(width: 28, height: 28)
    }
}

struct ChatBubble: View {
    let message: ChatMessage
    var mine: Bool = true

    /// This person's own messages sit on the right; the advisor's and the other grower's on the left.
    private var right: Bool { message.isUser && mine }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            if right {
                Spacer(minLength: 48)
            } else if !message.isUser {
                LeafGlyph()
            }
            VStack(alignment: right ? .trailing : .leading, spacing: 4) {
                if message.isUser && !mine, let who = message.author {
                    Text(who).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                }
                Text(message.content ?? "")
                    .font(.body)
                    .foregroundStyle(right ? Color.white : Color.primary)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(right ? Color.brand : (message.isUser ? Color.night.opacity(0.12) : Color.card),
                                in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .textSelection(.enabled)
                Text(Formatting.relative(message.createdAt)).font(.caption2).foregroundStyle(.tertiary)
            }
            if !right { Spacer(minLength: 48) }
        }
    }
}
