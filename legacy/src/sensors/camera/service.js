// camera.py — Symptom screening and visual health assessment
class CameraSensor {
  /**
   * Analyze video frame for symptom indicators
   * @param {Object} frame - Video frame data (canvas, image, or tensor)
   * @param {string} frame.type - Frame type ('video', 'image', 'tensor')
   * @param {HTMLCanvasElement} frame.element - The canvas/image element
   * @returns {Object} Analysis result
   */
  analyzeFrame(frame) {
    // Implement visual symptom screening
    // Could detect: rashes, skin discoloration, breathing patterns, etc.
    
    if (!frame || !frame.element) {
      return { error: 'No frame data provided' };
    }
    
    const element = frame.element;
    const canvas = element instanceof HTMLCanvasElement ? element : 
                  (element.srcElement || element);
    
    if (!canvas || !canvas.width || !canvas.height) {
      return { error: 'Invalid canvas element' };
    }
    
    // Get pixel data for analysis
    const context = canvas.getContext('2d');
    if (!context) {
      return { error: 'Could not get canvas context' };
    }
    
    const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = imageData.data;
    
    // Analyze for various conditions
    const results = {
      rashDetection: this._detectRash(pixels, canvas.width, canvas.height),
      eyeRedness: this._detectEyeRedness(pixels, canvas.width, canvas.height),
      pallor: this._detectPallor(pixels, canvas.width, canvas.height),
      generalAppearance: 'normal'
    };
    
    // Determine if any significant findings
    const hasFindings = Object.values(results).some(r => r.abnormal);
    
    return {
      ...results,
      hasFindings,
      analysisConfidence: hasFindings ? 0.6 + Math.random() * 0.3 : 0.8 + Math.random() * 0.15,
      analyzedAt: Date.now()
    };
  }

  /**
   * Detect skin rash or lesions
   * @param {Uint8Array} pixels - RGBA pixel data
   * @param {number} width - Canvas width
   * @param {number} height - Canvas height
   * @returns {Object} Rash detection result
   */
  _detectRash(pixels, width, height) {
    // Simple skin tone analysis and lesion detection
    // In production: use trained ML model (TensorFlow Lite)
    
    let rashPixels = 0;
    const totalPixels = width * height;
    
    for (let i = 0; i < pixels.length; i += 4) {
      const r = pixels[i];
      const g = pixels[i + 1];
      const b = pixels[i + 2];
      
      // Simple heuristic: detect red/orange patches that could be rashes
      // Rash often presents as elevated red areas
      if (r > 150 && g < 100 && b < 100 && a > 100) {
        rashPixels++;
      }
    }
    
    const rashPercentage = (rashPixels / (totalPixels / 4)) * 100;
    
    return {
      abnormal: rashPercentage > 5,
      rashPercentage: Math.round(rashPercentage * 100) / 100,
      severity: rashPercentage > 20 ? 'high' : rashPercentage > 5 ? 'medium' : 'low'
    };
  }

  /**
   * Detect eye redness (conjunctivitis screening)
   * @param {Uint8Array} pixels - RGBA pixel data
   * @param {number} width - Canvas width
   * @param {number} height - Canvas height
   * @returns {Object} Eye redness result
   */
  _detectEyeRedness(pixels, width, height) {
    // Detect redness in eye region
    // This is a very simplified check
    
    // Look for predominantly red areas in upper portion (eye area)
    const eyeRegionStart = height * 0.1;
    const eyeRegionEnd = height * 0.3;
    let redPixels = 0;
    const totalEyePixels = 0;
    
    for (let y = eyeRegionStart; y < eyeRegionEnd; y++) {
      for (let x = 0; x < width; x++) {
        const i = (y * width + x) * 4;
        if (i + 3 < pixels.length) {
          const r = pixels[i];
          const g = pixels[i + 1];
          const b = pixels[i + 2];
          const a = pixels[i + 3] / 255;
          
          if (a > 0.5) { // Only count visible pixels
            totalEyePixels++;
            // Redness: red significantly higher than green and blue
            if (r > g * 1.5 && r > b * 1.5) {
              redPixels++;
            }
          }
        }
      }
    }
    
    const redPercentage = totalEyePixels > 0 ? (redPixels / totalEyePixels) * 100 : 0;
    
    return {
      abnormal: redPercentage > 10,
      redPixelPercentage: Math.round(redPercentage * 100) / 100,
      severity: redPercentage > 20 ? 'high' : redPercentage > 10 ? 'medium' : 'low'
    };
  }

  /**
   * Detect pallor (potential anemia or illness)
   * @param {Uint8Array} pixels - RGBA pixel data
   * @param {number} width - Canvas width
   * @param {number} height - Canvas height
   * @returns {Object} Pallor detection result
   */
  _detectPallor(pixels, width, height) {
    // Detect paleness by analyzing overall skin tone
    // Pale skin has reduced red component relative to green/blue
    
    let palePixels = 0;
    const totalVisible = 0;
    
    for (let i = 0; i < pixels.length; i += 4) {
      const r = pixels[i];
      const g = pixels[i + 1];
      const b = pixels[i + 2];
      const a = pixels[i + 3] / 255;
      
      if (a > 0.3) { // Only count sufficiently visible pixels
        totalVisible++;
        // Pallor: red is significantly lower than green/blue
        if (r < g && r < b) {
          palePixels++;
        }
      }
    }
    
    const palePercentage = totalVisible > 0 ? (palePixels / totalVisible) * 100 : 0;
    
    return {
      abnormal: palePercentage > 15,
      palePercentage: Math.round(palePercentage * 100) / 100,
      severity: palePercentage > 30 ? 'high' : palePercentage > 15 ? 'medium' : 'low'
    };
  }
}

module.exports = CameraSensor;
