import SwiftUI

enum LogKind: String, CaseIterable, Identifiable {
    case ph, ec, water, feed, height, note

    var id: String { rawValue }

    var title: String {
        switch self {
        case .ph: return "pH"
        case .ec: return "EC / PPM"
        case .water: return "Watered"
        case .feed: return "Fed"
        case .height: return "Height"
        case .note: return "Note"
        }
    }

    var symbol: String {
        switch self {
        case .ph: return "drop.circle.fill"
        case .ec: return "bolt.circle.fill"
        case .water: return "drop.triangle.fill"
        case .feed: return "fork.knife.circle.fill"
        case .height: return "arrow.up.and.down.circle.fill"
        case .note: return "text.bubble.fill"
        }
    }

    var color: Color {
        switch self {
        case .ph: return .night
        case .ec: return .warn
        case .water: return .brand
        case .feed: return .good
        case .height: return .leaf
        case .note: return .secondary
        }
    }

    var hasContext: Bool { self == .ph || self == .ec }
}

struct LogView: View {
    @Environment(AppState.self) private var app
    @State private var selectedKind: LogKind?

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    Text("Tell the advisor what you did or measured. It replies with advice right away.")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(LogKind.allCases) { kind in
                            Button { selectedKind = kind } label: {
                                VStack(alignment: .leading, spacing: 10) {
                                    Image(systemName: kind.symbol)
                                        .font(.system(size: 30, weight: .semibold))
                                        .foregroundStyle(kind.color)
                                    Text(kind.title).font(.headline).foregroundStyle(.primary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 96, alignment: .leading)
                                .padding(16)
                                .background(Color.card, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                                .overlay(alignment: .topTrailing) {
                                    Circle().fill(kind.color.opacity(0.14)).frame(width: 44, height: 44).offset(x: 10, y: -10)
                                }
                                .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                                .softShadow()
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(text: "Recent entries")
                        if app.logEntries.isEmpty {
                            Text("Nothing logged yet.").font(.subheadline).foregroundStyle(.secondary)
                        }
                        ForEach(app.logEntries) { e in
                            LogEntryRow(entry: e)
                            if e.id != app.logEntries.last?.id { Divider() }
                        }
                    }
                    .card()
                }
                .padding(Theme.spacing)
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("Log")
            .refreshable { await app.loadLog() }
            .task { await app.loadLog() }
            .sheet(item: $selectedKind) { kind in
                LogEntrySheet(kind: kind)
            }
        }
    }
}

struct LogEntryRow: View {
    let entry: LogEntry

    private var kind: LogKind? { LogKind(rawValue: entry.kind ?? "") ?? (entry.kind == "ppm" ? .ec : nil) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: kind?.symbol ?? "circle.fill")
                .foregroundStyle(kind?.color ?? .secondary)
                .frame(width: 26)
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(headline).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(Formatting.relative(entry.createdAt)).font(.caption).foregroundStyle(.secondary)
                }
                if let n = entry.note, !n.isEmpty {
                    Text(n).font(.footnote).foregroundStyle(.secondary).lineLimit(2)
                }
                if let a = entry.adviceSummary, !a.isEmpty {
                    Text(a).font(.footnote).foregroundStyle(.primary).lineLimit(3)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var headline: String {
        var s = (entry.kind ?? "entry").replacingOccurrences(of: "_", with: " ").capitalized
        if entry.kind == "ph" { s = "pH" }
        if entry.kind == "ec" { s = "EC" }
        if entry.kind == "ppm" { s = "PPM" }
        if let v = entry.value {
            s += " \(Formatting.number(v, decimals: 2))"
            if let u = entry.unit, !u.isEmpty, u.lowercased() != "ph" { s += " \(u)" }
        }
        if let c = entry.context, !c.isEmpty {
            s += " · \(LogEntrySheet.contextLabel(c))"
        }
        return s
    }
}

// MARK: - Entry sheet

struct LogEntrySheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    let kind: LogKind

    @State private var valueText = ""
    @State private var context = "water_in"
    @State private var ecUnit = "EC"
    @State private var heightUnit = "cm"
    @State private var note = ""
    @State private var submitting = false
    @State private var result: LogResponse?
    @State private var alert: AlertMessage?
    @FocusState private var valueFocused: Bool

    static let contexts: [(String, String)] = [("water_in", "Water going in"), ("runoff", "Runoff"), ("reservoir", "Reservoir")]

    static func contextLabel(_ c: String) -> String {
        contexts.first { $0.0 == c }?.1 ?? c.replacingOccurrences(of: "_", with: " ").capitalized
    }

    var body: some View {
        NavigationStack {
            Group {
                if submitting {
                    WorkingView(title: "Asking the advisor…", subtitle: "This usually takes 10–40 seconds.")
                } else if let result {
                    AdviceResultView(result: result) { dismiss() }
                } else {
                    form
                }
            }
            .navigationTitle(result == nil ? "Log \(kind.title)" : "Advice")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if result == nil && !submitting {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                }
            }
            .errorAlert($alert)
            .interactiveDismissDisabled(submitting)
        }
    }

    private var form: some View {
        Form {
            switch kind {
            case .ph:
                Section("pH reading") {
                    numberField(placeholder: "e.g. 6.3", suffix: "pH")
                    contextPicker
                }
            case .ec:
                Section("Nutrient strength") {
                    Picker("Unit", selection: $ecUnit) {
                        Text("EC (mS/cm)").tag("EC")
                        Text("PPM").tag("PPM")
                    }
                    .pickerStyle(.segmented)
                    numberField(placeholder: ecUnit == "EC" ? "e.g. 1.4" : "e.g. 700", suffix: ecUnit == "EC" ? "mS/cm" : "ppm")
                    contextPicker
                }
            case .water:
                Section("How much water? (optional)") {
                    numberField(placeholder: "e.g. 1.5", suffix: "litres")
                }
            case .feed:
                Section("How much feed solution? (optional)") {
                    numberField(placeholder: "e.g. 1.5", suffix: "litres")
                }
            case .height:
                Section("Plant height") {
                    Picker("Unit", selection: $heightUnit) {
                        Text("cm").tag("cm")
                        Text("inches").tag("in")
                    }
                    .pickerStyle(.segmented)
                    numberField(placeholder: "e.g. 35", suffix: heightUnit)
                }
            case .note:
                EmptyView()
            }

            Section(kind == .note ? "What did you notice or do?" : "Note (optional)") {
                TextField(kind == .note ? "e.g. Lower leaves look a bit yellow…" : "Anything else the advisor should know", text: $note, axis: .vertical)
                    .lineLimit(3...6)
            }

            Section {
                Button {
                    Task { await submit() }
                } label: {
                    Text("Send to advisor").frame(maxWidth: .infinity)
                }
                .buttonStyle(BigButtonStyle(color: kind.color))
                .disabled(!canSubmit)
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.bg.ignoresSafeArea())
        .onAppear { valueFocused = kind != .note }
    }

    private func numberField(placeholder: String, suffix: String) -> some View {
        HStack {
            TextField(placeholder, text: $valueText)
                .keyboardType(.decimalPad)
                .font(.title2)
                .focused($valueFocused)
            Text(suffix).foregroundStyle(.secondary)
        }
    }

    private var contextPicker: some View {
        Picker("Measured", selection: $context) {
            ForEach(Self.contexts, id: \.0) { c in Text(c.1).tag(c.0) }
        }
        .pickerStyle(.menu)
    }

    private var parsedValue: Double? {
        let cleaned = valueText.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces)
        return Double(cleaned)
    }

    private var canSubmit: Bool {
        switch kind {
        case .ph, .ec, .height: return parsedValue != nil
        case .note: return !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .water, .feed: return true
        }
    }

    private func submit() async {
        var req: LogRequest
        let trimmedNote = note.trimmingCharacters(in: .whitespacesAndNewlines)
        switch kind {
        case .ph:
            req = LogRequest(kind: "ph", value: parsedValue, unit: "pH", context: context, note: nil)
        case .ec:
            req = LogRequest(kind: ecUnit == "EC" ? "ec" : "ppm", value: parsedValue, unit: ecUnit == "EC" ? "mS/cm" : "ppm", context: context, note: nil)
        case .water:
            req = LogRequest(kind: "water", value: parsedValue, unit: parsedValue == nil ? nil : "L", context: nil, note: nil)
        case .feed:
            req = LogRequest(kind: "feed", value: parsedValue, unit: parsedValue == nil ? nil : "L", context: nil, note: nil)
        case .height:
            req = LogRequest(kind: "height", value: parsedValue, unit: heightUnit, context: nil, note: nil)
        case .note:
            req = LogRequest(kind: "note", value: nil, unit: nil, context: nil, note: nil)
        }
        if !trimmedNote.isEmpty { req.note = trimmedNote }

        submitting = true
        defer { submitting = false }
        do {
            result = try await app.submitLog(req)
        } catch {
            alert = AlertMessage(title: "Couldn't send that", message: error.localizedDescription)
        }
    }
}

// MARK: - Advice result

struct AdviceResultView: View {
    let result: LogResponse
    var onDone: () -> Void

    var body: some View {
        let advice = result.advice
        let urgency = advice?.urgency ?? "info"
        let color = LevelColor.infoColor(for: urgency)
        ScrollView {
            VStack(spacing: Theme.spacing) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 10) {
                        Image(systemName: LevelColor.symbol(for: urgency)).font(.title2)
                        Text(urgencyTitle(urgency)).font(.title3.bold())
                        Spacer()
                    }
                    .foregroundStyle(Color.white)
                    if let s = advice?.summary, !s.isEmpty {
                        Text(s).font(.body).foregroundStyle(Color.white.opacity(0.95)).fixedSize(horizontal: false, vertical: true)
                    } else {
                        Text("Logged. No specific advice this time.").foregroundStyle(Color.white.opacity(0.9))
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(color, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))

                if let steps = advice?.steps, !steps.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Next steps").font(.headline)
                        NumberedList(items: steps, color: color)
                    }
                    .card()
                }

                CreatedItemsView(tasks: advice?.tasks, photoRequests: advice?.photoRequests)

                Button("Done", action: onDone)
                    .buttonStyle(BigButtonStyle())
            }
            .padding(Theme.spacing)
        }
        .background(Color.bg.ignoresSafeArea())
    }

    private func urgencyTitle(_ u: String) -> String {
        switch u {
        case "urgent": return "Act now"
        case "attention": return "Worth a look"
        default: return "Advisor says"
        }
    }
}
