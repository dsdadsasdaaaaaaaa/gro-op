import SwiftUI

struct TasksView: View {
    @Environment(AppState.self) private var app
    @State private var showDone = false
    @State private var showAdd = false
    @State private var alert: AlertMessage?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if app.openTasks.isEmpty {
                        EmptyStateView(symbol: "checkmark.seal", title: "Nothing to do", message: "The advisor will add tasks here when something needs doing.")
                            .listRowBackground(Color.clear)
                    }
                    ForEach(app.openTasks) { t in
                        TaskRow(task: t) {
                            do { try await app.completeTask(t) }
                            catch { alert = AlertMessage(message: error.localizedDescription) }
                        }
                    }
                } header: {
                    Text("To do")
                }

                if showDone {
                    Section("Done") {
                        if app.doneTasks.isEmpty {
                            Text("No completed tasks yet.").foregroundStyle(.secondary)
                        }
                        ForEach(app.doneTasks) { t in
                            TaskRow(task: t) {
                                do { try await app.reopenTask(t) }
                                catch { alert = AlertMessage(message: error.localizedDescription) }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Tasks")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(showDone ? "Hide done" : "Show done") {
                        showDone.toggle()
                        if showDone { Task { await app.loadTasks(includeDone: true) } }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showAdd = true } label: { Image(systemName: "plus") }
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

    private var dueColor: Color {
        guard let d = Formatting.parseDay(task.due), !task.isDone else { return .secondary }
        if d < Calendar.current.startOfDay(for: Date()) { return .red }
        if Calendar.current.isDateInToday(d) { return .orange }
        return .secondary
    }

    private var dueText: String {
        guard let due = task.due, !due.isEmpty else { return "" }
        guard let d = Formatting.parseDay(due) else { return due }
        if Calendar.current.isDateInToday(d) { return "Today" }
        if Calendar.current.isDateInTomorrow(d) { return "Tomorrow" }
        if d < Calendar.current.startOfDay(for: Date()) { return "Overdue · \(d.formatted(date: .abbreviated, time: .omitted))" }
        return d.formatted(date: .abbreviated, time: .omitted)
    }

    var body: some View {
        Button {
            Task {
                busy = true
                await onToggle()
                busy = false
            }
        } label: {
            HStack(alignment: .top, spacing: 12) {
                if busy {
                    ProgressView().frame(width: 28, height: 28)
                } else {
                    Image(systemName: task.isDone ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 28))
                        .foregroundStyle(task.isDone ? Color.accentColor : (task.isHigh ? .red : .secondary))
                }
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(task.title ?? "Task")
                            .font(.body.weight(task.isHigh && !task.isDone ? .semibold : .regular))
                            .strikethrough(task.isDone)
                            .foregroundStyle(task.isDone ? .secondary : .primary)
                        if task.isHigh && !task.isDone {
                            LevelChip(text: "High", color: .red)
                        }
                    }
                    if let d = task.detail, !d.isEmpty {
                        Text(d).font(.subheadline).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 8) {
                        if !dueText.isEmpty {
                            Label(dueText, systemImage: "calendar").font(.caption).foregroundStyle(dueColor)
                        }
                        if task.createdBy == "advisor" {
                            Label("Advisor", systemImage: "sparkles").font(.caption).foregroundStyle(.purple)
                        }
                    }
                }
                Spacer()
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
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
