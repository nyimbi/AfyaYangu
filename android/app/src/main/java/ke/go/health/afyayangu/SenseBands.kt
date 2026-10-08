package ke.go.health.afyayangu

/** Client-side band engines — same contracts as src/afya/sensors/service.py. Pure Kotlin, JVM-testable. */
object SenseBands {
	fun respiration(rate: Double): String = when {
		rate < 12.0 || rate > 25.0 -> "alert"
		else -> "normal"
	}

	fun cough(perHour: Double): String = when {
		perHour >= 30.0 -> "alert"
		perHour >= 15.0 -> "watch"
		else -> "normal"
	}

	fun ppg(hr: Double): String = when {
		hr < 45.0 || hr > 120.0 -> "alert"
		hr < 55.0 || hr > 100.0 -> "watch"
		else -> "normal"
	}

	fun fall(peakG: Double): String = if (peakG > 4.0) "alert" else "normal"
}