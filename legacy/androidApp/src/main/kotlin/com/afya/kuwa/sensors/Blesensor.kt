package com.afya.kuwa.sensors

import android.util.Log

class Blesensor {
    private val TAG = "Blesensor"

    /**
     * Scan for BLE beacons in range
     * @param duration Scan duration in seconds
     * @returns Detected EBIDs (Ephemeral Bluetooth Identifiers)
     */
    fun scan(options: Map<String, Any> = mapOf()): List<Map<String, Any>> {
        val duration = options["duration"] as? Int ?: 5
        val simulatedEbids = mutableListOf<Map<String, Any>>()

        // Simulate BLE scan results
        for (i in 1..3) {
            simulatedEbids.add(mapOf(
                "id" to "ebid-$i",
                "rssi" to -50 - (i * 10), // RSSI in dBm
                "timestamp" to System.currentTimeMillis(),
                "ttl" to Math.max(1, 128 - (i * 16)) // TTL hops remaining
            ))
        }

        Log.i(TAG, "BLE scan found ${simulatedEbids.size} identifiers")
        return simulatedEbids
    }

    /**
     * Parse EBID from advertisement data
     * @param advData BLE advertisement data
     * @returns Parsed EBID info
     */
    fun parseEbid(advData: ByteArray): Map<String, Any> {
        if (advData.size < 16) {
            emptyMap().also {
                Log.w(TAG, "Invalid EBID advertisement data (too short)")
            }
        }

        val ephemeralId = advData.copyOfRange(0, 16)
            .joinToString("") { "%02x".format(it) }

        return mapOf(
            "ephemeralId" to ephemeralId,
            "timestamp" to System.currentTimeMillis(),
            "rawDataSize" to advData.size
        )
    }

    /**
     * Check if EBID indicates potential exposure risk
     * @param ebid Parsed EBID from scan
     * @param options Risk assessment options
     * @returns Risk assessment
     */
    fun assessExposureRisk(ebid: Map<String, Any>, options: Map<String, Any> = mapOf()): Map<String, Any> {
        val ttl = options["ttl"] as? Int ?: ebid["ttl"] as? Int ?: 128
        val rssi = options["rssi"] as? Double ?: ebid["rssi"] as? Double ?: -50.0
        val localEbid = options["localEbid"] as? String ?: ""

        var riskScore = 0.0

        // TTL-based risk (remaining hops)
        if (ttl <= 4) riskScore += 0.9 // Very recent exposure
        else if (ttl <= 8) riskScore += 0.6
        else if (ttl <= 16) riskScore += 0.3

        // RSSI-based risk (proximity)
        if (rssi < -50) riskScore += 0.1 // Far
        else if (rssi < -30) riskScore += 0.5 // Moderate
        else riskScore += 0.9 // Very close

        // Filter out own EBID
        val ebidId = ebid["id"] as? String ?: ""
        if (ebidId == localEbid) riskScore = 0.0

        val isHighRisk = riskScore > 1.2

        mapOf(
            "riskScore" to riskScore.coerceIn(0.0, 1.0),
            "isHighRisk" to isHighRisk,
            "ttl" to ttl,
            "rssi" to rssi,
            "recommendation" to if (isHighRisk) {
                "Monitor for symptoms, consider testing in 3-5 days"
            } else {
                "Continue standard precautions"
            }
        )
    }
}
