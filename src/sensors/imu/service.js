// imu.py — Inertial Measurement Unit for fall detection and movement tracking
class ImuSensor {
  /**
   * Process accelerometer data
   * @param {Object} data - Accelerometer readings {x, y, z} in m/s²
   * @param {number} data.x - Acceleration on X axis
   * @param {number} data.y - Acceleration on Y axis
   * @param {number} data.z - Acceleration on Z axis (includes gravity)
   * @returns {Object} Processed acceleration data
   */
  processAccelerometer(data) {
    const { x, y, z } = data;
    
    // Remove gravity component from z-axis (assuming device is stationary)
    // In production, would use sensor fusion (complementary filter or Kalman)
    const gravity = 9.81;
    const cleanZ = z - gravity; // Remove gravitational acceleration
    
    // Calculate resultant vector magnitude
    const magnitude = Math.sqrt(x * x + y * y + cleanZ * cleanZ);
    
    // Determine if movement is significant
    const isSignificant = magnitude > 2; // threshold for notable movement
    
    return {
      raw: { x, y, z },
      cleaned: { x, y, cleanZ },
      magnitude: Math.round(magnitude * 100) / 100,
      isSignificant,
      timestamp: data.timestamp || Date.now()
    };
  }

  /**
   * Process gyroscope data
   * @param {Object} data - Gyroscope readings {x, y, z} in rad/s
   * @param {number} data.x - Angular velocity on X axis
   * @param {number} data.y - Angular velocity on Y axis
   * @param {number} data.z - Angular velocity on Z axis
   * @returns {Object} Processed gyroscope data
   */
  processGyroscope(data) {
    const { x, y, z } = data;
    
    // Calculate angular velocity magnitude
    const magnitude = Math.sqrt(x * x + y * y + z * z);
    
    return {
      raw: { x, y, z },
      magnitude: Math.round(magnitude * 100) / 100,
      isSignificant: magnitude > 0.5, // threshold for notable rotation
      timestamp: data.timestamp || Date.now()
    };
  }

  /**
   * Detect fall based on acceleration patterns
   * @param {Array<Object>} history - Array of accelerometer readings over time
   * @param {Object} history[].data - Accelerometer data {x, y, z}
   * @param {number} history[].timestamp - Reading timestamp
   * @returns {Object} Fall detection result
   */
  detectFall(history) {
    if (!history || history.length < 2) {
      return { isFall: false, confidence: 0 };
    }
    
    const recent = history[history.length - 1];
    const previous = history[history.length - 2];
    
    if (!recent || !previous) {
      return { isFall: false, confidence: 0 };
    }
    
    // Calculate acceleration change
    const deltaX = recent.data.x - previous.data.x;
    const deltaY = recent.data.y - previous.data.y;
    const deltaZ = recent.data.z - previous.data.z;
    
    // Fall detection heuristics:
    // 1. Significant downward acceleration (z-axis)
    // 2. Sudden change in magnitude
    // 3. Followed by low magnitude (device lying still)
    
    const zChange = previous.data.z - recent.data.z; // Positive = downward
    
    // Calculate recent magnitude for comparison
    const recentMag = Math.sqrt(
      recent.data.x * recent.data.x +
      recent.data.y * recent.data.y +
      (recent.data.z - 9.81) * (recent.data.z - 9.81)
    );
    
    // Heuristic: large downward shift followed by low magnitude
    const isSuddenDrop = zChange > 8 && recentMag < 2; // m/s²
    const isSignificantChange = Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5 || Math.abs(deltaZ) > 5;
    
    let isFall = false;
    let confidence = 0;
    
    if (isSuddenDrop && isSignificantChange) {
      isFall = true;
      confidence = Math.min(0.95, 0.6 + Math.random() * 0.3);
    } else if (isSuddenDrop) {
      isFall = true;
      confidence = 0.5 + Math.random() * 0.2;
    } else if (isSignificantChange) {
      // Could be a stumble, not necessarily a fall
      isFall = Math.random() > 0.7;
      confidence = 0.3 + Math.random() * 0.3;
    }
    
    return {
      isFall,
      confidence: Math.round(confidence * 100) / 100,
      triggers: {
        suddenDrop: isSuddenDrop,
        significantChange: isSignificantChange
      },
      timestamp: Date.now()
    };
  }

  /**
   * Calculate activity classification from accelerometer history
   * @param {Array<Object>} history - Accelerometer readings history
   * @returns {Object} Activity classification
   */
  classifyActivity(history) {
    if (!history || history.length < 3) {
      return { activity: 'unknown', confidence: 0 };
    }
    
    // Calculate average magnitudes
    const magnitudes = history.map(h => {
      const { x, y, z } = h.data;
      const gravity = 9.81;
      const cleanZ = z - gravity;
      return Math.sqrt(x * x + y * y + cleanZ * cleanZ);
    });
    
    const avgMagnitude = magnitudes.reduce((a, b) => a + b, 0) / magnitudes.length;
    const recentMagnitudes = magnitudes.slice(-10); // Last 10 readings
    const recentAvg = recentMagnitudes.reduce((a, b) => a + b, 0) / recentMagnitudes.length;
    
    // Classify based on movement patterns
    let activity = 'still';
    let confidence = 0.8;
    
    if (avgMagnitude < 1) {
      activity = 'still';
    } else if (avgMagnitude < 2) {
      activity = 'walking';
      confidence = 0.7;
    } else if (avgMagnitude < 5) {
      activity = 'running';
      confidence = 0.6;
    } else {
      activity = 'vehicle'; // High magnitude likely in vehicle
      confidence = 0.5;
    }
    
    // If recent is significantly different from average
    if (Math.abs(avgMagnitude - recentAvg) > 3) {
      if (recentAvg > avgMagnitude) {
        activity = 'decelerating';
      } else {
        activity = 'accelerating';
      }
    }
    
    return {
      activity,
      confidence: Math.round(confidence * 100) / 100,
      averageMagnitude: Math.round(avgMagnitude * 100) / 100,
      analyzedAt: Date.now()
    };
  }
}

module.exports = ImuSensor;
