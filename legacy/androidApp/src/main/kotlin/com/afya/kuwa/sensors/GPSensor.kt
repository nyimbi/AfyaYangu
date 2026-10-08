package com.afya.kuwa.sensors

import android.util.Log

class GPSSensor {
    private val TAG = "GPSSensor"

    /**
     * Get current geographic location
     * @returns Location data
     */
    fun getCurrentLocation(): Map<String, Any> {
        // In production: use FusedLocationProviderClient
        // For now: return default Kenya coordinates
        return mapOf(
            "latitude" to -1.2921, // Nairobi
            "longitude" to 36.8219,
            "accuracy" to 500.0,
            "altitude" to 0.0,
            "heading" to 0.0,
            "velocity" to 0.0,
            "timestamp" to System.currentTimeMillis()
        )
    }

    /**
     * Set up geofence for risk area monitoring
     * @param latitude Geofence center latitude
     * @param longitude Geofence center longitude
     * @param radius Radius in meters
     * @param riskType Type of risk (ebola, cholera, etc.)
     * @returns Geofence configuration
     */
    fun setGeofence(latitude: Double, longitude: Double, radius: Double, riskType: String = "general"): Map<String, Any> {
        return mapOf(
            "geofenceId" to "geofence-${System.currentTimeMillis()}",
            "latitude" to latitude,
            "longitude" to longitude,
            "radiusMeters" to radius,
            "riskType" to riskType,
            "alertLevel" to "low",
            "createdAt" to System.currentTimeMillis(),
            "triggered" to false,
            "enterCount" to 0,
            "exitCount" to 0
        )
    }

    /**
     * Check if current location is within geofence
     * @param geofence Geofence configuration
     * @param currentLocation Current location
     * @returns Whether inside geofence
     */
    fun isInGeofence(geofence: Map<String, Any>, currentLocation: Map<String, Any>): Boolean {
        val radius = geofence["radiusMeters"] as? Double ?: 5000.0
        val glat = geofence["latitude"] as? Double ?: 0.0
        val glon = geofence["longitude"] as? Double ?: 0.0

        val clat = currentLocation["latitude"] as? Double ?: 0.0
        val clon = currentLocation["longitude"] as? Double ?: 0.0

        // Haversine formula
        val earthRadius = 6371000.0 // meters
        val dLat = (clat - glat) * Math.PI / 180
        val dLon = (clon - glon) * Math.PI / 180

        val a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(glat * Math.PI / 180) * Math.cos(clat * Math.PI / 180) *
                        Math.sin(dLon / 2) * Math.sin(dLon / 2)

        val c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
        val distance = earthRadius * c

        return distance <= radius
    }

    /**
     * Calculate distance between two points (Haversine)
     * @param lat1 Latitude 1
     * @param lon1 Longitude 1
     * @param lat2 Latitude 2
     * @param lon2 Longitude 2
     * @returns Distance in meters
     */
    fun calculateDistance(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val earthRadius = 6371000.0
        val dLat = (lat2 - lat1) * Math.PI / 180
        val dLon = (lon2 - lon1) * Math.PI / 180

        val a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                        Math.sin(dLon / 2) * Math.sin(dLon / 2)

        val c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
        return earthRadius * c
    }
}
