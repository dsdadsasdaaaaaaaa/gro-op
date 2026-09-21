package com.growop.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Same palette as the iOS Theme.swift / asset catalog. */
data class GrowPalette(
    val bg: Color,
    val card: Color,
    val brand: Color,
    val leaf: Color,
    val good: Color,
    val warn: Color,
    val alert: Color,
    val sun: Color,
    val night: Color,
    val text: Color,
    val textSecondary: Color,
    val textTertiary: Color,
    val track: Color,
    val isDark: Boolean,
)

val LightPalette = GrowPalette(
    bg = Color(0xFFF6F5F0),
    card = Color(0xFFFFFFFF),
    brand = Color(0xFF1F6F3F),
    leaf = Color(0xFF7ED957),
    good = Color(0xFF2E8B57),
    warn = Color(0xFFD9962B),
    alert = Color(0xFFD9534F),
    sun = Color(0xFFF5C451),
    night = Color(0xFF1F2A44),
    text = Color(0xFF17201A),
    textSecondary = Color(0xFF17201A).copy(alpha = 0.62f),
    textTertiary = Color(0xFF17201A).copy(alpha = 0.40f),
    track = Color(0xFF000000).copy(alpha = 0.08f),
    isDark = false,
)

val DarkPalette = GrowPalette(
    bg = Color(0xFF111412),
    card = Color(0xFF1B1F1C),
    brand = Color(0xFF3BA55D),
    leaf = Color(0xFF7ED957),
    good = Color(0xFF4CC27A),
    warn = Color(0xFFF0B04A),
    alert = Color(0xFFF07470),
    sun = Color(0xFFF5C451),
    night = Color(0xFF2C3B5E),
    text = Color(0xFFF2F4F1),
    textSecondary = Color(0xFFF2F4F1).copy(alpha = 0.64f),
    textTertiary = Color(0xFFF2F4F1).copy(alpha = 0.42f),
    track = Color(0xFFFFFFFF).copy(alpha = 0.10f),
    isDark = true,
)

val LocalGrowPalette = staticCompositionLocalOf { LightPalette }

object GrowTheme {
    val colors: GrowPalette
        @Composable get() = LocalGrowPalette.current

    val radius = 20.dp
    val chipRadius = 16.dp
    val spacing = 16.dp
    val sectionSpacing = 24.dp
}

val GrowShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

val GrowTypography = Typography(
    displayLarge = TextStyle(fontSize = 64.sp, fontWeight = FontWeight.Bold, lineHeight = 68.sp),
    displayMedium = TextStyle(fontSize = 44.sp, fontWeight = FontWeight.Bold, lineHeight = 50.sp),
    displaySmall = TextStyle(fontSize = 36.sp, fontWeight = FontWeight.Bold, lineHeight = 42.sp),
    headlineLarge = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, lineHeight = 34.sp),
    headlineMedium = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.Bold, lineHeight = 30.sp),
    headlineSmall = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, lineHeight = 26.sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold, lineHeight = 26.sp),
    titleMedium = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, lineHeight = 22.sp),
    titleSmall = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
    bodyLarge = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.Normal, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Normal, lineHeight = 20.sp),
    bodySmall = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Normal, lineHeight = 18.sp),
    labelLarge = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp),
    labelMedium = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.SemiBold, lineHeight = 18.sp),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, lineHeight = 14.sp),
)

@Composable
fun GrowOpTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val p = if (dark) DarkPalette else LightPalette
    val scheme = if (dark) darkColorScheme(
        primary = p.brand, onPrimary = Color.White,
        primaryContainer = p.brand.copy(alpha = 0.25f), onPrimaryContainer = p.text,
        secondary = p.leaf, onSecondary = Color(0xFF0C2A15),
        secondaryContainer = p.brand.copy(alpha = 0.28f), onSecondaryContainer = p.text,
        tertiary = p.night, onTertiary = Color.White,
        background = p.bg, onBackground = p.text,
        surface = p.card, onSurface = p.text,
        surfaceVariant = Color(0xFF262B27), onSurfaceVariant = p.textSecondary,
        surfaceContainer = p.card, surfaceContainerLow = p.card, surfaceContainerHigh = Color(0xFF232823),
        surfaceContainerHighest = Color(0xFF2A302B), surfaceContainerLowest = p.bg,
        error = p.alert, onError = Color.White,
        outline = Color.White.copy(alpha = 0.22f), outlineVariant = Color.White.copy(alpha = 0.12f),
    ) else lightColorScheme(
        primary = p.brand, onPrimary = Color.White,
        primaryContainer = p.brand.copy(alpha = 0.12f), onPrimaryContainer = p.brand,
        secondary = p.leaf, onSecondary = Color(0xFF0C2A15),
        secondaryContainer = p.brand.copy(alpha = 0.14f), onSecondaryContainer = p.brand,
        tertiary = p.night, onTertiary = Color.White,
        background = p.bg, onBackground = p.text,
        surface = p.card, onSurface = p.text,
        surfaceVariant = Color(0xFFECEBE4), onSurfaceVariant = p.textSecondary,
        surfaceContainer = p.card, surfaceContainerLow = p.card, surfaceContainerHigh = Color(0xFFF0EFE9),
        surfaceContainerHighest = Color(0xFFE9E8E1), surfaceContainerLowest = Color.White,
        error = p.alert, onError = Color.White,
        outline = Color.Black.copy(alpha = 0.20f), outlineVariant = Color.Black.copy(alpha = 0.10f),
    )
    CompositionLocalProvider(LocalGrowPalette provides p) {
        MaterialTheme(colorScheme = scheme, typography = GrowTypography, shapes = GrowShapes, content = content)
    }
}
