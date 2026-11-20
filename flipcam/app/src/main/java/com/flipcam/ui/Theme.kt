package com.flipcam.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Neon palette shared by the HUD and the skeleton overlay. */
object Neon {
    val Cyan = Color(0xFF22E6FF)
    val CyanDim = Color(0x6622E6FF)
    val Amber = Color(0xFFFFB020)
    val AmberDim = Color(0x66FFB020)
    val Glass = Color(0xB3121216)
    val GlassLight = Color(0x33FFFFFF)
    val Ink = Color(0xFFF2F4F8)
    val Muted = Color(0xFF9AA3B2)
    val Record = Color(0xFFFF3B30)
}

private val scheme = darkColorScheme(
    primary = Neon.Cyan,
    onPrimary = Color.Black,
    secondary = Neon.Amber,
    background = Color.Black,
    onBackground = Neon.Ink,
    surface = Neon.Glass,
    onSurface = Neon.Ink,
    error = Neon.Record,
)

private val hudType = Typography(
    labelSmall = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Bold,
        fontSize = 10.sp,
        letterSpacing = 1.2.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.Bold,
        fontSize = 12.sp,
        letterSpacing = 1.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
    ),
)

@Composable
fun FlipCamTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = scheme, typography = hudType, content = content)
}
