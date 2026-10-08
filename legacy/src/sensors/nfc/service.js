// nfc.py — Near Field Communication for token exchange and device pairing
class NfcSensor {
  /**
   * Read NFC tag data
   * @param {Uint8Array} tagData - Raw NFC tag data from reader
   * @returns {Object} Parsed tag information
   */
  readTag(tagData) {
    if (!tagData || tagData.length === 0) {
      return { error: 'No tag data available' };
    }
    
    // Try to interpret NFC tag data
    // Could be NDEF message, URI, or custom format
    
    // Check for NDEF format (simple check)
    if (tagData.length >= 3 && 
        tagData[0] === 0xD1 && tagData[1] === 0xE1) {
      // NDEF well-known message format
      return this._parseNdef(tagData);
    }
    
    // Check for our custom Private Encounter Token (PET) format
    // PET: 16-byte ephemeral encounter token
    if (tagData.length >= 16) {
      const pet = Array.from(tagData.slice(0, 16))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
      
      return {
        format: 'PET',
        ephemeralToken: pet,
        timestamp: tagData[16] ? tagData[16] : Date.now(),
        type: 'encounter_token'
      };
    }
    
    // Generic binary data
    return {
      format: 'binary',
      dataLength: tagData.length,
      hex: Array.from(tagData).map(b => b.toString(16).padStart(2, '0')).join(''),
      timestamp: Date.now()
    };
  }

  /**
   * Parse NDEF (NFC Data Exchange Format) message
   * @param {Uint8Array} ndefData - NDEF formatted data
   * @returns {Object} Parsed NDEF content
   */
  _parseNdef(ndefData) {
    // Simplified NDEF parser
    // In production would use robust NDEF parsing
    
    // Check for URI record type definition
    const urnOffset = 3; // After TNF + Type Length + Length
    if (ndefData.length < urnOffset) return { rawNdef: Array.from(ndefData) };
    
    const tnf = ndefData[0];
    const typeLength = ndefData[1];
    const messageLength = ndefData[2];
    
    // URI prefix lookup (GSMA specification)
    const uriPrefixes = [
      '', 'http://www.', 'https://www.', 'http://', 'https://',
      'tel:', 'mailto:', 'ftp://', 'ftpps://', 'sms:', 'telnet://'
    ];
    
    let uriPrefix = '';
    let encoding = 0; // 0 = UTF-8, 1 = UTF-16
    
    if (tnf >= 1 && tnf <= 6) {
      encoding = tnf >> 3;
      tnf = tnf & 0x07; // Type Name Format
      uriPrefix = uriPrefixes[tnn] || '';
    }
    
    // Extract URI data (after header bytes)
    const uriStart = 3 + typeLength;
    if (uriStart >= ndefData.length) return { rawNdef: Array.from(ndefData) };
    
    // The first byte after header indicates URI length or is part of URI
    const firstByte = ndefData[uriStart];
    
    // Simple URI extraction
    let uri = '';
    if (firstByte < 0xE0) {
      // 1-byte URI identifier
      uri = uriPrefix + String.fromCharCode(firstByte);
    } else if (firstByte < 0xF0) {
      // 2-byte URI identifier
      const secondByte = ndefData[uriStart + 1];
      uri = uriPrefix + String.fromCharCode(
        (firstByte & 0x0F) * 256 + secondByte
      );
    }
    
    return {
      type: 'URI',
      uri: uri || 'unknown',
      rawUri: ndefData.slice(uriStart).reduce(
        (a, b) => a + String.fromCharCode(b), ''
      ),
      timestamp: Date.now()
    };
  }

  /**
   * Write Private Encounter Token (PET) to NFC tag
   * @param {Object} options - PET write options
   * @param {string} options.ephemeralToken - 16-byte PET hex string
   * @param {string} options.ownerId - Identifier of token owner
   * @param {number} options.expiresAt - Expiration timestamp
   * @param {string} options.signature - Digital signature for authenticity
   * @returns {Object} Write result
   */
  writePet(options) {
    const { ephemeralToken, ownerId, expiresAt, signature } = options;
    
    if (!ephemeralToken || ephemeralToken.length !== 32) {
      throw new Error('Invalid PET: must be 16 bytes (32 hex chars)');
    }
    
    // Construct PET data frame
    // Format: [ownerId (optional)] + ephemeralToken + expiresAt (4 bytes) + signature (optional)
    const tokenBytes = Array.from(ephemeralToken.match(/.{2}/g).map(h => parseInt(h, 16)));
    
    let data = tokenBytes;
    
    // Add expiration (4 bytes, big-endian)
    if (expiresAt) {
      const expiryBytes = [
        (expiresAt >> 24) & 0xFF,
        (expiresAt >> 16) & 0xFF,
        (expiresAt >> 8) & 0xFF,
        expiresAt & 0xFF
      ];
      data = data.concat(expiryBytes);
    }
    
    // Add signature if provided
    if (signature && typeof signature === 'string' && signature.length === 64) {
      const sigBytes = Array.from(signature.match(/.{2}/g).map(h => parseInt(h, 16)));
      data = data.concat(sigBytes);
    }
    
    // In production: would actually write to NFC tag via Web NFC API
    // For now, return success status
    return {
      success: true,
      token: ephemeralToken,
      dataLength: data.length,
      writtenAt: Date.now()
    };
  }

  /**
   * Check for potential Ebola exposure via NFC token exchange
   * @param {Object} options - Exposure check options
   * @param {string} options.myPet - My 16-byte ephemeral token (hex)
   * @param {Array<string>} options.exposedPETs - List of PETs I was exposed to
   * @param {string} options.myOwnPet - My own PET (to exclude self)
   * @returns {Object} Exposure assessment
   */
  checkExposure(options) {
    const { myPet, exposedPETs, myOwnPet } = options;
    
    if (!myPet || myPet.length !== 32) {
      return { error: 'Invalid myPet format' };
    }
    
    // Exclude my own PET from exposure check
    const othersPETs = exposedPETs?.filter(pet => pet !== myOwnPet) || [];
    
    // Check if any exposed PET matches mine
    const matched = othersPETs.some(pet => pet === myPet);
    
    if (matched) {
      // Calculate approximate exposure duration based on TTL
      // In production: would use EBID TTL from BLE scan
      const daysSinceExposure = Math.floor(Math.random() * 14) + 1;
      
      return {
        exposed: true,
        daysSinceExposure,
        riskLevel: daysSinceExposure <= 3 ? 'high' : 
                   daysSinceExposure <= 7 ? 'medium' : 'low',
        recommendation: 'Isolate and contact health hotline 719 immediately',
        timestamp: Date.now()
      };
    }
    
    return {
      exposed: false,
      daysSinceExposure: 0,
      riskLevel: 'none',
      recommendation: 'Continue standard health monitoring',
      timestamp: Date.now()
    };
  }
}

module.exports = NfcSensor;
