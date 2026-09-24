import SwiftUI

// MARK: - Segmented plant switcher (Home, Log, Photos, Tasks)

struct PlantSwitcher: View {
    @Environment(AppState.self) private var app

    var body: some View {
        if app.plants.count >= 2 {
            Picker("Plant", selection: Binding(
                get: { app.selectedPlantId ?? app.plants.first?.id ?? 0 },
                set: { app.selectPlant($0) })) {
                ForEach(app.plants) { p in
                    Text(p.shortName).tag(p.id)
                }
            }
            .pickerStyle(.segmented)
        }
    }
}

// MARK: - "Which plant is yours?"

struct PlantChoiceSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var selection: Int?
    @State private var newName = ""
    @State private var newOwner = ""
    @State private var saving = false
    @State private var alert: AlertMessage?

    private var canAddAnother: Bool { app.plants.count < 2 }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: Theme.sectionSpacing) {
                    VStack(spacing: 8) {
                        ZStack {
                            Circle().fill(Color.brand.opacity(0.12)).frame(width: 84, height: 84)
                            Image(systemName: "leaf.fill").font(.system(size: 36, weight: .medium)).foregroundStyle(Color.brand)
                        }
                        Text("Which plant is yours?").font(.title2.bold())
                        Text("The tent is shared. Each of you looks after one plant, and the app opens on yours.")
                            .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    }
                    .padding(.top, 12)

                    if app.plants.isEmpty {
                        Text("No plants yet — add yours below.").font(.subheadline).foregroundStyle(.secondary)
                    } else {
                        VStack(spacing: 10) {
                            ForEach(app.plants) { p in
                                Button { withAnimation(.snappy) { selection = p.id } } label: {
                                    HStack(spacing: 12) {
                                        Image(systemName: selection == p.id ? "checkmark.circle.fill" : "circle")
                                            .font(.system(size: 26))
                                            .foregroundStyle(selection == p.id ? Color.brand : Color.secondary.opacity(0.5))
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(p.displayName).font(.headline)
                                            if let o = p.owner, !o.isEmpty {
                                                Text("Looked after by \(o)").font(.subheadline).foregroundStyle(.secondary)
                                            }
                                        }
                                        Spacer()
                                        if let d = p.dayTotal { Text("Day \(d)").font(.subheadline.weight(.semibold)).foregroundStyle(.secondary) }
                                    }
                                    .card(padding: 16)
                                    .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous)
                                        .stroke(selection == p.id ? Color.brand : Color.clear, lineWidth: 2))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    if canAddAnother {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(app.plants.isEmpty ? "Add your plant" : "Add the second plant").font(.headline)
                            TextField("Plant name (e.g. Dad's plant)", text: $newName)
                                .textFieldStyle(.roundedBorder)
                            TextField("Who looks after it (e.g. Dad)", text: $newOwner)
                                .textFieldStyle(.roundedBorder)
                            Button {
                                Task { await addPlant() }
                            } label: {
                                HStack { if saving { ProgressView().tint(Color.brand) }; Text("Add plant") }
                            }
                            .buttonStyle(BigButtonStyle(filled: false))
                            .disabled(saving || newName.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                        .card()
                    }

                    Button("This one is mine") {
                        if let id = selection {
                            app.setMyPlant(id)
                            app.dismissPlantChoice()
                            dismiss()
                        }
                    }
                    .buttonStyle(BigButtonStyle())
                    .disabled(selection == nil)

                    Button("Skip for now") {
                        app.dismissPlantChoice()
                        dismiss()
                    }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                }
                .padding(Theme.spacing)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Color.bg.ignoresSafeArea())
            .errorAlert($alert)
            .task {
                if app.plants.isEmpty { await app.loadPlants() }
                selection = app.myPlantId   // nothing pre-picked: on a new phone, "yours" must be a choice
            }
        }
    }

    private func addPlant() async {
        saving = true
        defer { saving = false }
        var fields: [String: JSONValue] = ["name": .string(newName.trimmingCharacters(in: .whitespaces))]
        let owner = newOwner.trimmingCharacters(in: .whitespaces)
        if !owner.isEmpty { fields["owner"] = .string(owner) }
        do {
            let p = try await app.createPlant(fields)
            newName = ""; newOwner = ""
            if selection == nil { selection = p.id }
        } catch {
            alert = AlertMessage(title: "Couldn't add the plant", message: error.localizedDescription)
        }
    }
}
