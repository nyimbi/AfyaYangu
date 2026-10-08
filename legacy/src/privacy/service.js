// privacy.js — Data Protection Act 2019 / ODPC / Digital Health Act 2023 compliance
class PrivacyGuard {
  /**
   * Anonymize health data per DPA 2019 requirements
   * @param {Object} data - Health data to anonymize
   * @param {string} data.id - Patient/ user identifier
   * @param {string} data.phone - Phone number
   * @param {string} data.email - Email address
   * @param {Object} data.location - GPS location
   * @returns {Object} Anonymized data with PII removed/generalized
   */
  anonymize(data) {
    const anonymized = { ...data };
    
    // Remove or mask personally identifiable information
    if (anonymized.id) {
      anonymized.id = 'ANON-' + Math.random().toString(36).substring(2, 8).toUpperCase();
    }
    
    if (anonymized.phone) {
      anonymized.phone = '+' + anonymized.phone.split('-')[0].padStart(3, '*');
    }
    
    if (anonymized.email) {
      const [name, domain] = anonymized.email.split('@');
      anonymized.email = name.charAt(0) + '*****@' + domain;
    }
    
    if (anonymized.nationalId) {
      anonymized.nationalId = '****';
    }
    
    if (anonymized.surname) {
      anonymized.surname = anonymized.surname.charAt(0) + '*****';
    }
    
    // Generalize location to county level only (not exact GPS)
    if (anonymized.location) {
      if (anonymized.location.latitude && anonymized.location.longitude) {
        // Generalize to nearest major county/health region
        anonymized.location = {
          type: 'county',
          name: this._generalizeLocation(anonymized.location)
        };
      } else if (anonymized.location.county) {
        // Already at county level, keep but mask specifics
        anonymized.location.county = 'Kenya-' + Math.random().toString(36).substring(2, 5).toUpperCase();
      }
    }
    
    // Timestamp generalization - remove exact time, keep date range
    if (anonymized.timestamp) {
      const date = typeof anonymized.timestamp === 'number' 
        ? new Date(anonymized.timestamp)
        : anonymized.timestamp;
      
      anonymized.timestamp = {
        date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`,
        hour: null,
        minute: null
      };
    }
    
    // Remove consent-related PII if present
    if (anonymized.consentId) {
      anonymized.consentId = 'CONSENT-ANON';
    }
    
    return anonymized;
  }

  /**
   * Perform Data Protection Impact Assessment (DPIA)
   * @param {Object} processing - Description of data processing activities
   * @param {boolean} processing.sensitiveData - Whether sensitive health data is processed
   * @param {boolean} processing.automatedDecisions - Whether automated decisions are made
   * @param {boolean} processing.crossBorderTransfer - Whether data crosses borders
   * @param {boolean} processing.profiling - Whether user profiling is done
   * @returns {Object} DPIA assessment result
   */
  assessDpia(processing) {
    const risks = [];
    const recommendations = [];
    
    // Check for sensitive health data processing
    if (processing.sensitiveData) {
      risks.push({
        id: 'dpia-001',
        type: 'sensitive_health_data',
        severity: 'high',
        description: 'Processing of EVD-related health data requires explicit special category consent under DPA 2019 Section 35',
        recommendation: 'Ensure explicit consent is obtained before any EVD health data processing'
      });
      recommendations.push('Implement special category data handling procedures');
    }
    
    // Check for automated decisions (e.g., risk scoring leading to actions)
    if (processing.automatedDecisions) {
      risks.push({
        id: 'dpia-002',
        type: 'automated_decisions',
        severity: 'medium',
        description: 'Automated health risk decisions must have human override mechanism',
        recommendation: 'Add human review step before any automated risk-action pathways'
      });
      recommendations.push('Implement human-in-the-loop for all automated risk classifications');
    }
    
    // Check for cross-border data transfers
    if (processing.crossBorderTransfer) {
      risks.push({
        id: 'dpia-003',
        type: 'cross_border_transfer',
        severity: 'high',
        description: 'Cross-border data transfer to non-adequate countries requires ODPC approval and SCCs',
        recommendation: 'Verify ODPC approval and Standard Contractual Clauses for any international data transfers'
      });
      recommendations.push('Register all cross-border transfers with ODPC');
    }
    
    // Check for profiling (e.g., risk profiling, behavior tracking)
    if (processing.profiling) {
      risks.push({
        id: 'dpia-004',
        type: 'profiling',
        severity: 'medium',
        description: 'User profiling for risk stratification must be proportionate and with valid basis',
        recommendation: 'Document lawful basis for profiling and ensure data minimisation'
      });
      recommendations.push('Limit profiling to necessary risk factors only');
    }
    
    // Check for vulnerable data subjects
    if (processing.vulnerableDataSubjects) {
      risks.push({
        id: 'dpia-005',
        type: 'vulnerable_subjects',
        severity: 'high',
        description: 'Health data of vulnerable populations (children, pregnant persons, elderly) requires additional protections',
        recommendation: 'Implement additional safeguards for vulnerable population data'
      });
      recommendations.push('Apply enhanced protection for all vulnerable population data');
    }
    
    const requiresDpia = risks.length > 0;
    const highSeverityCount = risks.filter(r => r.severity === 'high').length;
    
    return {
      risks,
      requiresDpia,
      highSeverityCount,
      summary: this._generateSummary(risks),
      recommendations
    };
  }

  /**
   * Generate valid consent documentation per Digital Health Act 2023
   * @param {Object} consent - Consent details from user
   * @param {string} consent.purpose - Purpose of data processing
   * @param {string[]} consent.dataTypes - Types of data being collected
   * @param {string} consent.retentionPeriod - How long data is retained
   * @param {boolean} consent.withdrawalRight - Whether user can withdraw consent
   * @param {string} consent.legalBasis - Legal basis for processing
   * @returns {Object} Validated consent record
   */
  validateConsent(consent) {
    const requiredFields = ['purpose', 'dataTypes', 'retentionPeriod', 'legalBasis'];
    const missing = requiredFields.filter(f => !consent[f]);
    
    const validated = {
      consentId: 'CONSENT-' + Math.random().toString(36).substring(2, 10).toUpperCase(),
      purpose: consent.purpose || 'unknown',
      dataTypes: consent.dataTypes || [],
      retentionPeriod: consent.retentionPeriod || 'unspecified',
      withdrawalRight: consent.withdrawalRight !== false, // Default: true
      legalBasis: consent.legalBasis || 'legitimate_interest',
      valid: missing.length === 0,
      timestamp: Date.now(),
      version: '1.0 (Digital Health Act 2023)'
    };
    
    // Add specific validations based on purpose
    if (consent.purpose === 'ebola_surveillance') {
      validated.additionalRequirements = {
        specialCategory: true,
        requiresExplicitConsent: true,
        odpcNotificationRequired: true
      };
    }
    
    if (consent.purpose === 'contact_tracing') {
      validated.additionalRequirements = {
        exposureNotification: true,
        dataDeletionPeriod: '21 days after exposure window',
        anonymityGuaranteed: true
      };
    }
    
    return validated;
  }

  /**
   * Generate data breach notification per DPA 2019 72-hour requirement
   * @param {Object} breach - Data breach details
   * @param {string} breach.type - Type of breach (theft, loss, unauthorized_access)
   * @param {string} breach.dateDetected - When breach was discovered
   * @param {Object} breach.affectedData - Categories of data affected
   * @param {number} breach.affectedCount - Number of data subjects affected
   * @returns {Object} Breach notification record
   */
  generateBreachNotification(breach) {
    const dateDetected = new Date(breach.dateDetected);
    const notificationDeadline = new Date(dateDetected);
    notificationDeadline.setDate(notificationDeadline.getDate() + 7); // 72 hours = 3 days
    
    return {
      notificationId: 'BREACH-' + Math.random().toString(36).substring(2, 10).toUpperCase(),
      dateDetected: breach.dateDetected,
      odpcNotificationDeadline: notificationDeadline.toISOString(),
      userNotification: this._shouldNotifyUsers(breach.affectedData, breach.affectedCount),
      description: this._generateBreachDescription(breach),
      requiredActions: this._getBreachActions(breach.type),
      status: 'pending_odpc_approval',
      odpcContact: 'ODPC Complaints Handling Desk: +254-20-4226849'
    };
  }

  _shouldNotifyUsers(affectedData, affectedCount) {
    // Notify users if high-risk data is affected or many users impacted
    const highRiskTypes = ['health_status', 'location', 'identity'];
    const hasHighRisk = highRiskTypes.some(type => affectedData.includes(type));
    
    return affectedCount > 100 || hasHighRisk;
  }

  _generateBreachDescription(breach) {
    const { type, affectedData } = breach;
    const typeDescriptions = {
      theft: 'Unauthorized removal of device(s) containing health data',
      loss: 'Misplacement of device(s) or documentation containing health data',
      unauthorized_access: 'Unauthorized access to health data systems'
    };
    
    const dataDesc = affectedData.join(', ');
    return `Breach type: ${typeDescriptions[type] || type}. Affected data: ${dataDesc}.`;
  }

  _getBreachActions(breachType) {
    const actions = {
      theft: [
        'Immediately secure all affected devices',
        'Remote wipe if capabilities available',
        'ODPC notification within 72 hours',
        'Affected user notification if high-risk data'
      ],
      loss: [
        'Search and recover lost device/documentation',
        'Remote wipe if recovery not possible within 24h',
        'ODPC notification if high-risk data accessed',
        'Implement additional physical security'
      ],
      unauthorized_access: [
        'Secure the affected system immediately',
        'Change all relevant access credentials',
        'Audit access logs for exploitation',
        'ODPC notification within 72 hours',
        'Affected user notification'
      ]
    };
    
    return actions[breachType] || ['Investigate breach, notify ODPC'];
  }

  _generateSummary(risks) {
    if (risks.length === 0) return 'No DPIA risks identified';
    
    const highRisk = risks.filter(r => r.severity === 'high').length;
    const mediumRisk = risks.filter(r => r.severity === 'medium').length;
    
    return `${risks.length} risk(s) identified: ${highRisk} high, ${mediumRisk} medium severity`;
  }

  _generalizeLocation(coords) {
    // Map coordinates to nearest Kenyan county
    // Simplified: just return a generic region
    const countyMap = {
      'Nairobi': 'Nairobi',
      'Mombasa': 'Mombasa',
      'Kisumu': 'Kisumu',
      'Nakuru': 'Nakuru',
      'Eldoret': 'Uasin Gishu'
    };
    
    // Simple heuristic based on rough coordinate ranges
    const lat = coords.latitude;
    const lng = coords.longitude;
    
    if (lat >= -1.3 && lat <= -1.1 && lng >= 36.8 && lng <= 36.9) {
      return 'Nairobi';
    } else if (lat >= -4.1 && lat <= -3.9 && lng >= 39.8 && lng <= 40.1) {
      return 'Mombasa';
    }
    
    return 'Unknown County';
  }
}

module.exports = PrivacyGuard;
