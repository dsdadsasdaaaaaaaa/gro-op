import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var app
    @Binding var selectedTab: AppTab
    @State private var showSettings = false
    @State private var alert: AlertMessage?
    @State private var confirmStandby = false
    @State private var powerBusy = false
    @State private var selectedDevice: DeviceSelection?
    @State private var path = NavigationPath()
    // Launch-argument hooks for screenshots/testing, like `-growop.initialTab`:
    //   -growop.initialScroll plan|devices|needs   -growop.initialScreen plan|settings   -growop.initialDevice <role>
    private let initialScroll = UserDefaults.standard.string(forKey: "growop.initialScroll")
    private let initialScreen = UserDefaults.standard.string(forKey: "growop.initialScreen")
    private let initialDevice = UserDefaults.standard.string(forKey: "growop.initialDevice")

    var body: some View {
        NavigationStack(path: $path) {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: Theme.sectionSpacing) {
                    if let st = app.status {
                        content(st)
                    } else if let err = app.statusError {
                        connectionProblem(err)
                    } else {
                        WorkingView(title: "Loading your grow…")
                            .padding(.top, 80)
                    }
                }
                .padding(.horizontal, Theme.spacing)
                .padding(.top, 4)
                .padding(.bottom, 40)
            }
            .onChange(of: app.status == nil) { _, isNil in
                guard !isNil, let target = initialScroll else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                    withAnimation { proxy.scrollTo(target, anchor: .top) }
                }
            }
            }
            .navigationDestination(for: String.self) { screen in
                if screen == "plan" { PlanView() }
            }
            .background(Color.bg.ignoresSafeArea())
            .refreshable {
                await app.refreshStatus()
                await app.loadHistory(force: true)
            }
            .navigationTitle("")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.hidden, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape.fill")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(.secondary)
                    }
                    .accessibilityLabel("Settings")
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .sheet(item: $selectedDevice) { sel in
                DeviceSheet(role: sel.role)
                    .presentationDetents([.medium])
                    .presentationDragIndicator(.visible)
            }
            .sheet(isPresented: $confirmStandby) {
                StandbyConfirmSheet { Task { await setStandby(true) } }
                    .presentationDetents([.medium])
                    .presentationDragIndicator(.visible)
            }
            .errorAlert($alert)
            .task {
                if initialScreen == "plan" { path.append("plan") }
                if initialScreen == "settings" { showSettings = true }
                if let role = initialDevice { selectedDevice = DeviceSelection(role: role) }
                if app.plantsSupported == nil { await app.loadPlants() }
                if app.plan == nil { await app.loadPlan() }
                if app.history.isEmpty { await app.loadHistory() }
                await app.loadTasks()
                await app.loadPhotoRequests()
            }
        }
    }

    // MARK: - Content

    @ViewBuilder
    private func content(_ st: StatusResponse) -> some View {
        let standby = st.standby == true

        HomeHeader(day: app.selectedPlant?.dayTotal ?? st.grow?.dayTotal, subtitle: headerSubtitle(st, standby: standby), standby: standby)

        PlantSwitcher()

        notices(st)

        TentPowerPill(running: !standby, busy: powerBusy) {
            if standby { Task { await setStandby(false) } } else { confirmStandby = true }
        }

        if standby {
            StandbyCard(busy: powerBusy) { Task { await setStandby(false) } }
        }

        VitalsCard(sensor: st.sensor, targets: st.targets, usesF: app.usesFahrenheit,
                   history: app.history, muted: standby)

        AssessmentLine(assessment: st.assessment, standby: standby)

        LightBar(onTime: st.targets?.lightOnTime,
                 hours: st.targets?.lightHours,
                 isOn: st.light?.isOn ?? false,
                 nextChange: Formatting.parseISO(st.light?.nextChangeAt),
                 schedule: st.light?.schedule,
                 muted: standby)

        NavigationLink {
            PlanView()
        } label: {
            GrowPlanCard(plan: app.plan, growStartDate: app.selectedPlant?.startDate ?? st.grow?.startDate)
        }
        .buttonStyle(.plain)
        .id("plan")

        DevicesGrid(devices: (st.devices ?? []).filter { $0.isSwitch && $0.entityId != nil }, muted: standby) { d in
            selectedDevice = DeviceSelection(role: d.role)
        }
        .id("devices")

        NeedsYouRow(tasks: app.needsYouTaskCount, photos: app.needsYouPhotoCount,
                    unreadBrief: st.unreadBrief ?? false) { tab in selectedTab = tab }
        .id("needs")

        footer(st)
    }

    private func headerSubtitle(_ st: StatusResponse, standby: Bool) -> String {
        var parts: [String] = []
        if standby, let d = app.selectedPlant?.dayTotal ?? st.grow?.dayTotal { parts.append("Day \(d)") }
        if let phase = app.plan?.current?.displayTitle {
            parts.append(phase)
        } else if let stage = st.grow?.stage, !stage.isEmpty {
            parts.append(stage.capitalized)
        }
        if let plant = app.selectedPlant {
            parts.append(plant.displayName)
        } else if let strain = st.grow?.strain, !strain.isEmpty {
            parts.append(strain)
        }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder
    private func notices(_ st: StatusResponse) -> some View {
        let items: [(String, String, Color)] = {
            var out: [(String, String, Color)] = []
            if let err = app.statusError {
                out.append(("wifi.exclamationmark", "Showing the last update. \(err)", .warn))
            }
            if st.haConnected == false {
                out.append(("exclamationmark.triangle.fill", "Home Assistant isn't connected, so devices can't be controlled right now.", .alertRed))
            }
            if st.sensor?.stale == true, st.standby != true {
                out.append(("antenna.radiowaves.left.and.right.slash", "Sensor not reporting. Readings are muted until it comes back.", .warn))
            }
            if let until = st.controlPausedUntil, let d = Formatting.parseISO(until), st.standby != true {
                out.append(("pause.circle.fill", "Automation paused until \(d.formatted(date: .omitted, time: .shortened)).", .warn))
            }
            return out
        }()
        if !items.isEmpty {
            VStack(spacing: 8) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, n in
                    InlineNotice(symbol: n.0, text: n.1, tint: n.2)
                }
            }
        }
    }

    private func connectionProblem(_ err: String) -> some View {
        VStack(spacing: 14) {
            ZStack {
                Circle().fill(Color.warn.opacity(0.12)).frame(width: 84, height: 84)
                Image(systemName: "wifi.exclamationmark").font(.system(size: 34, weight: .medium)).foregroundStyle(Color.warn)
            }
            Text("Can't reach the grow brain").font(.title3.weight(.semibold))
            Text(err).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            Button("Try again") { Task { await app.refreshStatus() } }
                .buttonStyle(BigButtonStyle(filled: false))
            Button("Connection settings") { showSettings = true }
                .font(.subheadline.weight(.semibold))
        }
        .card()
        .padding(.top, 40)
    }

    @ViewBuilder
    private func footer(_ st: StatusResponse) -> some View {
        VStack(spacing: 6) {
            if let until = st.controlPausedUntil, st.standby != true, Formatting.parseISO(until) != nil {
                Button("Resume automation now") {
                    Task {
                        do { try await app.resumeControl() } catch { alert = AlertMessage(message: error.localizedDescription) }
                    }
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.brand)
            }
            if let t = app.lastStatusAt {
                Text("Updated \(t.formatted(date: .omitted, time: .shortened))")
                    .font(.caption).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }

    // MARK: - Actions

    private func setStandby(_ on: Bool) async {
        powerBusy = true
        defer { powerBusy = false }
        do {
            if on { try await app.setStandby() } else { try await app.startTent() }
        } catch {
            alert = AlertMessage(title: on ? "Couldn't turn the tent off" : "Couldn't start the tent", message: error.localizedDescription)
        }
    }
}
