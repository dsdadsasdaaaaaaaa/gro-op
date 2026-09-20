import SwiftUI

// MARK: - Header

struct HomeHeader: View {
    let day: Int?
    let subtitle: String
    let standby: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if standby {
                Text("Tent is off")
                    .font(.hero(44))
                    .foregroundStyle(.secondary)
            } else {
                Text(day.map { "Day \($0)" } ?? "Your grow")
                    .font(.hero(64))
                    .contentTransition(.numericText())
            }
            if !subtitle.isEmpty {
                Text(subtitle).font(.title3.weight(.medium)).foregroundStyle(.secondary)
            }
            Text(Date().formatted(.dateTime.weekday(.wide).month(.wide).day()))
                .font(.footnote).foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(.spring(duration: 0.4), value: standby)
    }
}

// MARK: - Tent power

struct TentPowerPill: View {
    let running: Bool
    let busy: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ZStack {
                    if running {
                        Circle().fill(Color.leaf.opacity(0.35)).frame(width: 24, height: 24).blur(radius: 3)
                    }
                    Circle().fill(running ? Color.leaf : Color.secondary.opacity(0.35)).frame(width: 11, height: 11)
                }
                .frame(width: 24, height: 24)
                Text(running ? "Tent running" : "Standby")
                    .font(.headline)
                    .foregroundStyle(running ? Color.brand : Color.secondary)
                Spacer()
                if busy {
                    ProgressView().controlSize(.small)
                } else {
                    Text(running ? "Turn off" : "Start")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(running ? Color.secondary : Color.brand)
                    Image(systemName: "power")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(running ? Color.secondary : Color.brand)
                }
            }
            .padding(.horizontal, 18).padding(.vertical, 14)
            .background(Capsule().fill(running ? Color.brand.opacity(0.12) : Color.secondary.opacity(0.10)))
            .overlay(Capsule().stroke(running ? Color.brand.opacity(0.30) : Color.clear, lineWidth: 1))
            .shadow(color: running ? Color.leaf.opacity(0.30) : .clear, radius: 16, y: 2)
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .animation(.spring(duration: 0.45), value: running)
        .accessibilityLabel(running ? "Tent running. Turn off" : "Tent in standby. Start")
    }
}

struct StandbyCard: View {
    let busy: Bool
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Image(systemName: "moon.zzz.fill").font(.title2).foregroundStyle(Color.night)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Everything is switched off").font(.headline)
                    Text("Nothing runs until you start the tent.").font(.subheadline).foregroundStyle(.secondary)
                }
            }
            Button(action: action) {
                HStack(spacing: 8) {
                    if busy { ProgressView().tint(.white) } else { Image(systemName: "power") }
                    Text("Start tent")
                }
            }
            .buttonStyle(BigButtonStyle())
            .disabled(busy)
            Text("Start it when the seedling goes in")
                .font(.footnote).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity)
        }
        .card()
    }
}

struct StandbyConfirmSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onConfirm: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "power.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(Color.alertRed)
                .padding(.top, 8)
            Text("Turn the tent off?").font(.title2.bold())
            Text("Every device switches off and stays off until you start it again.")
                .font(.body).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer(minLength: 0)
            Button("Turn off") { onConfirm(); dismiss() }
                .buttonStyle(BigButtonStyle(color: .alertRed))
            Button("Keep running") { dismiss() }
                .buttonStyle(BigButtonStyle(color: .brand, filled: false))
        }
        .padding(24)
        .background(Color.bg.ignoresSafeArea())
    }
}

// MARK: - Vitals

enum BandStatus {
    case good, warn, alert, unknown

    var color: Color {
        switch self {
        case .good: return .good
        case .warn: return .warn
        case .alert: return .alertRed
        case .unknown: return .secondary
        }
    }

    static func of(value: Double?, min: Double?, max: Double?, tolerance: Double) -> BandStatus {
        guard let value, let min, let max else { return .unknown }
        if value >= min && value <= max { return .good }
        let dist = value < min ? min - value : value - max
        return dist <= tolerance ? .warn : .alert
    }
}

struct VitalSpec {
    var title: String
    var symbol: String
    var unit: String
    var decimals: Int
    var scaleMin: Double
    var scaleMax: Double
    var tolerance: Double
}

struct VitalsCard: View {
    let sensor: SensorReading?
    let targets: Targets?
    let usesF: Bool
    let history: [HistoryPoint]
    let muted: Bool

    private var stale: Bool { sensor?.stale == true }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Vitals").font(.headline)
                Spacer()
                if stale {
                    Label("Sensor not reporting", systemImage: "antenna.radiowaves.left.and.right.slash")
                        .font(.caption.weight(.semibold)).foregroundStyle(Color.warn)
                } else if let t = sensor?.updatedAt, !t.isEmpty {
                    Text(Formatting.relative(t)).font(.caption).foregroundStyle(.tertiary)
                }
            }
            HStack(alignment: .top, spacing: 6) {
                VitalColumn(spec: VitalSpec(title: "Temp", symbol: "thermometer.medium", unit: usesF ? "°F" : "°C",
                                            decimals: 1, scaleMin: usesF ? 50 : 10, scaleMax: usesF ? 104 : 40,
                                            tolerance: usesF ? 2.7 : 1.5),
                            value: tempValue, bandMin: tempMin, bandMax: tempMax,
                            series: history.map { p in usesF ? (p.tempF ?? p.tempC.map(Formatting.cToF)) : (p.tempC ?? p.tempF.map(Formatting.fToC)) },
                            muted: muted || stale)
                VitalColumn(spec: VitalSpec(title: "Humidity", symbol: "humidity.fill", unit: "%", decimals: 0,
                                            scaleMin: 20, scaleMax: 90, tolerance: 5),
                            value: sensor?.humidity, bandMin: targets?.humidityMin, bandMax: targets?.humidityMax,
                            series: history.map { $0.humidity },
                            muted: muted || stale)
                VitalColumn(spec: VitalSpec(title: "VPD", symbol: "wind", unit: "kPa", decimals: 2,
                                            scaleMin: 0, scaleMax: 2, tolerance: 0.2),
                            value: sensor?.vpdKpa, bandMin: targets?.vpdMin, bandMax: targets?.vpdMax,
                            series: history.map { $0.vpdKpa },
                            muted: muted || stale)
            }
        }
        .card(padding: 16)
    }

    private var tempValue: Double? {
        if usesF { return sensor?.tempF ?? sensor?.tempC.map(Formatting.cToF) }
        return sensor?.tempC ?? sensor?.tempF.map(Formatting.fToC)
    }
    private var tempMin: Double? {
        if usesF { return targets?.tempMinF ?? targets?.tempMinC.map(Formatting.cToF) }
        return targets?.tempMinC ?? targets?.tempMinF.map(Formatting.fToC)
    }
    private var tempMax: Double? {
        if usesF { return targets?.tempMaxF ?? targets?.tempMaxC.map(Formatting.cToF) }
        return targets?.tempMaxC ?? targets?.tempMaxF.map(Formatting.fToC)
    }
}

struct VitalColumn: View {
    let spec: VitalSpec
    let value: Double?
    let bandMin: Double?
    let bandMax: Double?
    let series: [Double?]
    let muted: Bool

    private var status: BandStatus {
        muted ? .unknown : BandStatus.of(value: value, min: bandMin, max: bandMax, tolerance: spec.tolerance)
    }

    var body: some View {
        VStack(spacing: 8) {
            Label(spec.title, systemImage: spec.symbol)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            VitalRing(value: value, unit: spec.unit, decimals: spec.decimals,
                      scaleMin: spec.scaleMin, scaleMax: spec.scaleMax,
                      bandMin: bandMin, bandMax: bandMax, color: status.color, muted: muted)
            Sparkline(values: series, bandMin: bandMin, bandMax: bandMax, color: status.color, muted: muted)
                .frame(height: 26)
            if let bandMin, let bandMax {
                Text("\(Formatting.number(bandMin, decimals: spec.decimals))–\(Formatting.number(bandMax, decimals: spec.decimals))")
                    .font(.caption2).foregroundStyle(.tertiary)
            } else {
                Text("no target").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity)
    }
}

struct VitalRing: View {
    let value: Double?
    let unit: String
    let decimals: Int
    let scaleMin: Double
    let scaleMax: Double
    let bandMin: Double?
    let bandMax: Double?
    let color: Color
    let muted: Bool

    private let size: CGFloat = 96
    private let trackWidth: CGFloat = 5
    private let bandWidth: CGFloat = 9
    private let sweep: Double = 0.75

    private func frac(_ v: Double) -> Double {
        guard scaleMax > scaleMin else { return 0 }
        return min(max((v - scaleMin) / (scaleMax - scaleMin), 0), 1)
    }

    var body: some View {
        ZStack {
            Circle()
                .trim(from: 0, to: sweep)
                .stroke(Color.track, style: StrokeStyle(lineWidth: trackWidth, lineCap: .round))
                .rotationEffect(.degrees(135))
                .padding(bandWidth / 2)
            if let bandMin, let bandMax, bandMax > bandMin {
                Circle()
                    .trim(from: frac(bandMin) * sweep, to: frac(bandMax) * sweep)
                    .stroke(Color.brand.opacity(muted ? 0.25 : 0.85), style: StrokeStyle(lineWidth: bandWidth, lineCap: .round))
                    .rotationEffect(.degrees(135))
                    .padding(bandWidth / 2)
            }
            if let value {
                let angle = (135 + 270 * frac(value)) * Double.pi / 180
                let r = (size - bandWidth) / 2
                Circle()
                    .fill(muted ? Color.secondary.opacity(0.5) : color)
                    .frame(width: 13, height: 13)
                    .overlay(Circle().stroke(Color.card, lineWidth: 2.5))
                    .shadow(color: muted ? .clear : color.opacity(0.4), radius: 3)
                    .offset(x: r * CGFloat(cos(angle)), y: r * CGFloat(sin(angle)))
            }
            VStack(spacing: 0) {
                Text(value.map { String(format: "%.\(decimals)f", $0) } ?? "—")
                    .font(.hero(24))
                    .contentTransition(.numericText())
                    .foregroundStyle(value == nil || muted ? Color.secondary : color)
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                Text(unit).font(.caption2.weight(.medium)).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 14)
        }
        .frame(width: size, height: size)
        .animation(.spring(duration: 0.5), value: value)
    }
}

struct Sparkline: View {
    let values: [Double?]
    let bandMin: Double?
    let bandMax: Double?
    let color: Color
    let muted: Bool

    var body: some View {
        Canvas { ctx, size in
            let present = values.compactMap { $0 }
            var lo = present.min() ?? bandMin ?? 0
            var hi = present.max() ?? bandMax ?? 1
            if let bandMin { lo = min(lo, bandMin) }
            if let bandMax { hi = max(hi, bandMax) }
            if hi - lo < 0.0001 { hi = lo + 1 }
            let pad = (hi - lo) * 0.12
            lo -= pad; hi += pad
            func y(_ v: Double) -> CGFloat { size.height - CGFloat((v - lo) / (hi - lo)) * size.height }

            if let bandMin, let bandMax, bandMax > bandMin {
                let rect = CGRect(x: 0, y: y(bandMax), width: size.width, height: max(1, y(bandMin) - y(bandMax)))
                ctx.fill(Path(roundedRect: rect, cornerRadius: 2), with: .color(Color.brand.opacity(muted ? 0.08 : 0.14)))
            }
            guard present.count >= 2 else {
                var base = Path()
                base.move(to: CGPoint(x: 0, y: size.height / 2))
                base.addLine(to: CGPoint(x: size.width, y: size.height / 2))
                ctx.stroke(base, with: .color(Color.secondary.opacity(0.25)), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                return
            }
            var path = Path()
            var started = false
            let n = values.count
            for (i, v) in values.enumerated() {
                guard let v else { started = false; continue }
                let x = n > 1 ? CGFloat(i) / CGFloat(n - 1) * size.width : 0
                let p = CGPoint(x: x, y: y(v))
                if started { path.addLine(to: p) } else { path.move(to: p); started = true }
            }
            ctx.stroke(path, with: .color(muted ? Color.secondary.opacity(0.45) : color),
                       style: StrokeStyle(lineWidth: 1.6, lineCap: .round, lineJoin: .round))
        }
    }
}

// MARK: - Assessment

struct AssessmentLine: View {
    let assessment: Assessment?
    let standby: Bool

    var body: some View {
        let level = standby ? AssessmentLevel.standby : (assessment?.levelValue ?? .warn)
        let tint: Color = {
            switch level {
            case .good: return .good
            case .warn: return .warn
            case .alert: return .alertRed
            case .standby: return .secondary
            }
        }()
        let headline = standby ? "Tent is off" : (assessment?.headline ?? "Waiting for the first reading")
        if level == .alert {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: LevelColor.symbol(for: level.rawValue)).font(.title3).foregroundStyle(tint)
                    Text(headline).font(.headline)
                    Spacer()
                }
                if let details = assessment?.details, !details.isEmpty {
                    BulletList(items: details, color: tint)
                        .font(.subheadline)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        } else {
            HStack(spacing: 10) {
                Image(systemName: LevelColor.symbol(for: level.rawValue)).foregroundStyle(tint)
                Text(headline).font(.subheadline.weight(.medium)).foregroundStyle(standby ? .secondary : .primary)
                Spacer()
            }
            .padding(.horizontal, 4)
        }
    }
}

// MARK: - Light bar

struct LightBar: View {
    let onTime: String?
    let hours: Double?
    let isOn: Bool
    let nextChange: Date?
    let schedule: String?
    let muted: Bool

    private var onStartMinutes: Int? {
        guard let onTime else { return nil }
        let parts = onTime.split(separator: ":").compactMap { Int($0) }
        guard parts.count >= 2 else { return nil }
        return parts[0] * 60 + parts[1]
    }

    /// Fractions of the day (0–1) that are lights-on; two segments if it wraps midnight.
    private var segments: [(Double, Double)] {
        guard let start = onStartMinutes, let h = hours, h > 0 else { return [] }
        let s = Double(start) / 1440
        let len = min(h / 24, 1)
        let e = s + len
        if e <= 1 { return [(s, e)] }
        return [(s, 1), (0, e - 1)]
    }

    private var nowFraction: Double {
        let c = Calendar.current.dateComponents([.hour, .minute], from: Date())
        return Double((c.hour ?? 0) * 60 + (c.minute ?? 0)) / 1440
    }

    private var lit: Bool { isOn && !muted }

    private var headline: String {
        if muted { return "Lights off" }
        return isOn ? "Lights on" : "Lights off"
    }

    private var detail: String {
        var parts: [String] = []
        if muted {
            parts.append("Standby")
        } else if let next = nextChange {
            parts.append((isOn ? "Off in " : "On in ") + Formatting.countdown(to: next))
        }
        if let schedule, !schedule.isEmpty { parts.append(schedule) }
        if let onTime, !onTime.isEmpty { parts.append("on at \(onTime)") }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: lit ? "sun.max.fill" : "moon.fill")
                    .font(.title3)
                    .foregroundStyle(lit ? Color.sun : Color.night)
                    .symbolEffect(.pulse, options: .repeating, isActive: false)
                Text(headline).font(.headline)
                Spacer()
                Text(detail).font(.subheadline).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
            }
            GeometryReader { geo in
                let w = geo.size.width
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.night.opacity(muted ? 0.35 : 1))
                    ForEach(Array(segments.enumerated()), id: \.offset) { _, seg in
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(Color.sun.opacity(muted ? 0.35 : 1))
                            .frame(width: max(3, w * (seg.1 - seg.0)))
                            .offset(x: w * seg.0)
                    }
                    if let seg = segments.max(by: { ($0.1 - $0.0) < ($1.1 - $1.0) }), w * (seg.1 - seg.0) > 40 {
                        Image(systemName: "sun.max.fill")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Color.night.opacity(0.75))
                            .offset(x: w * (seg.0 + seg.1) / 2 - 5)
                    }
                    if let gap = largestNightGap, w * (gap.1 - gap.0) > 40 {
                        Image(systemName: "moon.fill")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(Color.sun.opacity(0.85))
                            .offset(x: w * (gap.0 + gap.1) / 2 - 5)
                    }
                    Capsule()
                        .fill(Color.primary)
                        .frame(width: 3, height: 22)
                        .overlay(Capsule().stroke(Color.card, lineWidth: 1))
                        .offset(x: w * nowFraction - 1.5)
                }
            }
            .frame(height: 14)
            HStack(spacing: 0) {
                ForEach(Array(["12am", "6am", "12pm", "6pm", "12am"].enumerated()), id: \.offset) { i, t in
                    if i > 0 { Spacer(minLength: 0) }
                    Text(t).font(.system(size: 9, weight: .medium)).foregroundStyle(.tertiary)
                }
            }
        }
        .card(padding: 16)
        .opacity(muted ? 0.75 : 1)
    }

    private var largestNightGap: (Double, Double)? {
        let segs = segments.sorted { $0.0 < $1.0 }
        var gaps: [(Double, Double)] = []
        var cursor = 0.0
        for s in segs {
            if s.0 > cursor { gaps.append((cursor, s.0)) }
            cursor = max(cursor, s.1)
        }
        if cursor < 1 { gaps.append((cursor, 1)) }
        return gaps.max { ($0.1 - $0.0) < ($1.1 - $1.0) }
    }
}

// MARK: - Devices

enum DeviceSymbol {
    static func symbol(for role: String) -> String {
        switch role {
        case "light": return "lightbulb.max.fill"
        case "exhaust_fan": return "fan.fill"
        case "intake_fan": return "wind"
        case "circulation_fan", "circulation_fan_2": return "fanblades.fill"
        case "humidifier": return "humidity.fill"
        case "dehumidifier": return "dehumidifier.fill"
        case "heater": return "flame.fill"
        case "cooler": return "snowflake"
        default: return "powerplug.fill"
        }
    }
}

struct DevicesGrid: View {
    let devices: [DeviceStatus]
    let muted: Bool
    let onSelect: (DeviceStatus) -> Void

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Devices").font(.headline)
                Spacer()
                if muted { Text("All off").font(.caption.weight(.semibold)).foregroundStyle(.secondary) }
            }
            if devices.isEmpty {
                Text("No devices set up yet. Open Settings to map your tent equipment.")
                    .font(.subheadline).foregroundStyle(.secondary)
                    .card()
            } else {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(devices) { d in
                        DeviceChip(device: d, muted: muted) { onSelect(d) }
                    }
                }
            }
        }
    }
}

struct DeviceChip: View {
    let device: DeviceStatus
    let muted: Bool
    let action: () -> Void

    private var isMapped: Bool { device.entityId != nil }
    private var isOn: Bool { device.isOn && !muted }

    private var dotColor: Color {
        if !isMapped { return Color.secondary.opacity(0.3) }
        if device.available == false { return .alertRed }
        return isOn ? .leaf : Color.secondary.opacity(0.35)
    }

    private var reasonLine: String {
        if !isMapped { return "Not set up" }
        if device.available == false { return "Unavailable" }
        if muted { return "Standby" }
        if let m = device.mode, m != "auto" {
            return "Manual · \(m == "on" ? "on" : "off")" + (device.reason.map { $0.isEmpty ? "" : " · \($0)" } ?? "")
        }
        if let r = device.reason, !r.isEmpty { return r }
        return device.isOn ? "On · automatic" : "Off · automatic"
    }

    var body: some View {
        Button(action: action) {
            HStack(alignment: .center, spacing: 10) {
                ZStack(alignment: .topTrailing) {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(isOn ? Color.brand.opacity(0.15) : Color.secondary.opacity(0.10))
                    Image(systemName: DeviceSymbol.symbol(for: device.role))
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(isOn ? Color.brand : Color.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    Circle()
                        .fill(dotColor)
                        .frame(width: 9, height: 9)
                        .overlay(Circle().stroke(Color.card, lineWidth: 2))
                        .offset(x: 3, y: -3)
                }
                .frame(width: 42, height: 42)
                VStack(alignment: .leading, spacing: 3) {
                    Text(device.displayLabel)
                        .font(.footnote.weight(.semibold))
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(reasonLine)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .frame(minHeight: 46)
            .chipSurface()
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .opacity(muted || !isMapped ? 0.6 : 1)
        .animation(.spring(duration: 0.35), value: isOn)
    }
}

struct DeviceSelection: Identifiable {
    let role: String
    var id: String { role }
}

struct DeviceSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    let role: String

    @State private var pendingMode: String?
    @State private var askDuration = false
    @State private var busy = false
    @State private var alert: AlertMessage?

    private var device: DeviceStatus? { app.status?.devices?.first { $0.role == role } }
    private var standby: Bool { app.isStandby }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let d = device {
                HStack(spacing: 14) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(d.isOn && !standby ? Color.brand.opacity(0.15) : Color.secondary.opacity(0.10))
                        Image(systemName: DeviceSymbol.symbol(for: d.role))
                            .font(.system(size: 24, weight: .semibold))
                            .foregroundStyle(d.isOn && !standby ? Color.brand : Color.secondary)
                    }
                    .frame(width: 56, height: 56)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(d.displayLabel).font(.title3.weight(.semibold))
                        HStack(spacing: 8) {
                            LevelChip(text: stateText(d), color: stateColor(d))
                            if let m = d.mode, m != "auto" {
                                LevelChip(text: "Manual", color: .warn)
                            }
                        }
                    }
                    Spacer()
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Why").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text(standby ? "The tent is in standby, so everything stays off." : ((d.reason?.isEmpty == false) ? d.reason! : "No reason reported."))
                        .font(.body)
                        .fixedSize(horizontal: false, vertical: true)
                    if let until = Formatting.parseISO(d.overrideUntil) {
                        Label("Manual until \(until.formatted(date: .omitted, time: .shortened))", systemImage: "clock")
                            .font(.footnote).foregroundStyle(Color.warn)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Mode").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Picker("Mode", selection: Binding(
                        get: { d.mode ?? "auto" },
                        set: { newValue in
                            guard newValue != (d.mode ?? "auto") else { return }
                            if newValue == "auto" {
                                apply(mode: "auto", minutes: nil)
                            } else {
                                pendingMode = newValue
                                askDuration = true
                            }
                        })) {
                        Text("Auto").tag("auto")
                        Text("On").tag("on")
                        Text("Off").tag("off")
                    }
                    .pickerStyle(.segmented)
                    .disabled(busy || d.entityId == nil)
                    Text("Auto lets the grow brain decide. On or Off holds it there for a while.")
                        .font(.caption).foregroundStyle(.tertiary)
                }
                if busy {
                    HStack { ProgressView(); Text("Updating…").font(.footnote).foregroundStyle(.secondary) }
                }
            } else {
                Text("Device not found").foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.bg.ignoresSafeArea())
        .confirmationDialog("For how long?", isPresented: $askDuration, titleVisibility: .visible) {
            Button("1 hour") { apply(mode: pendingMode ?? "on", minutes: 60) }
            Button("4 hours") { apply(mode: pendingMode ?? "on", minutes: 240) }
            Button("Until I change it") { apply(mode: pendingMode ?? "on", minutes: nil) }
            Button("Cancel", role: .cancel) { pendingMode = nil }
        }
        .errorAlert($alert)
    }

    private func stateText(_ d: DeviceStatus) -> String {
        if d.entityId == nil { return "Not set up" }
        if d.available == false { return "Unavailable" }
        if standby { return "Off · standby" }
        switch d.state {
        case "on": return "On"
        case "off": return "Off"
        default: return "Unknown"
        }
    }

    private func stateColor(_ d: DeviceStatus) -> Color {
        if d.entityId == nil { return .secondary }
        if d.available == false { return .alertRed }
        if standby { return .secondary }
        return d.isOn ? .good : .secondary
    }

    private func apply(mode: String, minutes: Int?) {
        Task {
            busy = true
            defer { busy = false; pendingMode = nil }
            do { try await app.setOverride(role: role, mode: mode, minutes: minutes) }
            catch { alert = AlertMessage(title: "Couldn't change the device", message: error.localizedDescription) }
        }
    }
}

// MARK: - Needs you

struct NeedsYouRow: View {
    let tasks: Int
    let photos: Int
    let unreadBrief: Bool
    let onTap: (AppTab) -> Void

    var body: some View {
        if tasks > 0 || photos > 0 || unreadBrief {
            VStack(alignment: .leading, spacing: 10) {
                Text("Needs you").font(.headline)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        if unreadBrief {
                            Button { onTap(.advisor) } label: { PillChip(text: "New brief", symbol: "sparkles", tint: .night, filled: true) }
                        }
                        if photos > 0 {
                            Button { onTap(.photos) } label: { PillChip(text: photos == 1 ? "1 photo request" : "\(photos) photo requests", symbol: "camera.fill", tint: .brand) }
                        }
                        if tasks > 0 {
                            Button { onTap(.tasks) } label: { PillChip(text: tasks == 1 ? "1 task" : "\(tasks) tasks", symbol: "checklist", tint: .brand) }
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }
}
