// App entry — Afya Yangu (Mlinzi) per spec v2.0
import RadioChannel from './channels/radio/service.js';
import SmsChannel from './channels/sms/service.js';
import UssdChannel from './channels/ussd/service.js';
import WhatsAppChannel from './channels/whatsapp/service.js';
import SocialMediaChannel from './channels/social/service.js';
import ChwChannel from './channels/chw/service.js';
import NativeAppChannel from './channels/app/service.js';
import PrivacyGuard from './privacy/service.js';
import JaliIntegration from './integrations/jali.js';
import { LiDARRespMonitor } from './sensors/lidar/service.js';
import { AcousticSensor } from './sensors/acoustic/service.js';
import { Blesensor } from './sensors/ble/service.js';
import { GpsSensor } from './sensors/gps/service.js';
import { ImuSensor } from './sensors/imu/service.js';
import { CameraSensor } from './sensors/camera/service.js';
import { NfcSensor } from './sensors/nfc/service.js';
import { PpgSensor } from './sensors/ppg/service.js';
import { WearableIntegration } from './sensors/wearable/service.js';
import * as Tier1 from './tiers/tier1/features.js';
import * as Tier2 from './tiers/tier2/features.js';
import * as Tier3 from './tiers/tier3/features.js';
import * as Tier4 from './tiers/tier4/features.js';

const DEFAULT_CONFIG = {
  county: 'Nairobi',
  language: 'en',
  defaultChannel: 'native',
  region: 'KE'
};

class AfyaYanguApp {
  constructor(userConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...userConfig };
    this.privacy = new PrivacyGuard();
    this.channels = {
      radio: new RadioChannel(),
      sms: new SmsChannel(),
      ussd: new UssdChannel(),
      whatsapp: new WhatsAppChannel(),
      social: new SocialMediaChannel(),
      chw: new ChwChannel(),
      native: new NativeAppChannel()
    };
    this.sensors = {
      acoustic: new AcousticSensor(),
      ble: new Blesensor(),
      camera: new CameraSensor(),
      gps: new GpsSensor(),
      imu: new ImuSensor(),
      lidar: new LiDARRespMonitor(),
      nfc: new NfcSensor(),
      ppg: new PpgSensor(),
      wearable: new WearableIntegration()
    };
    this.jali = new JaliIntegration({
      baseUrl: 'https://jala.kenya.gov.ke/api',
      apiKey: this.config.jaliApiKey
    });
    
    // Initialize tiers with their feature mappings
    this.tiers = {
      tier1: {
        features: Tier1.default,
        description: 'Earns the Download - core utility features',
        activated: new Set()
      },
      tier2: {
        features: Tier2.default,
        description: 'Earns the Return Visit - retention features',
        activated: new Set()
      },
      tier3: {
        features: Tier3.default,
        description: 'Earns the Home Screen - persistence features',
        activated: new Set()
      },
      tier4: {
        features: Tier4.default,
        description: 'Outbreak Superpower - dormant infrastructure',
        activated: new Set()
      }
    };
    
    this.initialized = false;
    this.featureActivationCount = { tier1: 0, tier2: 0, tier3: 0, tier4: 0 };
  }

  /**
   * Initialize the application
   */
  async init() {
    if (this.initialized) return;
    
    // Initialize privacy settings with consent
    const consent = this.privacy.validateConsent({
      purpose: 'health_companion',
      dataTypes: ['demographic', 'clinical', 'location'],
      retentionPeriod: '24 months',
      withdrawalRight: true,
      legalBasis: 'legitimate_interest'
    });
    
    console.log('Consent validated:', consent.consentId);
    
    // Initialize native app
    this.channels.native.init(this.config);
    
    // Set up sensor monitoring
    this._setupSensors();
    
    // Activate Tier 1 features by default (core utility)
    this.activateTierFeatures('tier1');
    
    this.initialized = true;
    console.log('Afya Yangu initialized successfully');
    console.log('Active tiers:', Object.keys(this.tiers).filter(t => this.tiers[t].activated.size > 0));
  }

  _setupSensors() {
    // Set up GPS geofencing for Nairobi region
    this.sensors.gps.setGeofence({
      latitude: -1.2921,
      longitude: 36.8219,
      radius: 10000,
      riskType: 'general',
      alertLevel: 'low'
    });
    
    // Initialize BLE scanning for proximity alerts
    const ebids = this.sensors.ble.scan({ duration: 3 });
    console.log(`BLE scan found ${ebids.length} identifiers`);
    
    // Initialize LiDAR respiration monitor (dormant until outbreak)
    console.log('LiDAR respiration monitoring ready (dormant)');
    
    console.log('Sensors initialized');
  }

  /**
   * Activate features for a specific tier
   * @param {string} tier - Tier name ('tier1', 'tier2', 'tier3', 'tier4')
   * @param {boolean} force - Force activation regardless of prerequisites
   */
  activateTierFeatures(tier = 'tier1', force = false) {
    const tierData = this.tiers[tier];
    if (!tierData) {
      console.error(`Unknown tier: ${tier}`);
      return;
    }
    
    // Check if already activated
    if (tierData.activated.size > 0 && !force) {
      console.log(`Tier ${tier} already activated`);
      return;
    }
    
    const features = tierData.features;
    let activatedCount = 0;
    
    for (const featureId of features) {
      try {
        const result = this.activateFeature(featureId);
        if (result && result.status !== 'unknown_feature') {
          tierData.activated.add(featureId);
          this.featureActivationCount[tier]++;
          activatedCount++;
          console.log(`✓ Activated ${featureId} (${tier})`);
        }
      } catch (e) {
        console.warn(`Failed to activate ${featureId}:`, e.message);
      }
    }
    
    console.log(`Tier ${tier} activation complete: ${activatedCount}/${features.length} features activated`);
    
    // Check if we should auto-advance to next tier
    if (tier === 'tier1' && activatedCount >= features.length * 0.8) {
      console.log('Auto-advancing to Tier 2 (return-visit retention)');
      this.activateTierFeatures('tier2');
    }
    
    return { tier, activatedCount, total: features.length };
  }

  /**
   * Activate a specific feature by ID
   * @param {string} featureId - Feature identifier (e.g., FND-001, MED-001)
   * @param {Object} params - Feature-specific parameters
   * @returns {Object} Activation result
   */
  async activateFeature(featureId, params = {}) {
    // Determine tier from feature ID prefix
    const tier = this._getFeatureTier(featureId);
    const tierData = this.tiers[tier];
    
    if (!tierData) {
      return { status: 'error', message: `Unknown tier for feature ${featureId}` };
    }
    
    // Route to appropriate handler based on feature ID pattern
    const result = this._routeFeature(featureId, params);
    
    if (result && result.status !== 'unknown_feature') {
      // Mark feature as activated in its tier
      tierData.activated.add(featureId);
      this.featureActivationCount[tier]++;
      
      // Auto-advance logic based on feature activation
      this._checkTierAdvancement(tier);
    }
    
    return result;
  }

  _getFeatureTier(featureId) {
    // Map feature IDs to tiers based on spec
    const tier1Features = [
      'INF-001', 'INF-002', 'INF-003', 'INF-004', 'INF-005', 'INF-006',
      'TRI-001', 'TRI-002',
      'FND-001', 'FND-002', 'FND-003', 'FND-004', 'FND-005',
      'MED-001', 'MED-002', 'MED-003',
      'REC-001', 'EMG-001', 'EMG-002', 'EMG-003'
    ];
    
    const tier2Features = [
      'FND-006', 'MED-004',
      'INF-007', 'INF-008', 'INF-009'
    ];
    
    const tier3Features = [
      'INF-010', 'REC-002', 'REC-003'
    ];
    
    const tier4Features = [
      'TRI-003'
    ];
    
    if (tier1Features.includes(featureId)) return 'tier1';
    if (tier2Features.includes(featureId)) return 'tier2';
    if (tier3Features.includes(featureId)) return 'tier3';
    if (tier4Features.includes(featureId)) return 'tier4';
    
    // Default to tier1 if unknown
    return 'tier1';
  }

  _routeFeature(featureId, params) {
    // Route feature to appropriate handler based on ID pattern
    switch (featureId.substring(0, 4)) {
      case 'CHAN':
        return this._handleChannelFeature(featureId, params);
      case 'INF':
        return this._handleInfoFeature(featureId, params);
      case 'TRI':
        return this._handleTriageFeature(featureId, params);
      case 'FND':
        return this._handleFacilityFeature(featureId, params);
      case 'MED':
        return this._handleMedicineFeature(featureId, params);
      case 'EMG':
        return this._handleEmergencyFeature(featureId, params);
      case 'REC':
        return this._handleRecordFeature(featureId, params);
      case 'SENS':
        return this._handleSensorFeature(featureId, params);
      default:
        return { status: 'unknown_feature', featureId };
    }
  }

  _handleChannelFeature(featureId, params) {
    return { status: 'channel_feature', featureId, channel: this.config.defaultChannel };
  }

  _handleInfoFeature(featureId, params) {
    const baseResult = {
      status: 'info_feature',
      featureId,
      county: this.config.county
    };
    
    // Add feature-specific info
    const infoMap = {
      'INF-001': { title: 'County Risk Dashboard', content: 'Current EVD risk status for your county' },
      'INF-002': { title: 'Decision Tree', content: 'What should I do based on symptoms?' },
      'INF-003': { title: 'Ebola Info Library', content: 'Comprehensive EVD information' },
      'INF-004': { title: 'Myth-Busting', content: 'Common EVD myths debunked' },
      'INF-005': { title: 'Travel Advisory', content: 'Travel health guidance' },
      'INF-006': { title: 'Hotline Directory', content: 'Contact information for 719 and partners' },
      'INF-007': { title: 'Service Status', content: 'Current health service statuses' },
      'INF-008': { title: 'Health Tips', content: 'Daily health education messages' },
      'INF-009': { title: 'First Aid', content: 'First aid guidance for common emergencies' },
      'INF-010': { title: 'Burial Guidance', content: 'Safe and dignified burial procedures' }
    };
    
    const info = infoMap[featureId];
    if (info) {
      return { ...baseResult, ...info };
    }
    
    return { ...baseResult, title: featureId, content: 'Information feature' };
  }

  _handleTriageFeature(featureId, params) {
    const { symptoms, temperature, exposure } = params;
    
    // Perform symptom check
    const symptomCheck = this._performSymptomCheck({ symptoms, temperature, exposure });
    
    const baseResult = {
      status: 'triage_feature',
      featureId,
      ...symptomCheck
    };
    
    // Tier-specific triage
    if (featureId === 'TRI-003') {
      // Ebola-specific triage (Tier 4)
      return {
        ...baseResult,
        ebolaSpecific: true,
        triageLevel: symptomCheck.riskLevel === 'high' ? 'isolate_immediately' : 'monitor',
        recommendation: symptomCheck.riskLevel === 'high' 
          ? 'Isolate and call 719 immediately'
          : 'Monitor for 21 days, seek care if symptoms develop'
      };
    }
    
    return baseResult;
  }

  _performSymptomCheck({ symptoms, temperature, exposure }) {
    // Basic Ebola symptom screening
    const ebolaSymptoms = ['fever', 'headache', 'muscle_pain', 'sore_throat', 'vomiting', 'diarrhea'];
    const foundSymptoms = (symptoms || []).filter(s => ebolaSymptoms.includes(s));
    
    let riskLevel = 'low';
    if (foundSymptoms.length >= 3) riskLevel = 'high';
    else if (foundSymptoms.length >= 1) riskLevel = 'medium';
    
    // Check temperature
    if (temperature && typeof temperature === 'number' && temperature > 38.5) {
      riskLevel = riskLevel === 'low' ? 'medium' : 'high';
    }
    
    // Check exposure
    if (exposure) {
      riskLevel = 'high';
    }
    
    return {
      riskLevel,
      foundSymptoms,
      temperature,
      recommendation: this._getSymptomRecommendation(riskLevel)
    };
  }

  _getSymptomRecommendation(riskLevel) {
    const recs = {
      low: 'Monitor symptoms, practice standard hygiene, call 719 if worsening',
      medium: 'Contact hotline 719, self-monitor for 48 hours, isolate if symptoms progress',
      high: 'Isolate immediately, call 719, seek emergency treatment at nearest isolation unit'
    };
    return recs[riskLevel] || 'Consult healthcare provider';
  }

  _handleFacilityFeature(featureId, params) {
    // Use GPS for location-based facility search
    const location = this.sensors.gps.getCurrentLocation();
    
    return {
      status: 'facility_search',
      featureId,
      location,
      county: this.config.county,
      ...params
    };
  }

  _handleMedicineFeature(featureId, params) {
    const { code, batchNumber } = params;
    
    // Medicine verification logic
    const verification = this._verifyMedicine(code, batchNumber);
    
    return {
      status: 'medicine_verification',
      featureId,
      verification,
      ...params
    };
  }

  _verifyMedicine(code, batchNumber) {
    // In production: check against PPB (Pharmacy and Poisons Board) database
    // For now, return structured verification result
    return {
      code,
      batchNumber,
      verified: code && code.length > 0, // Placeholder verification
      verificationTime: Date.now(),
      source: 'PPB database check',
      expirationDate: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() // 30 days
    };
  }

  _handleEmergencyFeature(featureId, params) {
    const { location, type, severity, symptoms } = params;
    
    // Trigger emergency protocols
    this._triggerEmergency({ location, type, severity, symptoms });
    
    return {
      status: 'emergency_triggered',
      featureId,
      timestamp: Date.now(),
      location,
      type,
      severity
    };
  }

  _triggerEmergency(params) {
    const { location, type, severity, symptoms } = params;
    
    console.log('🚨 EMERGENCY PROTOCOL ACTIVATED 🚨');
    console.log('Type:', type, 'Severity:', severity);
    console.log('Location:', location);
    console.log('Symptoms:', symptoms);
    
    // Emergency response actions:
    // 1. Send SMS to emergency contacts
    // 2. Notify nearest treatment facility via SMS/USSD
    // 3. Activate geofenced alert perimeter
    // 4. Potentially alert PHEOC via integration
    // 5. Prepare isolation unit notification
    
    // In production would integrate with:
    // - SMS channel (CHAN-001) for emergency broadcasts
    // - GPS geofencing (sensors/gps)
    // - PHEOC system integration
    // - CHW channel (CHAN-005) for community alerts
  }

  _handleRecordFeature(featureId, params) {
    // Return family health wallet state
    const wallet = this._getHealthWallet();
    
    return {
      status: 'record_feature',
      featureId,
      wallet,
      ...params
    };
  }

  _getHealthWallet() {
    // Return family health wallet state
    return {
      userId: 'U-' + Math.random().toString(36).substring(2, 10),
      county: this.config.county,
      records: {
        immunizations: [],
        pregnancies: [],
        chronicConditions: [],
        medications: [],
        recentSymptoms: [],
        exposureEvents: []
      },
      lastUpdated: Date.now(),
      version: '1.0',
      privacy: {
        anonymized: false,
        consentGiven: true
      }
    };
  }

  _handleSensorFeature(featureId, params) {
    const sensorType = featureId.replace('SENS-', '').toLowerCase();
    const sensor = this.sensors[sensorType];
    
    if (!sensor) return { status: 'unknown_sensor', featureId };
    
    // Route to appropriate sensor method
    const methodMap = {
      'acoustic': 'analyzeCough',
      'ble': 'scan',
      'camera': 'analyzeFrame',
      'gps': 'getCurrentLocation',
      'imu': 'processAccelerometer',
      'lidar': 'processFrame',
      'nfc': 'readTag',
      'ppg': 'calculateHeartRate',
      'wearable': 'syncDeviceData'
    };
    
    const method = methodMap[sensorType];
    if (sensor[method]) {
      const data = sensor[method](...(params[sensorType] || []));
      return {
        status: 'sensor_data',
        featureId,
        sensorType,
        data
      };
    }
    
    return { status: 'sensor_available', featureId, sensorType };
  }

  _checkTierAdvancement(currentTier) {
    const tierOrder = ['tier1', 'tier2', 'tier3', 'tier4'];
    const currentIndex = tierOrder.indexOf(currentTier);
    
    if (currentIndex < tierOrder.length - 1) {
      const nextTier = tierOrder[currentIndex + 1];
      const currentFeatureCount = this.featureActivationCount[currentTier];
      const totalFeatures = this.tiers[currentTier].features.length;
      
      // Advance if 70% of current tier features activated
      if (currentFeatureCount / totalFeatures >= 0.7) {
        console.log(`Auto-advancing from ${currentTier} to ${nextTier}`);
        this.activateTierFeatures(nextTier);
      }
    }
  }

  /**
   * Process input from any channel
   * @param {string} channel - Channel name
   * @param {Object} data - Channel-specific data
   * @returns {Promise<Object>} Processed response
   */
  async processChannelInput(channel, data) {
    const handler = this.channels[channel];
    if (!handler) {
      return { error: 'Unknown channel', channel };
    }
    
    // Special handling for WhatsApp with JALI integration
    if (channel === 'whatsapp') {
      return this.jali.processMessage(data);
    }
    
    if (channel === 'ussd') {
      return handler.handleSession(data.sessionId, data.text);
    }
    
    // Activate relevant features based on input
    await this._autoActivateFeatures(channel, data);
    
    return handler.processMessage ? handler.processMessage(data) : { status: 'ok' };
  }

  _autoActivateFeatures(channel, data) {
    // Auto-activate features based on channel input
    if (channel === 'ussd' && data.text) {
      // USSD menu selections could trigger feature activation
      const selection = parseInt(data.text);
      if (selection >= 1 && selection <= 3) {
        this.activateFeature(`INF-00${selection}`);
      }
    }
    
    if (channel === 'whatsapp') {
      const body = data.body?.toLowerCase() || '';
      if (body.includes('facility')) {
        this.activateFeature('FND-001');
      } else if (body.includes('symptom')) {
        this.activateFeature('TRI-001');
      } else if (body.includes('hotline')) {
        this.activateFeature('INF-006');
      }
    }
  }

  /**
   * Get current app state
   * @returns {Object} Complete app state
   */
  getState() {
    return {
      config: this.config,
      initialized: this.initialized,
      tiers: {
        tier1: {
          activated: Array.from(this.tiers.tier1.activated),
          count: this.featureActivationCount.tier1,
          total: this.tiers.tier1.features.length,
          description: this.tiers.tier1.description
        },
        tier2: {
          activated: Array.from(this.tiers.tier2.activated),
          count: this.featureActivationCount.tier2,
          total: this.tiers.tier2.features.length,
          description: this.tiers.tier2.description
        },
        tier3: {
          activated: Array.from(this.tiers.tier3.activated),
          count: this.featureActivationCount.tier3,
          total: this.tiers.tier3.features.length,
          description: this.tiers.tier3.description
        },
        tier4: {
          activated: Array.from(this.tiers.tier4.activated),
          count: this.featureActivationCount.tier4,
          total: this.tiers.tier4.features.length,
          description: this.tiers.tier4.description
        }
      },
      sensors: Object.keys(this.sensors).map(k => ({
        name: k,
        available: !!this.sensors[k]
      })),
      channels: Object.keys(this.channels).map(k => ({
        name: k,
        status: 'active'
      })),
      privacy: this.privacy ? 'configured' : 'not_configured',
      jali: this.jali ? 'connected' : 'disconnected'
    };
  }
}

// Export default instance for easy use
const app = new AfyaYanguApp();

export default app;
export { AfyaYanguApp };
