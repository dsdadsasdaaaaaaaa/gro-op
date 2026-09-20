import SwiftUI

struct AdvisorView: View {
    @Environment(AppState.self) private var app
    @State private var draft = ""
    @State private var sending = false
    @State private var runningBrief = false
    @State private var alert: AlertMessage?
    @State private var confirmClear = false
    @FocusState private var inputFocused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(spacing: 16) {
                            briefSection
                            Divider().padding(.vertical, 4)
                            SectionTitle(text: "Ask the advisor")
                            if app.chatMessages.isEmpty && !sending {
                                Text("Ask anything about your plants — watering, feeding, what a leaf looks like, when to flip to flower…")
                                    .font(.subheadline).foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            ForEach(app.chatMessages) { m in
                                ChatBubble(message: m).id(m.id)
                            }
                            if sending {
                                HStack {
                                    ProgressView()
                                    Text("The advisor is thinking…").font(.subheadline).foregroundStyle(.secondary)
                                    Spacer()
                                }
                                .id("typing")
                            }
                            Color.clear.frame(height: 1).id("bottom")
                        }
                        .padding()
                    }
                    .scrollDismissesKeyboard(.interactively)
                    .onChange(of: app.chatMessages.count) { _, _ in
                        withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
                    }
                    .onChange(of: sending) { _, _ in
                        withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
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
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Advisor")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { Task { await app.loadChat(); await app.loadBrief() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        Button(role: .destructive) { confirmClear = true } label: { Label("Clear chat", systemImage: "trash") }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
            .confirmationDialog("Clear the whole conversation?", isPresented: $confirmClear, titleVisibility: .visible) {
                Button("Clear chat", role: .destructive) {
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
                Label("No daily brief yet", systemImage: "sparkles")
                    .font(.headline)
                Text("The advisor writes a short report each morning. You can ask for one now.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            .card()
        }
        Button {
            Task { await runBrief() }
        } label: {
            HStack {
                if runningBrief { ProgressView().tint(.white) } else { Image(systemName: "sparkles") }
                Text(runningBrief ? "Writing your brief… (up to a minute)" : "Run brief now")
            }
        }
        .buttonStyle(BigButtonStyle(color: .purple))
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
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Ask the advisor…", text: $draft, axis: .vertical)
                .lineLimit(1...5)
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 20))
                .focused($inputFocused)
                .disabled(sending)
            Button {
                Task { await send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 34))
                    .foregroundStyle(canSend ? Color.accentColor : Color.gray)
            }
            .disabled(!canSend)
            .accessibilityLabel("Send")
        }
        .padding(.horizontal).padding(.vertical, 8)
        .background(.bar)
    }

    private var canSend: Bool {
        !sending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        sending = true
        defer { sending = false }
        do {
            try await app.sendChat(text)
        } catch {
            draft = text
            alert = AlertMessage(title: "Message not sent", message: error.localizedDescription)
        }
    }
}

// MARK: - Brief card

struct BriefCard: View {
    let brief: Brief

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Daily brief", systemImage: "sparkles").font(.subheadline.weight(.semibold)).foregroundStyle(.purple)
                Spacer()
                Text(Formatting.shortDateTime(brief.createdAt)).font(.caption).foregroundStyle(.secondary)
            }
            if let h = brief.headline, !h.isEmpty {
                Text(h).font(.title3.bold()).fixedSize(horizontal: false, vertical: true)
            }
            if let s = brief.summary, !s.isEmpty {
                Text(s).font(.body).fixedSize(horizontal: false, vertical: true)
            }
            if let c = brief.concerns, !c.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Concerns").font(.subheadline.weight(.semibold)).foregroundStyle(.orange)
                    BulletList(items: c, symbol: "exclamationmark.triangle.fill", color: .orange)
                }
            }
            if let a = brief.actions, !a.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("What to do").font(.subheadline.weight(.semibold)).foregroundStyle(Color.accentColor)
                    BulletList(items: a, symbol: "checkmark.circle.fill", color: .accentColor)
                }
            }
            if let tc = brief.targetChanges, !tc.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Target changes").font(.subheadline.weight(.semibold)).foregroundStyle(.blue)
                    ForEach(tc) { c in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(prettyField(c.field)).fontWeight(.medium)
                                Text("\(c.from?.description ?? "—") → \(c.to?.description ?? "—")")
                                    .foregroundStyle(.blue)
                            }
                            .font(.subheadline)
                            if let r = c.reason, !r.isEmpty {
                                Text(r).font(.caption).foregroundStyle(.secondary)
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

// MARK: - Chat bubble

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 40) }
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                Text(message.content ?? "")
                    .font(.body)
                    .foregroundStyle(message.isUser ? Color.white : Color.primary)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(message.isUser ? Color.accentColor : Color(.secondarySystemGroupedBackground),
                                in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .textSelection(.enabled)
                Text(Formatting.relative(message.createdAt)).font(.caption2).foregroundStyle(.tertiary)
            }
            if !message.isUser { Spacer(minLength: 40) }
        }
    }
}
