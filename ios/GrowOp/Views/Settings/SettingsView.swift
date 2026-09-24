import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss

    // Server (read-only: the connection is provisioned at first launch and never edited here)
    @State private var testing = false
    @State private var testResult: String?
    @State private var testOK: Bool?
    @State private var serverVersion: String?

    // Grow
    @State private var grow: GrowProfile?
    @State private var strain = ""
    @State private var breeder = ""
    @State private var seedType = ""
    @State private var medium = "soil"
    @State private var potSize: Double?
    @State private var plantCount = 1
    @State private var hasStartDate = false
    @State private var startDate = Date()
    @State private var expectedFlowerDays: Int?
    @State private var exhaustDucted = false
    @State private var notes = ""
    @State private var savingGrow = false
    @State private var stageSelection = ""
    @State private var pendingStage: String?
    @State private var showStageConfirm = false
    @State private var changingStage = false

    // Targets
    @State private var targets: Targets?
    @State private var tMin: Double?
    @State private var tMax: Double?
    @State private var hMin: Double?
    @State private var hMax: Double?
    @State private var vMin: Double?
    @State private var vMax: Double?
    @State private var lightOn = ""
    @State private var lightHours: Int?
    @State private var savingTargets = false

    // Preferences
    @State private var units = "c"
    @State private var briefTime = Date()
    @State private var notifyService = ""
    @State private var notifyOptions: [String] = []
    @State private var autoApply = true
    @State private var model = ""
    @State private var budget: Double?
    @State private var savingPrefs = false
    @State private var confirmReset = false
    @State private var confirmSetupAgain = false
    @State private var lightOnDate = Date()

    @State private var alert: AlertMessage?
    @State private var loading = true
    @State private var showAddPlant = false
    @State private var cameraCandidates: [CameraCandidate] = []
    @State private var cameraEntity = ""
    @State private var cameraSupported = true
    @State private var cameraBusy = false

    private static let hhmm: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    var body: some View {
        NavigationStack {
            Form {
                serverSection
                if app.isConfigured {
                    if loading {
                        Section { HStack { ProgressView(); Text("Loading settings…").foregroundStyle(.secondary) } }
                    } else {
                        plantsSection
                        tentSection
                        stageSection
                        targetsSection
                        preferencesSection
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .scrollContentBackground(.hidden)
            .background(Color.bg.ignoresSafeArea())
            .tint(Color.brand)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        Task {
                            if prefsChanged { await savePrefs() }
                            dismiss()
                        }
                    }
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .task { await loadAll() }
            .errorAlert($alert)
            .confirmationDialog("Reset targets to the stage defaults?", isPresented: $confirmReset, titleVisibility: .visible) {
                Button("Reset", role: .destructive) { Task { await resetTargets() } }
            } message: {
                Text("Your own changes and the advisor's tweaks for this stage are dropped.")
            }
            .confirmationDialog("Set this phone up again?", isPresented: $confirmSetupAgain, titleVisibility: .visible) {
                Button("Set up again", role: .destructive) { app.disconnect(); dismiss() }
            } message: {
                Text("GrowOp forgets how to reach the tent on this phone. Scan the setup QR code again afterwards.")
            }
            .alert("Change stage to \((pendingStage ?? "").capitalized)?", isPresented: $showStageConfirm) {
                Button("Change stage") { Task { await applyStage() } }
                Button("Cancel", role: .cancel) { stageSelection = grow?.stage ?? stageSelection }
            } message: {
                Text(stageMessage)
            }
        }
    }

    // MARK: - Loading

    private func loadAll() async {
        guard app.isConfigured else { loading = false; return }
        Task { serverVersion = (try? await app.client.health())?.version }
        loading = true
        async let g = try? app.client.grow()
        async let t = try? app.client.targets()
        async let s = try? app.client.settings()
        let (gr, tg, st) = await (g, t, s)
        if let gr { applyGrow(gr) }
        if let tg { applyTargets(tg) }
        if let st {
            app.settings = st
            applySettings(st)
        } else if let st = app.settings {
            applySettings(st)
        }
        await app.loadPlants()
        await loadCamera()
        loading = false
    }

    private func applyGrow(_ g: GrowProfile) {
        grow = g
        strain = g.strain ?? ""
        breeder = g.breeder ?? ""
        seedType = g.seedType ?? ""
        medium = g.medium ?? "soil"
        potSize = g.potSizeL
        plantCount = g.plantCount ?? 1
        if let d = Formatting.parseDay(g.startDate) { startDate = d; hasStartDate = true } else { hasStartDate = false }
        expectedFlowerDays = g.expectedFlowerDays
        exhaustDucted = g.exhaustDucted ?? false
        notes = g.notes ?? ""
        stageSelection = g.stage ?? ""
    }

    private func applyTargets(_ t: Targets) {
        targets = t
        let useF = app.usesFahrenheit
        if useF {
            tMin = t.tempMinF ?? t.tempMinC.map(Formatting.cToF)
            tMax = t.tempMaxF ?? t.tempMaxC.map(Formatting.cToF)
        } else {
            tMin = t.tempMinC ?? t.tempMinF.map(Formatting.fToC)
            tMax = t.tempMaxC ?? t.tempMaxF.map(Formatting.fToC)
        }
        hMin = t.humidityMin
        hMax = t.humidityMax
        vMin = t.vpdMin
        vMax = t.vpdMax
        lightOn = t.lightOnTime ?? ""
        if let d = Self.hhmm.date(from: lightOn) { lightOnDate = d }
        lightHours = t.lightHours.map { Int($0.rounded()) }
    }

    private func applySettings(_ s: Settings) {
        units = s.units ?? "c"
        if let bt = s.briefTime, let d = Self.hhmm.date(from: bt) { briefTime = d }
        notifyService = s.notifyService ?? ""
        notifyOptions = s.notifyServicesAvailable ?? []
        if !notifyService.isEmpty, !notifyOptions.contains(notifyService) { notifyOptions.append(notifyService) }
        autoApply = s.autoApplyAdvisorTargets ?? true
        model = s.model ?? ""
        budget = s.advisorBudgetUsd
    }

    private var stageMessage: String {
        let light: String = {
            switch pendingStage {
            case "flower": return " The light switches to 12 hours on and 12 off by itself: never turn it on during the dark hours."
            case "veg": return " The light stays on 18 hours a day."
            case "drying": return " The light stays off from now on."
            case "curing": return " Lights, humidifier and exhaust go idle."
            default: return ""
            }
        }()
        return "Temperature and humidity go to the new stage's settings, today is recorded as its start, and the advisor is told." + light
    }

    /// Anything typed in the shared settings that hasn't been saved yet.
    private var prefsChanged: Bool {
        guard let s = app.settings else { return false }
        return units != (s.units ?? "c")
            || Self.hhmm.string(from: briefTime) != (s.briefTime ?? "08:00")
            || notifyService != (s.notifyService ?? "")
            || autoApply != (s.autoApplyAdvisorTargets ?? true)
            || (!model.isEmpty && model != (s.model ?? ""))
            || (budget != nil && budget != s.advisorBudgetUsd)
    }

    // MARK: - Server (read-only)

    private var connectionTitle: String {
        app.config.mode == .homeAssistant ? "Connected through Home Assistant" : "Connected on home Wi‑Fi"
    }

    /// Green only when the most recent status poll succeeded.
    private var isHealthy: Bool { app.status != nil && app.statusError == nil }

    private var serverSection: some View {
        Section {
            HStack(spacing: 12) {
                Image(systemName: isHealthy ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                    .font(.title3)
                    .foregroundStyle(isHealthy ? Color.good : Color.warn)
                VStack(alignment: .leading, spacing: 2) {
                    Text(connectionTitle)
                    Text(serverVersion.map { "Grow Brain v\($0)" } ?? (isHealthy ? "Grow Brain" : "Last update failed"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    Task { await testConnection() }
                } label: {
                    if testing { ProgressView().controlSize(.small) } else { Text("Test connection") }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(Color.brand)
                .disabled(testing)
            }
            Button("Set up this phone again…") { confirmSetupAgain = true }
                .font(.subheadline)
            if let testResult {
                Label(testResult, systemImage: testOK == true ? "checkmark.circle" : "xmark.octagon")
                    .font(.footnote)
                    .foregroundStyle(testOK == true ? Color.secondary : Color.alertRed)
            }
        } header: {
            Text("Server")
        } footer: {
            Text("GrowOp app \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?")")
        }
    }

    private func testConnection() async {
        testing = true
        testResult = nil
        testOK = nil
        defer { testing = false }
        do {
            let r = try await app.client.verify(app.config)
            serverVersion = r.health.version
            testResult = "OK" + (r.health.haConnected == true ? " · Home Assistant connected" : " · Home Assistant not connected")
            testOK = true
        } catch {
            testResult = "Failed: \(error.localizedDescription)"
            testOK = false
        }
    }

    // MARK: - Plants

    private var plantsSection: some View {
        Section {
            if app.plantsSupported == false {
                Text("This grow brain version doesn't support separate plants yet.").foregroundStyle(.secondary)
            } else {
                if app.plants.isEmpty {
                    Text("No plants yet.").foregroundStyle(.secondary)
                }
                ForEach(app.plants) { p in
                    NavigationLink {
                        PlantEditView(plant: p)
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "leaf.fill").foregroundStyle(p.id == app.myPlantId ? Color.brand : Color.secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(p.displayName)
                                HStack(spacing: 6) {
                                    if let o = p.owner, !o.isEmpty { Text(o) }
                                    if let st = p.strain, !st.isEmpty { Text("· \(st)") }
                                    if let d = p.dayTotal { Text("· day \(d)") }
                                }
                                .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if p.id == app.myPlantId { LevelChip(text: "Mine", color: .brand) }
                        }
                    }
                }
                if !app.plants.isEmpty {
                    Picker("Which plant is mine", selection: Binding(
                        get: { app.myPlantId ?? -1 },
                        set: { app.setMyPlant($0 == -1 ? nil : $0) })) {
                        Text("Not set").tag(-1)
                        ForEach(app.plants) { p in Text(p.displayName).tag(p.id) }
                    }
                }
                Button("Add plant") { showAddPlant = true }
            }
        } header: {
            Text("Plants")
        } footer: {
            Text("One person per plant. The tent itself (devices, targets, light) is shared.")
        }
        .sheet(isPresented: $showAddPlant) { AddPlantSheet() }
    }

    // MARK: - Tent

    private func loadCamera() async {
        do {
            let r = try await app.client.camera()
            cameraSupported = true
            cameraCandidates = r.candidates ?? []
            cameraEntity = r.camera?.entityId ?? ""
            if !cameraEntity.isEmpty, !cameraCandidates.contains(where: { $0.entityId == cameraEntity }) {
                cameraCandidates.append(CameraCandidate(entityId: cameraEntity, name: r.camera?.name, state: nil, brand: nil, model: nil))
            }
        } catch let e as APIError {
            if case .http(let status, _) = e, status == 404 { cameraSupported = false }
        } catch {}
    }

    private func selectCamera(_ entityId: String) async {
        cameraBusy = true
        defer { cameraBusy = false }
        do {
            let r = try await app.setCamera(entityId: entityId.isEmpty ? nil : entityId)
            cameraCandidates = r.candidates ?? cameraCandidates
            cameraEntity = r.camera?.entityId ?? ""
        } catch {
            alert = AlertMessage(title: "Couldn't change the camera", message: error.localizedDescription)
            await loadCamera()
        }
    }

    private var tentSection: some View {
        Section("Tent") {
            if cameraSupported {
                HStack {
                    Picker("Tent camera", selection: Binding(
                        get: { cameraEntity },
                        set: { newValue in
                            guard newValue != cameraEntity else { return }
                            cameraEntity = newValue
                            Task { await selectCamera(newValue) }
                        })) {
                        Text("Off").tag("")
                        ForEach(cameraCandidates) { c in Text(c.displayName).tag(c.entityId) }
                    }
                    .disabled(cameraBusy)
                    if cameraBusy { ProgressView().controlSize(.small) }
                }
            }
            HStack {
                Text("Expected flower days")
                Spacer()
                TextField("65", value: $expectedFlowerDays, format: .number)
                    .keyboardType(.numberPad).multilineTextAlignment(.trailing).frame(width: 80)
            }
            Toggle("Exhaust is vented outside the tent", isOn: $exhaustDucted)
            TextField("Tent notes", text: $notes, axis: .vertical).lineLimit(2...5)
            Button {
                Task { await saveTent() }
            } label: {
                HStack { if savingGrow { ProgressView() }; Text("Save tent details") }
            }
            .disabled(savingGrow)
        }
    }

    private func saveTent() async {
        savingGrow = true
        defer { savingGrow = false }
        var p = GrowProfile()
        p.expectedFlowerDays = expectedFlowerDays
        p.exhaustDucted = exhaustDucted
        p.notes = notes
        do {
            let updated = try await app.client.updateGrow(p)
            applyGrow(updated)
            await app.refreshStatus()
        } catch {
            alert = AlertMessage(title: "Couldn't save", message: error.localizedDescription)
        }
    }

    // MARK: - Stage

    private var stageSection: some View {
        Section {
            Picker("Stage", selection: $stageSelection) {
                ForEach(GrowProfile.stages, id: \.self) { Text($0.capitalized).tag($0) }
                if !stageSelection.isEmpty, !GrowProfile.stages.contains(stageSelection) {
                    Text(stageSelection.capitalized).tag(stageSelection)
                }
            }
            .disabled(changingStage)
            .onChange(of: stageSelection) { old, new in
                guard !changingStage, let current = grow?.stage, new != current, new != old else { return }
                pendingStage = new
                showStageConfirm = true
            }
            if changingStage { HStack { ProgressView(); Text("Changing stage…") } }
            if let started = grow?.stageStarted, !started.isEmpty {
                Text("Current stage started \(Formatting.friendlyDay(started))").font(.footnote).foregroundStyle(.secondary)
            }
        } header: {
            Text("Change stage")
        } footer: {
            Text("Changing to Flower switches the light to 12 hours a day by itself. Targets move to the new stage's defaults.")
        }
    }

    private func applyStage() async {
        guard let s = pendingStage else { return }
        changingStage = true
        defer { changingStage = false; pendingStage = nil }
        do {
            let updated = try await app.client.setStage(s)
            applyGrow(updated)
            if let t = try? await app.client.targets() { applyTargets(t) }
            await app.refreshStatus()
        } catch {
            stageSelection = grow?.stage ?? ""
            alert = AlertMessage(title: "Couldn't change stage", message: error.localizedDescription)
        }
    }

    // MARK: - Targets

    private var targetsSection: some View {
        Section {
            if let t = targets {
                HStack {
                    Text("Currently from")
                    Spacer()
                    Text(sourceLabel(t.source)).foregroundStyle(.secondary)
                }
                if let n = t.note, !n.isEmpty {
                    Text(n).font(.footnote).foregroundStyle(.secondary)
                }
            }
            rangeRow(title: "Temperature", unit: app.tempUnitLabel, min: $tMin, max: $tMax)
            rangeRow(title: "Humidity", unit: "%", min: $hMin, max: $hMax)
            DatePicker("Lights on at", selection: $lightOnDate, displayedComponents: .hourAndMinute)
                .onChange(of: lightOnDate) { _, d in lightOn = Self.hhmm.string(from: d) }
            HStack {
                Text("Light hours per day")
                Spacer()
                TextField("18", value: $lightHours, format: .number)
                    .keyboardType(.numberPad).multilineTextAlignment(.trailing).frame(width: 80)
            }
            Button {
                Task { await saveTargets() }
            } label: {
                HStack { if savingTargets { ProgressView() }; Text("Save targets") }
            }
            .disabled(savingTargets)
            Button("Reset to stage defaults", role: .destructive) { confirmReset = true }
                .disabled(savingTargets)
        } header: {
            Text("Targets")
        } footer: {
            Text("The daytime ranges the automation keeps the tent in; at night it may be a few degrees cooler. Air dryness (VPD) follows from these.")
        }
    }

    private func sourceLabel(_ s: String?) -> String {
        switch s {
        case "stage_default": return "Stage defaults"
        case "advisor": return "Advisor"
        case "manual": return "You (manual)"
        default: return s ?? "—"
        }
    }

    private func rangeRow(title: String, unit: String, min: Binding<Double?>, max: Binding<Double?>) -> some View {
        HStack {
            Text(title)
            Spacer()
            TextField("min", value: min, format: .number)
                .keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 60)
            Text("–").foregroundStyle(.secondary)
            TextField("max", value: max, format: .number)
                .keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 60)
            Text(unit).foregroundStyle(.secondary).frame(width: 34, alignment: .leading)
        }
    }

    private func saveTargets() async {
        savingTargets = true
        defer { savingTargets = false }
        var fields: [String: JSONValue] = [:]
        let useF = app.usesFahrenheit
        if let v = tMin { fields["temp_min_c"] = .number(useF ? (Formatting.fToC(v) * 10).rounded() / 10 : v) }
        if let v = tMax { fields["temp_max_c"] = .number(useF ? (Formatting.fToC(v) * 10).rounded() / 10 : v) }
        if let v = hMin { fields["humidity_min"] = .number(v) }
        if let v = hMax { fields["humidity_max"] = .number(v) }
        let lo = lightOn.trimmingCharacters(in: .whitespaces)
        if !lo.isEmpty { fields["light_on_time"] = .string(lo) }
        if let h = lightHours { fields["light_hours"] = .number(Double(h)) }
        do {
            let t = try await app.client.updateTargets(fields)
            applyTargets(t)
            await app.refreshStatus()
        } catch {
            alert = AlertMessage(title: "Couldn't save targets", message: error.localizedDescription)
        }
    }

    private func resetTargets() async {
        savingTargets = true
        defer { savingTargets = false }
        do {
            let t = try await app.client.resetTargets()
            applyTargets(t)
            await app.refreshStatus()
        } catch {
            alert = AlertMessage(title: "Couldn't reset targets", message: error.localizedDescription)
        }
    }

    // MARK: - Preferences

    private var preferencesSection: some View {
        Section {
            Picker("Temperature units", selection: $units) {
                Text("°C").tag("c")
                Text("°F").tag("f")
            }
            .pickerStyle(.segmented)
            DatePicker("Daily brief time", selection: $briefTime, displayedComponents: .hourAndMinute)
            Toggle("Let the advisor fine-tune temperature and humidity", isOn: $autoApply)
            HStack {
                Text("Monthly advisor budget")
                Spacer()
                Text("$").foregroundStyle(.secondary)
                TextField("40", value: $budget, format: .number)
                    .keyboardType(.numberPad).multilineTextAlignment(.trailing).frame(width: 60)
            }
            DisclosureGroup("Advanced (tent setup)") {
                Picker("Extra phone for every alert", selection: $notifyService) {
                    Text("Nobody extra").tag("")
                    ForEach(notifyOptions, id: \.self) { s in Text(Formatting.phoneName(s)).tag(s) }
                }
                Picker("Advisor model", selection: $model) {
                    ForEach(app.settings?.modelsAvailable ?? [model], id: \.self) { m in Text(m).tag(m) }
                }
            }
            Button {
                Task { await savePrefs() }
            } label: {
                HStack { if savingPrefs { ProgressView() }; Text("Save") }
            }
            .disabled(savingPrefs)
            if let s = app.settings {
                VStack(alignment: .leading, spacing: 4) {
                    if let tz = s.timezone { Text("Timezone: \(tz)") }
                    if let lo = s.safetyTempMinC, let hi = s.safetyTempMaxC {
                        Text("Safety limits: \(Formatting.number(lo))–\(Formatting.number(hi))°C")
                    }
                    if let usd = s.advisorMonthUsd { Text("Advisor spend this month: $\(String(format: "%.2f", usd)) USD") }
                }
                .font(.footnote).foregroundStyle(.secondary)
            }
        } header: {
            Text("Tent settings (shared)")
        } footer: {
            Text("These apply to the whole tent, for both of you. Each plant's own phone is set under Plants.")
        }
    }

    private func savePrefs() async {
        savingPrefs = true
        defer { savingPrefs = false }
        var fields: [String: JSONValue] = [
            "units": .string(units),
            "brief_time": .string(Self.hhmm.string(from: briefTime)),
            "auto_apply_advisor_targets": .bool(autoApply),
            "notify_service": notifyService.isEmpty ? .null : .string(notifyService),
        ]
        let m = model.trimmingCharacters(in: .whitespaces)
        if !m.isEmpty { fields["model"] = .string(m) }
        if let b = budget { fields["advisor_budget_usd"] = .number(b) }
        do {
            try await app.saveSettings(fields)
            if let s = app.settings { applySettings(s) }
            if let t = try? await app.client.targets() { applyTargets(t) }
        } catch {
            alert = AlertMessage(title: "Couldn't save the settings", message: error.localizedDescription)
        }
    }
}
