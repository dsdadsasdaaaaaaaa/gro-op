import SwiftUI

// MARK: - Edit one plant

struct PlantEditView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    let plant: Plant

    @State private var name = ""
    @State private var owner = ""
    @State private var strain = ""
    @State private var breeder = ""
    @State private var seedType = ""
    @State private var medium = "soil"
    @State private var potSize: Double?
    @State private var hasStartDate = false
    @State private var startDate = Date()
    @State private var notes = ""
    @State private var notifyService = ""
    @State private var testSent = false
    @State private var saving = false
    @State private var confirmDelete = false
    @State private var alert: AlertMessage?

    private var notifyOptions: [String] {
        var opts = app.settings?.notifyServicesAvailable ?? []
        if !notifyService.isEmpty, !opts.contains(notifyService) { opts.append(notifyService) }
        return opts
    }

    var body: some View {
        Form {
            Section("Plant") {
                TextField("Name", text: $name)
                TextField("Who looks after it", text: $owner)
            }
            Section("Genetics") {
                TextField("Strain", text: $strain)
                TextField("Breeder", text: $breeder)
                TextField("Seed type (e.g. feminized photoperiod)", text: $seedType)
            }
            Section("Growing") {
                Picker("Medium", selection: $medium) {
                    ForEach(GrowProfile.mediums, id: \.self) { Text($0.capitalized).tag($0) }
                }
                HStack {
                    Text("Pot size")
                    Spacer()
                    TextField("11", value: $potSize, format: .number)
                        .keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 80)
                    Text("L").foregroundStyle(.secondary)
                }
                Toggle("Start date known", isOn: $hasStartDate)
                if hasStartDate {
                    DatePicker("Start date", selection: $startDate, displayedComponents: .date)
                }
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...5)
            }
            Section {
                Picker("Phone for alerts", selection: $notifyService) {
                    Text("No phone").tag("")
                    ForEach(notifyOptions, id: \.self) { s in Text(Formatting.phoneName(s)).tag(s) }
                }
                Button("Send a test notification") {
                    Task {
                        do { try await app.client.notifyTest(service: notifyService); testSent = true }
                        catch { alert = AlertMessage(title: "Test not sent", message: error.localizedDescription) }
                    }
                }
                .disabled(notifyService.isEmpty)
                if testSent { Label("Sent: check that phone", systemImage: "checkmark.circle").font(.footnote).foregroundStyle(.secondary) }
            } footer: {
                Text("Tent alerts and this plant's reminders go to this phone. It needs the Home Assistant app installed and signed in.")
            }
            Section {
                Button {
                    Task { await save() }
                } label: {
                    HStack { if saving { ProgressView() }; Text("Save plant") }
                }
                .disabled(saving || name.trimmingCharacters(in: .whitespaces).isEmpty)
                Button("Remove plant", role: .destructive) { confirmDelete = true }
                    .disabled(saving)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Color.bg.ignoresSafeArea())
        .navigationTitle(plant.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear(perform: load)
        .confirmationDialog("Remove \(plant.displayName)?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Remove plant", role: .destructive) { Task { await remove() } }
        } message: {
            Text("Its history is kept, but it disappears from the app.")
        }
        .errorAlert($alert)
    }

    private func load() {
        name = plant.name ?? ""
        owner = plant.owner ?? ""
        strain = plant.strain ?? ""
        breeder = plant.breeder ?? ""
        seedType = plant.seedType ?? ""
        medium = plant.medium ?? "soil"
        potSize = plant.potSizeL
        if let d = Formatting.parseDay(plant.startDate) { startDate = d; hasStartDate = true } else { hasStartDate = false }
        notes = plant.notes ?? ""
        notifyService = plant.notifyService ?? ""
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var f: [String: JSONValue] = [
            "name": .string(name.trimmingCharacters(in: .whitespaces)),
            "owner": .string(owner.trimmingCharacters(in: .whitespaces)),
            "strain": .string(strain),
            "breeder": .string(breeder),
            "seed_type": .string(seedType),
            "medium": .string(medium),
            "notes": .string(notes),
            "start_date": hasStartDate ? .string(Formatting.dayString(startDate)) : .null,
            "notify_service": notifyService.isEmpty ? .null : .string(notifyService),
        ]
        if let potSize { f["pot_size_l"] = .number(potSize) } else { f["pot_size_l"] = .null }
        do {
            try await app.updatePlant(id: plant.id, f)
            await app.refreshStatus()
            dismiss()
        } catch {
            alert = AlertMessage(title: "Couldn't save", message: error.localizedDescription)
        }
    }

    private func remove() async {
        do {
            try await app.deletePlant(id: plant.id)
            await app.refreshStatus()
            dismiss()
        } catch {
            alert = AlertMessage(title: "Couldn't remove the plant", message: error.localizedDescription)
        }
    }
}

// MARK: - Add a plant

struct AddPlantSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var owner = ""
    @State private var strain = ""
    @State private var hasStartDate = true
    @State private var startDate = Date()
    @State private var saving = false
    @State private var alert: AlertMessage?

    var body: some View {
        NavigationStack {
            Form {
                Section("Plant") {
                    TextField("Name (e.g. Dad's plant)", text: $name)
                    TextField("Who looks after it (e.g. Dad)", text: $owner)
                    TextField("Strain (optional)", text: $strain)
                }
                Section {
                    Toggle("Start date known", isOn: $hasStartDate)
                    if hasStartDate {
                        DatePicker("Start date", selection: $startDate, displayedComponents: .date)
                    }
                } footer: {
                    Text("The day it was germinated or planted. You can change everything else later.")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color.bg.ignoresSafeArea())
            .navigationTitle("New plant")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "Adding…" : "Add") { Task { await save() } }
                        .disabled(saving || name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .errorAlert($alert)
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        var f: [String: JSONValue] = ["name": .string(name.trimmingCharacters(in: .whitespaces))]
        let o = owner.trimmingCharacters(in: .whitespaces)
        if !o.isEmpty { f["owner"] = .string(o) }
        let st = strain.trimmingCharacters(in: .whitespaces)
        if !st.isEmpty { f["strain"] = .string(st) }
        if hasStartDate { f["start_date"] = .string(Formatting.dayString(startDate)) }
        do {
            try await app.createPlant(f)
            await app.refreshStatus()
            dismiss()
        } catch {
            alert = AlertMessage(title: "Couldn't add the plant", message: error.localizedDescription)
        }
    }
}
