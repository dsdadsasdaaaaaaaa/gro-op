import SwiftUI

// MARK: - Date helpers for the plan

extension Formatting {
    /// "Oct 10" style, or nil when the string isn't a date.
    static func monthDay(_ s: String?) -> String? {
        guard let d = parseDay(s) else { return nil }
        return d.formatted(.dateTime.month(.abbreviated).day())
    }

    /// "Sep 19 – Sep 22 · day 0–3" (whichever parts are available).
    static func phaseRange(_ p: PlanPhase) -> String {
        var parts: [String] = []
        if let a = monthDay(p.startDate) {
            if let b = monthDay(p.endDate) { parts.append("\(a) – \(b)") } else { parts.append("From \(a)") }
        }
        if let sd = p.startDay {
            if let ed = p.endDay { parts.append(parts.isEmpty ? "Day \(sd)–\(ed)" : "day \(sd)–\(ed)") }
            else { parts.append(parts.isEmpty ? "From day \(sd)" : "from day \(sd)") }
        }
        return parts.joined(separator: " · ")
    }
}

// MARK: - Compact card on Home

struct GrowPlanCard: View {
    let plan: GrowPlan?
    let growStartDate: String?

    private var missingStartDate: Bool { (plan?.startDate ?? growStartDate) == nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Grow plan", systemImage: "map.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(.tertiary)
            }

            if let plan {
                if let cur = plan.current {
                    Text(cur.displayTitle).font(.title3.weight(.semibold))
                    if let s = cur.subtitle, !s.isEmpty {
                        Text(s).font(.subheadline).foregroundStyle(.secondary)
                    }
                } else if plan.allDone {
                    Text("All phases complete").font(.title3.weight(.semibold))
                } else {
                    Text("Plan ready").font(.title3.weight(.semibold))
                }

                if !plan.orderedPhases.isEmpty {
                    PhaseProgressStrip(phases: plan.orderedPhases)
                }

                if missingStartDate {
                    Label("Set your start date in Settings → Grow", systemImage: "calendar.badge.exclamationmark")
                        .font(.footnote.weight(.medium)).foregroundStyle(Color.warn)
                } else if let next = plan.next {
                    if let date = Formatting.monthDay(next.startDate) {
                        Text("Next: \(next.displayTitle) · \(date)").font(.footnote).foregroundStyle(.secondary)
                    } else {
                        Text("Next: \(next.displayTitle)").font(.footnote).foregroundStyle(.secondary)
                    }
                }
            } else {
                Text("Plan not loaded yet").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .card()
        .contentShape(Rectangle())
    }
}

/// Thin segmented strip: done = Primary, current = Leaf with a dot, upcoming = track.
struct PhaseProgressStrip: View {
    let phases: [PlanPhase]

    private func color(_ p: PlanPhase) -> Color {
        if p.isDone { return .brand }
        if p.isCurrent { return .leaf }
        return .track
    }

    var body: some View {
        HStack(spacing: 3) {
            ForEach(phases) { p in
                ZStack {
                    Capsule().fill(color(p)).frame(height: 6)
                    if p.isCurrent {
                        Circle()
                            .fill(Color.brand)
                            .frame(width: 12, height: 12)
                            .overlay(Circle().stroke(Color.card, lineWidth: 2))
                    }
                }
                .frame(maxWidth: .infinity)
                .accessibilityLabel("\(p.displayTitle), \(p.status ?? "")")
            }
        }
        .frame(height: 14)
    }
}

// MARK: - Full timeline

struct PlanView: View {
    @Environment(AppState.self) private var app
    @State private var expanded: Set<String> = []
    @State private var seededExpansion = false
    @State private var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let plan = app.plan {
                    header(plan)
                    let phases = plan.orderedPhases
                    if phases.isEmpty {
                        EmptyStateView(symbol: "map", title: "No plan yet", message: "The grow brain hasn't produced a plan for this grow.")
                    }
                    VStack(spacing: 0) {
                        ForEach(Array(phases.enumerated()), id: \.element.key) { idx, phase in
                            PlanPhaseRow(phase: phase,
                                         isLast: idx == phases.count - 1,
                                         isExpanded: expanded.contains(phase.key)) {
                                withAnimation(.snappy) {
                                    if expanded.contains(phase.key) { expanded.remove(phase.key) } else { expanded.insert(phase.key) }
                                }
                            }
                        }
                    }
                } else if loading {
                    WorkingView(title: "Loading your plan…")
                } else {
                    EmptyStateView(symbol: "map", title: "Plan not available", message: "Couldn't load the grow plan. Pull down to try again.")
                }
            }
            .padding(Theme.spacing)
        }
        .background(Color.bg.ignoresSafeArea())
        .navigationTitle("Grow plan")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await app.loadPlan() }
        .task {
            if app.plan == nil {
                loading = true
                await app.loadPlan()
                loading = false
            }
            seedExpansion()
        }
        .onChange(of: app.plan?.currentPhase) { _, _ in seedExpansion() }
    }

    private func seedExpansion() {
        guard !seededExpansion, let cur = app.plan?.current else { return }
        expanded = [cur.key]
        seededExpansion = true
    }

    @ViewBuilder
    private func header(_ plan: GrowPlan) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                if let d = plan.dayTotal {
                    Text("Day \(d)").font(.hero(40))
                }
                Spacer()
                if let start = Formatting.parseDay(plan.startDate) {
                    Label("Started \(start.formatted(date: .abbreviated, time: .omitted))", systemImage: "calendar")
                        .font(.subheadline).foregroundStyle(.secondary)
                }
            }
            if plan.startDate == nil {
                Label("Set your start date in Settings → Grow to see dates on this plan.", systemImage: "calendar.badge.exclamationmark")
                    .font(.subheadline.weight(.medium)).foregroundStyle(Color.warn)
            }
            if let cur = plan.current {
                Text("You're in **\(cur.displayTitle)**.").font(.subheadline).foregroundStyle(.secondary)
            } else if plan.allDone {
                Text("This grow is finished. Nice work.").font(.subheadline).foregroundStyle(.secondary)
            }
            PhaseProgressStrip(phases: plan.orderedPhases)
        }
        .card()
    }
}

struct PlanPhaseRow: View {
    let phase: PlanPhase
    let isLast: Bool
    let isExpanded: Bool
    var onTap: () -> Void

    private var lineColor: Color { phase.isDone ? .brand : .track }

    private var chipText: String {
        if phase.isDone { return "Done" }
        if phase.isCurrent { return "Now" }
        return "Upcoming"
    }

    private var chipColor: Color {
        if phase.isDone { return .brand }
        if phase.isCurrent { return .leaf }
        return .secondary
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 0) {
                statusIcon.frame(width: 28, height: 28)
                if !isLast {
                    Rectangle().fill(lineColor).frame(width: 2).frame(maxHeight: .infinity).padding(.vertical, 2)
                }
            }
            .frame(width: 28)

            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(phase.displayTitle)
                        .font(.headline)
                        .foregroundStyle(phase.isUpcoming ? .secondary : .primary)
                    Spacer()
                    LevelChip(text: chipText, color: phase.isCurrent ? .brand : chipColor)
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(isExpanded ? 180 : 0))
                }
                if let s = phase.subtitle, !s.isEmpty {
                    Text(s).font(.subheadline).foregroundStyle(.secondary)
                }
                let range = Formatting.phaseRange(phase)
                if !range.isEmpty {
                    Label(range, systemImage: "calendar").font(.caption).foregroundStyle(.secondary)
                }

                if isExpanded {
                    if let what = phase.what, !what.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("What you do").font(.subheadline.weight(.semibold)).foregroundStyle(Color.brand)
                            BulletList(items: what, symbol: "checkmark.circle.fill", color: .brand)
                        }
                        .padding(.top, 4)
                    }
                    if let watch = phase.watchFor, !watch.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Watch for").font(.subheadline.weight(.semibold)).foregroundStyle(Color.warn)
                            BulletList(items: watch, symbol: "eye.fill", color: .warn)
                        }
                        .padding(.top, 4)
                    }
                    if let env = phase.environment, !env.isEmpty {
                        Label(env, systemImage: "thermometer.medium")
                            .font(.caption.weight(.medium))
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color.brand.opacity(0.12), in: Capsule())
                            .foregroundStyle(Color.brand)
                            .padding(.top, 2)
                    }
                }
            }
            .card()
            .contentShape(Rectangle())
            .onTapGesture(perform: onTap)
            .padding(.bottom, isLast ? 0 : 12)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityHint(isExpanded ? "Collapse" : "Expand")
    }

    @ViewBuilder
    private var statusIcon: some View {
        if phase.isDone {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 26)).foregroundStyle(Color.brand)
        } else if phase.isCurrent {
            Image(systemName: "circle.circle.fill").font(.system(size: 26)).foregroundStyle(Color.leaf)
                .symbolEffect(.pulse, options: .repeating)
        } else {
            Image(systemName: "circle").font(.system(size: 26)).foregroundStyle(Color.track)
        }
    }
}
