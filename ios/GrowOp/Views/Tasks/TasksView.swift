import SwiftUI

struct TasksView: View {
    @Environment(AppState.self) private var app
    @State private var showDone = false
    @State private var showAdd = false
    @State private var alert: AlertMessage?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.spacing) {
                    if app.openTasks.isEmpty {
                        EmptyStateView(symbol: "checkmark.seal.fill", title: "Nothing to do",
                                       message: "The advisor adds tasks here when something needs doing. You can add your own with +.")
                            .card()
                    } else {
                        VStack(spacing: 10) {
                            ForEach(app.openTasks) { t in
                                TaskRow(task: t) {
                                    do { try await app.completeTask(t) }
                                    catch { alert = AlertMessage(message: error.localizedDescription) }
                                }
                            }
                        }
                    }

                    Button {
                        withAnimation(.snappy) { showDone.toggle() }
                        if showDone { Task { await app.loadTasks(includeDone: true) } }
                    } label: {
                        HStack(spacing: 6) {
                            Text(showDone ? "Hide done" : "Show done")
                            Image(systemName: "chevron.down").rotationEffect(.degrees(showDone ? 180 : 0))
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                    }
                    .padding(.top, 4)

                    if showDone {
                        if app.doneTasks.isEmpty {
                            Text("No completed tasks yet.").font(.subheadline).foregroundStyle(.secondary)
                        }
                        VStack(spacing: 10) {
                            ForEach(app.doneTasks) { t in
                                TaskRow(task: t) {
                                    do { try await app.reopenTask(t) }
                                    catch { alert = AlertMessage(message: error.localizedDescription) }
                                }
                            }
                        }
                    }
                }
                .padding(Theme.spacing)
            }
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("Tasks")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showAdd = true } label: {
                        Image(systemName: "plus.circle.fill").font(.title3).foregroundStyle(Color.brand)
                    }
                    .accessibilityLabel("Add task")
                }
            }
            .refreshable { await app.loadTasks(includeDone: showDone) }
            .task { await app.loadTasks(includeDone: showDone) }
            .sheet(isPresented: $showAdd) { AddTaskSheet() }
            .errorAlert($alert)
        }
    }
}

struct TaskRow: View {
    let task: TaskItem
    var onToggle: () async -> Void
    @State private var busy = false
    @State private var justTapped = false

    private var overdue: Bool {
        guard let d = Formatting.parseDay(task.due), !task.isDone else { return false }
        return d < Calendar.current.startOfDay(for: Date())
    }

    private var dueColor: Color {
        guard let d = Formatting.parseDay(task.due), !task.isDone else { return .secondary }
        if overdue { return .alertRed }
        if Calendar.current.isDateInToday(d) { return .warn }
        return .secondary
    }

    private var dueText: String {
        guard let due = task.due, !due.isEmpty else { return "" }
        guard let d = Formatting.parseDay(due) else { return due }
        if Calendar.current.isDateInToday(d) { return "Today" }
        if Calendar.current.isDateInTomorrow(d) { return "Tomorrow" }
        if overdue { return "Overdue · \(d.formatted(date: .abbreviated, time: .omitted))" }
        return d.formatted(date: .abbreviated, time: .omitted)
    }

    var body: some View {
        Button {
            justTapped = true
            Task {
                busy = true
                await onToggle()
                busy = false
                justTapped = false
            }
        } label: {
            HStack(alignment: .top, spacing: 14) {
                ZStack {
                    if busy {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: task.isDone || justTapped ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 32, weight: .regular))
                            .foregroundStyle(task.isDone || justTapped ? Color.brand : (task.isHigh ? Color.alertRed : Color.secondary.opacity(0.5)))
                            .symbolEffect(.bounce, value: justTapped)
                            .contentTransition(.symbolEffect(.replace))
                    }
                }
                .frame(width: 32, height: 32)
                VStack(alignment: .leading, spacing: 5) {
                    Text(task.title ?? "Task")
                        .font(.body.weight(task.isHigh && !task.isDone ? .semibold : .regular))
                        .strikethrough(task.isDone)
                        .foregroundStyle(task.isDone ? .secondary : .primary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let d = task.detail, !d.isEmpty {
                        Text(d).font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    HStack(spacing: 8) {
                        if !dueText.isEmpty {
                            LevelChip(text: dueText, color: dueColor)
                        }
                        if task.isHigh && !task.isDone {
                            LevelChip(text: "High priority", color: .alertRed)
                        }
                        if task.createdBy == "advisor" {
                            Label("Advisor", systemImage: "sparkles").font(.caption).foregroundStyle(Color.night)
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(16)
            .padding(.leading, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.card, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .overlay(alignment: .leading) {
                if task.isHigh && !task.isDone {
                    RoundedRectangle(cornerRadius: 2).fill(Color.alertRed).frame(width: 4).padding(.vertical, 14).padding(.leading, 6)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .opacity(task.isDone ? 0.7 : 1)
    }
}

struct AddTaskSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var detail = ""
    @State private var hasDue = false
    @State private var due = Date()
    @State private var saving = false
    @State private var alert: AlertMessage?

    var body: some View {
        NavigationStack {
            Form {
                Section("Task") {
                    TextField("What needs doing?", text: $title)
                    TextField("Details (optional)", text: $detail, axis: .vertical).lineLimit(2...5)
                }
                Section {
                    Toggle("Has a due date", isOn: $hasDue)
                    if hasDue {
                        DatePicker("Due", selection: $due, displayedComponents: .date)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("New task")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Saving…" : "Add") { Task { await save() } }
                        .disabled(saving || title.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .errorAlert($alert)
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            let d = detail.trimmingCharacters(in: .whitespacesAndNewlines)
            try await app.addTask(title: title.trimmingCharacters(in: .whitespaces),
                                  detail: d.isEmpty ? nil : d,
                                  due: hasDue ? Formatting.dayString(due) : nil)
            dismiss()
        } catch {
            alert = AlertMessage(message: error.localizedDescription)
        }
    }
}
