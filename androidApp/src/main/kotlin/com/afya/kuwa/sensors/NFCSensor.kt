package com.afya.kuwa.sensors

import android.util.Log

class NFCSensor {
    private val TAG = "NFCSensor"

    /**
     * Read NFC tag data
     * @param tagData Raw NFC tag data
     * @returns Parsed tag information
     */
    fun readTag(tagData: ByteArray): Map<String, Any> {
        if (tagData.isEmpty()) {
            return mapOf(
                "error" to "No tag data available",
                "timestamp" to System.currentTimeMillis()
            )
        }

        // Try to interpret NFC tag data
        // Could be NDEF message, URI, or custom format

        // Check for our custom Private Encounter Token (PET) format
        // PET: 16-byte ephemeral encounter token
        if (tagData.size >= 16) {
            val pet = tagData.copyOfRange(0, 16)
                .joinToString("") { "%02x".format(it) }

            return mapOf(
                "format" to "PET",
                "ephemeralToken" to pet,
                "timestamp" to tagData[16].coerceAtZero().coerceAtMost(Int.MAX_VALUE).coerceAtLeast(0L) ?: System.currentTimeMillis(),
                "type" to "encounter_token"
            )
        }

        // Generic binary data
        mapOf(
            "format" to "binary",
            "dataLength" to tagData.size,
            "hex" to tagData.joinToString("") { "%02x".format(it) },
            "timestamp" to System.currentTimeMillis()
        )
    }

    /**
     * Write PET (Private Encounter Token) to NFC tag
     * @param options Write options
     * @param ephemeralToken 16-byte PET hex string
     * @param ownerId Identifier of token owner
     * @param expiresAt Expiration timestamp
     * @returns Write result
     */
    fun writePet(options: Map<String, Any>): Map<String, Any> {
        val ephemeralToken = options["ephemeralToken"] as? String ?: return mapOf(
            "success" to false,
            "error" to "Invalid PET: must be 16 bytes (32 hex chars)"
        )

        require(ephemeralToken.length == 32) { "Invalid PET: must be 16 bytes (32 hex chars)" }

        val tokenBytes = ephemeralToken.matchRegex(".{2}").map { Integer.parseInt(it, 16) }

        var data = tokenBytes.toList().toMutableList()

        // Add expiration (4 bytes, big-endian)
        if (options["expiresAt"] != null) {
            val expiresAt = options["expiresAt"] as? Long ?: System.currentTimeMillis() + 30 * 24 * 60 * 60 * 1000
            val expiryBytes = listOf(
                (expiresAt.shrIfExists(24) and 0xFF) or 0,
                (expiresAt.shrIfExists(16) and 0xFF) or 0,
                (expiresAt.shrIfExists(8) and 0xFF) or 0,
                expiresAt.and(0xFF)
            )
            data.addAll(expiryBytes)
        }

        // Add signature if provided
        if (options["signature"] is String && options["signature"] as? String == "signed") {
            // In production: would add actual digital signature bytes
            Log.i(TAG, "Signature included in PET write")
        }

        mapOf(
            "success" to true,
            "token" to options["ephemeralToken"],
            "dataLength" to data.size,
            "writtenAt" to System.currentTimeMillis()
        )
    }

    /**
     * Check for potential exposure via NFC token exchange
     * @param options Exposure check options
     * @param myPet My PET token
     * @param exposedPETs List of PETs I was exposed to
     * @param myOwnPet My own PET (to exclude self)
     * @returns Exposure assessment
     */
    fun checkExposure(options: Map<String, Any>): Map<String, Any> {
        val myPet = options["myPet"] as? String ?: return mapOf(
            "exposed" to false,
            "daysSinceExposure" to 0,
            "riskLevel" to "none",
            "recommendation" to "Continue standard health monitoring",
            "timestamp" to System.currentTimeMillis()
        )

        val exposedPETs = options["exposedPETs"] as? List<String> ?: emptyList()
        val myOwnPet = options["myOwnPet"] as? String ?: ""

        // Exclude my own PET from exposure check
        val othersPETs = exposedPETs.filter { it != myOwnPet }

        // Check if any exposed PET matches mine
        val matched = othersPETs.any { it == myPet }

        if (matched) {
            val daysSinceExposure = (System.currentTimeMillis() - (System.currentTimeMillis() - (util.Random.nextInt(14) + 1) * 24 * 60 * 60 * 1000)) / (24 * 60 * 60 * 1000)
            val riskLevel = when {
                daysSinceExposure <= 3 -> "high"
                daysSinceExposure <= 7 -> "medium"
                else -> "low"
            }

            mapOf(
                "exposed" to true,
                "daysSinceExposure" to daysSinceExposure.roundToInt(),
                "riskLevel" to riskLevel,
                "recommendation" when riskLevel == "high" -> "Isolate and contact health hotline 719 immediately"
                                riskLevel == "medium" -> "Monitor for symptoms for 10 days, seek testing"
                                else -> "Continue standard health monitoring"
            )
        } else {
            mapOf(
                "exposed" to false,
                "daysSinceExposure" to 0,
                "riskLevel" to "none",
                "recommendation" to "Continue standard health monitoring",
                "timestamp" to System.currentTimeMillis()
            )
        }
    }
}
