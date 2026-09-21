package com.growop.app.ui.home

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.EventBusy
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.Formatting
import com.growop.app.data.GrowPlan
import com.growop.app.data.PlanPhase
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BulletList
import com.growop.app.ui.shared.EmptyStateView
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.shared.WorkingView
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch

// MARK: - Compact card on Home

@Composable
fun GrowPlanCard(plan: GrowPlan?, growStartDate: String?, onClick: () -> Unit) {
    val c = GrowTheme.colors
    val missingStartDate = (plan?.startDate ?: growStartDate) == null
    GrowCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Map, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Grow plan", style = MaterialTheme.typography.titleSmall, color = c.textSecondary)
            Spacer(Modifier.weight(1f))
            Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = c.textTertiary)
        }
        Spacer(Modifier.height(10.dp))
        if (plan != null) {
            val cur = plan.current
            when {
                cur != null -> {
                    Text(cur.displayTitle, style = MaterialTheme.typography.titleLarge, color = c.text)
                    if (!cur.subtitle.isNullOrEmpty()) Text(cur.subtitle, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                }
                plan.allDone -> Text("All phases complete", style = MaterialTheme.typography.titleLarge, color = c.text)
                else -> Text("Plan ready", style = MaterialTheme.typography.titleLarge, color = c.text)
            }
            if (plan.orderedPhases.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                PhaseProgressStrip(plan.orderedPhases)
            }
            Spacer(Modifier.height(10.dp))
            if (missingStartDate) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.EventBusy, contentDescription = null, tint = c.warn, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Set your plant's start date in Settings → Plants", style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium), color = c.warn)
                }
            } else plan.next?.let { next ->
                val date = Formatting.monthDay(next.startDate)
                Text(if (date != null) "Next: ${next.displayTitle} · $date" else "Next: ${next.displayTitle}", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            }
        } else {
            Text("Plan not loaded yet", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
        }
    }
}

/** Thin segmented strip: done = brand, current = leaf with a dot, upcoming = track. */
@Composable
fun PhaseProgressStrip(phases: List<PlanPhase>) {
    val c = GrowTheme.colors
    Row(Modifier.fillMaxWidth().height(14.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        phases.forEach { p ->
            val color = when { p.isDone -> c.brand; p.isCurrent -> c.leaf; else -> c.track }
            Box(Modifier.weight(1f).fillMaxSize(), contentAlignment = Alignment.Center) {
                Box(Modifier.fillMaxWidth().height(6.dp).background(color, CircleShape))
                if (p.isCurrent) {
                    Box(Modifier.size(12.dp).background(c.card, CircleShape).padding(2.dp).background(c.brand, CircleShape))
                }
            }
        }
    }
}

// MARK: - Full timeline

@Composable
fun PlanScreen(app: AppState, onBack: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val plan = ui.plan
    var expanded by remember { mutableStateOf<Set<String>>(emptySet()) }
    var seeded by remember { mutableStateOf(false) }
    var loading by remember { mutableStateOf(false) }
    var refreshing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        if (app.value.plan == null) { loading = true; app.loadPlan(); loading = false }
    }
    LaunchedEffect(plan?.currentPhase, plan?.current?.key) {
        if (!seeded) plan?.current?.let { expanded = setOf(it.key); seeded = true }
    }

    Scaffold(
        containerColor = c.bg,
        topBar = {
            TopAppBar(
                title = { Text("Grow plan", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        PullToRefreshBox(
            isRefreshing = refreshing,
            onRefresh = { scope.launch { refreshing = true; app.loadPlan(); refreshing = false } },
            modifier = Modifier.fillMaxSize().padding(inner),
        ) {
            LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (plan != null) {
                    item { PlanHeader(plan) }
                    val phases = plan.orderedPhases
                    if (phases.isEmpty()) {
                        item { EmptyStateView(Icons.Filled.Map, "No plan yet", "The grow brain hasn't produced a plan for this grow.") }
                    }
                    itemsIndexed(phases, key = { _, p -> p.key }) { idx, phase ->
                        PlanPhaseRow(phase, isLast = idx == phases.size - 1, isExpanded = expanded.contains(phase.key)) {
                            expanded = if (expanded.contains(phase.key)) expanded - phase.key else expanded + phase.key
                        }
                    }
                } else if (loading) {
                    item { WorkingView("Loading your plan…") }
                } else {
                    item { EmptyStateView(Icons.Filled.Map, "Plan not available", "Couldn't load the grow plan. Pull down to try again.") }
                }
            }
        }
    }
}

@Composable
private fun PlanHeader(plan: GrowPlan) {
    val c = GrowTheme.colors
    GrowCard {
        Row(verticalAlignment = Alignment.Bottom) {
            plan.dayTotal?.let { Text("Day $it", style = MaterialTheme.typography.displaySmall, color = c.text) }
            Spacer(Modifier.weight(1f))
            Formatting.parseDay(plan.startDate)?.let { start ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.CalendarToday, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Started ${Formatting.abbrevDate(start)}", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        if (plan.startDate == null) {
            Row(verticalAlignment = Alignment.Top) {
                Icon(Icons.Filled.EventBusy, contentDescription = null, tint = c.warn, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Set your plant's start date in Settings → Plants to see dates on this plan.", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium), color = c.warn)
            }
            Spacer(Modifier.height(8.dp))
        }
        val cur = plan.current
        if (cur != null) {
            Text("You're in ${cur.displayTitle}.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
        } else if (plan.allDone) {
            Text("This grow is finished. Nice work.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
        }
        Spacer(Modifier.height(10.dp))
        PhaseProgressStrip(plan.orderedPhases)
    }
}

@Composable
fun PlanPhaseRow(phase: PlanPhase, isLast: Boolean, isExpanded: Boolean, onTap: () -> Unit) {
    val c = GrowTheme.colors
    val lineColor = if (phase.isDone) c.brand else c.track
    val chipText = when { phase.isDone -> "Done"; phase.isCurrent -> "Now"; else -> "Upcoming" }
    val chipColor = when { phase.isDone -> c.brand; phase.isCurrent -> c.brand; else -> c.textSecondary }
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Column(Modifier.width(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.size(28.dp), contentAlignment = Alignment.Center) {
                when {
                    phase.isDone -> Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = c.brand, modifier = Modifier.size(26.dp))
                    phase.isCurrent -> Box(Modifier.size(26.dp).background(c.leaf.copy(alpha = 0.35f), CircleShape).padding(6.dp).background(c.leaf, CircleShape))
                    else -> Box(Modifier.size(24.dp).border(2.dp, c.track, CircleShape))
                }
            }
            if (!isLast) Box(Modifier.width(2.dp).height(40.dp).background(lineColor))
        }
        Spacer(Modifier.width(12.dp))
        GrowCard(onClick = onTap, modifier = Modifier.weight(1f).animateContentSize()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(phase.displayTitle, style = MaterialTheme.typography.titleMedium, color = if (phase.isUpcoming) c.textSecondary else c.text, modifier = Modifier.weight(1f))
                LevelChip(chipText, chipColor)
                Spacer(Modifier.width(6.dp))
                Icon(Icons.Filled.ExpandMore, contentDescription = null, tint = c.textTertiary, modifier = Modifier.size(20.dp).rotate(if (isExpanded) 180f else 0f))
            }
            if (!phase.subtitle.isNullOrEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(phase.subtitle, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
            }
            val range = Formatting.phaseRange(phase)
            if (range.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.CalendarToday, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(range, style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                }
            }
            if (isExpanded) {
                val what = phase.what
                if (!what.isNullOrEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text("What you do", style = MaterialTheme.typography.titleSmall, color = c.brand)
                    Spacer(Modifier.height(6.dp))
                    BulletList(what, color = c.brand, icon = Icons.Filled.CheckCircle)
                }
                val watch = phase.watchFor
                if (!watch.isNullOrEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text("Watch for", style = MaterialTheme.typography.titleSmall, color = c.warn)
                    Spacer(Modifier.height(6.dp))
                    BulletList(watch, color = c.warn, icon = Icons.Filled.Visibility)
                }
                val env = phase.environment
                if (!env.isNullOrEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Row(
                        Modifier.clip(CircleShape).background(c.brand.copy(alpha = 0.12f)).padding(horizontal = 10.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Icons.Filled.Thermostat, contentDescription = null, tint = c.brand, modifier = Modifier.size(14.dp))
                        Spacer(Modifier.width(6.dp))
                        Text(env, style = MaterialTheme.typography.labelMedium, color = c.brand)
                    }
                }
            }
        }
    }
}
