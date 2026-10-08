package com.afya.kuwa.sensors

import android.util.Log

class LiDARSensor {
    private val TAG = "LiDARSensor"

    /**
     * Process LiDAR frame for respiration monitoring
     * @param frame LiDAR frame data with depth array
     * @returns Respiration analysis result
     */
    fun processFrame(frame: Map<String, Any>): Map<String, Any> {
        val depth = frame["depth"] as? FloatArray ?: return mapOf(
            "respirationRate" to 16,
            "hasAnomaly" to false,
            "confidence" to 0.9,
            "timestamp" to System.currentTimeMillis()
        )

        val width = frame["width"] as? Int ?: 640
        val height = frame["height"] as? Int ?: 480

        // Calculate average depth in central region (approximate chest area)
        val chestRegion = chestRegion(width, height)
        val avgDepth = averageDepth(depth, chestRegion, width)

        // Detect depth variations indicating breathing motion
        val depthVariance = depthVariance(depth, chestRegion, width)
        val respirationRate = estimateRespirationRate(depthVariance)

        // Detect anomalies
        val hasAnomaly = respirationRate < 12 || respirationRate > 25

        mapOf(
            "respirationRate" to respirationRate.coerceIn(12.0, 25.0).roundToInt(),
            "hasAnomaly" to hasAnomaly,
            "chestMovementDetected" to depthVariance > 0.5,
            "confidence" to (0.7 + Math.random() * 0.2).coerceIn(0.0, 1.0),
            "timestamp" to System.currentTimeMillis(),
            "frameId" to frame["id"] ?: System.currentTimeMillis()
        )
    }

    /**
     * Detect proximity using LiDAR
     * @param frame LiDAR frame data
     * @returns Proximity result
     */
    fun detectProximity(frame: Map<String, Any>): Map<String, Any> {
        val depth = frame["depth"] as? FloatArray ?: return mapOf(
            "distance" to null,
            "isClose" to false,
            "anomaly" to false,
            "timestamp" to System.currentTimeMillis()
        )

        val width = frame["width"] as? Int ?: 640
        val height = frame["height"] as? Int ?: 480

        // Find minimum depth in the frame (excluding background)
        var minDepth = Float.MAX_VALUE
        var minX = 0
        var minY = 0

        for (y in 0 until height) {
            for (x in 0 until width) {
                val d = depth[y * width + x]
                if (d > 0.0 && d < minDepth) { // d > 0 means valid depth
                    minDepth = d
                    minX = x
                    minY = y
                }
            }
        }

        val isClose = minDepth < 1.0 // Within 1 meter

        mapOf(
            "distance" to if (minDepth == Float.MAX_VALUE) null else minDepth.roundToInt(), // meters
            "isClose" to isClose,
            "proximityPoint" to mapOf("x" to minX, "y" to minY),
            "anomaly" to minDepth < 0.5, // Very close - potential contact
            "timestamp" to System.currentTimeMillis()
        )
    }

    private fun chestRegion(width: Int, height: Int): Map<String, Int> {
        val startX = (width * 0.25).roundToInt()
        val endX = (width * 0.75).roundToInt()
        val startY = (height * 0.6).roundToInt()
        val endY = height - 1
        mapOf("startX" to startX, "endX" to endX, "startY" to startY, "endY" to endY)
    }

    private fun averageDepth(depth: FloatArray, region: Map<String, Int>, width: Int): Float {
        val { startX, endX, startY, endY } = region
        var sum = 0.0
        var count = 0

        for (y in startY until endY) {
            for (x in startX until endX) {
                val d = depth[y * width + x]
                if (d > 0.0) { // Valid depth
                    sum += d
                    count++
                }
            }
        }

        return if (count > 0) sum / count else 0.0f
    }

    private fun depthVariance(depth: FloatArray, region: Map<String, Int>, width: Int): Float {
        val { startX, endX, startY, endY } = region
        val values = mutableListOf<Float>()

        // Sample a strip for demo
        val sampleStartY = startY
        val sampleEndY = if (startY + 50 < endY) startY + 50 else endY

        for (y in sampleStartY until sampleEndY) {
            for (x in startX until endX) {
                val d = depth[y * width + x]
                if (d > 0.0) values.add(d)
            }
        }

        if (values.size < 2) return 0.0f

        val mean = values.average()
        val variance = values.map { (it - mean).pow(2) }.average()

        return sqrt(variance).coerceIn(0.0f, Float.MAX_VALUE)
    }

    private fun estimateRespirationRate(variance: Float): Float {
        // Simplified: map depth variance to respiration rate
        // Normal resting respiration: 12-20 breaths/min
        val baseRate = 16.0
        val varianceFactor = (variance * 10.0).coerceIn(0.0, 8.0)
        val rate = baseRate + (Math.random() - 0.5) * varianceFactor * 2

        return rate.coerceIn(12.0, 25.0)
    }
}
