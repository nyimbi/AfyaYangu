// gps.py — Location tracking and geofencing
class GpsSensor {
  /**
   * Get current geographic location
   * @returns {Object} Location data with latitude, longitude, accuracy
   */
  getCurrentLocation() {
    // In production would use navigator.geolocation.getCurrentPosition
    // For now, return a placeholder location for Kenya
    
    // If geolocation is available, use it
    if (typeof navigator !== 'undefined' && navigator.geolocation) {
      return new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          (position) => {
            resolve({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              accuracy: position.coords.accuracy,
              altitude: position.coords.altitude,
              heading: position.coords.heading,
              velocity: position.coords.velocity,
              timestamp: position.timestamp
            });
          },
          (error) => {
            // Fallback to default Kenya location if geolocation fails
            reject(error);
          },
          { timeout: 10000, maximumAge: 5000 }
        );
      });
    }
    
    // Fallback: default Kenya coordinates (Nairobi)
    return {
      latitude: -1.2921,
      longitude: 36.8219,
      accuracy: 500,
      altitude: 0,
      heading: 0,
      velocity: 0,
      timestamp: Date.now()
    };
  }

  /**
   * Set up geofence for risk area monitoring
   * @param {Object} options - Geofence configuration
   * @param {number} options.latitude - Geofence center latitude
   * @param {number} options.longitude - Geofence center longitude
   * @param {number} options.radius - Radius in meters
   * @param {string} options.riskType - Type of risk (ebola, cholera, etc.)
   * @param {string} options.alertLevel - Alert level (low, medium, high)
   * @returns {Object} Created geofence monitor
   */
  setGeofence(options) {
    const geofence = {
      id: 'geofence-' + Date.now(),
      latitude: options.latitude,
      longitude: options.longitude,
      radius: options.radius || 5000,
      riskType: options.riskType || 'general',
      alertLevel: options.alertLevel || 'low',
      createdAt: Date.now(),
      triggered: false,
      enterCount: 0,
      exitCount: 0
    };
    
    // Store geofence - in production would use persistent storage
    this._geofences = this._geofences || [];
    this._geofences.push(geofence);
    
    return geofence;
  }

  /**
   * Check if current location is within any active geofence
   * @returns {Array<Object>} List of triggered geofences
   */
  checkGeofences() {
    if (!this._geofences) return [];
    
    const location = this.getCurrentLocation();
    const triggered = [];
    
    for (const geofence of this._geofences) {
      if (!geofence.triggered) {
        const distance = this._calculateDistance(
          location.latitude, location.longitude,
          geofence.latitude, geofence.radius
        );
        
        if (distance <= geofence.radius) {
          geofence.triggered = true;
          geofence.enterCount++;
          triggered.push(geofence);
        }
      }
    }
    
    return triggered;
  }

  /**
   * Check if location has exited a geofence
   * @param {Object} geofence - Geofence to check
   * @returns {boolean} Whether location has exited
   */
  checkGeofenceExit(geofence) {
    if (!geofence) return false;
    
    const location = this.getCurrentLocation();
    const distance = this._calculateDistance(
      location.latitude, location.longitude,
      geofence.latitude, geofence.longitude
    );
    
    if (distance > geofence.radius && geofence.triggered) {
      geofence.triggered = false;
      geofence.exitCount++;
      return true;
    }
    
    return false;
  }

  _calculateDistance(lat1, lon1, lat2, lon2) {
    // Haversine formula for distance calculation between two points
    const R = 6371; // Earth's radius in kilometers
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c * 1000; // Convert to meters
  }
}

module.exports = GpsSensor;
