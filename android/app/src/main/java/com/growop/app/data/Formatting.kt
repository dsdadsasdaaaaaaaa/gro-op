package com.growop.app.data

import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

object Formatting {
    private val dayFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.US)
    private val monthDayFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d", Locale.getDefault())
    private val abbrevDateFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.getDefault())
    private val timeFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("h:mm a", Locale.getDefault())
    private val hhmm: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm", Locale.US)

    /** Parses ISO-8601 timestamps (with or without fractional seconds / zone). Returns null if unparseable. */
    fun parseISO(s: String?): Instant? {
        if (s.isNullOrBlank()) return null
        val t = s.trim()
        runCatching { return Instant.parse(t) }
        runCatching { return OffsetDateTime.parse(t).toInstant() }
        runCatching { return LocalDateTime.parse(t).toInstant(ZoneOffset.UTC) }
        runCatching { return LocalDate.parse(t.take(10), dayFmt).atStartOfDay(ZoneId.systemDefault()).toInstant() }
        return null
    }

    fun parseDay(s: String?): LocalDate? {
        if (s == null || s.length < 10) return null
        return runCatching { LocalDate.parse(s.take(10), dayFmt) }.getOrNull()
    }

    fun dayString(d: LocalDate): String = d.format(dayFmt)

    fun number(d: Double, decimals: Int = 1): String {
        if (d == Math.rint(d) && abs(d) < 1e15) return d.toLong().toString()
        return String.format(Locale.getDefault(), "%.${decimals}f", d)
    }

    fun fixed(d: Double, decimals: Int): String = String.format(Locale.getDefault(), "%.${decimals}f", d)

    /** "5 min ago" / "2 hr ago" / "just now" / "in 3 hr". */
    fun relative(s: String?): String {
        val d = parseISO(s) ?: return ""
        return relative(d)
    }

    fun relative(d: Instant, now: Instant = Instant.now()): String {
        val secs = now.epochSecond - d.epochSecond
        val past = secs >= 0
        val a = abs(secs)
        val body = when {
            a < 45 -> return if (past) "just now" else "in a moment"
            a < 90 -> "1 min"
            a < 3600 -> "${(a / 60)} min"
            a < 5400 -> "1 hr"
            a < 86400 -> "${(a / 3600.0).roundToInt()} hr"
            a < 172800 -> "1 day"
            a < 86400L * 30 -> "${(a / 86400)} days"
            a < 86400L * 60 -> "1 mo"
            else -> "${(a / (86400L * 30))} mo"
        }
        return if (past) "$body ago" else "in $body"
    }

    fun shortDateTime(s: String?): String {
        val d = parseISO(s) ?: return s ?: ""
        val z = d.atZone(ZoneId.systemDefault())
        return "${z.format(abbrevDateFmt)} at ${z.format(timeFmt)}"
    }

    fun shortTime(d: Instant): String = d.atZone(ZoneId.systemDefault()).format(timeFmt)

    fun friendlyDay(s: String?): String {
        val d = parseDay(s) ?: return s ?: ""
        return d.format(abbrevDateFmt)
    }

    fun abbrevDate(d: LocalDate): String = d.format(abbrevDateFmt)

    /** "Oct 10" style, or null when the string isn't a date. */
    fun monthDay(s: String?): String? = parseDay(s)?.format(monthDayFmt)

    /** "Saturday, September 20" for the Home header. */
    fun todayLong(): String {
        val d = LocalDate.now()
        val wd = d.dayOfWeek.getDisplayName(TextStyle.FULL, Locale.getDefault())
        val m = d.month.getDisplayName(TextStyle.FULL, Locale.getDefault())
        return "$wd, $m ${d.dayOfMonth}"
    }

    /** "4h 12m" style countdown to a future instant. */
    fun countdown(to: Instant, from: Instant = Instant.now()): String {
        val secs = maxOf(0L, to.epochSecond - from.epochSecond)
        val h = secs / 3600
        val m = (secs % 3600) / 60
        return if (h > 0) "${h}h ${m}m" else "${m}m"
    }

    fun hhmm(t: LocalTime): String = t.format(hhmm)
    fun parseHHmm(s: String?): LocalTime? = runCatching { LocalTime.parse(s ?: return null, hhmm) }.getOrNull()

    /** "Sep 19 – Sep 22 · day 0–3" (whichever parts are available). */
    fun phaseRange(p: PlanPhase): String {
        val parts = mutableListOf<String>()
        val a = monthDay(p.startDate)
        if (a != null) {
            val b = monthDay(p.endDate)
            parts.add(if (b != null) "$a – $b" else "From $a")
        }
        val sd = p.startDay
        if (sd != null) {
            val ed = p.endDay
            if (ed != null) parts.add(if (parts.isEmpty()) "Day $sd–$ed" else "day $sd–$ed")
            else parts.add(if (parts.isEmpty()) "From day $sd" else "from day $sd")
        }
        return parts.joinToString(" · ")
    }

    fun cToF(c: Double): Double = c * 9 / 5 + 32
    fun fToC(f: Double): Double = (f - 32) * 5 / 9

    fun capitalize(s: String): String = s.replace('_', ' ').replaceFirstChar { it.uppercase() }
}
