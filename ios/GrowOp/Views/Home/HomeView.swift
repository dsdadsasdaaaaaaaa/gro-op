import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var app
    @Binding var selectedTab: AppTab
    @State private var showSettings = false
    @State private var alert: AlertMessage?
    @State private var busyPause = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if let st = app.status {
                        content(st)
                    } else if let err = app.statusError {
                        VStack(spacing: 12) {
                            Image(systemName: "wifi.exclamationmark").font(.system(size: 40)).foregroundStyle(.orange)
                            Text("Can't reach the grow brain").font(.headline)
                            Text(err).font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
                            Button("Try again") { Task { await app.refreshStatus() } }
                                .buttonStyle(.bordered)
                        }
                        .card()
                    } else {
                        WorkingView(title: "Loading your grow…")
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .refreshable { await app.refreshStatus() }
            .navigationTitle("GrowOp")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings")
                }
            }
            .sheet(isPresented: $showSettings) { SettingsView() }
            .errorAlert($alert)
        }
    }

    // MARK: Content

    @ViewBuilder
    private func content(_ st: StatusResponse) -> some View {
        if let err = app.statusError {
            Label("Showing last known status. \(err)", systemImage: "wifi.exclamationmark")
                .font(.footnote).foregroundStyle(.orange)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        if st.haConnected == false {
            Label("Home Assistant is not connected. Devices can't be controlled right now.", systemImage: "exclamationmark.triangle.fill")
                .font(.footnote).foregroundStyle(.red)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        if let until = st.controlPausedUntil, let d = Formatting.parseISO(until) {
            HStack {
                Image(systemName: "pause.circle.fill").foregroundStyle(.orange)
                Text("Automation paused until \(d.formatted(date: .omitted, time: .shortened))")
                    .font(.subheadline.weight(.medium))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color.orange.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
        }

        assessmentBanner(st.assessment)

        sensorTiles(st)

        if st.sensor?.stale == true {
            Label("Sensor readings are old — the sensor may be offline. Last update \(Formatting.relative(st.sensor?.updatedAt)).", systemImage: "clock.badge.exclamationmark")
                .font(.footnote).foregroundStyle(.orange)
                .frame(maxWidth: .infinity, alignment: .leading)
        }

        lightRow(st)
        growRow(st)
        shortcutsRow(st)
        devicesCard(st)
        alertsCard(st)
        pauseButton(st)

        if let t = app.lastStatusAt {
            Text("Updated \(t.formatted(date: .omitted, time: .shortened))")
                .font(.caption).foregroundStyle(.tertiary)
        }
    }

    // MARK: Assessment

    private func assessmentBanner(_ a: Assessment?) -> some View {
        let level = a?.level ?? "unknown"
        let color = LevelColor.color(for: level)
        let title: String = {
            switch level {
            case "good": return "All good"
            case "warn": return "Needs a look"
            case "alert": return "Needs attention now"
            default: return "Status unknown"
            }
        }()
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Image(systemName: LevelColor.symbol(for: level))
                    .font(.system(size: 34))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.title2.bold())
                    if let h = a?.headline, !h.isEmpty {
                        Text(h).font(.subheadline)
                    }
                }
                Spacer()
            }
            if let details = a?.details, !details.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(details.enumerated()), id: \.offset) { _, d in
                        Text("• \(d)").font(.footnote)
                    }
                }
                .opacity(0.9)
            }
        }
        .foregroundStyle(.white)
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(color, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    // MARK: Sensor tiles

    private func sensorTiles(_ st: StatusResponse) -> some View {
        let s = st.sensor
        let t = st.targets
        let useF = app.usesFahrenheit

        var tempValue: Double? = useF ? s?.tempF : s?.tempC
        if tempValue == nil, let c = s?.tempC, useF { tempValue = Formatting.cToF(c) }
        if tempValue == nil, let f = s?.tempF, !useF { tempValue = Formatting.fToC(f) }
        var tMin: Double? = useF ? t?.tempMinF : t?.tempMinC
        var tMax: Double? = useF ? t?.tempMaxF : t?.tempMaxC
        if tMin == nil, let c = t?.tempMinC, useF { tMin = Formatting.cToF(c) }
        if tMax == nil, let c = t?.tempMaxC, useF { tMax = Formatting.cToF(c) }

        return HStack(spacing: 10) {
            SensorTile(title: "Temp", symbol: "thermometer.medium",
                       value: tempValue, unit: app.tempUnitLabel, decimals: 1,
                       min: tMin, max: tMax)
            SensorTile(title: "Humidity", symbol: "humidity",
                       value: s?.humidity, unit: "%", decimals: 0,
                       min: t?.humidityMin, max: t?.humidityMax)
            SensorTile(title: "VPD", symbol: "wind",
                       value: s?.vpdKpa, unit: "kPa", decimals: 2,
                       min: t?.vpdMin, max: t?.vpdMax)
        }
    }

    // MARK: Light

    private func lightRow(_ st: StatusResponse) -> some View {
        let light = st.light
        let isOn = light?.isOn ?? false
        var subtitle = ""
        if let next = Formatting.parseISO(light?.nextChangeAt) {
            subtitle = (isOn ? "off in " : "on in ") + Formatting.countdown(to: next)
        }
        return HStack(spacing: 14) {
            Image(systemName: isOn ? "sun.max.fill" : "moon.fill")
                .font(.system(size: 30))
                .foregroundStyle(isOn ? .yellow : .indigo)
                .frame(width: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(isOn ? "Lights ON" : "Lights OFF").font(.headline)
                if !subtitle.isEmpty {
                    Text(subtitle.prefix(1).uppercased() + subtitle.dropFirst()).font(.subheadline).foregroundStyle(.secondary)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let sched = light?.schedule, !sched.isEmpty {
                    Text(sched).font(.title3.weight(.semibold))
                    Text("hours on/off").font(.caption2).foregroundStyle(.secondary)
                }
                if let on = st.targets?.lightOnTime, !on.isEmpty {
                    Text("On at \(on)").font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .card()
    }

    // MARK: Grow

    private func growRow(_ st: StatusResponse) -> some View {
        let g = st.grow
        let stage = (g?.stage ?? "").capitalized
        var dayLine = ""
        if let total = g?.dayTotal { dayLine = "Day \(total)" }
        if let inStage = g?.dayInStage, !stage.isEmpty {
            dayLine += dayLine.isEmpty ? "" : " "
            dayLine += "(day \(inStage) of \(stage.lowercased()))"
        }
        return HStack(spacing: 14) {
            Image(systemName: "leaf.fill")
                .font(.system(size: 30))
                .foregroundStyle(Color.accentColor)
                .frame(width: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(g?.strain?.isEmpty == false ? g!.strain! : "Your grow").font(.headline)
                if !stage.isEmpty {
                    Text(stage + (g?.medium.map { " · \($0.capitalized)" } ?? "")).font(.subheadline).foregroundStyle(.secondary)
                }
                if !dayLine.isEmpty {
                    Text(dayLine).font(.subheadline)
                }
                if let h = g?.expectedHarvestDate, !h.isEmpty {
                    Text("Expected harvest \(Formatting.friendlyDay(h))").font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .card()
    }

    // MARK: Shortcuts

    @ViewBuilder
    private func shortcutsRow(_ st: StatusResponse) -> some View {
        let tasks = st.openTasks ?? 0
        let photos = st.openPhotoRequests ?? 0
        let unread = st.unreadBrief ?? false
        if tasks > 0 || photos > 0 || unread {
            VStack(spacing: 8) {
                if unread {
                    ShortcutRow(symbol: "sparkles", color: .purple, text: "New advisor brief to read") { selectedTab = .advisor }
                }
                if photos > 0 {
                    ShortcutRow(symbol: "camera.fill", color: .blue, text: photos == 1 ? "1 photo requested" : "\(photos) photos requested") { selectedTab = .photos }
                }
                if tasks > 0 {
                    ShortcutRow(symbol: "checklist", color: .accentColor, text: tasks == 1 ? "1 task to do" : "\(tasks) tasks to do") { selectedTab = .tasks }
                }
            }
        }
    }

    // MARK: Devices

    private func devicesCard(_ st: StatusResponse) -> some View {
        let devices = st.devices ?? []
        let switches = devices.filter { $0.isSwitch }
        let sensors = devices.filter { !$0.isSwitch }
        return VStack(alignment: .leading, spacing: 12) {
            SectionTitle(text: "Devices")
            if switches.isEmpty {
                Text("No devices set up yet. Open Settings to map your tent equipment.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(switches) { d in
                DeviceRow(device: d) { mode in
                    do { try await app.setOverride(role: d.role, mode: mode) }
                    catch { alert = AlertMessage(message: error.localizedDescription) }
                }
                if d.id != switches.last?.id { Divider() }
            }
            if !sensors.isEmpty {
                Divider()
                ForEach(sensors) { s in
                    HStack {
                        Image(systemName: "sensor.fill").foregroundStyle(.secondary).frame(width: 22)
                        Text(s.displayLabel).font(.subheadline)
                        Spacer()
                        Text(s.entityId == nil ? "Not set up" : (s.state ?? "—"))
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .card()
    }

    // MARK: Alerts

    @ViewBuilder
    private func alertsCard(_ st: StatusResponse) -> some View {
        if let alerts = st.alerts, !alerts.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionTitle(text: "Recent alerts")
                ForEach(alerts) { a in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: LevelColor.symbol(for: a.level))
                            .foregroundStyle(LevelColor.infoColor(for: a.level))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(a.message ?? "").font(.subheadline)
                            Text(Formatting.relative(a.at)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .card()
        }
    }

    // MARK: Pause

    private func pauseButton(_ st: StatusResponse) -> some View {
        let paused = st.controlPausedUntil != nil
        return Button {
            Task {
                busyPause = true
                defer { busyPause = false }
                do {
                    if paused { try await app.resumeControl() } else { try await app.pauseControl(minutes: 30) }
                } catch { alert = AlertMessage(message: error.localizedDescription) }
            }
        } label: {
            HStack {
                if busyPause { ProgressView() } else {
                    Image(systemName: paused ? "play.fill" : "pause.fill")
                }
                Text(paused ? "Resume automation" : "Pause automation 30 min")
            }
        }
        .buttonStyle(BigButtonStyle(color: paused ? .accentColor : .orange, filled: false))
        .disabled(busyPause)
    }
}

// MARK: - Subviews

struct SensorTile: View {
    var title: String
    var symbol: String
    var value: Double?
    var unit: String
    var decimals: Int
    var min: Double?
    var max: Double?

    private var inRange: Bool? {
        guard let value, let min, let max else { return nil }
        return value >= min && value <= max
    }

    private var tint: Color {
        switch inRange {
        case .some(true): return .green
        case .some(false): return .orange
        case .none: return .gray
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: symbol)
                Text(title)
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(tint)

            if let value {
                (Text(String(format: "%.\(decimals)f", value))
                    .font(.system(size: 28, weight: .bold, design: .rounded))
                + Text(unit == "%" ? "%" : " \(unit)")
                    .font(.caption.weight(.semibold)))
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
            } else {
                Text("—").font(.system(size: 28, weight: .bold, design: .rounded))
            }

            if let min, let max {
                Text("Target \(Formatting.number(min, decimals: decimals))–\(Formatting.number(max, decimals: decimals))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            } else {
                Text("No target").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct ShortcutRow: View {
    var symbol: String
    var color: Color
    var text: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack {
                Image(systemName: symbol).foregroundStyle(color).frame(width: 26)
                Text(text).font(.subheadline.weight(.medium)).foregroundStyle(.primary)
                Spacer()
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
            }
            .padding(12)
            .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct DeviceRow: View {
    let device: DeviceStatus
    var onModeChange: (String) async -> Void
    @State private var busy = false

    private var stateColor: Color {
        if device.entityId == nil { return .gray }
        if device.available == false { return .red }
        switch device.state {
        case "on": return .green
        case "off": return Color(.systemGray3)
        default: return .orange
        }
    }

    private var stateText: String {
        if device.entityId == nil { return "Not set up" }
        if device.available == false { return "Unavailable" }
        switch device.state {
        case "on": return "On"
        case "off": return "Off"
        default: return "Unknown"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                Circle().fill(stateColor).frame(width: 12, height: 12)
                Text(device.displayLabel).font(.body.weight(.semibold))
                Spacer()
                Text(stateText).font(.subheadline).foregroundStyle(.secondary)
            }
            if let reason = device.reason, !reason.isEmpty {
                Text(reason).font(.footnote).foregroundStyle(.secondary)
            }
            if let until = Formatting.parseISO(device.overrideUntil) {
                Text("Manual until \(until.formatted(date: .omitted, time: .shortened))")
                    .font(.caption).foregroundStyle(.orange)
            }
            if device.entityId != nil {
                HStack {
                    Picker("Mode", selection: Binding(
                        get: { device.mode ?? "auto" },
                        set: { newValue in
                            guard newValue != (device.mode ?? "auto") else { return }
                            Task {
                                busy = true
                                await onModeChange(newValue)
                                busy = false
                            }
                        })) {
                        Text("Auto").tag("auto")
                        Text("On").tag("on")
                        Text("Off").tag("off")
                    }
                    .pickerStyle(.segmented)
                    .disabled(busy)
                    if busy { ProgressView().controlSize(.small) }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
