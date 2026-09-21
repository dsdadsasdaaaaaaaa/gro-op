package com.growop.app.ui.home

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AcUnit
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.NightsStay
import androidx.compose.material.icons.filled.Opacity
import androidx.compose.material.icons.filled.Power
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.SensorsOff
import androidx.compose.material.icons.filled.Thermostat
import androidx.compose.material.icons.filled.Cyclone
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material.icons.filled.Whatshot
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Assessment
import com.growop.app.data.AssessmentLevel
import com.growop.app.data.DeviceStatus
import com.growop.app.data.Formatting
import com.growop.app.data.HistoryPoint
import com.growop.app.data.SensorReading
import com.growop.app.data.Targets
import com.growop.app.state.AppState
import com.growop.app.state.AppTab
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.BulletList
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.shared.LevelColor
import com.growop.app.ui.shared.PillChip
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalTime
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

// MARK: - Header

@Composable
fun HomeHeader(day: Int?, subtitle: String, standby: Boolean) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (standby) {
            Text("Tent is off", style = MaterialTheme.typography.displayMedium, color = c.textSecondary)
        } else {
            Text(day?.let { "Day $it" } ?: "Your grow", style = MaterialTheme.typography.displayLarge, color = c.text)
        }
        if (subtitle.isNotEmpty()) {
            Text(subtitle, style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Medium), color = c.textSecondary)
        }
        Text(Formatting.todayLong(), style = MaterialTheme.typography.bodySmall, color = c.textTertiary)
    }
}

// MARK: - Tent power

@Composable
fun TentPowerPill(running: Boolean, busy: Boolean, onClick: () -> Unit) {
    val c = GrowTheme.colors
    val bg by animateColorAsState(if (running) c.brand.copy(alpha = 0.12f) else c.textSecondary.copy(alpha = 0.10f), label = "pillBg")
    Row(
        Modifier.fillMaxWidth().clip(CircleShape).background(bg)
            .border(1.dp, if (running) c.brand.copy(alpha = 0.30f) else Color.Transparent, CircleShape)
            .clickable(enabled = !busy, onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(24.dp), contentAlignment = Alignment.Center) {
            if (running) Box(Modifier.size(22.dp).background(c.leaf.copy(alpha = 0.30f), CircleShape))
            Box(Modifier.size(11.dp).background(if (running) c.leaf else c.textSecondary.copy(alpha = 0.35f), CircleShape))
        }
        Spacer(Modifier.width(12.dp))
        Text(if (running) "Tent running" else "Standby", style = MaterialTheme.typography.titleMedium, color = if (running) c.brand else c.textSecondary)
        Spacer(Modifier.weight(1f))
        if (busy) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.brand)
        } else {
            Text(if (running) "Turn off" else "Start", style = MaterialTheme.typography.labelLarge, color = if (running) c.textSecondary else c.brand)
            Spacer(Modifier.width(6.dp))
            Icon(Icons.Filled.PowerSettingsNew, contentDescription = null, tint = if (running) c.textSecondary else c.brand, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
fun StandbyCard(busy: Boolean, onStart: () -> Unit) {
    val c = GrowTheme.colors
    GrowCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.NightsStay, contentDescription = null, tint = c.night, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(12.dp))
            Column {
                Text("Everything is switched off", style = MaterialTheme.typography.titleMedium, color = c.text)
                Text("Nothing runs until you start the tent.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
            }
        }
        Spacer(Modifier.height(14.dp))
        BigButton("Start tent", loading = busy, icon = Icons.Filled.PowerSettingsNew, onClick = onStart)
        Spacer(Modifier.height(10.dp))
        Text("Start it when the seedling goes in", style = MaterialTheme.typography.bodySmall, color = c.textSecondary,
            modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
    }
}

@Composable
fun StandbyConfirmSheet(onConfirm: () -> Unit, onDismiss: () -> Unit) {
    val c = GrowTheme.colors
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = c.bg) {
        Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Icon(Icons.Filled.PowerSettingsNew, contentDescription = null, tint = c.alert, modifier = Modifier.size(56.dp))
            Text("Turn the tent off?", style = MaterialTheme.typography.headlineMedium, color = c.text)
            Text("Every device switches off and stays off until you start it again.",
                style = MaterialTheme.typography.bodyLarge, color = c.textSecondary, textAlign = TextAlign.Center)
            Spacer(Modifier.height(4.dp))
            BigButton("Turn off", color = c.alert) { onConfirm(); onDismiss() }
            BigButton("Keep running", filled = false, onClick = onDismiss)
            Spacer(Modifier.height(16.dp))
        }
    }
}

// MARK: - Vitals

enum class BandStatus {
    GOOD, WARN, ALERT, UNKNOWN;

    companion object {
        fun of(value: Double?, min: Double?, max: Double?, tolerance: Double): BandStatus {
            if (value == null || min == null || max == null) return UNKNOWN
            if (value >= min && value <= max) return GOOD
            val dist = if (value < min) min - value else value - max
            return if (dist <= tolerance) WARN else ALERT
        }
    }
}

@Composable
fun BandStatus.color(): Color = when (this) {
    BandStatus.GOOD -> GrowTheme.colors.good
    BandStatus.WARN -> GrowTheme.colors.warn
    BandStatus.ALERT -> GrowTheme.colors.alert
    BandStatus.UNKNOWN -> GrowTheme.colors.textSecondary
}

data class VitalSpec(
    val title: String,
    val icon: ImageVector,
    val unit: String,
    val decimals: Int,
    val scaleMin: Double,
    val scaleMax: Double,
    val tolerance: Double,
)

@Composable
fun VitalsCard(sensor: SensorReading?, targets: Targets?, usesF: Boolean, history: List<HistoryPoint>, muted: Boolean) {
    val c = GrowTheme.colors
    val stale = sensor?.stale == true
    val tempValue = if (usesF) sensor?.tempF ?: sensor?.tempC?.let(Formatting::cToF) else sensor?.tempC ?: sensor?.tempF?.let(Formatting::fToC)
    val tempMin = if (usesF) targets?.tempMinF ?: targets?.tempMinC?.let(Formatting::cToF) else targets?.tempMinC ?: targets?.tempMinF?.let(Formatting::fToC)
    val tempMax = if (usesF) targets?.tempMaxF ?: targets?.tempMaxC?.let(Formatting::cToF) else targets?.tempMaxC ?: targets?.tempMaxF?.let(Formatting::fToC)

    GrowCard(padding = 16.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Vitals", style = MaterialTheme.typography.titleMedium, color = c.text)
            Spacer(Modifier.weight(1f))
            if (stale) {
                Icon(Icons.Filled.SensorsOff, contentDescription = null, tint = c.warn, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(4.dp))
                Text("Sensor not reporting", style = MaterialTheme.typography.labelSmall, color = c.warn)
            } else if (!sensor?.updatedAt.isNullOrEmpty()) {
                Text(Formatting.relative(sensor?.updatedAt), style = MaterialTheme.typography.bodySmall, color = c.textTertiary)
            }
        }
        Spacer(Modifier.height(14.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.Top) {
            VitalColumn(
                VitalSpec("Temp", Icons.Filled.Thermostat, if (usesF) "°F" else "°C", 1, if (usesF) 50.0 else 10.0, if (usesF) 104.0 else 40.0, if (usesF) 2.7 else 1.5),
                tempValue, tempMin, tempMax,
                history.map { p -> if (usesF) p.tempF ?: p.tempC?.let(Formatting::cToF) else p.tempC ?: p.tempF?.let(Formatting::fToC) },
                muted || stale, Modifier.weight(1f),
            )
            VitalColumn(
                VitalSpec("Humidity", Icons.Filled.WaterDrop, "%", 0, 20.0, 90.0, 5.0),
                sensor?.humidity, targets?.humidityMin, targets?.humidityMax,
                history.map { it.humidity }, muted || stale, Modifier.weight(1f),
            )
            VitalColumn(
                VitalSpec("VPD", Icons.Filled.Air, "kPa", 2, 0.0, 2.0, 0.2),
                sensor?.vpdKpa, targets?.vpdMin, targets?.vpdMax,
                history.map { it.vpdKpa }, muted || stale, Modifier.weight(1f),
            )
        }
    }
}

@Composable
fun VitalColumn(spec: VitalSpec, value: Double?, bandMin: Double?, bandMax: Double?, series: List<Double?>, muted: Boolean, modifier: Modifier = Modifier) {
    val c = GrowTheme.colors
    val status = if (muted) BandStatus.UNKNOWN else BandStatus.of(value, bandMin, bandMax, spec.tolerance)
    val color = status.color()
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(spec.icon, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(4.dp))
            Text(spec.title, style = MaterialTheme.typography.labelMedium, color = c.textSecondary, maxLines = 1)
        }
        VitalRing(value, spec.unit, spec.decimals, spec.scaleMin, spec.scaleMax, bandMin, bandMax, color, muted)
        Sparkline(series, bandMin, bandMax, color, muted, Modifier.fillMaxWidth().height(26.dp))
        if (bandMin != null && bandMax != null) {
            Text("${Formatting.number(bandMin, spec.decimals)}–${Formatting.number(bandMax, spec.decimals)}", style = MaterialTheme.typography.labelSmall, color = c.textTertiary)
        } else {
            Text("no target", style = MaterialTheme.typography.labelSmall, color = c.textTertiary)
        }
    }
}

@Composable
fun VitalRing(
    value: Double?, unit: String, decimals: Int, scaleMin: Double, scaleMax: Double,
    bandMin: Double?, bandMax: Double?, color: Color, muted: Boolean,
) {
    val c = GrowTheme.colors
    val size = 96.dp
    val sweep = 270f
    val startAngle = 135f
    fun frac(v: Double): Float {
        if (scaleMax <= scaleMin) return 0f
        return ((v - scaleMin) / (scaleMax - scaleMin)).coerceIn(0.0, 1.0).toFloat()
    }
    val trackColor = c.track
    val bandColor = c.brand.copy(alpha = if (muted) 0.25f else 0.85f)
    val markerColor = if (muted) c.textSecondary.copy(alpha = 0.5f) else color
    val cardColor = c.card
    Box(
        Modifier.size(size).drawBehind {
            val trackW = 5.dp.toPx()
            val bandW = 9.dp.toPx()
            val inset = bandW / 2
            val arcSize = Size(this.size.width - bandW, this.size.height - bandW)
            drawArc(trackColor, startAngle, sweep, false, topLeft = Offset(inset, inset), size = arcSize, style = Stroke(trackW, cap = StrokeCap.Round))
            if (bandMin != null && bandMax != null && bandMax > bandMin) {
                val a = frac(bandMin) * sweep
                val b = frac(bandMax) * sweep
                drawArc(bandColor, startAngle + a, max(b - a, 1f), false, topLeft = Offset(inset, inset), size = arcSize, style = Stroke(bandW, cap = StrokeCap.Round))
            }
            if (value != null) {
                val angle = Math.toRadians((startAngle + sweep * frac(value)).toDouble())
                val r = (this.size.width - bandW) / 2
                val center = Offset(this.size.width / 2 + r * cos(angle).toFloat(), this.size.height / 2 + r * sin(angle).toFloat())
                drawCircle(cardColor, radius = 6.5.dp.toPx() + 2.5.dp.toPx(), center = center)
                drawCircle(markerColor, radius = 6.5.dp.toPx(), center = center)
            }
        },
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(horizontal = 14.dp)) {
            Text(
                value?.let { Formatting.fixed(it, decimals) } ?: "—",
                style = MaterialTheme.typography.headlineMedium.copy(fontSize = 24.sp, lineHeight = 26.sp),
                color = if (value == null || muted) c.textSecondary else color,
                maxLines = 1, softWrap = false, overflow = TextOverflow.Visible,
            )
            Text(unit, style = MaterialTheme.typography.labelSmall, color = c.textSecondary)
        }
    }
}

@Composable
fun Sparkline(values: List<Double?>, bandMin: Double?, bandMax: Double?, color: Color, muted: Boolean, modifier: Modifier = Modifier) {
    val c = GrowTheme.colors
    val bandFill = c.brand.copy(alpha = if (muted) 0.08f else 0.14f)
    val lineColor = if (muted) c.textSecondary.copy(alpha = 0.45f) else color
    val dashColor = c.textSecondary.copy(alpha = 0.25f)
    Canvas(modifier) {
        val present = values.filterNotNull()
        var lo = present.minOrNull() ?: bandMin ?: 0.0
        var hi = present.maxOrNull() ?: bandMax ?: 1.0
        if (bandMin != null) lo = min(lo, bandMin)
        if (bandMax != null) hi = max(hi, bandMax)
        if (hi - lo < 0.0001) hi = lo + 1
        val pad = (hi - lo) * 0.12
        lo -= pad; hi += pad
        val h = size.height
        val w = size.width
        fun y(v: Double): Float = (h - ((v - lo) / (hi - lo)) * h).toFloat()

        if (bandMin != null && bandMax != null && bandMax > bandMin) {
            val top = y(bandMax)
            val bottom = y(bandMin)
            drawRoundRect(bandFill, topLeft = Offset(0f, top), size = Size(w, max(1f, bottom - top)), cornerRadius = CornerRadius(2.dp.toPx()))
        }
        if (present.size < 2) {
            drawLine(dashColor, Offset(0f, h / 2), Offset(w, h / 2), strokeWidth = 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            return@Canvas
        }
        val path = Path()
        var started = false
        val n = values.size
        values.forEachIndexed { i, v ->
            if (v == null) { started = false; return@forEachIndexed }
            val x = if (n > 1) i.toFloat() / (n - 1) * w else 0f
            val p = Offset(x, y(v))
            if (started) path.lineTo(p.x, p.y) else { path.moveTo(p.x, p.y); started = true }
        }
        drawPath(path, lineColor, style = Stroke(width = 1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

// MARK: - Assessment

@Composable
fun AssessmentLine(assessment: Assessment?, standby: Boolean) {
    val c = GrowTheme.colors
    val level = if (standby) AssessmentLevel.STANDBY else (assessment?.levelValue ?: AssessmentLevel.WARN)
    val tint = when (level) {
        AssessmentLevel.GOOD -> c.good
        AssessmentLevel.WARN -> c.warn
        AssessmentLevel.ALERT -> c.alert
        AssessmentLevel.STANDBY -> c.textSecondary
    }
    val headline = if (standby) "Tent is off" else (assessment?.headline ?: "Waiting for the first reading")
    val icon = LevelColor.icon(level.name.lowercase())
    if (level == AssessmentLevel.ALERT) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(GrowTheme.radius)).background(tint.copy(alpha = 0.12f)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(10.dp))
                Text(headline, style = MaterialTheme.typography.titleMedium, color = c.text)
            }
            val details = assessment?.details
            if (!details.isNullOrEmpty()) BulletList(details, color = tint)
        }
    } else {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(10.dp))
            Text(headline, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium), color = if (standby) c.textSecondary else c.text)
        }
    }
}

// MARK: - Light bar

@Composable
fun LightBar(onTime: String?, hours: Double?, isOn: Boolean, nextChange: Instant?, schedule: String?, muted: Boolean) {
    val c = GrowTheme.colors
    val onStartMinutes: Int? = onTime?.split(":")?.mapNotNull { it.trim().toIntOrNull() }?.takeIf { it.size >= 2 }?.let { it[0] * 60 + it[1] }
    /** Fractions of the day (0–1) that are lights-on; two segments if it wraps midnight. */
    val segments: List<Pair<Float, Float>> = run {
        val start = onStartMinutes ?: return@run emptyList()
        val h = hours ?: return@run emptyList()
        if (h <= 0) return@run emptyList()
        val s = start / 1440f
        val len = min(h / 24.0, 1.0).toFloat()
        val e = s + len
        if (e <= 1f) listOf(s to e) else listOf(s to 1f, 0f to (e - 1f))
    }
    val now = LocalTime.now()
    val nowFraction = (now.hour * 60 + now.minute) / 1440f
    val lit = isOn && !muted
    val headline = if (muted) "Lights off" else if (isOn) "Lights on" else "Lights off"
    val detail = buildList {
        if (muted) add("Standby")
        else if (nextChange != null) add((if (isOn) "Off in " else "On in ") + Formatting.countdown(nextChange))
        if (!schedule.isNullOrEmpty()) add(schedule)
        if (!onTime.isNullOrEmpty()) add("on at $onTime")
    }.joinToString(" · ")

    val nightColor = c.night.copy(alpha = if (muted) 0.35f else 1f)
    val sunColor = c.sun.copy(alpha = if (muted) 0.35f else 1f)
    val markerColor = c.text
    val cardColor = c.card

    GrowCard(padding = 16.dp, modifier = Modifier.alpha(if (muted) 0.75f else 1f)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(if (lit) Icons.Filled.WbSunny else Icons.Filled.DarkMode, contentDescription = null, tint = if (lit) c.sun else c.night, modifier = Modifier.size(22.dp))
            Spacer(Modifier.width(10.dp))
            Text(headline, style = MaterialTheme.typography.titleMedium, color = c.text)
            Spacer(Modifier.weight(1f))
            Text(detail, style = MaterialTheme.typography.bodySmall, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(12.dp))
        Canvas(Modifier.fillMaxWidth().height(22.dp)) {
            val w = size.width
            val barH = 14.dp.toPx()
            val top = (size.height - barH) / 2
            drawRoundRect(nightColor, topLeft = Offset(0f, top), size = Size(w, barH), cornerRadius = CornerRadius(barH / 2))
            segments.forEach { (s, e) ->
                drawRoundRect(sunColor, topLeft = Offset(w * s, top), size = Size(max(3f, w * (e - s)), barH), cornerRadius = CornerRadius(6.dp.toPx()))
            }
            val mx = w * nowFraction
            drawRoundRect(cardColor, topLeft = Offset(mx - 2.5.dp.toPx(), 0f), size = Size(5.dp.toPx(), size.height), cornerRadius = CornerRadius(2.5.dp.toPx()))
            drawRoundRect(markerColor, topLeft = Offset(mx - 1.5.dp.toPx(), 0f), size = Size(3.dp.toPx(), size.height), cornerRadius = CornerRadius(1.5.dp.toPx()))
        }
        Spacer(Modifier.height(4.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            listOf("12am", "6am", "12pm", "6pm", "12am").forEach { t ->
                Text(t, style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp), color = c.textTertiary)
            }
        }
    }
}

// MARK: - Devices

object DeviceIcons {
    fun icon(role: String): ImageVector = when (role) {
        "light" -> Icons.Filled.Lightbulb
        "exhaust_fan" -> Icons.Filled.Cyclone
        "intake_fan" -> Icons.Filled.Air
        "circulation_fan", "circulation_fan_2" -> Icons.Filled.Cyclone
        "humidifier" -> Icons.Filled.WaterDrop
        "dehumidifier" -> Icons.Filled.Opacity
        "heater" -> Icons.Filled.Whatshot
        "cooler" -> Icons.Filled.AcUnit
        else -> Icons.Filled.Power
    }
}

@Composable
fun DevicesGrid(devices: List<DeviceStatus>, muted: Boolean, onSelect: (DeviceStatus) -> Unit) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Devices", style = MaterialTheme.typography.titleMedium, color = c.text)
            Spacer(Modifier.weight(1f))
            if (muted) Text("All off", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
        }
        if (devices.isEmpty()) {
            GrowCard { Text("No devices set up yet. Equipment is mapped on the grow brain (server) side.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary) }
        } else {
            devices.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { d -> DeviceChip(d, muted, Modifier.weight(1f)) { onSelect(d) } }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
fun DeviceChip(device: DeviceStatus, muted: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = GrowTheme.colors
    val isMapped = device.entityId != null
    val isOn = device.isOn && !muted
    val dotColor = when {
        !isMapped -> c.textSecondary.copy(alpha = 0.3f)
        device.available == false -> c.alert
        isOn -> c.leaf
        else -> c.textSecondary.copy(alpha = 0.35f)
    }
    val reasonLine = when {
        !isMapped -> "Not set up"
        device.available == false -> "Unavailable"
        muted -> "Standby"
        device.mode != null && device.mode != "auto" ->
            "Manual · ${if (device.mode == "on") "on" else "off"}" + (device.reason?.takeIf { it.isNotEmpty() }?.let { " · $it" } ?: "")
        !device.reason.isNullOrEmpty() -> device.reason
        else -> if (device.isOn) "On · automatic" else "Off · automatic"
    }
    GrowCard(modifier = modifier.alpha(if (muted || !isMapped) 0.6f else 1f), padding = 12.dp, radius = GrowTheme.chipRadius, onClick = onClick) {
        Row(Modifier.heightIn(min = 46.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(42.dp)) {
                Box(Modifier.size(42.dp).background(if (isOn) c.brand.copy(alpha = 0.15f) else c.textSecondary.copy(alpha = 0.10f), RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
                    Icon(DeviceIcons.icon(device.role), contentDescription = null, tint = if (isOn) c.brand else c.textSecondary, modifier = Modifier.size(22.dp))
                }
                Box(Modifier.align(Alignment.TopEnd).size(13.dp).background(c.card, CircleShape).padding(2.dp).background(dotColor, CircleShape))
            }
            Spacer(Modifier.width(10.dp))
            Column {
                Text(device.displayLabel, style = MaterialTheme.typography.labelLarge, color = c.text, maxLines = 2)
                Text(reasonLine, style = MaterialTheme.typography.bodySmall, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

@Composable
fun DeviceSheet(app: AppState, role: String, onDismiss: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val device = ui.status?.devices?.firstOrNull { it.role == role }
    val standby = ui.isStandby
    val scope = rememberCoroutineScope()
    var pendingMode by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    fun apply(mode: String, minutes: Int?) {
        scope.launch {
            busy = true
            try { app.setOverride(role, mode, minutes) } catch (e: Throwable) { error = ApiError.wrap(e).message } finally { busy = false; pendingMode = null }
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = state, containerColor = c.bg) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 24.dp).padding(bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            if (device == null) {
                Text("Device not found", color = c.textSecondary)
            } else {
                val d = device
                val on = d.isOn && !standby
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(56.dp).background(if (on) c.brand.copy(alpha = 0.15f) else c.textSecondary.copy(alpha = 0.10f), RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) {
                        Icon(DeviceIcons.icon(d.role), contentDescription = null, tint = if (on) c.brand else c.textSecondary, modifier = Modifier.size(28.dp))
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(d.displayLabel, style = MaterialTheme.typography.titleLarge, color = c.text)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            val stateText = when {
                                d.entityId == null -> "Not set up"
                                d.available == false -> "Unavailable"
                                standby -> "Off · standby"
                                d.state == "on" -> "On"
                                d.state == "off" -> "Off"
                                else -> "Unknown"
                            }
                            val stateColor = when {
                                d.entityId == null -> c.textSecondary
                                d.available == false -> c.alert
                                standby -> c.textSecondary
                                d.isOn -> c.good
                                else -> c.textSecondary
                            }
                            LevelChip(stateText, stateColor)
                            if (d.mode != null && d.mode != "auto") LevelChip("Manual", c.warn)
                        }
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Why", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
                    Text(if (standby) "The tent is in standby, so everything stays off." else (d.reason?.takeIf { it.isNotEmpty() } ?: "No reason reported."),
                        style = MaterialTheme.typography.bodyLarge, color = c.text)
                    Formatting.parseISO(d.overrideUntil)?.let { until ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Schedule, contentDescription = null, tint = c.warn, modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("Manual until ${Formatting.shortTime(until)}", style = MaterialTheme.typography.bodySmall, color = c.warn)
                        }
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Mode", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
                    val current = d.mode ?: "auto"
                    val options = listOf("auto" to "Auto", "on" to "On", "off" to "Off")
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        options.forEachIndexed { i, (key, label) ->
                            SegmentedButton(
                                selected = current == key,
                                enabled = !busy && d.entityId != null,
                                onClick = {
                                    if (key == current) return@SegmentedButton
                                    if (key == "auto") apply("auto", null) else pendingMode = key
                                },
                                shape = SegmentedButtonDefaults.itemShape(index = i, count = options.size),
                                colors = SegmentedButtonDefaults.colors(
                                    activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand,
                                    inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary,
                                    activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track,
                                ),
                                icon = {},
                            ) { Text(label, style = MaterialTheme.typography.labelLarge) }
                        }
                    }
                    Text("Auto lets the grow brain decide. On or Off holds it there for a while.", style = MaterialTheme.typography.bodySmall, color = c.textTertiary)
                }
                if (busy) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.brand)
                        Spacer(Modifier.width(8.dp))
                        Text("Updating…", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                    }
                }
            }
        }
    }

    pendingMode?.let { mode ->
        AlertDialog(
            onDismissRequest = { pendingMode = null },
            containerColor = c.card,
            title = { Text("For how long?") },
            text = {
                Column {
                    listOf("1 hour" to 60, "4 hours" to 240, "Until I change it" to null).forEach { (label, mins) ->
                        TextButton(onClick = { apply(mode, mins) }, modifier = Modifier.fillMaxWidth()) {
                            Text(label, color = c.brand, style = MaterialTheme.typography.titleMedium, modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { pendingMode = null }) { Text("Cancel", color = c.textSecondary) } },
        )
    }
    ErrorDialog(error, title = "Couldn't change the device") { error = null }
}

// MARK: - Needs you

@Composable
fun NeedsYouRow(tasks: Int, photos: Int, unreadBrief: Boolean, onTap: (AppTab) -> Unit) {
    val c = GrowTheme.colors
    if (tasks <= 0 && photos <= 0 && !unreadBrief) return
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Needs you", style = MaterialTheme.typography.titleMedium, color = c.text)
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (unreadBrief) PillChip("New brief", icon = Icons.Filled.AutoAwesome, tint = c.night, filled = true) { onTap(AppTab.ADVISOR) }
            if (photos > 0) PillChip(if (photos == 1) "1 photo request" else "$photos photo requests", icon = Icons.Filled.CameraAlt, tint = c.brand) { onTap(AppTab.PHOTOS) }
            if (tasks > 0) PillChip(if (tasks == 1) "1 task" else "$tasks tasks", icon = Icons.Filled.Checklist, tint = c.brand) { onTap(AppTab.TASKS) }
        }
    }
}
