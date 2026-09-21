package com.growop.app.ui.shared

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.horizontalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.NightsStay
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.growop.app.data.PhotoRequest
import com.growop.app.data.TaskItem
import com.growop.app.ui.theme.GrowTheme

// MARK: - Card surface

/** The standard card: 20dp radius, generous padding, soft shadow in light mode only. */
@Composable
fun GrowCard(
    modifier: Modifier = Modifier,
    padding: Dp = 20.dp,
    radius: Dp = GrowTheme.radius,
    background: Color = GrowTheme.colors.card,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val c = GrowTheme.colors
    val shape = RoundedCornerShape(radius)
    var m = modifier.fillMaxWidth()
    if (!c.isDark) m = m.shadow(elevation = 6.dp, shape = shape, ambientColor = Color.Black.copy(alpha = 0.10f), spotColor = Color.Black.copy(alpha = 0.12f))
    m = m.clip(shape).background(background, shape)
    if (onClick != null) m = m.clickable(onClick = onClick)
    Column(modifier = m.padding(padding), content = content)
}

// MARK: - Level -> colour / icon

object LevelColor {
    /** Good / warn / alert (used for assessment, alerts, urgencies). */
    @Composable
    fun color(level: String?): Color {
        val c = GrowTheme.colors
        return when ((level ?: "").lowercase()) {
            "good", "ok" -> c.good
            "warn", "warning", "attention" -> c.warn
            "alert", "urgent", "error" -> c.alert
            else -> c.textSecondary
        }
    }

    /** Same, but "info" is neutral brand (findings / urgencies). */
    @Composable
    fun infoColor(level: String?): Color {
        val c = GrowTheme.colors
        return when ((level ?: "").lowercase()) {
            "info" -> c.brand
            "warn", "warning", "attention" -> c.warn
            "alert", "urgent", "error" -> c.alert
            else -> c.textSecondary
        }
    }

    fun icon(level: String?): ImageVector = when ((level ?: "").lowercase()) {
        "good", "ok" -> Icons.Filled.CheckCircle
        "warn", "warning", "attention" -> Icons.Filled.Warning
        "alert", "urgent", "error" -> Icons.Filled.Error
        "standby" -> Icons.Filled.NightsStay
        else -> Icons.Filled.Info
    }
}

// MARK: - Buttons

@Composable
fun BigButton(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = GrowTheme.colors.brand,
    filled: Boolean = true,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp),
        shape = RoundedCornerShape(16.dp),
        colors = if (filled) ButtonDefaults.buttonColors(containerColor = color, contentColor = Color.White,
            disabledContainerColor = color.copy(alpha = 0.45f), disabledContentColor = Color.White.copy(alpha = 0.8f))
        else ButtonDefaults.buttonColors(containerColor = color.copy(alpha = 0.12f), contentColor = color,
            disabledContainerColor = color.copy(alpha = 0.07f), disabledContentColor = color.copy(alpha = 0.5f)),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp),
    ) {
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp, color = if (filled) Color.White else color)
            Spacer(Modifier.width(10.dp))
        } else if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = MaterialTheme.typography.titleMedium)
    }
}

/** Pill chip used for badges, filters and small actions. */
@Composable
fun PillChip(
    text: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    tint: Color = GrowTheme.colors.brand,
    filled: Boolean = false,
    onClick: (() -> Unit)? = null,
) {
    var m = modifier.clip(CircleShape).background(if (filled) tint else tint.copy(alpha = 0.14f))
    if (onClick != null) m = m.clickable(onClick = onClick)
    Row(m.padding(horizontal = 14.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        if (icon != null) {
            Icon(icon, contentDescription = null, tint = if (filled) Color.White else tint, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
        }
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (filled) Color.White else tint)
    }
}

/** Tiny capsule label (status chips). */
@Composable
fun LevelChip(text: String, color: Color, modifier: Modifier = Modifier) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold),
        color = color,
        modifier = modifier.clip(CircleShape).background(color.copy(alpha = 0.16f)).padding(horizontal = 8.dp, vertical = 4.dp),
    )
}

/** A one-line notice with an icon on a tinted background. */
@Composable
fun InlineNotice(icon: ImageVector, text: String, tint: Color, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(tint.copy(alpha = 0.12f)).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.Top,
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium), color = GrowTheme.colors.text)
    }
}

// MARK: - Section title

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, color = GrowTheme.colors.text, modifier = modifier.fillMaxWidth())
}

// MARK: - Lists

@Composable
fun BulletList(items: List<String>, color: Color = GrowTheme.colors.brand, icon: ImageVector? = null, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items.forEach { item ->
            Row(verticalAlignment = Alignment.Top) {
                if (icon != null) {
                    Icon(icon, contentDescription = null, tint = color, modifier = Modifier.padding(top = 2.dp).size(18.dp))
                } else {
                    Box(Modifier.padding(top = 8.dp).size(7.dp).background(color, CircleShape))
                }
                Spacer(Modifier.width(10.dp))
                Text(item, style = MaterialTheme.typography.bodyLarge, color = GrowTheme.colors.text)
            }
        }
    }
}

/** Numbered steps with circles. */
@Composable
fun NumberedList(items: List<String>, color: Color = GrowTheme.colors.brand, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items.forEachIndexed { idx, item ->
            Row(verticalAlignment = Alignment.Top) {
                Box(
                    Modifier.size(26.dp).border(1.5.dp, color, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("${idx + 1}", style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = color)
                }
                Spacer(Modifier.width(12.dp))
                Text(item, style = MaterialTheme.typography.bodyLarge, color = GrowTheme.colors.text, modifier = Modifier.padding(top = 2.dp))
            }
        }
    }
}

// MARK: - Created items (tasks / photo requests returned with advice)

@Composable
fun CreatedItemsView(tasks: List<TaskItem>?, photoRequests: List<PhotoRequest>?) {
    val t = tasks ?: emptyList()
    val r = photoRequests ?: emptyList()
    if (t.isEmpty() && r.isEmpty()) return
    val c = GrowTheme.colors
    GrowCard {
        Text("Added for you", style = MaterialTheme.typography.titleSmall, color = c.textSecondary)
        Spacer(Modifier.height(10.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            t.forEach { task -> PillChip(task.title ?: "Task", icon = Icons.Filled.Checklist, tint = c.brand) }
            r.forEach { req -> PillChip(req.title ?: "Photo", icon = Icons.Filled.CameraAlt, tint = c.night) }
        }
        if (r.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text("Photo requests are waiting in the Photos tab.", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
        }
    }
}

// MARK: - Loading / empty

@Composable
fun WorkingView(title: String, subtitle: String? = null, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        CircularProgressIndicator(color = GrowTheme.colors.brand, modifier = Modifier.size(40.dp), strokeWidth = 4.dp)
        Text(title, style = MaterialTheme.typography.titleMedium, color = GrowTheme.colors.text, textAlign = TextAlign.Center)
        if (subtitle != null) {
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = GrowTheme.colors.textSecondary, textAlign = TextAlign.Center)
        }
    }
}

@Composable
fun EmptyStateView(icon: ImageVector, title: String, message: String, modifier: Modifier = Modifier) {
    val c = GrowTheme.colors
    Column(modifier.fillMaxWidth().padding(vertical = 30.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(84.dp).background(c.brand.copy(alpha = 0.10f), CircleShape), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = c.brand, modifier = Modifier.size(38.dp))
        }
        Text(title, style = MaterialTheme.typography.titleLarge, color = c.text, textAlign = TextAlign.Center)
        Text(message, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary, textAlign = TextAlign.Center)
    }
}

@Composable
fun FullScreenLoading(text: String = "Loading…") {
    Box(Modifier.fillMaxSize().background(GrowTheme.colors.bg), contentAlignment = Alignment.Center) {
        WorkingView(text)
    }
}

// MARK: - Dialogs

/** Simple OK alert for error messages. */
@Composable
fun ErrorDialog(message: String?, title: String = "Something went wrong", onDismiss: () -> Unit) {
    if (message == null) return
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = { TextButton(onClick = onDismiss) { Text("OK") } },
        containerColor = GrowTheme.colors.card,
    )
}

/** Yes/no confirmation. */
@Composable
fun ConfirmDialog(
    title: String,
    message: String?,
    confirmText: String,
    destructive: Boolean = false,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { if (message != null) Text(message) },
        confirmButton = {
            TextButton(onClick = { onDismiss(); onConfirm() }) {
                Text(confirmText, color = if (destructive) GrowTheme.colors.alert else GrowTheme.colors.brand, fontWeight = FontWeight.SemiBold)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = GrowTheme.colors.textSecondary) } },
        containerColor = GrowTheme.colors.card,
    )
}

/** Mutable holder for an alert shown to the user. */
class AlertMessage(val title: String = "Something went wrong", val message: String)
