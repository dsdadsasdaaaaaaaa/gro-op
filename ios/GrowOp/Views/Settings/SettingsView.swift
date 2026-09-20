import SwiftUI

struct SettingsView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss

    // Server
    @State private var mode: ConnectionMode = .direct
    @State private var serverURL = ""
    @State private var haURL = ""
    @State private var haToken = ""
    @State private var apiKey = ""
    @State private var testing = false
    @State private var testResult: String?
    @State private var testOK: Bool?
    @State private var confirmDisconnect = false

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

    // Devices
    @State private var roles: [DeviceRole] = []
    @State private var mapping: [String: String] = [:]
    @State private var entities: [HAEntity] = []
    @State private var automapping = false
    @State private var busyRole: String?

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
    @State private var savingPrefs = false

    @State private var alert: AlertMessage?
    @State private var loading = true

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
                        growSection
                        stageSection
                        devicesSection
                        targetsSection
                        preferencesSection
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .scrollDismissesKeyboard(.interactively)
            .task { await loadAll() }
            .errorAlert($alert)
            .alert("Change stage to \((pendingStage ?? "").capitalized)?", isPresented: $showStageConfirm) {
                Button("Change stage") { Task { await applyStage() } }
                Button("Cancel", role: .cancel) { stageSelection = grow?.stage ?? stageSelection }
            } message: {
                Text("This records today as the start of the new stage, resets targets to that stage's defaults, and tells the advisor.")
            }
            .confirmationDialog("Disconnect from this grow brain?", isPresented: $confirmDisconnect, titleVisibility: .visible) {
                Button("Disconnect", role: .destructive) {
                    app.disconnect()
                    dismiss()
                }
            } message: {
                Text("You'll be asked for the server address and key again.")
            }
        }
    }

    // MARK: - Loading

    private func loadAll() async {
        mode = app.config.mode
        serverURL = app.config.baseURL.isEmpty ? ServerConfig.defaultURL : app.config.baseURL
        haURL = app.config.haURL
        haToken = app.config.haToken
        apiKey = app.config.apiKey
        guard app.isConfigured else { loading = false; return }
        loading = true
        async let g = try? app.client.grow()
        async let d = try? app.client.devices()
        async let e = try? app.client.haEntities()
        async let t = try? app.client.targets()
        async let s = try? app.client.settings()
        let (gr, dv, en, tg, st) = await (g, d, e, t, s)
        if let gr { applyGrow(gr) }
        if let dv { applyDevices(dv) }
        entities = en?.entities ?? []
        if let tg { applyTargets(tg) }
        if let st {
            app.settings = st
            applySettings(st)
        } else if let st = app.settings {
            applySettings(st)
        }
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

    private func applyDevices(_ d: DevicesResponse) {
        roles = d.roles ?? []
        var m: [String: String] = [:]
        for dev in d.devices ?? [] { m[dev.role] = dev.entityId ?? "" }
        mapping = m
        if roles.isEmpty {
            // Fall back to roles implied by the devices list.
            roles = (d.devices ?? []).map { DeviceRole(role: $0.role, label: $0.label, kind: $0.kind, required: nil, description: nil) }
        }
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
    }

    // MARK: - Server

    private var candidate: ServerConfig {
        ServerConfig(mode: mode, baseURL: serverURL, apiKey: apiKey, haURL: haURL, haToken: haToken,
                     haAddonSlug: app.config.haAddonSlug, haIngressPath: app.config.haIngressPath)
    }

    private var serverChanged: Bool { candidate.differsInUserFields(from: app.config) }

    private var serverSection: some View {
        Section {
            Picker("Connection", selection: $mode) {
                ForEach(ConnectionMode.allCases, id: \.self) { m in Text(m.title).tag(m) }
            }
            .pickerStyle(.segmented)
            .onChange(of: mode) { _, _ in testResult = nil; testOK = nil }

            if mode == .direct {
                TextField("http://homeassistant.local:8099", text: $serverURL)
                    .keyboardType(.URL).textContentType(.URL)
                    .autocorrectionDisabled().textInputAutocapitalization(.never)
            } else {
                TextField("https://….ui.nabu.casa", text: $haURL)
                    .keyboardType(.URL).textContentType(.URL)
                    .autocorrectionDisabled().textInputAutocapitalization(.never)
                VStack(alignment: .leading, spacing: 4) {
                    SecureField("Home Assistant access token", text: $haToken)
                        .autocorrectionDisabled().textInputAutocapitalization(.never)
                    Text("Home Assistant → your profile (bottom left) → Security → Create token")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let slug = app.config.haAddonSlug, mode == app.config.mode {
                    Text("Add-on: \(slug)").font(.caption).foregroundStyle(.secondary)
                }
            }
            TextField("Grow Brain API key", text: $apiKey)
                .autocorrectionDisabled().textInputAutocapitalization(.never)

            Button {
                Task { await testConnection() }
            } label: {
                HStack {
                    if testing { ProgressView() }
                    Text(testing ? "Testing…" : "Test connection")
                    Spacer()
                    if let ok = testOK {
                        Image(systemName: ok ? "checkmark.circle.fill" : "xmark.octagon.fill")
                            .foregroundStyle(ok ? .green : .red)
                    }
                }
            }
            .disabled(testing || !candidate.isConfigured)
            if let testResult {
                Text(testResult).font(.footnote).foregroundStyle(testOK == true ? Color.secondary : Color.red)
            }
            if serverChanged {
                Button("Save and connect") { Task { await saveServer() } }
                    .disabled(testing || !candidate.isConfigured)
            }
            if app.isConfigured {
                Button("Disconnect", role: .destructive) { confirmDisconnect = true }
            }
        } header: {
            Text("Server")
        } footer: {
            Text(mode == .direct
                 ? "Talks to the grow brain directly on your home network. Only works while you're on the same Wi‑Fi."
                 : "Goes through Home Assistant (for example your Nabu Casa address), so it works away from home too. The Grow Brain API key is still needed.")
        }
    }

    private func testConnection() async {
        testing = true
        testResult = nil
        testOK = nil
        defer { testing = false }
        do {
            let r = try await app.client.verify(candidate)
            var parts: [String] = [mode == .homeAssistant ? "Connected through Home Assistant" : "Connected"]
            if let v = r.health.version { parts.append("v\(v)") }
            if mode == .homeAssistant, let slug = r.config.haAddonSlug { parts.append("add-on \(slug)") }
            parts.append(r.health.haConnected == true ? "Home Assistant OK" : "Home Assistant NOT connected")
            parts.append(r.health.advisorEnabled == true ? "advisor on" : "advisor off")
            if let t = r.status.sensor?.tempC { parts.append("temp \(Formatting.number(t))°C") }
            testResult = parts.joined(separator: " · ")
            testOK = true
        } catch {
            testResult = error.localizedDescription
            testOK = false
        }
    }

    private func saveServer() async {
        testing = true
        defer { testing = false }
        do {
            try await app.connect(candidate)
            testResult = "Saved and connected."
            testOK = true
            await loadAll()
        } catch {
            testResult = error.localizedDescription
            testOK = false
        }
    }

    // MARK: - Grow

    private var growSection: some View {
        Section("Grow") {
            TextField("Strain", text: $strain)
            TextField("Breeder", text: $breeder)
            TextField("Seed type (e.g. feminized photoperiod)", text: $seedType)
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
            Stepper("Plants: \(plantCount)", value: $plantCount, in: 1...50)
            Toggle("Start date known", isOn: $hasStartDate)
            if hasStartDate {
                DatePicker("Start date", selection: $startDate, displayedComponents: .date)
            }
            HStack {
                Text("Expected flower days")
                Spacer()
                TextField("65", value: $expectedFlowerDays, format: .number)
                    .keyboardType(.numberPad).multilineTextAlignment(.trailing).frame(width: 80)
            }
            Toggle("Exhaust is vented outside the tent", isOn: $exhaustDucted)
            TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...5)
            Button {
                Task { await saveGrow() }
            } label: {
                HStack { if savingGrow { ProgressView() }; Text("Save grow details") }
            }
            .disabled(savingGrow)
        }
    }

    private func saveGrow() async {
        savingGrow = true
        defer { savingGrow = false }
        var p = GrowProfile()
        p.strain = strain
        p.breeder = breeder
        p.seedType = seedType
        p.medium = medium
        p.potSizeL = potSize
        p.plantCount = plantCount
        p.startDate = hasStartDate ? Formatting.dayString(startDate) : nil
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
            Text("Move to Flower when you flip the lights to 12/12. Targets reset to the new stage's defaults.")
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

    // MARK: - Devices

    private var devicesSection: some View {
        Section {
            if roles.isEmpty {
                Text("No device roles reported by the server.").foregroundStyle(.secondary)
            }
            ForEach(roles) { role in
                HStack {
                    Picker(selection: mappingBinding(for: role)) {
                        Text("Not mapped").tag("")
                        ForEach(candidates(for: role)) { e in
                            Text(e.displayName).tag(e.entityId)
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(role.displayLabel + (role.required == true ? " *" : ""))
                            if let d = role.description, !d.isEmpty {
                                Text(d).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                    .disabled(busyRole == role.role)
                    if busyRole == role.role { ProgressView().controlSize(.small) }
                }
            }
            Button {
                Task { await automap() }
            } label: {
                HStack { if automapping { ProgressView() }; Text("Auto-map from names") }
            }
            .disabled(automapping)
            Button("Reload entity list") { Task { entities = (try? await app.client.haEntities())?.entities ?? [] } }
        } header: {
            Text("Devices")
        } footer: {
            Text("Match each job in the tent to the Home Assistant device that does it. * = required.")
        }
    }

    private func candidates(for role: DeviceRole) -> [HAEntity] {
        let domains: Set<String> = role.isSwitch ? ["switch", "light", "fan", "input_boolean"] : ["sensor"]
        var list = entities.filter { domains.contains($0.domain ?? "") }
        let current = mapping[role.role] ?? ""
        if !current.isEmpty, !list.contains(where: { $0.entityId == current }) {
            if let e = entities.first(where: { $0.entityId == current }) {
                list.append(e)
            } else {
                list.append(HAEntity(entityId: current, name: current, domain: nil, state: nil, unit: nil, deviceClass: nil, suggestedRole: nil))
            }
        }
        return list.sorted { a, b in
            let sa = a.suggestedRole == role.role, sb = b.suggestedRole == role.role
            if sa != sb { return sa }
            return a.displayName.localizedCaseInsensitiveCompare(b.displayName) == .orderedAscending
        }
    }

    private func mappingBinding(for role: DeviceRole) -> Binding<String> {
        Binding(
            get: { mapping[role.role] ?? "" },
            set: { newValue in
                let old = mapping[role.role] ?? ""
                guard newValue != old else { return }
                mapping[role.role] = newValue
                Task {
                    busyRole = role.role
                    defer { busyRole = nil }
                    do {
                        let dev = try await app.client.mapDevice(role: role.role, entityId: newValue.isEmpty ? nil : newValue)
                        mapping[role.role] = dev.entityId ?? ""
                        await app.refreshStatus()
                    } catch {
                        mapping[role.role] = old
                        alert = AlertMessage(title: "Couldn't map device", message: error.localizedDescription)
                    }
                }
            })
    }

    private func automap() async {
        automapping = true
        defer { automapping = false }
        do {
            let d = try await app.client.automap()
            applyDevices(d)
            await app.refreshStatus()
        } catch {
            alert = AlertMessage(title: "Auto-map failed", message: error.localizedDescription)
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
            rangeRow(title: "VPD", unit: "kPa", min: $vMin, max: $vMax)
            HStack {
                Text("Lights on at")
                Spacer()
                TextField("06:00", text: $lightOn)
                    .keyboardType(.numbersAndPunctuation).multilineTextAlignment(.trailing).frame(width: 90)
            }
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
            Button("Reset to stage defaults", role: .destructive) { Task { await resetTargets() } }
                .disabled(savingTargets)
        } header: {
            Text("Targets")
        } footer: {
            Text("The ranges the automation tries to keep the tent in. Leave them alone unless you know why you're changing them.")
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
        if let v = vMin { fields["vpd_min"] = .number(v) }
        if let v = vMax { fields["vpd_max"] = .number(v) }
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
            Picker("Phone notifications", selection: $notifyService) {
                Text("Off").tag("")
                ForEach(notifyOptions, id: \.self) { s in
                    Text(s.replacingOccurrences(of: "notify.", with: "")).tag(s)
                }
            }
            Toggle("Auto-apply advisor target changes", isOn: $autoApply)
            HStack {
                Text("Advisor model")
                Spacer()
                TextField("claude-opus-5", text: $model)
                    .autocorrectionDisabled().textInputAutocapitalization(.never)
                    .multilineTextAlignment(.trailing)
            }
            Button {
                Task { await savePrefs() }
            } label: {
                HStack { if savingPrefs { ProgressView() }; Text("Save preferences") }
            }
            .disabled(savingPrefs)
            if let s = app.settings {
                VStack(alignment: .leading, spacing: 4) {
                    if let tz = s.timezone { Text("Timezone: \(tz)") }
                    if let lo = s.safetyTempMinC, let hi = s.safetyTempMaxC {
                        Text("Safety limits: \(Formatting.number(lo))–\(Formatting.number(hi))°C")
                    }
                    if let ci = s.controlIntervalS { Text("Control loop every \(Formatting.number(ci))s") }
                }
                .font(.footnote).foregroundStyle(.secondary)
            }
        } header: {
            Text("Preferences")
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
        do {
            try await app.saveSettings(fields)
            if let s = app.settings { applySettings(s) }
            if let t = try? await app.client.targets() { applyTargets(t) }
        } catch {
            alert = AlertMessage(title: "Couldn't save preferences", message: error.localizedDescription)
        }
    }
}
