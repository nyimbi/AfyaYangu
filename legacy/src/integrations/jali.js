// jali.js — Kenya MoH WhatsApp chatbot (JALI) integration
/**
 * JALI (Jenga Adui na Lucha za Afya) - Kenya Ministry of Health WhatsApp chatbot
 * Integration for Afya Yangu app per spec Section 5.3 CHAN-003
 */

class JaliIntegration {
  /**
   * Initialize JALI connection
   * @param {Object} config - Connection configuration
   * @param {string} config.baseUrl - JALI API base URL
   * @param {string} config.apiKey - Authentication API key
   * @param {string} config.sessionToken - Session token for continued conversations
   */
  constructor(config = {}) {
    this.baseUrl = config.baseUrl || 'https://jala.kenya.gov.ke/api';
    this.apiKey = config.apiKey || '';
    this.sessionToken = config.sessionToken || null;
    this.userProfile = config.userProfile || {};
    this.conversationHistory = [];
  }

  /**
   * Process incoming WhatsApp message through JALI
   * @param {Object} message - WhatsApp message object
   * @param {string} message.from - Sender phone number (WA ID format)
   * @param {string} message.body - Message text content
   * @param {string[]} message.tags - Message tags (if any)
   * @returns {Promise<Object>} JALI bot response
   */
  async processMessage(message) {
    const { from, body } = message;
    const lowerBody = body.toLowerCase().trim();
    
    // Update user profile from contact
    this._updateUserProfile(from, body);
    
    // Route message to appropriate handler
    let response;
    
    // Ebola-specific inquiries
    if (lowerBody.includes('ebola') || lowerBody.includes('ebv') || lowerBody.includes('ebvd')) {
      response = this._handleEbolaInquiry(body);
    }
    // Facility/health service inquiries
    else if (lowerBody.includes('facility') || lowerBody.includes('hospital') || 
             lowerBody.includes('clinic') || lowerBody.includes('health')) {
      response = this._handleFacilityInquiry(body);
    }
    // Symptom reporting
    else if (lowerBody.includes('symptom') || lowerBody.includes('symptoms') || 
             lowerBody.includes('feeling')) {
      response = this._handleSymptomReport(body);
    }
    // Travel advice
    else if (lowerBody.includes('travel') || lowerBody.includes('trip') || 
             lowerBody.includes('journey')) {
      response = this._handleTravelAdvice(body);
    }
    // Hotline information
    else if (lowerBody.includes('hotline') || lowerBody.includes('719') || 
             lowerBody.includes('call')) {
      response = this._handleHotlineInfo(body);
    }
    // General help/query
    else {
      response = this._handleGeneralHelp();
    }
    
    // Store in conversation history
    this.conversationHistory.push({
      from,
      body,
      response: response.text,
      timestamp: Date.now()
    });
    
    // Limit history size
    if (this.conversationHistory.length > 50) {
      this.conversationHistory = this.conversationHistory.slice(-25);
    }
    
    return response;
  }

  _updateUserProfile(from, body) {
    // Extract and update user info from contact
    // In production: would query JALI user profile service
    const phoneMatch = from.match(/^\+?254\d{9}$/);
    if (phoneMatch) {
      this.userProfile.phone = phoneMatch[0];
    }
    
    // Extract name if available in message
    const nameMatch = body.match(/^(ni|jina\s+)?([A-Za-z\s]+)/i);
    if (nameMatch && nameMatch[2]) {
      this.userProfile.name = nameMatch[2].trim().substring(0, 50);
    }
  }

  _handleEbolaInquiry(body) {
    // Comprehensive Ebola information response
    return {
      type: 'ebola_info',
      text: `🦠 EBOLA VIRUS DISEASE INFORMATION

🔍 KEY SYMPTOMS (appear 2-21 days after exposure):
• Fever (temperature > 38.5°C)
• Severe headache
• Muscle pain (myalgia)
• Sore throat
• Vomiting
• Diarrhea
• Rash (may appear on chest, stomach, and back)

⚠️ HIGH RISK IF:
• Recent travel to affected areas
• Contact with EVD patient bodily fluids
• Healthcare worker without proper PPE

📞 IMMEDIATE ACTIONS:
1. Isolate yourself from others
2. Call toll-free hotline: 719 (available 24/7)
3. Seek nearest treatment unit
4. Avoid direct contact with bodily fluids

💡 PROTECTION:
• Frequent handwashing with soap
• Avoid bushmeat consumption
• Use safe burial practices
• Avoid handling bodies of EVD victims

Would you like:
• More detailed symptom information?
• Facility finder for nearest treatment center?
• Contact tracing information?
• Travel advisories?`,
      suggestions: ['symptoms', 'facility', 'hotline', 'travel']
    };
  }

  _handleFacilityInquiry(body) {
    // Parse county from user message or use default
    const countyMatch = body.match(/(nairobi|mombasa|kisumu|nakuru|eldoret|kenya)/i);
    const county = countyMatch ? countyMatch[1].toLowerCase() : this.userProfile.defaultCounty || 'nairobi';
    
    // In production: would call JALI facility lookup API
    // For now, return structured response
    return {
      type: 'facility_search',
      text: `🏥 FACILITY FINDER - ${county.toUpperCase()}

Searching for health facilities in ${county}...

📍 Available services:
• Treatment units
• Testing sites
• Vaccination points
• Pharmacies

🔍 Please specify:
• Exact suburb or area, OR
• Type of service needed

Alternatively, send your GPS location for automatic nearest-facility search.`,
      suggestions: ['area', 'type', 'gps'],
      county: county
    };
  }

  _handleSymptomReport(body) {
    // Parse symptoms from user message
    const commonSymptoms = ['fever', 'headache', 'cough', 'sore throat', 
                           'vomiting', 'diarrhea', 'rash', 'muscle pain',
                           'fatigue', 'difficulty breathing'];
    
    const foundSymptoms = commonSymptoms.filter(s => 
      lowerBody.includes(s)
    );
    
    // Build response with risk assessment
    let riskLevel = 'low';
    if (foundSymptoms.includes('fever') && foundSymptoms.includes('diarrhea')) {
      riskLevel = 'high';
    } else if (foundSymptoms.includes('fever') || foundSymptoms.includes('cough')) {
      riskLevel = 'medium';
    }
    
    return {
      type: 'symptom_check',
      text: `🤒 SYMPTOM ASSESSMENT

🔍 Detected symptoms: ${foundSymptoms.length > 0 ? foundSymptoms.join(', ') : 'none specific'}

⚠️ Risk level: ${riskLevel.toUpperCase()}

📋 NEXT STEPS:
${riskLevel === 'high' 
  ? '• Isolate immediately\n• Call 719 now\n• Avoid contact with others'
  : riskLevel === 'medium'
    ? '• Monitor for 48 hours\n• Check temperature regularly\n• Call 719 if worsening'
    : '• Practice good hygiene\n• Rest and hydrate\n• Seek care if symptoms develop'
    }

🆘 EMERGENCY SIGNS (seek immediate care):
• Difficulty breathing
• Persistent vomiting
• Confusion or disorientation
• High fever (>39°C) unresponsive to medication

Would you like to:
• Get nearby facility information?
• Speak with a health professional?
• Learn about self-monitoring?`,
      suggestions: ['facility', 'professional', 'monitoring'],
      riskLevel,
      foundSymptoms
    };
  }

  _handleTravelAdvice(body) {
    // Check for travel destinations mentioned
    const destinationMatch = body.match(/(nairobi|mombasa|kisumu|nairobi|naivasha|malindi)/i);
    const originMatch = body.match(/(from\s+([A-Za-z\s]+?)(?:\s+to|\s*$))/i);
    
    return {
      type: 'travel_advisory',
      text: `🌍 TRAVEL ADVICE

📍 General EVD travel precautions:

✅ SAFE PRACTICES:
• Standard travel hygiene
• Handwashing facilities at airports
• Health screening at entry points
• No travel restrictions currently for general travel

⚠️ CONSIDERATIONS:
• If traveling from affected counties: enhanced screening
• If traveling to healthcare facilities: use verified facilities
• Monitor health for 21 days after return from affected areas

🛂 AT KENYA PORTS:
• Temperature screening at all major entry points
• Health declaration forms
• Possible quarantine if symptoms develop

📞 IF YOU DEVELOP SYMPTOMS DURING/TRAVEL:
• Inform flight crew or border officials immediately
• Isolate and call 719
• Do not use public transport

Safe travels! Would you like:
• Specific destination advisories?
• Pre-travel health checklist?
• Post-travel monitoring guidance?`,
      suggestions: ['destination', 'checklist', 'post-travel']
    };
  }

  _handleHotlineInfo(body) {
    return {
      type: 'hotline_info',
      text: `📞 KENYA HEALTH HOTLINE (719)

� available 24 hours a day, 7 days a week

🔹 Toll-free number: 719 (from any Safaricom, Airtel, or Telkom line)
🔹 Alternative: +254-20-4226849 (ODPC/PHEOC line)
🔹 WhatsApp JALI chatbot: Available through this app

🕐 What to expect when you call:
1. Automated menu or operator greeting
2. Describe your symptoms or concern
3. Receive guidance based on risk assessment
4. Referral to nearest facility if needed
5. Callback options for follow-up

📱 WhatsApp alternatives:
• Send 'Hello' to JALI bot within this app
• Get instant symptom assessment
• Facility finder requests
• General health information

🎯 When to call 719:
• If you have EVD symptoms + travel/contact risk
• If you've been identified as a contact of confirmed case
• If you need isolation facility location
• For any health concern requiring immediate advice

Your call is confidential and operators are trained in data privacy per DPA 2019.`,
      suggestions: ['symptoms', 'facility', 'contact']
    };
  }

  _handleGeneralHelp() {
    return {
      type: 'general_help',
      text: `🤝 AFYA YANGU - WELCOME

I'm JALI, your health companion chatbot. I can help you with:

🔹 Ebola information and risk assessment
🏥 Finding nearby health facilities
🤒 Symptom checking and advice
🌍 Travel health advisories
📞 Health hotline (719) connection
💊 Medicine verification
🏠 Family health wallet

💬 Just type what you need help with, or choose from:
• 'Ebola info' - Learn about symptoms and prevention
• 'Find facility' - Locate nearest health center
• 'Check symptoms' - Assess your health status
• 'Travel advice' - Travel health guidance
• 'Hotline' - Contact 719

🔒 All conversations are confidential and per Kenya's Data Protection Act 2019.

How can I help you today?`,
      suggestions: ['ebola info', 'find facility', 'check symptoms', 'travel advice', 'hotline']
    };
  }
}

module.exports = JaliIntegration;
