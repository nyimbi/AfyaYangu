package com.afya.kuwa.sensors

import android.util.Log

class IMUSensor {
    private val TAG = "IMUSensor"

    /**
     * Process accelerometer data
     * @param data Accelerometer readings {x, y, z} in m/s²
     * @returns Processed acceleration data
     */
    fun processAccelerometer(data: Map<String, Any>): Map<String, Any> {
        val x = data["x"] as? Double ?: 0.0
        val y = data["y"] as? Double ?: 0.0
        val z = data["z"] as? Double ?: 9.81 // Includes gravity

        // Remove gravity component from z-axis
        val cleanZ = z - 9.81

        // Calculate resultant vector magnitude
        val magnitude = Math.sqrt(x * x + y * y + cleanZ * cleanZ).coerceIn(0.0, Double.MAX_VALUE)

        // Determine if movement is significant
        val isSignificant = magnitude > 2.0

        mapOf(
            "raw" to mapOf("x" to x, "y" to y, "z" to z),
            "cleaned" to mapOf("x" to x, "y" to y, "cleanZ" to cleanZ),
            "magnitude" to magnitude.coerceIn(0.0, Double.MAX_VALUE),
            "isSignificant" to isSignificant,
            "timestamp" to System.currentTimeMillis()
        )
    }

    /**
     * Process gyroscope data
     * @param data Gyroscope readings {x, y, z} in rad/s
     * @returns Processed gyroscope data
     */
    fun processGyroscope(data: Map<String, Any>): Map<String, Any> {
        val x = data["x"] as? Double ?: 0.0
        val y = data["y"] as? Double ?: 0.0
        val z = data["z"] as? Double ?: 0.0

        val magnitude = Math.sqrt(x * x + y * y + z * z).coerceIn(0.0, Double.MAX_VALUE)

        mapOf(
            "raw" to mapOf("x" to x, "y" to y, "z" to z),
            "magnitude" to magnitude.coerceIn(0.0, Double.MAX_VALUE),
            "isSignificant" to magnitude > 0.5,
            "timestamp" to System.currentTimeMillis()
        )
    }

    /**
     * Detect fall based on acceleration patterns
     * @param history Array of accelerometer readings over time
     * @returns Fall detection result
     */
    fun detectFall(history: List<Map<String, Any>>): Map<String, Any> {
        if (history.size < 2) {
            return mapOf(
                "isFall" to false,
                "confidence" to 0.0,
                "triggers" to mapOf("suddenDrop" to false, "significantChange" to false),
                "timestamp" to System.currentTimeMillis()
            )
        }

        val recent = history.last()
        val previous = history[history.size - 2]

        if (recent.isEmpty() || previous.isEmpty()) {
            return mapOf(
                "isFall" to false,
                "confidence" to 0.0,
                "timestamp" to System.currentTimeMillis()
            )
        }

        // Calculate acceleration change
        val prevZ = previous["data"] as? Map<String, Double> ?: return mapOf("isFall" to false, "confidence" to 0.0)
        val currZ = recent["data"] as? Map<String, Double> ?: return mapOf("isFall" to false, "confidence" to 0.0)

        val deltaZ = prevZ["z"]!! - currZ["z"]!! // Positive = downward
        val recentMag = sqrt(
            pow(currZ["x"]!!, 2) + pow(currZ["y"]!!, 2) + pow(currZ["z"]!! - 9.81, 2)
        )

        // Fall detection heuristics
        val suddenDrop = deltaZ > 8 && recentMag < 2.0
        val significantChange = magnitudeOfChange(previous, recent) > 5.0

        val isFall = suddenDrop && significantChange
        val confidence = if (isFall) 0.6 + Math.random() * 0.3 else 0.1 + Math.random() * 0.2

        mapOf(
            "isFall" to isFall,
            "confidence" to confidence.coerceIn(0.0, 1.0),
            "triggers" to mapOf(
                "suddenDrop" to suddenDrop,
                "significantChange" to significantChange
            ),
            "timestamp" to System.currentTimeMillis()
        )
    }

    private fun magnitudeOfChange(prev: Map<String, Any>, curr: Map<String, Any>): Double {
        val prevData = prev["data"] as? Map<String, Double> ?: return 0.0
        val currData = curr["data"] as? Map<String, Double> ?: return 0.0

        val dx = prevData["x"]!! - currData["x"]!!
        val dy = prevData["y"]!! - currData["y"]!!
        val dz = prevData["z"]!! - currData["z"]!!

        return sqrt(dx * dx + dy * dy + dz * dz)
    }

    /**
     * Calculate activity classification from accelerometer history
     * @param history Accelerometer readings history
     * @returns Activity classification
     */
    fun classifyActivity(history: List<Map<String, Any>>): Map<String, Any> {
        if (history.size < 3) {
            return mapOf(
                "activity" to "unknown",
                "confidence" to 0.0,
                "averageMagnitude" to 0.0,
                "analyzedAt" to System.currentTimeMillis()
            )
        }

        // Calculate average magnitudes
        val magnitudes = history.map { h ->
            val data = h["data"] as? Map<String, Double> ?: return@map 0.0
            val x = data["x"]!!
            val y = data["y"]!!
            val z = data["z"]!!
            val gravity = 9.81
            val cleanZ = z - gravity
            sqrt(x * x + y * y + cleanZ * cleanZ)
        }

        val avgMagnitude = magnitudes.average().coerceIn(0.0, Double.MAX_VALUE)
        val recentMagnitudes = magnitudes.dropLast(magnitudes.size - 10)
        val recentAvg = recentMagnitudes.average().coerceIn(0.0, Double.MAX_VALUE)

        var activity = "still"
        var confidence = 0.8

        when {
            avgMagnitude < 1.0 -> activity = "still"
            avgMagnitude < 2.0 -> {
                activity = "walking"
                confidence = 0.7
            }
            avgMagnitude < 5.0 -> {
                activity = "running"
                confidence = 0.6
            }
            else -> activity = "vehicle"
        }

        // If recent is significantly different from average
        if (Math.abs(avgMagnitude - recentAvg) > 3.0) {
            if (recentAvg > avgMagnitude) {
                activity = "decelerating"
            } else {
                activity = "accelerating"
            }
        }

        mapOf(
            "activity" to activity,
            "confidence" to confidence.coerceIn(0.0, 1.0),
            "averageMagnitude" to avgMagnitude.coerceIn(0.0, Double.MAX_VALUE),
            "analyzedAt" to System.currentTimeMillis()
        )
    }
}
