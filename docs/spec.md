# Product Specification Document

## Project Mlinzi / Afya Yangu

### A National Health Companion with Dormant Outbreak Superpowers

| | |
|---|---|
| **Document Version** | 2.0 (Supersedes v1.0) |
| **Date** | October 7, 2026 |
| **Classification** | Public — For Ministry of Health, County Health Teams, Telcos, and Implementing Partners |
| **Status** | Draft for Review |
| **Prepared for** | Kenya Ministry of Health, PHEOC, County Health Management Teams |
| **Product Owner** | [TBD — MoH Digital Health Agency / Implementing Partner] |

---

> **⚠️ Verification Note.** Specific epidemiological figures, hotline codes, platform names, and case counts referenced in this document are drawn from open reporting and prior drafts and have **not been independently confirmed**. All operational specifics must be validated against MoH / PHEOC official channels before publication, external distribution, or engineering commitment. The product design logic is independent of these specifics.

---

## Table of Contents

**Part I — Strategy**
1. Executive Summary
2. Background and Problem Statement
3. Product Vision, Positioning, and Design Principles
4. Target Users and Personas
5. The Channel Architecture (Channels 0–6)
6. Information and Content Strategy

**Part II — Feature Specifications**
7. Feature Architecture Overview and Tier Model
8. Tier 1 — Earns the Download
9. Tier 2 — Earns the Return Visit
10. Tier 3 — Earns the Home Screen
11. Tier 4 — The Outbreak Superpower
12. Cross-Cutting Feature Specifications

**Part III — Sensors and Sensing**
13. Sensor Capability Matrix
14. Detailed Sensor Specifications

**Part IV — Engineering**
15. Technical Architecture
16. Offline-First and Low-Resource Design
17. Data Privacy, Security, and Regulatory Compliance
18. Integration with Existing Systems
19. AI, Analytics, and Prediction

**Part V — Go-to-Market and Operations**
20. Distribution, Partnerships, and Growth Strategy
21. Rollout and Phasing
22. Success Metrics and Evaluation
23. Risks and Mitigations
24. Operational Considerations

**Part VI — Appendices**
A. Glossary
B. Feature Index by ID
C. References
D. Open Questions and Decisions Required

---

# PART I — STRATEGY

---

## 1. Executive Summary

Kenya has confirmed an imported Ebola Virus Disease (EVD) case and activated national response mechanisms including a toll-free hotline, a WhatsApp chatbot, laboratory networks at border points, isolation and treatment units, and healthcare worker training. National monitoring systems already track ICU bed availability and priority health indicators.

Despite this, a critical gap remains: **there is no citizen-facing tool that turns every phone in Kenya into a personal safety device, a community reporting node, and a durable health companion.**

Project **Mlinzi** (Swahili: *guardian*), delivered under the public-facing brand **Afya Yangu** (*My Health*), closes that gap.

### The central strategic insight

An app cannot be built for Ebola alone. With one reported case in a country of 50 million, personal risk is negligible. A fear-driven "Ebola app" would be downloaded by a few hundred thousand people, opened twice, and deleted when the news cycle moves on — leaving nothing in place for the next outbreak.

**Therefore:**

1. **Information is delivered primarily through channels people already use** — WhatsApp, SMS, USSD, radio, social media, and community health workers. No download required. This is the *reach* product.
2. **The app is a genuine, year-round health utility** — facility finder, medicine verifier, family health wallet, immunisation tracker, medication reminders. This is the *retention* product.
3. **Outbreak capability is dormant infrastructure** — symptom surveillance, proximity alerting, geofenced risk alerts, contact tracing, LiDAR respiration monitoring — that activates when PHEOC triggers it. This is the *response* product.

A user who installs Afya Yangu for the facility finder in November automatically has outbreak surveillance capability in their pocket in March.

### Scope of this document

This specification covers:

- Seven delivery channels, from radio to native app
- A four-tier feature model spanning 80+ discrete features
- Eleven categories of smartphone sensor use including LiDAR, acoustic, IMU, PPG, camera, BLE, GPS, NFC, and wearable integration
- Full data protection architecture compliant with Kenya's Data Protection Act 2019, ODPC health data guidance, and the Digital Health Act 2023
- Integration with ADaM, JALI, 719, and PHEOC systems
- Distribution, zero-rating, phasing, metrics, and risk framework

---

## 2. Background and Problem Statement

### 2.1 Current Situation

Kenya's Ebola preparedness and response posture includes:

- Isolation and treatment units across the country, with plans for further expansion
- Thousands of healthcare providers trained in Ebola prevention and case management
- Mobile laboratories at border points including Busia and Lwakhakha
- Activation of a toll-free reporting platform
- A WhatsApp chatbot for public information
- Daily health dashboards tracking ICU bed availability and priority indicators
- Screening of hundreds of thousands of travelers
- Hundreds of samples tested through the national laboratory network

### 2.2 The Last-Mile Gap

Official systems operate at the health-system layer: surveillance, laboratory, case management, contact tracing by trained teams. What is missing is the **citizen layer**:

| Gap | Consequence |
|---|---|
| No self-triage tool | People with fever don't know whether to stay home, go to a clinic, or call a hotline |
| No persistent monitoring tool | Contacts under 21-day observation have no structured way to log symptoms |
| No citizen reporting channel beyond a phone number | Reporting requires a call, which many avoid |
| No localized risk awareness | National case counts are abstract; people don't know their own neighbourhood status |
| No consented contact-tracing assistance | Manual recall is unreliable; phone data is unused |
| No passive surveillance | Symptom signals never reach the health system until someone presents at a facility |
| No misinformation counter | Rumours spread faster than official correction |

### 2.3 Lessons from Comparable Systems

**AVADAR (Auto-Visual AFP Detection and Reporting).** Deployed across ten African countries for polio surveillance, AVADAR equipped community health workers with a mobile reporting tool. SMS-based alerts sent automatic notifications to surveillance officers, achieving real-time detection in high-risk areas. Key lesson: **CHW-mediated mobile reporting works, when the tool is simple and the alerting is automatic.**

**Offline-first modular mHealth platforms.** Research from ACM MobiSys and similar venues demonstrates that mobile clients operating as the source of truth, with opportunistic backend synchronisation, can function reliably in low-connectivity environments. Key lesson: **assume no connectivity, treat sync as a bonus.**

**COVID-19 exposure notification systems.** The DESIRE architecture combined centralised and decentralised approaches using Ephemeral Bluetooth Identifiers and Private Encounter Tokens, with declarations routed through a trusted proxy to prevent social graph inference. Key lesson: **proximity notification is feasible and privacy-preservable, but only if it is opt-in and transparent.**

**LiDAR respiration monitoring (LiBre and successors).** Motion-resilient algorithms can decouple device movement from respiration-induced chest displacement, achieving sub-1-breath-per-minute error at distances up to 4 metres, with per-frame processing under 120 ms. Key lesson: **contactless respiratory monitoring is now viable on consumer handsets.**

**On-device acoustic cough detection.** Lightweight models optimised for on-device execution can detect, segment, and classify coughs and respiratory patterns without transmitting raw audio. Key lesson: **passive acoustic surveillance is possible without a privacy catastrophe, if processing stays on-device.**

---

## 3. Product Vision, Positioning, and Design Principles

### 3.1 Vision

> Every person in Kenya carries a guardian in their pocket — a tool that helps them find care today, protect their family tomorrow, and stand together against an outbreak when it comes.

### 3.2 Positioning

**Public-facing name:** Afya Yangu (My Health)

**Internal/programme name:** Mlinzi (Guardian)

**Positioning statement:** *Afya Yangu is the free health companion for every Kenyan family — find care, verify your medicine, keep your family's health records safe, and get warned early when something is going around.*

**What Afya Yangu is not:** It is not "the Ebola app." Ebola is one of the conditions it handles. The brand must survive the outbreak's end.

### 3.3 Design Principles

| # | Principle | Implication |
|---|---|---|
| 1 | **Channels before apps** | Reach is achieved through WhatsApp, SMS, USSD, and radio. The app is the power tier, not the entry point. |
| 2 | **Zero friction to first value** | Under 60 seconds from install to usefulness. No login, no signup, no permissions required for Tier 1. |
| 3 | **Zero-rated or it doesn't count** | Data cost is the single largest barrier. Every channel must be zero-rated or free-at-point-of-use. |
| 4 | **Offline-first, always** | Every core feature works with no connectivity. Sync is opportunistic. |
| 5 | **Triage all causes, not one** | A fever in Kenya is malaria far more often than Ebola. Broad differential triage is clinically correct and commercially durable. |
| 6 | **Anonymity by default** | No account required. Identity is opt-in. |
| 7 | **On-device processing** | Raw sensor data never leaves the phone. Only derived metrics, with consent. |
| 8 | **Local language first** | Swahili and major local languages are primary. English is secondary. |
| 9 | **Answers, not information** | Never "Ebola is a viral haemorrhagic fever." Always "You have fever and no travel history — most likely malaria. Go to a clinic today." |
| 10 | **Every output is forwardable** | Any answer must be shareable as a WhatsApp card. That is how information moves in Kenya. |
| 11 | **Trust through transparency** | Open-source client. Privacy policy in Swahili. In-app data dashboard. Co-branded with trusted institutions. |
| 12 | **Build for the outbreak after this one** | Tier 4 activates for Ebola, cholera, Rift Valley fever, mpox, measles, and the next unknown. |

### 3.4 Non-Goals

- Not a replacement for clinical care, laboratory confirmation, or official case definitions
- Not a diagnostic device; all outputs are triage guidance, not diagnosis
- Not a government surveillance tool; all data sharing is consented and minimised
- Not a paid product; no premium tier, no advertising, no data monetisation
- Not a social network; no public posting, no follower graph

---

## 4. Target Users and Personas

### 4.1 Primary Personas

#### Persona A — Wanjiku, 34, Nairobi (Ruaka)
Market trader, Android Go phone, 1GB data bundle per week, Swahili-first, moderate literacy. Two children aged 4 and 9.
**Needs:** Know if it's safe to send children to school. Find a clinic that takes SHA. Keep immunisation records. Get alerts about her area.
**Friction:** Will not spend data on something she isn't sure she needs. Will not create an account.
**Entry point:** WhatsApp bot forwarded by a friend, then app download for the health wallet.

#### Persona B — Otieno, 28, Kisumu
Boda boda rider, mid-range Android, WhatsApp heavy user, Luo and Swahili, high literacy.
**Needs:** Emergency SOS. Community alerts. Somewhere to check if a medicine is genuine before his mother takes it.
**Friction:** Wants speed. Will abandon anything with a loading screen.
**Entry point:** SOS feature recommended by his SACCO chairman.

#### Persona C — Mama Zawadi, 45, Busia (border)
Community Health Worker, 12 years' experience, Android phone with patchy data.
**Needs:** Structured case reporting that works offline. Automatic alerts to her supervisor. Guidance on what to do with a suspected case. PPE reminders.
**Friction:** Already uses three reporting tools. Will reject a fourth unless it saves time.
**Entry point:** County health team rollout, provisioned account.

#### Persona D — Dr. Kimani, 41, Nairobi
Clinician at a county referral hospital isolation unit.
**Needs:** Prognostic support, structured case reporting, PPE guidance, occupational monitoring for himself and his team.
**Friction:** Clinical tools must be fast and accurate. Will reject anything that adds time.
**Entry point:** Professional rollout, hospital training.

#### Persona E — Hassan, 22, Garissa
University student, iPhone, high data usage, social-media native.
**Needs:** Credible information he can share. County risk dashboard. Air quality.
**Friction:** Will not use anything that looks government-propaganda or outdated.
**Entry point:** TikTok/Instagram content, then app for the dashboard.

#### Persona F — Grace, 52, Siaya
Farmer, basic feature phone, no smartphone, low literacy, Dholuo speaker.
**Needs:** Know what's going around. Know what to do if someone in the household is sick. Reach a health worker.
**Friction:** No smartphone at all. Cannot read long text.
**Entry point:** SMS alerts, USSD menus, community radio, CHW visit.

#### Persona G — Amina, 19, Mombasa
Pregnant, first child, smartphone, Swahili and English.
**Needs:** ANC visit reminders, danger signs, birth planning, facility information.
**Entry point:** ANC clinic recommendation, then Tier 2 retention.

### 4.2 Secondary Personas

- County Health Management Team members
- PHEOC analysts and epidemiologists
- Ministry of Health policymakers
- Pharmacy and chemist staff
- Faith leaders and community mobilisers
- Implementing partner field staff
- School administrators and teachers

### 4.3 Segment Priorities for Launch

| Priority | Segment | Rationale |
|---|---|---|
| P0 | High-risk counties (border, urban) | Direct outbreak relevance |
| P0 | Community Health Workers | Force multiplier for adoption and reporting |
| P1 | Caregivers of children under 5 | Highest health-seeking frequency |
| P1 | Pregnant women | Highest clinic-contact frequency |
| P1 | Chronically ill adults | Highest daily medication need |
| P2 | Students | Highest smartphone penetration and social spread |
| P2 | Boda boda and transport workers | High mobility, high contact, respected voices |
| P3 | General adult population | Reached primarily via non-app channels |

---

## 5. The Channel Architecture

### 5.1 Rationale

An app is the worst possible delivery mechanism for pure information. It requires a download, storage space, data, trust, an account, and a reason to reopen. For "what is Ebola and what should I do," that trade-off is unacceptable for most of the population.

Information must live where people already are. In Kenya that is, in rough order of daily attention: WhatsApp, SMS, radio, Facebook, TikTok, and human conversation.

### 5.2 The Seven Channels

| Ch | Channel | Reach | Cost to User | Primary Role | Owned By |
|---|---|---|---|---|---|
| **0** | **Community radio** | Highest | Free | Daily situation updates, guidance, myth-busting in local language | Partner stations |
| **1** | **SMS (zero-rated)** | Very high | Free | Alerts, hotline number, one-line triage, recall prompts | Telco gateway |
| **2** | **USSD** | High | Free | Symptom reporting, callback requests, facility lookup | Telco |
| **3** | **WhatsApp bot** | High and growing | Data (zero-rated) | Triage, Q&A, myth-busting, guidance, record sharing | Meta Business API |
| **4** | **Social media** | High | Data | Short video, myth-busting, reach, credibility | Organic + paid |
| **5** | **Human intermediaries** | High trust | n/a | Explanation, referral, reassurance, enrolment | CHWs, chemists, faith leaders |
| **6** | **Native app** | Moderate | Data + storage | Persistent state, monitoring, sensors, proximity, records | Owned |

### 5.3 Channel Specifications

#### CHAN-0: Community Radio

**Feature ID:** CHAN-000

**Description:** A structured radio partnership programme delivering daily outbreak and health information in local languages.

**Content formats:**
- 60-second daily situation update (county-level, verified)
- 3-minute myth-busting segment
- Call-in Q&A with a health worker
- Pre-recorded drama vignettes on prevention, care-seeking, and stigma
- Emergency interruption slots for PHEOC alerts

**Language coverage:** Swahili, Dholuo, Luhya (Bukusu, Maragoli), Kalenjin, Kikuyu, Kamba, Somali, Maasai, Turkana, Kisii, Taita, Pokomo, and others by region.

**Distribution:** Partner with Kenya Broadcasting Corporation, Radio Citizen, Radio Jambo, Kiss FM, Ghetto Radio, and county-level stations. Provide scripts and audio files free of charge.

**Measurement:** Airtime logs, station reports, call-in volume, pre/post awareness surveys.

---

#### CHAN-1: SMS (Zero-Rated)

**Feature ID:** CHAN-001

**Description:** Free inbound and outbound SMS for health alerts, triage, and reporting.

**Outbound use cases:**
- Outbreak alerts by county ("New suspected case in Busia. Avoid [location]. Call 719 if unwell.")
- Recall prompts for contacts under observation ("Day 7 of 21. Any fever? Reply 1 for yes, 2 for no.")
- Appointment and immunisation reminders
- Medication adherence reminders
- Misinformation corrections
- Follow-up after a USSD report

**Inbound use cases:**
- Structured symptom reports (e.g., `SYMPTOM FEVER 2 BUSIA`)
- Callback requests (`CALLBACK`)
- Facility lookup (`CLINIC 40100`)

**Format:** 160 characters, plain language, local language option via keyword (e.g., prefix `SW`, `LU`, `KY`).

**Delivery:** Bulk SMS gateway with telco-level zero-rating. Fallback to a shortcode for inbound.

**Critical requirement:** Zero-rated at the telco level. If a user is charged, adoption collapses.

---

#### CHAN-2: USSD

**Feature ID:** CHAN-002

**Description:** A free USSD menu for symptom reporting, callback requests, and facility lookup — for users without data or smartphones.

**Menu structure (illustrative):**

```
*XXX#
1. Report symptoms
   1. Fever
   2. Cough
   3. Diarrhoea / vomiting
   4. Bleeding
   5. Other
   → Send my location? 1=Yes 2=No
   → Request callback? 1=Yes 2=No
2. Find a clinic near me
   → Enter your area code
3. Health information
   1. What is Ebola?
   2. How do I protect my family?
   3. Is it safe to travel?
4. Request a CHW visit
5. Language: English / Kiswahili / Dholuo / ...
```

**Session limits:** Must complete within 2 USSD sessions (approx. 360 characters) to avoid timeouts.

**Integration:** Reports flow into the same backend as app and WhatsApp reports, deduplicated by phone number.

---

#### CHAN-3: WhatsApp Bot (PRIMARY INFORMATION PRODUCT)

**Feature ID:** CHAN-003

**Description:** A conversational agent on WhatsApp delivering triage, information, myth-busting, and record access — with zero download friction.

**Why WhatsApp is the primary product:**
- Near-universal in Kenya
- Supports text, voice notes, images, documents, and location sharing
- Zero user education required
- Inherently forwardable — every answer can be shared
- No app store, no storage, no updates

**Capabilities:**

| Capability | Description |
|---|---|
| **Symptom triage** | Guided conversation → risk classification → recommended action |
| **Voice note triage** | User sends a voice note describing symptoms; speech-to-text in local language; same triage flow |
| **Image triage** | User sends a photo of a rash or wound; routed to a health worker for review with consent |
| **Location-based answers** | User shares location → county/sub-county specific guidance and facility list |
| **Myth-busting** | Keyword-triggered corrections ("Is it true that...?") |
| **Facility lookup** | Nearest facility with services and hours |
| **Callback request** | Escalates to 719 or a CHW |
| **Record retrieval** | Returns immunisation schedule, medication list, or appointment dates for the user's family |
| **Broadcast** | Opt-in county alerts |
| **Forwardable cards** | Every response includes a shareable summary card |

**Languages:** Swahili, English, Dholuo, Luhya, Kalenjin, Kikuyu, Kamba, Somali, Maasai. Voice note support in the top five.

**Privacy:** No account required. Phone number is the only identifier. Conversation history stored for 90 days, then deleted. Users can type `DELETE MY DATA` at any time.

**Accessibility:** Designed for low literacy — short sentences, numbered choices, emoji-supported icons, voice replies available on request.

**Integration:** Shares backend triage engine with CHAN-1, CHAN-2, and CHAN-6 (app). Shares case reports with ADaM. Shares misinformation signals with PHEOC.

---

#### CHAN-4: Social Media

**Feature ID:** CHAN-004

**Description:** Organic and paid content on TikTok, Facebook, Instagram, and X.

**Content types:**
- 15–30 second myth-busting videos in Swahili and Sheng
- "Day in the life" CHW content
- Animated explainers on symptoms and prevention
- Live Q&A with clinicians
- County dashboard screenshots (daily)
- User-generated content from satisfied users (with consent)

**Objectives:** Reach, credibility with youth, misinformation countering, app-install attribution.

**Measurement:** Reach, engagement, shares, install attribution via deep links.

---

#### CHAN-5: Human Intermediaries

**Feature ID:** CHAN-005

**Description:** A structured programme to equip trusted community figures with tools and scripts.

**Target intermediaries:**
- Community Health Workers and Community Health Promoters
- Pharmacy and chemist staff
- Faith leaders (pastors, imams, catechists)
- Boda boda SACCO chairmen
- Market association leaders
- Teachers and school health patrons
- Chama (savings group) leaders

**Tools provided:**
- Printed job aids and flip charts
- CHW-specific app module (see COM-101)
- Referral codes (each intermediary gets a code for attribution)
- Air time / data bundle incentives for verified referrals
- Short training (2 hours) and refresher content

**Rationale:** These people, not app stores, drive adoption in Kenya. Trust transfers through relationships.

---

#### CHAN-6: Native Application

**Feature ID:** CHAN-006

**Description:** The Afya Yangu mobile application for Android and iOS.

**Role:** The power tier. Everything that requires persistent state, sensor access, or offline storage.

**Constraints:**
- APK size under 15 MB (Android), under 40 MB (iOS)
- Android 8.0+ (Go edition compatible)
- iOS 14+
- Full offline functionality for all Tier 1–3 features
- No login required for Tier 1
- Anonymous mode by default

**Detailed feature specification follows in Sections 8–12.**

---

### 5.4 Channel Interoperability

All channels share:

- **A single triage engine** — same clinical logic regardless of entry point
- **A single case-report backend** — deduplicated by phone number
- **A single content repository** — one source of truth for all messaging
- **A single identity model** — phone number, with optional linkage to an app profile
- **A single consent registry** — consent granted on one channel applies across channels

**Cross-channel journeys (examples):**

| Journey | Path |
|---|---|
| Radio → SMS → App | Hears alert on radio → opts in to SMS → downloads app for monitoring |
| WhatsApp → USSD → CHW | Triage on WhatsApp → no data → USSD report → CHW visit |
| App → WhatsApp → SMS | App user shares forwardable card → friend without app continues on WhatsApp → relative on feature phone gets SMS |
| CHW → App → ADaM | CHW logs case in app offline → syncs → flows to ADaM → surveillance officer alerted |

---

## 6. Information and Content Strategy

### 6.1 What People Actually Want to Know

Ordered by real demand, not by what health authorities want to publish:

| Rank | Question | Content Response |
|---|---|---|
| 1 | Is it near me? | County and sub-county case map, updated daily |
| 2 | Is it safe to go to school / market / church / work? | Location-specific guidance, not blanket advice |
| 3 | I have a fever right now — what do I do? | Triage flow (see 6.3) |
| 4 | How do I protect my family? | Household checklist, hygiene guidance, isolation prep |
| 5 | What's true and what's rumour? | Myth-busting library, updated daily |
| 6 | Where do I go if I'm sick, and who do I call? | Facility finder, 719 hotline, USSD callback |
| 7 | Is there a vaccine or treatment? | Honest, current, plain-language status |
| 8 | Can I get tested? Where? Is it free? | Testing site list with cost and hours |
| 9 | How many cases today, and where? | Dashboard, county-level |
| 10 | Is the border / school / church open or closed? | Service status feed |

### 6.2 Content Principles

1. **Answer "what should I do," not "what is X."** Information without action is noise.
2. **Localise to county and sub-county.** National numbers are abstract and unactionable.
3. **Timestamp everything.** "Updated 2 hours ago" builds trust; undated content destroys it.
4. **Local language first**, English second. Never publish English-only for a life-safety message.
5. **Never say "don't panic."** It doesn't work. Give a concrete action instead.
6. **Every answer must be forwardable** as a WhatsApp card or an SMS.
7. **Correct misinformation within 24 hours**, not within a week.
8. **Acknowledge uncertainty.** "We don't know yet" is more trustworthy than a confident guess.
9. **Avoid stigmatising language.** Say "a person who is sick," not "an Ebola victim." Say "the area where a case was reported," not "the Ebola zone."
10. **Design for low literacy.** Short sentences. Numbered options. Icons and emoji. Voice alternative.

### 6.3 The Malaria Trap — Critical Clinical Design Decision

**This is the single most important content and logic decision in the product.**

In Kenya, a fever is overwhelmingly more likely to be malaria, typhoid, a respiratory infection, or another common cause than Ebola. If the tool flags every fever as "possible Ebola," it will:

- Cause panic and flood isolation units with false alarms
- Cause people to **avoid** clinics for fear of being labelled or isolated
- Miss malaria cases — which kill far more Kenyans than Ebola will
- Destroy its own credibility after the first false alarm

**Therefore:**

Afya Yangu implements a **broad febrile-illness triage** that risk-stratifies across common causes and treats Ebola as one branch among several, gated on epidemiological criteria.

**Triage logic outline:**

| Step | Assessment | Branch |
|---|---|---|
| 1 | Does the person have fever or history of fever? | No → general symptom pathway |
| 2 | Duration and severity | <7 days, 7–14 days, >14 days |
| 3 | Accompanying symptoms | Cough, diarrhoea, vomiting, headache, rash, bleeding, joint pain, confusion |
| 4 | **Epidemiological criteria** | Travel to affected area in last 21 days? Contact with a known/suspected case? Attendance at a known exposure site? |
| 5 | **Red flags** | Unexplained bleeding, bleeding gums, blood in stool/vomit, bruising without cause, confusion, difficulty breathing |
| 6 | Pregnancy status | Changes malaria and other risk profiles |
| 7 | Age | Under 5 and over 65 escalate |
| 8 | Risk classification | See below |

**Risk classification and action:**

| Classification | Criteria | Action |
|---|---|---|
| **Emergency** | Red flag present (bleeding, confusion, difficulty breathing) | Call 719 immediately. Go to nearest facility. Isolation precautions if Ebola epi criteria met. |
| **High — Ebola suspicion** | Fever + epidemiological criteria met | Call 719. Do not travel by public transport. Await instructions. |
| **High — other cause** | Fever + severe symptoms but no epi criteria | Go to a facility today. Malaria test. |
| **Moderate** | Fever + mild symptoms, no red flags | Test for malaria within 24 hours. Monitor. Return if worse. |
| **Low** | No fever, mild symptoms | Home care. Monitor. Return if worse. |

**Messaging examples:**

> ❌ *"You may have Ebola. Go to an isolation facility immediately."*
>
> ✅ *"You have fever and no travel history. In Kenya this is most often malaria. Please get a malaria test at a clinic today — it is quick and usually free. If you cannot go today, here is what to watch for. Call 719 if you develop bleeding, confusion, or difficulty breathing."*

**This design makes the tool useful in December when Ebola is forgotten — which is exactly what retention requires.**

### 6.4 Misinformation Response Protocol

| Step | Action | Owner | SLA |
|---|---|---|---|
| 1 | Detect | Community tracker, social listening, WhatsApp flags | Continuous |
| 2 | Triage | PHEOC risk communication team | 4 hours |
| 3 | Verify | Technical working group | 12 hours |
| 4 | Draft correction | Comms team, in all relevant languages | 24 hours |
| 5 | Publish | All channels simultaneously | 24 hours |
| 6 | Monitor | Track spread and sentiment | Ongoing |

**Common myth categories to pre-draft:**

- False cures (herbal, spiritual, pharmaceutical)
- Transmission myths (airborne, mosquito-borne, cursed)
- Vaccine myths
- Conspiracy narratives (population control, bioweapon)
- Stigma narratives (blaming specific communities, counties, or nationalities)
- Burial and body-handling myths

### 6.5 Content Governance

- **Single source of truth:** A content repository managed by MoH Health Promotion Unit
- **Review cycle:** Clinical content reviewed weekly during active outbreak; monthly otherwise
- **Version control:** Every content item has an owner, a reviewer, a date, and a version
- **Localisation workflow:** English draft → clinical review → translation → back-translation → community validation → publish
- **Retirement:** Outdated content is archived, not deleted, for audit
- **Escalation:** Any content error affecting safety triggers immediate review and correction broadcast

---

# PART II — FEATURE SPECIFICATIONS

---

## 7. Feature Architecture Overview and Tier Model

### 7.1 The Four-Tier Model

| Tier | Name | Purpose | Usage Frequency | Ebola-Specific? |
|---|---|---|---|---|
| **1** | Earns the Download | Value in 60 seconds | First session | No |
| **2** | Earns the Return Visit | Repeat utility | Weekly–monthly | No |
| **3** | Earns the Home Screen | Daily habit | Daily | No |
| **4** | Outbreak Superpower | Response capability | Dormant → daily in outbreak | Yes |

**The strategic logic:** A user who installs the app in November for the facility finder automatically has outbreak surveillance in their pocket in March. Tier 4 needs no separate adoption effort because Tiers 1–3 already earned the install.

### 7.2 Feature ID Scheme

| Prefix | Domain |
|---|---|
| CHAN-xxx | Channel features (Section 5) |
| INF-xxx | Information and content |
| TRI-xxx | Triage |
| FND-xxx | Find a facility / service |
| MED-xxx | Medicine and pharmacy |
| EMG-xxx | Emergency |
| REC-xxx | Records and health wallet |
| MON-xxx | Monitoring and reminders |
| SENS-xxx | Sensor-based capabilities |
| LOC-xxx | Location and proximity |
| COM-xxx | Community and CHW |
| ALT-xxx | Alerting |
| AI-xxx | AI and analytics |
| ACC-xxx | Accessibility |
| SEC-xxx | Security and privacy |
| GTM-xxx | Go-to-market |

### 7.3 Tier-to-Feature Map (Summary)

| Tier | Feature IDs |
|---|---|
| **Tier 1** | TRI-001, TRI-002, FND-001…005, MED-001…003, EMG-001…003, INF-001…006, LOC-001 |
| **Tier 2** | MON-001…004, REC-001, MED-004, FND-006, INF-007, ALT-003 |
| **Tier 3** | REC-002…006, MON-005…008, ALT-001…002, INF-008…010, COM-005 |
| **Tier 4** | TRI-003, MON-009, COM-101…104, LOC-002…005, SENS-001…008, AI-001…003, ALT-004 |
| **Cross-cutting** | ACC-001…005, SEC-001…006, AI-004…005 |

---

## 8. Tier 1 — Earns the Download

**Design constraint:** Under 60 seconds from install to first value. No login. No permissions required. Under 15 MB APK. Fully offline after install.

---

### 8.1 Fever and Symptom Triage

#### TRI-001: Broad Febrile-Illness Triage

**Tier:** 1 (core) / 4 (Ebola branch)

**Description:** A guided triage tool that risk-stratifies across all common causes of fever and acute illness in Kenya, with Ebola as one gated branch.

**Inputs:**
- Fever presence and duration
- Accompanying symptoms (multi-select, icon-driven): cough, headache, muscle pain, joint pain, sore throat, vomiting, diarrhoea, rash, bleeding, confusion, difficulty breathing, abdominal pain, fatigue
- Age band (under 5, 5–17, 18–49, 50–64, 65+)
- Pregnancy status
- **Epidemiological criteria:** travel to an affected area within 21 days; contact with a known or suspected case; attendance at a known exposure site
- **Red flags:** unexplained bleeding, bleeding gums, blood in stool or vomit, bruising without cause, confusion, difficulty breathing, inability to drink, convulsions

**Outputs:**
- Risk classification: Emergency / High (Ebola suspicion) / High (other cause) / Moderate / Low
- Recommended action with one-tap execution (call 719, find facility, request CHW visit)
- Watch-for list for the next 24–48 hours
- Forwardable summary card

**Clinical basis:** WHO Ebola case definitions, Kenya MoH IDSR guidance, Kenya national malaria treatment guidelines, IMCI algorithms for under-fives.

**Offline:** Fully functional. Triage logic runs on-device. Results stored locally.

**Accessibility:** Icon-driven. Voice input available. Read-aloud output in local languages.

**Languages:** Swahili, English, Dholuo, Luhya, Kalenjin, Kikuyu, Kamba, Somali, Maasai.

**Privacy:** All triage data stays on-device unless the user consents to share. Anonymous mode available.

---

#### TRI-002: Symptom Diary and Follow-Up

**Tier:** 1

**Description:** A simple log of symptoms over time, with automatic prompts to re-assess if symptoms worsen.

**Features:**
- Log symptoms with timestamp
- Daily "how are you feeling?" prompt (opt-in)
- Automatic escalation if new red flags are logged
- Trend view: is this getting better or worse?
- Exportable summary for a clinician

**Offline:** Yes.

---

### 8.2 Find a Facility

#### FND-001: Facility Finder

**Tier:** 1

**Description:** Locate the nearest appropriate health facility, with live status, services, and payment information.

**Data displayed per facility:**
- Name and level (dispensary, health centre, sub-county hospital, county referral, national referral)
- Distance and estimated travel time
- Open now / closed, with hours
- Services offered (maternal, child, HIV, TB, malaria, emergency, isolation capacity)
- **SHA/NHIF acceptance** — critical for cost anxiety
- Approximate cost band
- Contact number
- Whether it is a designated Ebola screening or isolation facility (Tier 4)
- Crowd level (crowdsourced or historical)
- Recent user reports ("no malaria tests today," "long queue")

**Features:**
- GPS-based nearest search
- Search by area name or code
- Filter by service, level, cost, SHA acceptance
- One-tap directions (opens maps app)
- One-tap call
- Offline mode: caches facilities within 50 km of the user's home area

**Offline:** Partial — caches last-known data. Full offline bundle for user's home county available on first sync.

**Data source:** Kenya Master Health Facility List (MoHF), with crowdsourced corrections.

---

#### FND-002: Emergency Department Status

**Tier:** 1

**Description:** Real-time or near-real-time availability of emergency and ICU capacity at referral facilities.

**Features:**
- ICU bed availability
- Emergency department queue status
- Ambulance availability
- Trauma capability
- Isolation bed availability (Tier 4)

**Data source:** Integration with PHEOC daily dashboards and facility reporting.

**Offline:** Cached, with timestamp visible.

---

#### FND-003: Testing Site Locator

**Tier:** 1 / 4

**Description:** Find locations offering relevant diagnostic tests.

**Test types (context-dependent):**
- Malaria RDT and microscopy
- Typhoid
- HIV
- TB
- COVID-19
- Ebola (designated sites only)
- General laboratory panels

**Features:** Filter by test, cost, hours, results turnaround.

---

#### FND-004: Pharmacy and Chemist Finder

**Tier:** 1

**Description:** Locate nearby pharmacies and chemists, with stock and pricing signals.

**Features:**
- Nearest registered pharmacies (PPB registry)
- Open now
- Whether they accept SHA
- Crowdsourced stock reports (see MED-004)
- One-tap call

---

#### FND-005: Vaccination Point Finder

**Tier:** 1

**Description:** Find locations offering routine and campaign vaccinations.

**Features:** Filter by vaccine, age eligibility, cost (usually free), hours, whether walk-in or appointment.

---

### 8.3 Medicine

#### MED-001: Medicine Verifier

**Tier:** 1 — **The flagship demo feature**

**Description:** Scan a medicine barcode or enter a registration number to verify it against the Pharmacy and Poisons Board (PPB) registry.

**Why this feature:** Counterfeit and substandard medicines kill people in Kenya every day. This is the single best "show me in 10 seconds" demo — it makes the value proposition immediately obvious and it has nothing to do with Ebola.

**Features:**
- Barcode scan using the camera
- Manual entry of the PPB registration number
- Photo of packaging for batch verification (where supported)
- Result: Registered / Not found / Expired registration / Recalled
- Display: product name, manufacturer, registration status, expiry, batch recalls
- **Report a suspicious medicine** — one tap to flag to PPB

**Offline:** Requires a local cache of the PPB registry (updated on sync). Approx. 20–40 MB compressed — cache the top 2,000 products by volume for full offline; full registry lookup when online.

**Privacy:** Scans are not stored or transmitted unless the user reports a suspicious product.

---

#### MED-002: Drug Interaction and Safety Checker

**Tier:** 1

**Description:** Check whether two medicines can be taken together.

**Features:**
- Select or scan two or more medicines
- Check for known interactions
- Flag contraindications for pregnancy, children, and common conditions
- Guidance to consult a pharmacist

**Offline:** Yes, using a bundled interaction database.

**Disclaimer:** Informational only. Not a substitute for professional advice.

---

#### MED-003: Dosage Calculator

**Tier:** 1

**Description:** Weight-based dosing calculator for common medications, especially paediatric.

**Features:**
- Enter weight and age
- Select medicine
- Get dose range
- Common paediatric formulations (paracetamol, amoxicillin, ORS, zinc, artemether-lumefantrine)
- Warning for maximum doses

**Target user:** Parents and caregivers.

---

### 8.4 Emergency

#### EMG-001: Emergency SOS

**Tier:** 1

**Description:** One-tap emergency alert that works with or without data.

**Features:**
- Large, hard-to-mistap SOS button
- Sends location and a preset message to up to three emergency contacts
- Sends to the nearest ambulance dispatch where integrated
- **Works over SMS when data is unavailable**
- Countdown with cancel option (prevents accidental activation)
- Optional medical profile attachment (blood group, allergies, conditions, medications)
- Optional auto-dial of emergency services

**Configuration:** User sets contacts during onboarding (optional — can be set later).

**Offline:** Yes, via SMS.

**Battery:** Designed to function even at low battery by minimising background processing.

---

#### EMG-002: Fall Detection and Auto-Alert

**Tier:** 1 (opt-in)

**Description:** Uses the accelerometer and gyroscope to detect falls or sudden collapse and automatically alert emergency contacts.

**Behaviour:**
- Continuous low-power monitoring of tri-axis accelerometer and gyroscope
- On-device classifier distinguishes falls from routine motion
- On detection: 30-second prompt ("Are you OK?")
- No response → automatic alert to emergency contacts and, if enabled, 719, with location

**Target users:** Elderly, chronically ill, people living alone, healthcare workers on shift.

**Privacy:** On-device only. Only fall events (timestamp + location) are logged.

**Battery impact:** Optimised to <2% per day.

---

#### EMG-003: Offline Emergency Card

**Tier:** 1

**Description:** A lock-screen-accessible card showing critical medical information.

**Contents:** Blood group, allergies, chronic conditions, current medications, emergency contacts, organ donor status, SHA number.

**Access:** Available from the lock screen without unlocking the phone (opt-in). Critical for unconscious patients.

---

### 8.5 Information

#### INF-001: County Risk Dashboard

**Tier:** 1

**Description:** A simple, visual, daily-updated dashboard of health risks in the user's county and neighbouring counties.

**Displays:**
- Current outbreak status by county (Ebola and other notifiable diseases)
- Case counts (confirmed, suspected) with trend
- Affected sub-counties and locations
- Active alerts and advisories
- Service status (schools, borders, markets — where available)
- Last updated timestamp
- Data source attribution

**Design:** Traffic-light visual language. No jargon. Icons for each disease. Large text option.

**Offline:** Shows last-cached version with a clear "as of [time]" label.

---

#### INF-002: "What Should I Do?" Decision Tree

**Tier:** 1

**Description:** A simple, guided decision tree for the most common questions.

**Entry questions:**
- I have a fever
- Someone in my house is sick
- I'm worried about travel
- I want to protect my family
- I heard something — is it true?
- I need to go to hospital

**Output:** Specific, actionable guidance with facility and hotline links.

---

#### INF-003: Ebola Information Library

**Tier:** 1

**Description:** Plain-language, illustrated information on Ebola.

**Topics:**
- What Ebola is and how it spreads
- Symptoms and when they appear
- How to protect yourself and your family
- What to do if you think you've been exposed
- Testing and treatment
- Safe and dignified burial (see INF-010)
- Stigma and how to fight it
- What happens at an isolation facility
- Recovery and survivors

**Format:** Short articles (under 200 words), illustrations, audio versions, video versions.

**Languages:** All supported languages.

---

#### INF-004: Myth-Busting Library

**Tier:** 1

**Description:** A searchable library of common rumours with clear corrections.

**Format:** "Rumour: [claim]. Fact: [correction]. Source: [authority]."

**Features:**
- Search
- Browse by category
- "Ask about a rumour" — submit a claim for verification
- Shareable as a card

---

#### INF-005: Travel Advisory

**Tier:** 1

**Description:** Current guidance for travel to and from affected areas.

**Features:**
- Country and county advisories
- Border point status and wait times
- Screening requirements
- What to do if you feel unwell after travel
- 21-day self-monitoring enrolment for travellers (links to MON-009)

---

#### INF-006: Hotline and Contact Directory

**Tier:** 1

**Description:** A single screen with all relevant contacts.

**Contents:** 719 hotline, county health office, nearest facility, ambulance, CHW, mental health helpline, GBV helpline, child helpline.

**Features:** One-tap call, one-tap SMS, save to contacts, share.

---

### 8.6 Location

#### LOC-001: Geofenced Risk Alerts

**Tier:** 1 (basic) / 4 (full)

**Description:** Alerts users when they enter a high-risk zone.

**Tier 1 behaviour:** Static advisory zones (e.g., known outbreak areas) with opt-in alerts.

**Tier 4 behaviour:** Dynamic geofences defined by county health authorities based on live epidemiological data; alert on entry and exit.

**Alert content:** "You have entered an area where a case was reported. Avoid [specific location]. Monitor for symptoms for 21 days. Call 719 if you feel unwell."

**Privacy:** Location processed on-device. Only entry/exit events logged, and only with consent.

**User control:** Fully disableable.

---

## 9. Tier 2 — Earns the Return Visit

**Design constraint:** Genuine recurring utility. Features people need weekly or monthly.

---

### 9.1 Monitoring and Reminders

#### MON-001: Child Immunisation Tracker

**Tier:** 2 — **The parental hook**

**Description:** Tracks each child's immunisation schedule against Kenya's EPI schedule and sends reminders.

**Features:**
- Add children with date of birth
- Automatic schedule generation (BCG, OPV, Pentavalent, PCV, Rotavirus, Measles-Rubella, Yellow Fever where relevant, HPV for girls)
- Reminders 3 days and 1 day before due date
- Record doses given (with photo of card)
- Catch-up schedule for defaulters
- Missed-dose alerts
- Facility finder integration for vaccination points
- Campaign notifications (polio, measles)
- Shareable immunisation record

**Why this works:** Parents care intensely about their children's health. This is the highest-frequency, highest-motivation health action in the population. It also builds a durable record that outlives the paper card.

**Offline:** Fully functional.

---

#### MON-002: Pregnancy and Antenatal Care Tracker

**Tier:** 2

**Description:** Supports pregnant women through ANC, delivery planning, and postnatal care.

**Features:**
- Estimated due date calculator
- WHO/Kenya ANC visit schedule (8 contacts)
- Visit reminders
- Danger sign education and one-tap escalation
- Birth plan builder (facility, transport, birth companion, blood donor, funds)
- Trimester-specific guidance
- Postnatal visit reminders
- Newborn danger signs
- Facility finder for maternity services
- Referral to PMTCT where relevant

**Why this works:** Pregnant women have the most frequent clinic contact of any group. The app becomes a trusted companion across nine months and beyond.

---

#### MON-003: Chronic Disease Log

**Tier:** 2

**Description:** Tracking and management support for chronic conditions.

**Conditions supported:**
- Hypertension
- Diabetes
- Asthma
- Epilepsy
- HIV (with strong privacy protections)
- Sickle cell disease
- Chronic kidney disease

**Features:**
- Log readings (BP, blood sugar, peak flow, weight)
- Trend charts
- Medication reminders
- Refill reminders
- Appointment tracking
- Lifestyle guidance
- Shareable reports for clinicians
- Danger thresholds with escalation

**Privacy:** Extra protections for HIV status. Separate PIN. No inclusion in any shareable record without explicit per-share consent.

---

#### MON-004: Medication Reminders

**Tier:** 2

**Description:** Simple, reliable reminders to take medication.

**Features:**
- Add medication, dose, frequency, duration
- Multiple daily reminders
- Mark as taken / skipped / snooze
- Adherence history
- Refill alerts when supply is running low
- Support for multiple family members
- Works with no data connection

**Why this works:** This is the highest-frequency health action anyone takes. It drives daily app opens.

---

### 9.2 Records

#### REC-001: Family Health Wallet (Basic)

**Tier:** 2

**Description:** A secure place for each family member's health documents.

**Contents:**
- Immunisation cards (photo or digital)
- ANC cards
- Lab results
- Prescriptions
- Discharge summaries
- Referral letters
- Insurance/SHA details
- Clinic appointment cards

**Features:**
- Multiple profiles (up to 10)
- Photo capture and storage
- Offline access
- Share via secure link or PDF export
- Optional encrypted cloud backup
- Search

**Why this works:** "I lost the card" is a permanent, universal problem. This solves it permanently.

---

### 9.3 Medicine (Extended)

#### MED-004: Drug Stock Crowdsourcing

**Tier:** 2

**Description:** Community-reported availability of essential medicines at nearby facilities and pharmacies.

**Features:**
- Search for a medicine
- See recent reports ("available at [pharmacy], 2 hours ago")
- Report availability yourself (one tap)
- Flag stockouts
- Essential medicines list prioritised (insulin, ARVs, TB drugs, oxytocin, malaria ACTs, ORS, zinc, contraceptives)
- Alert when a previously out-of-stock medicine becomes available

**Why this works:** Drug stockouts are a real, unsolved, daily problem. This is a genuine public service with high engagement.

**Anti-gaming:** Require location proximity to report. Weight reports by reporter reliability. Show report age clearly.

---

### 9.4 Facility (Extended)

#### FND-006: Appointment Booking and Queue Management

**Tier:** 2

**Description:** Book appointments and reduce waiting.

**Features:**
- View available slots at participating facilities
- Book, reschedule, cancel
- Queue number and estimated wait time
- Check-in on arrival via QR code (see LOC-004)
- Reminder notifications

**Rollout:** Pilot at high-volume facilities; expand based on results.

---

### 9.5 Information (Extended)

#### INF-007: Service Status Feed

**Tier:** 2

**Description:** Real-time status of public services relevant to health.

**Contents:** School closures, border post status, market closures, water interruptions, road closures affecting facility access, public transport disruptions.

---

### 9.6 Alerting (Extended)

#### ALT-003: Personalised Alert Preferences

**Tier:** 2

**Description:** Granular control over what alerts the user receives.

**Options:** County alerts, disease-specific alerts, facility alerts, appointment reminders, medication reminders, immunisation reminders, community alerts, air quality alerts, water quality alerts.

**Critical alerts** (exposure notification, immediate danger) cannot be disabled.

---

## 10. Tier 3 — Earns the Home Screen

**Design constraint:** Daily habit. Something the user opens without being prompted.

---

### 10.1 Records (Extended)

#### REC-002: Family Health Wallet (Full)

**Tier:** 3

**Description:** Full-featured health record with cloud sync, sharing, and provider access.

**Additional features over REC-001:**
- Encrypted cloud backup
- Share with a specific provider for a limited time
- Provider-side view (for participating facilities)
- Timeline view of all health events
- Growth charts for children
- Vaccination certificates (for travel/school)
- Export to PDF for school, travel, or employment

---

#### REC-003: Growth and Development Tracker

**Tier:** 3

**Description:** Track child growth against WHO standards.

**Features:** Weight, height, head circumference, MUAC; percentile charts; undernutrition alerts; feeding guidance by age; milestone checklists.

---

#### REC-004: Menstrual and Reproductive Health Tracker

**Tier:** 3

**Description:** Cycle tracking with reproductive health information.

**Features:** Period logging, cycle prediction, contraception reminders, fertility awareness, menopause support, referral to services.

**Privacy:** PIN-protected. Excluded from cloud backup by default.

---

#### REC-005: Mental Health Self-Check and Support

**Tier:** 3

**Description:** Screening and support for common mental health conditions.

**Features:**
- PHQ-9 and GAD-7 screenings (validated, localised)
- Mood tracking
- Coping strategies and psychoeducation
- Referral to services
- Crisis line access
- Outbreak-specific: isolation distress, grief support, healthcare worker burnout

**Why this matters for outbreaks:** Isolation, grief, stigma, and healthcare worker burnout are major, under-addressed consequences of outbreaks.

---

#### REC-006: Blood Donor Matching

**Tier:** 3

**Description:** Connect blood donors with recipients.

**Features:**
- Register as a donor (blood group, location, availability)
- Receive alerts when your blood type is urgently needed nearby
- Find donation centres
- Donation history and eligibility tracker
- Emergency requests from facilities

**Why this works:** Chronic shortage. High emotional value. Strong word-of-mouth.

---

### 10.2 Monitoring (Extended)

#### MON-005: Water Quality Alerts

**Tier:** 3

**Description:** Alerts on water safety issues in the user's area.

**Features:** Boil-water notices, contamination reports, treatment guidance, safe storage guidance, point-of-use treatment reminders.

---

#### MON-006: Air Quality Index

**Tier:** 3

**Description:** Local air quality with health guidance.

**Features:** AQI for user's location, health advisories for sensitive groups, mask guidance, best times for outdoor activity, pollution source information.

**Data sources:** Reference monitors where available; low-cost sensor networks; satellite-derived estimates; crowdsourced visibility reports.

---

#### MON-007: Vector and Environmental Risk

**Tier:** 3

**Description:** Seasonal risk information for vector-borne disease.

**Features:** Malaria season alerts by region, mosquito breeding site reporting, larviciding campaign notifications, personal protection reminders, Rift Valley fever alerts for livestock-adjacent communities.

---

#### MON-008: Nutrition and Food Safety

**Tier:** 3

**Description:** Guidance on nutrition and food safety.

**Features:** Seasonal food availability, aflatoxin alerts, food recall notifications, infant feeding guidance, therapeutic feeding programme locations, recipe ideas for local ingredients.

---

### 10.3 Alerting (Extended)

#### ALT-001: Community Alert Feed

**Tier:** 3

**Description:** A feed of verified local alerts.

**Contents:** Disease outbreaks, weather emergencies, floods, fires, road closures, security incidents affecting health access, drug recalls, water notices, food recalls.

**Verification:** All alerts verified before publishing. Source and timestamp always visible.

---

#### ALT-002: Family Safety Check-In

**Tier:** 3

**Description:** During an emergency, let family members quickly confirm they are safe.

**Features:**
- "I'm safe" button that notifies linked family members
- Family status board during an active alert
- Automatic check-in prompts during a declared emergency in the user's area
- Works over SMS when data is unavailable

---

### 10.4 Community (Extended)

#### COM-005: Community Reporting

**Tier:** 3

**Description:** Report community-level issues that affect health.

**Reportable items:** Broken water point, open sewage, illegal dumping, mosquito breeding site, dead animal, unsafe food vendor, suspected counterfeit medicine, facility stockout, facility staff absence.

**Flow:** Report → routed to relevant county authority → status tracking → notification on resolution.

**Why this works:** Civic engagement, visible impact, builds trust in the app as a tool that does something.

---

### 10.5 Information (Extended)

#### INF-008: Health Tips and Education

**Tier:** 3

**Description:** Rotating, seasonal, locally relevant health education.

**Format:** Short cards, 30-second videos, audio clips.

**Topics:** Hygiene, nutrition, mental health, first aid, child development, chronic disease management, injury prevention, sexual and reproductive health.

---

#### INF-009: First Aid Guide

**Tier:** 3

**Description:** Offline first-aid instructions with illustrations.

**Topics:** Bleeding, burns, choking, drowning, fractures, poisoning, snakebite, seizure, unconsciousness, CPR, shock.

**Offline:** Fully offline. One of the most valuable offline resources possible.

---

#### INF-010: Safe and Dignified Burial Guidance

**Tier:** 3 / 4

**Description:** Culturally sensitive guidance on safe burial practices during outbreaks.

**Content:**
- Why safe burial matters for Ebola
- How to conduct a safe and dignified burial
- Who to contact (burial team)
- Cultural and religious considerations
- Support for grieving families
- What happens if the family cannot conduct the burial themselves

**Sensitivity:** Developed with religious leaders, community elders, and anthropologists. Available in all relevant languages. Emphasises dignity, not just safety.

---

## 11. Tier 4 — The Outbreak Superpower

**Design constraint:** Dormant until triggered by PHEOC. Activates automatically for users in affected areas. Requires no separate adoption effort because Tiers 1–3 already earned the install.

### 11.1 Activation Model

| Trigger | Scope | Features Activated |
|---|---|---|
| PHEOC declares an outbreak event | National or county | ALT-004, LOC-002, LOC-003, COM-101, AI-001 |
| Confirmed case in a county | County | LOC-001 (dynamic geofences), ALT-004 |
| User identified as a contact | Individual | MON-009 |
| User enters a high-risk zone | Individual | LOC-001, ALT-004 |
| User requests activation | Individual | MON-009, LOC-002 |

**Deactivation:** Automatic when PHEOC closes the event. Users are notified. Data retention clocks begin.

---

### 11.2 Triage (Extended)

#### TRI-003: Ebola-Specific Triage

**Tier:** 4

**Description:** The Ebola branch of TRI-001, activated when epidemiological criteria are met.

**Additional inputs:**
- Specific exposure history (funeral attendance, healthcare work, contact with a case, consumption of bushmeat)
- Vaccination status (if a vaccine is available and deployed)
- Isolation status

**Outputs:**
- Ebola suspicion classification
- Immediate action (call 719, do not travel by public transport, await instructions)
- Isolation guidance for the household
- Contact list building (see COM-103)

**Escalation:** Any Ebola-suspected triage result triggers an automatic, consented notification to the county rapid response team if the user opts in.

---

### 11.3 Monitoring (Extended)

#### MON-009: 21-Day Contact Monitoring Diary

**Tier:** 4

**Description:** Daily monitoring for individuals identified as contacts of a confirmed case. Ebola symptoms can appear up to 21 days after exposure.

**Features:**
- Daily temperature logging (manual or via Bluetooth thermometer)
- Symptom checklist (fever, fatigue, muscle pain, headache, sore throat, vomiting, diarrhoea, rash, bleeding)
- Twice-daily reminders
- Visual countdown to the end of the 21-day period
- **Escalation logic:** Any fever or new symptom triggers an immediate prompt to call 719 and, with consent, notifies the assigned CHW or county team
- Location logging (with consent) to support contact tracing
- Household member monitoring in the same interface
- Psychological support resources
- Direct line to the assigned monitoring officer

**Data flow:** All data stored locally. Daily summaries shared with the assigned CHW or county health team through ADaM, with consent.

**Offline:** Fully functional. Syncs when connectivity is available.

**Adherence design:** Simple, fast, two taps per check-in. Reminders escalate in urgency if missed.

---

### 11.4 Community and CHW

#### COM-101: Community Health Worker Reporting Module

**Tier:** 4

**Description:** A dedicated interface for CHWs to log suspected cases and submit structured reports.

**Features:**
- Guided case report form based on WHO IDSR and Kenya MoH standards
- Patient demographics (name optional; can be anonymous)
- Symptom checklist
- Exposure history
- **Geotagged photo capture** (with consent) of visible symptoms
- **Voice-to-text notes** in local languages
- **Offline report queue** — reports stored locally and submitted when connectivity is available
- Automatic alerts to the appropriate disease surveillance officer on submission (mirroring AVADAR)
- Case status tracking (reported → investigated → lab result → closed)
- PPE reminders and guidance
- Reference materials and job aids
- Daily activity log for supervision

**Access control:** Accounts provisioned by county health teams, verified against the national CHW registry.

**Offline:** Full offline operation. Sync on connectivity. Conflict resolution is server-authoritative for case reports.

**Integration:** Reports flow directly into ADaM.

**Training:** 2-hour initial training, plus in-app refresher content and a supervised first three reports.

---

#### COM-102: Peer-to-Peer Community Alert Network

**Tier:** 4

**Description:** When a confirmed or suspected case is reported, the app sends anonymised alerts to users within a defined radius.

**Features:**
- Geofenced alert zones (500 m, 1 km, 5 km — configurable by county)
- Alert content: "A suspected case has been reported in your area. Avoid [specific location]. Monitor for symptoms for 21 days. Call 719 if you feel unwell."
- No personally identifiable information about the case
- Users acknowledge alerts and receive follow-up guidance
- Follow-up prompts on days 3, 7, 14, and 21

**Verification:** Alerts are only sent after verification by county health authorities, to prevent misinformation and panic.

**Tone:** Calm, factual, actionable. Never alarmist. Tested with community representatives before deployment.

---

#### COM-103: Contact-Tracing Assistance for Individuals

**Tier:** 4

**Description:** If a user is confirmed positive or identified as a contact, the app helps them recall and list everyone they interacted with during the exposure window.

**Features:**
- Guided prompts based on call logs, calendar events, and location history (with full consent)
- Simple form to list names and contact details
- "I don't know their name" option — record a description and approximate location instead
- Categorised by setting (home, work, transport, worship, market, social)
- Option to share with health authorities through a secure, encrypted channel
- Progress indicator

**Data handling:** Contact lists encrypted on-device. Transmitted only with explicit consent. Deleted after the contact-tracing window closes.

**Support:** A guided conversation, not a cold form. This is emotionally difficult; the interface must be humane.

---

#### COM-104: Community Misinformation Tracker

**Tier:** 4

**Description:** Allows users to flag misinformation they encounter.

**Features:**
- Simple "Report misinformation" button
- Text, voice, or screenshot submission
- Aggregation by topic and location
- Dashboard for health authorities showing trending misinformation
- Push notification with corrections when a rumour the user flagged is addressed

**Flow:** Flag → aggregated → verified → correction drafted → published on all channels → flagger notified.

---

### 11.5 Location and Proximity

#### LOC-002: Bluetooth Proximity Logging

**Tier:** 4

**Description:** Uses Bluetooth Low Energy to detect other app users in close proximity and log encounters anonymously.

**How it works:**
1. Each device periodically generates an **Ephemeral Bluetooth Identifier (EBID)** and broadcasts it over BLE.
2. Devices collect EBIDs of encountered devices and generate **Private Encounter Tokens (PET)** that identify an encounter without revealing user identity.
3. EBIDs rotate every 15 minutes to prevent tracking.
4. If a user later tests positive and consents, their PET tokens are uploaded to a secure server.
5. Other users' apps check against these tokens and notify them of exposure.
6. Declarations are routed through a **trusted proxy** to prevent social graph inference.

**Privacy properties:**
- No location data used for proximity detection
- No centralised record of who met whom
- Opt-in only; can be disabled at any time
- Open-source client for independent verification

**Battery impact:** Tuned for <3% per day. Uses BLE advertising and scanning at adaptive intervals.

**Limitations:** Only detects other app users. Penetration-dependent. Should supplement, not replace, manual contact tracing.

**Reference:** Architecture mirrors the DESIRE system's combination of centralised and decentralised approaches.

---

#### LOC-003: GPS Location History for Contact Tracing

**Tier:** 4

**Description:** Records the user's location history (with consent) to support contact tracing if they test positive.

**How it works:**
- Location data stored locally on-device in encrypted form
- 21-day rolling window (configurable to 28 days)
- If the user tests positive and consents, the app generates a location history report showing places visited during the exposure window
- Report shared with health authorities through a secure channel
- **Geohashing** anonymises location data before sharing

**Privacy:** Never uploaded without explicit consent. Deletable at any time. Clearly explained in plain language.

**Offline:** Fully functional. Location logged locally regardless of connectivity.

---

#### LOC-004: QR Code and NFC Check-In

**Tier:** 4

**Description:** Uses QR codes and NFC tags at designated points to check in and receive location-specific guidance.

**Deployment points:**
- Border posts and points of entry
- Health facilities and screening points
- Isolation and treatment units
- Vaccination points
- Schools and workplaces during an outbreak
- Events and gatherings

**Behaviour:**
- Scan QR or tap NFC
- App displays location-specific guidance
- Check-in logged locally; synced with consent
- Used for attendance tracking, follow-up scheduling, and exposure window determination

**Benefit:** Contactless, fast, works offline, and creates an auditable record without manual data entry.

---

#### LOC-005: Border and Point-of-Entry Module

**Tier:** 4

**Description:** A specialised module for travellers and border staff.

**Features:**
- Pre-travel advisory by destination
- Screening queue status at major border points
- Self-declaration form (digital, replaces paper)
- 21-day post-arrival monitoring enrolment
- Post-arrival symptom reporting
- Multi-language support for cross-border travellers
- Integration with mobile laboratory results at border points

---

### 11.6 Sensor-Based Monitoring

*(Full specifications in Section 14.)*

| ID | Feature | Sensor |
|---|---|---|
| SENS-001 | LiDAR respiration monitoring | LiDAR |
| SENS-002 | Acoustic cough and respiratory monitoring | Microphone |
| SENS-003 | Fall detection and collapse alert | Accelerometer, gyroscope |
| SENS-004 | Camera-based symptom capture | Camera |
| SENS-005 | Screen/camera PPG health monitoring | Camera, flash, screen |
| SENS-006 | Wearable integration | BLE, HealthKit / Health Connect |
| SENS-007 | Sleep and activity monitoring | Accelerometer, wearables |
| SENS-008 | Ambient environmental sensing | Barometer, thermometer (where available) |

---

### 11.7 AI and Analytics

#### AI-001: Community-Level Risk Prediction

**Tier:** 4

**Description:** Uses anonymised, aggregated data to predict which neighbourhoods or contact clusters are most likely to see new cases.

**Inputs:** Aggregated symptom reports, geofence entries, proximity encounter density, crowdsourced facility reports, search and content-engagement signals.

**Outputs:** Hotspot predictions, transmission cluster identification, resource deployment recommendations.

**Consumers:** County health teams, PHEOC.

**Privacy:** All data anonymised and aggregated. Minimum cell size of 10 to prevent re-identification. No individual-level data used for prediction without consent.

---

#### AI-002: Personal Risk Scoring

**Tier:** 4

**Description:** Provides users with a personalised risk score based on symptoms, exposure history, and proximity to cases.

**Inputs:** Symptoms, travel history, proximity encounters, geofence entries, known exposures.

**Output:** Low / Moderate / High with actionable guidance.

**Privacy:** Calculated on-device. No personal data transmitted for scoring.

---

#### AI-003: Outbreak Early Warning Signal

**Tier:** 4

**Description:** Detects anomalous patterns in aggregated data that may indicate an undetected outbreak.

**Signals monitored:**
- Sudden increase in fever triage in a locality
- Increase in cough detection events
- Increase in facility-finder searches for a specific symptom
- Increase in medicine searches for a specific drug
- Increase in "I feel unwell" check-ins
- Anomalous proximity encounter density

**Alerting:** Signals above threshold trigger a review by PHEOC epidemiologists. Never automatic public alerts.

**Value:** This is how the app contributes to detecting the *next* outbreak before it is clinically recognised.

---

### 11.8 Alerting

#### ALT-004: Exposure Notification

**Tier:** 4

**Description:** A critical, non-disableable notification that the user may have been exposed.

**Content:** "You may have been in contact with a confirmed case. Please self-monitor for 21 days. Call 719 if you develop fever or feel unwell. Tap for more information."

**Delivery:** Push notification, SMS fallback, WhatsApp fallback.

**Follow-up:** Enrols the user in MON-009. Provides immediate guidance. Offers a callback from a health worker.

**Tone:** Calm, clear, non-stigmatising. Tested with community representatives.

---

## 12. Cross-Cutting Feature Specifications

### 12.1 Accessibility

#### ACC-001: Low-Literacy Interface

**Tier:** Cross-cutting

**Description:** Icon-driven navigation with minimal text, supported by voice prompts and video.

**Features:**
- Pictogram navigation for all core functions
- Video tutorials in local languages
- Colour-coded risk levels (green / yellow / red) with universal symbols
- Large touch targets (minimum 48dp)
- Simplified forms
- Read-aloud on every screen
- Optional "simple mode" that hides advanced features

---

#### ACC-002: Multilingual Voice Interface

**Tier:** Cross-cutting

**Description:** Voice-based interaction for users who cannot or prefer not to type.

**Features:**
- Voice-guided symptom reporting in Swahili, Dholuo, Luhya, Kalenjin, Kikuyu, and English
- Text-to-speech for reading alerts and guidance aloud
- Voice-to-text for CHW notes and case descriptions
- Voice note triage on WhatsApp
- Offline speech recognition for core commands

**Languages:** Priority order — Kiswahili, English, Dholuo, Luhya (Bukusu, Maragoli), Kalenjin, Kikuyu, Kamba, Somali, Maasai, Kisii, Meru, Taita.

---

#### ACC-003: Offline-First Architecture

**Tier:** Cross-cutting

**Description:** All core features function without internet connectivity.

**Technical approach:**
- Local-first data storage (SQLite / Room / Core Data)
- Write-ahead sync queue
- Opportunistic synchronisation
- Conflict resolution: last-write-wins for personal logs; server-authoritative for case reports
- Minimal bandwidth footprint: compressed, batched sync payloads
- Clear offline indicator in the UI
- Pre-cached offline bundles: facility list for home county, first aid guide, information library, drug interaction database

---

#### ACC-004: Battery Efficiency

**Tier:** Cross-cutting

**Description:** Minimise battery drain from continuous sensor monitoring.

**Technical approach:**
- On-device AI to avoid cloud round-trips
- Adaptive sensor sampling rates based on context (charging, stationary, time of day)
- Low-power always-on listening for acoustic monitoring
- User-configurable monitoring intensity (Low / Balanced / Maximum)
- Battery-saver mode that disables non-critical sensors
- Target: <5% total daily battery impact with all Tier 4 sensors enabled
- Explicit battery impact display in settings

---

#### ACC-005: Device Compatibility

**Tier:** Cross-cutting

**Description:** Support the widest possible device range.

**Targets:**
- Android 8.0+ (Go edition compatible)
- APK under 15 MB base download
- Feature modules downloaded on demand
- iOS 14+
- Graceful degradation for missing sensors (see Section 13.2)
- Support for 512 MB RAM devices
- Support for low-resolution screens
- Support for devices without Google Play Services (Huawei AppGallery distribution)

---

### 12.2 Security and Privacy

#### SEC-001: Consent Management

**Tier:** Cross-cutting

**Description:** Granular, revocable, plain-language consent for every data use.

**Consent categories:**
- Symptom data storage
- Location tracking
- Proximity logging
- Sensor monitoring (each sensor separately)
- Data sharing with health authorities
- Data sharing with CHWs
- Cloud backup
- Research use (opt-in, separate)

**Features:**
- Plain-language explanations in local languages
- Granular toggles
- One-tap revocation
- Clear statement of consequences of revocation
- Consent audit log visible to the user

---

#### SEC-002: On-Device Processing

**Tier:** Cross-cutting

**Description:** Raw sensor data never leaves the device.

**Application:**
- LiDAR point clouds discarded immediately; only derived respiration rate stored
- Audio never stored or transmitted; only cough counts and derived metrics
- PPG signals processed on-device; only heart rate and BP estimates stored
- Photos encrypted and only shared with explicit per-item consent
- Location processed on-device; only consented events shared

---

#### SEC-003: Encryption

**Tier:** Cross-cutting

**Description:** All data encrypted at rest and in transit.

**Standards:**
- At rest: AES-256
- In transit: TLS 1.3
- Contact lists and location history: additional application-layer encryption
- Cloud backup: end-to-end encrypted with user-held key
- Key management: hardware-backed keystore (Android Keystore, iOS Secure Enclave)

---

#### SEC-004: Anonymity and Pseudonymity

**Tier:** Cross-cutting

**Description:** Users can use the app without revealing identity.

**Features:**
- No account required for Tier 1–3
- Phone number is the only identifier
- Optional pseudonymous profile
- Geohashing for location sharing
- PET tokens for proximity
- Minimum cell size of 10 for any aggregated reporting

---

#### SEC-005: Data Retention and Deletion

**Tier:** Cross-cutting

**Description:** Clear retention periods and user-initiated deletion.

| Data type | Retention | Deletion trigger |
|---|---|---|
| Symptom logs | 90 days | User deletion or automatic |
| Triage results | 90 days | User deletion or automatic |
| Location history | 21 days rolling | Automatic |
| Proximity tokens (PET) | 21 days | Automatic |
| Contact lists | Until tracing window closes | Automatic |
| Case reports | Per MoH record retention policy | Policy-driven |
| Immunisation records | Lifetime (user-controlled) | User deletion |
| Chatbot conversations | 90 days | Automatic |
| Photos | Until clinical review complete | Automatic unless user retains |

**User rights:** View, export, and delete all personal data at any time. `DELETE MY DATA` command on all channels.

---

#### SEC-006: Transparency and Audit

**Tier:** Cross-cutting

**Description:** Users and regulators can see what data exists and how it has been used.

**Features:**
- In-app data dashboard: what is stored, what has been shared, with whom, when
- Public transparency reports (quarterly)
- Open-source client code
- Independent security audits (annual)
- Bug bounty programme

---

# PART III — SENSORS AND SENSING

---

## 13. Sensor Capability Matrix

### 13.1 Full Sensor Inventory

| Sensor | Android | iOS | Primary Features | Data Sensitivity | Battery Cost |
|---|---|---|---|---|---|
| **LiDAR** | Select flagships | iPhone Pro / iPad Pro | SENS-001 | Low (derived only) | Medium |
| **Microphone** | All | All | SENS-002, ACC-002, CHAN-003 | High | Low |
| **Accelerometer** | All | All | SENS-003, SENS-007 | Low | Very low |
| **Gyroscope** | Most | All | SENS-003 | Low | Very low |
| **Magnetometer** | Most | All | Navigation aid | Low | Very low |
| **Barometer** | Some | Most | SENS-008, altitude | Low | Very low |
| **Ambient light** | All | All | Screen adaptation | Low | Negligible |
| **Proximity** | All | All | Screen management | Low | Negligible |
| **GPS / GNSS** | All | All | LOC-001, LOC-003, FND-001, EMG-001 | High | High |
| **Bluetooth LE** | All | All | LOC-002, SENS-006 | Medium | Medium |
| **NFC** | Most | Most | LOC-004 | Low | Negligible |
| **Camera (rear)** | All | All | MED-001, SENS-004, REC-001 | High | Medium |
| **Camera (front)** | All | All | SENS-005 | Medium | Medium |
| **Flash / LED** | All | All | SENS-005 | Low | Low |
| **Screen** | All | All | SENS-005 (Sensor OLED), UI | Low | Medium |
| **Thermometer** | Very rare | None | SENS-008 | Low | Negligible |
| **Heart rate (optical)** | Rare | None | SENS-005 alternative | Medium | Medium |
| **USB / OTG** | Most | Limited | External thermometer, BP cuff | Medium | Negligible |

### 13.2 Graceful Degradation Strategy

Not all devices have all sensors. Every feature must degrade gracefully.

| Missing sensor | Fallback |
|---|---|
| No LiDAR | Acoustic respiration estimation (SENS-002) or manual entry |
| No microphone access | Manual symptom entry |
| No gyroscope | Accelerometer-only fall detection (reduced accuracy) |
| No GPS | Manual location entry, cell-tower triangulation, QR check-in |
| No Bluetooth | Manual contact listing |
| No NFC | QR code scan |
| No camera | Manual medicine registration number entry |
| No biometric sensor | Manual temperature entry |
| No wearable | Manual health data entry |

**Principle:** No user is excluded because of their device. Every feature has a manual or alternative path.

---

## 14. Detailed Sensor Specifications

### 14.1 SENS-001: LiDAR-Based Contactless Respiration Monitoring

**Tier:** 4

**Sensors used:** LiDAR (Light Detection and Ranging)

**Availability:** iPhone Pro and iPad Pro models; select Android flagships.

**Description:** Monitors respiratory rate without physical contact by detecting chest and abdominal displacement.

**How it works:**
1. The LiDAR sensor emits light pulses and measures reflections from the user's chest and abdomen.
2. A **motion-resilient algorithm** decouples device movement from respiration-induced displacement.
3. The algorithm achieves **<1 breath-per-minute error** at sensing distances up to **4 metres**.
4. Per-frame processing completes within **120 ms**, meeting real-time mobile health monitoring requirements.
5. Derived respiratory rate is stored; raw point clouds are discarded immediately.

**Use cases:**
- Respiratory rate monitoring for individuals under 21-day observation (MON-009)
- Early detection of respiratory distress, a complication in severe Ebola and other conditions
- Night-time monitoring of household members without waking them
- Monitoring of healthcare workers during high-risk shifts
- Triage support at screening points (contactless, reduces exposure risk)

**Clinical relevance:** Respiratory rate is a core vital sign and an early indicator of deterioration. In outbreak settings, contactless measurement reduces healthcare worker exposure.

**Accuracy:** Validated against manual counting and capnography in published research. Expected error <1 bpm in controlled conditions; wider in practice. Displayed with a confidence indicator.

**Privacy:**
- All processing on-device
- Raw point clouds discarded immediately
- Only derived respiratory rate stored
- No images or depth maps retained
- User must explicitly enable LiDAR monitoring
- Clear indication when monitoring is active

**Battery:** LiDAR is power-intensive. Monitoring sessions default to 5 minutes, 2× daily. Continuous overnight monitoring available but flagged as high battery use.

**Limitations:**
- Requires LiDAR-equipped device (<5% of Kenyan devices at launch)
- Requires a relatively still subject
- Clothing and bedding can reduce accuracy
- Not a substitute for clinical assessment

**Fallback:** SENS-002 (acoustic) or manual entry.

---

### 14.2 SENS-002: Acoustic Cough and Respiratory Monitoring

**Tier:** 4

**Sensors used:** Microphone

**Availability:** All devices.

**Description:** Passively detects coughs, sneezes, and abnormal breathing patterns using on-device audio analysis.

**How it works:**
1. Continuous low-power audio monitoring with on-device wake detection
2. AI-based **cough detection and segmentation** — lightweight models optimised for on-device execution
3. Classification of cough type (dry, productive, wheeze-associated)
4. Detection of respiratory rate from breath sounds
5. Detection of abnormal patterns (persistent cough, paroxysmal cough, stridor)
6. Aggregation into hourly and daily metrics

**Use cases:**
- Passive monitoring for individuals under observation
- Early warning of respiratory symptom onset
- Aggregated, anonymised cough data for community-level surveillance (AI-003)
- Longitudinal tracking for chronic respiratory conditions (asthma, COPD)
- Healthcare worker occupational monitoring

**Metrics captured:**
- Cough count per hour
- Cough intensity distribution
- Cough type distribution
- Estimated respiratory rate
- Night-time disturbance index
- Deviation from personal baseline

**Alerting:** If cough frequency exceeds the user's baseline by a defined threshold (e.g., 3× over 6 hours), the app prompts a symptom check and offers escalation.

**Privacy — critical:**
- **All audio processed on-device. No raw audio stored or transmitted. Ever.**
- Only cough counts and derived metrics stored
- **Privacy mode** disables audio monitoring temporarily (e.g., during a private conversation)
- Clear, persistent indicator when listening is active
- Microphone permission can be revoked at any time
- Independent audit of the on-device model to verify no audio exfiltration

**Battery optimisation:**
- Ultra-low-power always-on keyword-style detection
- Full model invoked only on candidate detection
- Adaptive sampling based on context (disabled when on a call, in a meeting, or when the user sets "do not monitor")
- Target: <2% per day

**Languages and contexts:** Trained on cough sounds, which are largely language-independent. Validated across diverse populations.

**Limitations:** Background noise reduces accuracy. Not diagnostic. Cannot distinguish Ebola cough from any other cough.

---

### 14.3 SENS-003: Fall Detection and Collapse Alert

**Tier:** 1 (basic) / 4 (outbreak-enhanced)

**Sensors used:** Accelerometer, gyroscope, barometer (optional)

**Availability:** All devices.

**Description:** Detects falls or sudden collapse and automatically alerts emergency contacts.

**How it works:**
1. Continuous monitoring of tri-axis accelerometer and tri-axis gyroscope data at low frequency
2. On-device AI classifier trained to distinguish genuine falls from routine motions (sitting down quickly, dropping the phone, jumping)
3. On detection of a probable fall:
   - 30-second countdown with a loud prompt: "Are you OK?"
   - User can cancel (I'm fine) or confirm (I need help)
   - No response → automatic alert
4. Alert sends location and a preset message to emergency contacts and, if enabled, to 719

**Use cases:**
- Elderly users living alone
- Chronically ill users
- Individuals under 21-day observation (sudden weakness is a symptom)
- Healthcare workers in isolation facilities (fatigue, heat stress under PPE)
- Pregnant women (fall risk in later trimesters)

**Refinement during outbreak:** Sensitivity is increased for users enrolled in MON-009, since sudden collapse is a serious symptom.

**Privacy:** On-device only. Only fall events (timestamp + location) are logged.

**Battery:** <2% per day.

**False positive management:** Machine learning reduces false positives, but they will occur. The 30-second cancel window is the primary mitigation. Users can adjust sensitivity.

---

### 14.4 SENS-004: Camera-Based Symptom Capture

**Tier:** 4

**Sensors used:** Rear camera, flash

**Availability:** All devices.

**Description:** Captures images of visible symptoms for remote clinical review.

**Features:**
- Guided capture with framing overlay for rash, wound, eye, mouth, or skin
- On-device image quality check (lighting, focus, angle, distance)
- Colour calibration using a reference card (optional, for accurate rash assessment)
- **Geotagging** of the photo (with consent) for epidemiological mapping
- Consent-gated sharing with a health worker via secure channel or JALI
- Comparison view for tracking changes over time

**Use cases:**
- Rash assessment (a late Ebola symptom)
- Wound or lesion assessment
- Eye redness or discharge
- Remote dermatology consultation
- Documenting a medicine or packaging (MED-001)
- Documenting an immunisation card (REC-001)

**Privacy:**
- Photos encrypted on-device
- Explicit per-photo consent required for sharing
- Photos deleted after clinical review unless the user chooses to retain
- No automatic upload
- No facial recognition
- EXIF location data stripped unless explicitly consented

**Clinical workflow:** Photo submitted → routed to a health worker queue → reviewed → response returned to the user. Target turnaround: 4 hours during an outbreak.

---

### 14.5 SENS-005: Screen and Camera PPG Health Monitoring

**Tier:** 1 (basic) / 4 (monitoring)

**Sensors used:** Camera, flash, screen (OLED), optical heart rate sensor (where available)

**Availability:** All devices with a camera and flash.

**Description:** Estimates heart rate and blood pressure using photoplethysmography (PPG).

**How it works:**
1. **Fingertip method:** User places a fingertip over the rear camera lens with the flash on. The camera detects subtle colour changes in the fingertip as blood pulses.
2. **Screen method (OLED devices):** The screen emits light and the front camera detects reflected changes, allowing measurement without the flash.
3. Signal processing extracts heart rate and estimates blood pressure from pulse waveform characteristics.
4. Results are logged alongside other health data.

**Use cases:**
- Heart rate monitoring for individuals under observation
- Tachycardia detection (a relevant sign in severe infection)
- Blood pressure estimation for chronic disease management (MON-003)
- Stress and recovery monitoring
- Pre-consultation vitals

**Metrics:**
- Heart rate (BPM)
- Heart rate variability (HRV)
- Estimated blood pressure (systolic/diastolic)
- Blood oxygen saturation (SpO₂) — where signal quality permits
- Stress index

**Accuracy:** Heart rate is reasonably accurate (±5 bpm). Blood pressure estimation is **less accurate** than cuff-based measurement and varies by device, skin tone, and technique. **Clearly labelled as an estimate.** Always recommends clinical confirmation.

**Bias consideration:** PPG accuracy varies with skin pigmentation. Models must be validated across diverse skin tones, and the app must disclose known accuracy limitations. This is an ethical requirement, not an optional refinement.

**Privacy:** On-device processing. Only derived metrics stored.

---

### 14.6 SENS-006: Wearable Integration

**Tier:** 2 (basic) / 4 (outbreak)

**Sensors used:** Bluetooth LE, platform health APIs

**Availability:** Depends on wearable ownership.

**Description:** Integrates with smartwatches and fitness bands to pull continuous health data.

**Supported platforms:** Apple HealthKit, Android Health Connect, Garmin, Fitbit, Samsung Health, Xiaomi Mi Band, Huawei Health.

**Data types:**
- Heart rate (continuous)
- Body temperature (from wearables with temperature sensors)
- Blood oxygen saturation (SpO₂)
- Sleep duration and quality
- Activity and step count
- Respiratory rate (on supported devices)
- ECG (on supported devices)
- Fall detection events

**Use cases:**
- Early detection of fever or tachycardia before symptoms are consciously noticed
- Monitoring of healthcare workers during high-risk shifts (heat stress, fatigue)
- Longitudinal health trends for individuals under observation
- Sleep quality as a recovery indicator
- Adherence support through activity tracking

**Anomaly detection:** The app establishes a personal baseline and alerts when heart rate, temperature, or sleep deviate significantly — prompting a symptom check.

**Privacy:** User-controlled sync. Data stored locally. Not shared without consent.

---

### 14.7 SENS-007: Sleep and Activity Monitoring

**Tier:** 3

**Sensors used:** Accelerometer, gyroscope, wearables

**Availability:** All devices (basic) or wearables (enhanced).

**Description:** Tracks sleep and activity patterns as health indicators.

**Metrics:** Sleep duration, sleep efficiency, time to fall asleep, night wakings, daily steps, active minutes, sedentary time, estimated energy expenditure.

**Use cases:** Recovery monitoring, chronic disease management, mental health support, fatigue risk for healthcare workers.

**Privacy:** On-device. Aggregated and anonymised if shared.

---

### 14.8 SENS-008: Environmental and Ambient Sensing

**Tier:** 3

**Sensors used:** Barometer, thermometer (where available), light sensor, camera (for visibility/haze), microphone (for environmental noise)

**Availability:** Varies by device.

**Description:** Collects environmental data relevant to health.

**Metrics:**
- Barometric pressure (weather, altitude, headache and respiratory risk)
- Ambient temperature (heat stress risk)
- Ambient light (sleep environment)
- Estimated air quality (via camera haze analysis, where validated)
- Ambient noise level

**Use cases:** Heat stress alerts for outdoor workers; air quality advisories; weather-linked disease risk (malaria, Rift Valley fever); sleep environment guidance.

---

### 14.9 Additional Sensor Applications

#### External Device Integration (USB/OTG and BLE)

**Feature ID:** SENS-009

**Description:** Connect external medical devices for accurate measurements.

**Supported devices:**
- Bluetooth thermometers (accurate fever measurement)
- Bluetooth blood pressure cuffs
- Bluetooth pulse oximeters
- Bluetooth glucometers
- Bluetooth scales
- Bluetooth ECG devices

**Value:** Converts consumer measurements into clinical-grade data, improving triage accuracy and monitoring quality.

**Integration:** Data flows into the health wallet (REC-002) and monitoring diary (MON-009).

---

#### NFC for Tag-Based Workflows

**Feature ID:** SENS-010

**Description:** Uses NFC for fast, contactless interactions.

**Applications:**
- Check-in at facilities (LOC-004)
- Patient wristband identification at isolation units
- Medication authentication (tapping a medicine package with an NFC tag)
- PPE station logging for healthcare workers
- Equipment tracking

---

# PART IV — ENGINEERING

---

## 15. Technical Architecture

### 15.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER CHANNELS                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Feature  │ │ SMS /    │ │ WhatsApp │ │ Social   │ │ Radio  │  │
│  │ Phone    │ │ USSD     │ │ Bot      │ │ Media    │ │        │  │
│  │ (CHAN-1,2)│ │(CHAN-1,2)│ │(CHAN-3)  │ │(CHAN-4)  │ │(CHAN-0)│  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬───┘  │
│       │            │            │            │            │       │
│       └────────────┴────────────┴────────────┴────────────┘       │
│                              │                                     │
│                    ┌─────────▼─────────┐                          │
│                    │  Native App       │                          │
│                    │  (CHAN-6)         │                          │
│                    │  Android / iOS    │                          │
│                    └─────────┬─────────┘                          │
└──────────────────────────────┼────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────┐
│                     LOCAL DATA LAYER                               │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  SQLite / Room (Android) · Core Data (iOS)                 │   │
│  │  · Symptom logs          · Immunisation records            │   │
│  │  · Triage results        · Medication schedules            │   │
│  │  · Monitoring diary      · Facility cache                  │   │
│  │  · Location history (encrypted)                            │   │
│  │  · PET tokens            · Content cache                   │   │
│  │  · Sensor-derived metrics (no raw data)                    │   │
│  └────────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  Hardware-Backed Keystore (Android Keystore / Secure Enclave)│  │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────┐
│                   SYNC & COMMUNICATION LAYER                       │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────┐  │
│  │ HTTPS/TLS │ │ BLE       │ │ SMS / USSD│ │ WhatsApp Business │  │
│  │ REST API  │ │ Proximity │ │ Gateway   │ │ API               │  │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────────┬─────────┘  │
└────────┼─────────────┼─────────────┼─────────────────┼────────────┘
         │             │             │                 │
┌────────▼─────────────▼─────────────▼─────────────────▼────────────┐
│                       BACKEND SERVICES                             │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  API Gateway (rate limiting, auth, routing, audit)           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Triage   │ │ Case Mgmt│ │ Exposure │ │ Content  │ │ Facility│ │
│  │ Service  │ │ Service  │ │ Notify   │ │ Service  │ │ Service │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Medicine │ │ Records  │ │ Alerting │ │ AI/ML    │ │ Consent │ │
│  │ Registry │ │ Service  │ │ Service  │ │ Engine   │ │ Registry│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└──────────────────────────────┬────────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────────┐
│                     INTEGRATION LAYER                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ ADaM     │ │ JALI     │ │ PHEOC    │ │ 719      │ │ PPB     │ │
│  │ Platform │ │ Chatbot  │ │Dashboards│ │ Hotline  │ │ Registry│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ MoHF     │ │ SHA/NHIF │ │ EPI      │ │ Lab      │ │ Telco   │ │
│  │ Facility │ │          │ │ Schedule │ │ Results  │ │ Gateways│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### 15.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Mobile framework** | Flutter | Single codebase for Android and iOS; strong offline support; small binary |
| **Local DB** | SQLite + Room (Android), Core Data (iOS) | Proven, ACID-compliant, offline-first |
| **On-device ML** | TensorFlow Lite, ONNX Runtime Mobile | Lightweight, mature, supports the required models |
| **Backend runtime** | Node.js (Fastify) + Python (FastAPI) | Node for APIs, Python for ML and data pipelines |
| **Primary DB** | PostgreSQL 16 | Robust, open-source, mature ecosystem |
| **Geospatial** | PostGIS | Geofencing, geohashing, spatial queries |
| **Time-series** | TimescaleDB | Sensor metrics, monitoring diaries |
| **Cache / queue** | Redis | Sessions, rate limiting, job queues |
| **Object storage** | S3-compatible (MinIO on-prem option) | Photos, documents, exports |
| **Search** | OpenSearch | Content search, facility search, misinformation tracking |
| **Message queue** | RabbitMQ or Kafka | Async processing, alert fan-out |
| **WhatsApp** | Meta WhatsApp Business API | Official channel |
| **SMS / USSD** | Africa's Talking or Telco direct | Proven in Kenya |
| **Cloud** | AWS Africa (Cape Town) or Azure South Africa | Data residency, low latency |
| **On-prem option** | Kubernetes on MoH infrastructure | Data sovereignty option for sensitive components |
| **CI/CD** | GitHub Actions + Fastlane | Standard, cost-effective |
| **Monitoring** | Prometheus + Grafana + Sentry | Standard observability |
| **Feature flags** | Unleash | Tier 4 activation control |

### 15.3 Data Residency and Sovereignty

- **Primary data residency:** Kenya or, at minimum, African Union jurisdiction
- **Sensitive components** (case management, contact tracing) may be deployed on-premise at MoH
- **Anonymised analytics** may be processed in the cloud
- **No data transfer outside African jurisdictions** without explicit legal review
- **Data processing agreements** with all vendors

### 15.4 Scalability Targets

| Metric | Target |
|---|---|
| Registered users | 10 million |
| Daily active users (outbreak) | 2 million |
| Daily active users (steady state) | 500,000 |
| Concurrent API requests | 50,000 |
| Triage requests per second | 500 |
| Push notifications per hour | 5 million |
| SMS per day | 10 million |
| WhatsApp messages per day | 2 million |
| Data ingestion (sensor metrics) | 100 million events/day |
| API latency (p95) | <300 ms |
| Uptime | 99.9% |
| Recovery time objective | 1 hour |
| Recovery point objective | 15 minutes |

### 15.5 API Design

- **REST** for synchronous operations
- **WebSocket** for real-time alerts
- **gRPC** for internal service-to-service
- **Versioned** (`/v1/`, `/v2/`)
- **Idempotency keys** for all write operations
- **Rate limiting** per device and per endpoint
- **OpenAPI 3.1** specification published
- **OAuth 2.0 + PKCE** for health worker authentication
- **Anonymous tokens** for citizen endpoints

---

## 16. Offline-First and Low-Resource Design

### 16.1 Offline-First Principles

1. **Local write always succeeds.** Every user action is written to the local database first.
2. **Sync is a background concern.** The UI never blocks on the network.
3. **Conflict resolution is explicit.** Documented per data type.
4. **Offline state is visible.** The UI clearly indicates sync status.
5. **Nothing is lost.** Every queued write survives app restart and device reboot.

### 16.2 Sync Queue Design

```
Write → Local DB → Sync Queue → [Network available?]
                                      │
                          ┌───────────┴───────────┐
                          │ Yes                   │ No
                          ▼                       ▼
                    Batch & send            Retry with
                    (exponential            exponential
                     backoff)               backoff
                          │                       │
                          ▼                       │
                    Ack received?                 │
                          │                       │
                  ┌───────┴───────┐               │
                  │ Yes           │ No            │
                  ▼               ▼               │
              Mark synced    Retry ───────────────┘
```

### 16.3 Conflict Resolution Matrix

| Data type | Strategy | Rationale |
|---|---|---|
| Symptom logs | Last-write-wins | Personal data, low conflict |
| Temperature readings | Last-write-wins | Append-only in practice |
| Case reports | Server-authoritative | Clinical accuracy critical |
| Immunisation records | Server-authoritative on conflict, user can appeal | Safety-critical |
| Medication schedules | Last-write-wins | Personal |
| Facility data | Server-authoritative | Central source of truth |
| Content | Server-authoritative | Must match official messaging |
| Proximity tokens | Append-only | No conflicts possible |

### 16.4 Bandwidth Minimisation

- **Payload compression:** gzip / Brotli
- **Delta sync:** only changed fields
- **Batching:** multiple writes in one request
- **Image compression:** WebP, aggressive compression, resumable upload
- **Content caching:** content pushed rather than pulled
- **Adaptive sync:** reduced frequency on metered connections

### 16.5 App Size Strategy

| Component | Size | Delivery |
|---|---|---|
| Base app | <15 MB | Initial download |
| Tier 1 features | Included | Initial download |
| Tier 2 features | Included | Initial download |
| Tier 3 features | ~8 MB | On-demand module |
| LiDAR module | ~4 MB | On-demand (LiDAR devices only) |
| Acoustic module | ~6 MB | On-demand |
| Medicine registry (offline) | ~25 MB | On-demand, optional |
| Offline content library | ~15 MB | On-demand, optional |
| Offline facility cache | ~5 MB | Automatic per county |

**Total with all modules:** ~60 MB. Base install under 15 MB.

---

## 17. Data Privacy, Security, and Regulatory Compliance

### 17.1 Regulatory Framework

| Instrument | Requirement | Implementation |
|---|---|---|
| **Kenya Data Protection Act 2019** | Health data is sensitive personal data; requires explicit consent, purpose limitation, data minimisation, storage limitation | Consent registry; data minimisation by design; retention schedule; user data controls |
| **ODPC Guidance Note on Health Data** | Lawful, fair, transparent processing; accuracy; accountability | Plain-language notices; accuracy SLAs; DPO appointed |
| **Digital Health Act No. 15 of 2023** | Governs e-health service delivery including m-health and telehealth | Compliance review; MoH registration |
| **Computer Misuse and Cybercrimes Act 2018** | Security of systems and data | Security controls; incident response |
| **Public Health Act (Cap 242)** | Disease surveillance obligations | Legal basis for outbreak data sharing where required |
| **WHO International Health Regulations** | Surveillance and reporting | Alignment with IDSR |

### 17.2 Privacy Principles and Implementation

| Principle | Implementation |
|---|---|
| **Lawfulness** | Consent-based for all citizen data; legal obligation basis for mandatory disease notification only |
| **Purpose limitation** | Data collected for Ebola response is not used for other purposes without fresh consent |
| **Data minimisation** | Only data necessary for the specific purpose is collected. Raw sensor data is never retained. |
| **Accuracy** | Content reviewed weekly; user data editable; correction workflows |
| **Storage limitation** | Defined retention periods per data type; automatic deletion |
| **Integrity and confidentiality** | AES-256 at rest, TLS 1.3 in transit, RBAC, audit logging |
| **Accountability** | DPO appointed; DPIAs conducted; transparency reports published |

### 17.3 Data Protection Impact Assessment (DPIA)

A full DPIA is required before launch, covering:

- LiDAR and acoustic monitoring (novel, potentially intrusive)
- Location tracking and geofencing
- Proximity logging and exposure notification
- Contact tracing assistance
- AI-based risk scoring
- Data sharing with health authorities
- Processing of children's data
- Cross-border data transfer

The DPIA must be reviewed and updated before each Tier 4 activation.

### 17.4 Role-Based Access Control

| Role | Access |
|---|---|
| Citizen (anonymous) | Own data only |
| Citizen (identified) | Own and linked family data |
| CHW | Assigned patients, community aggregates |
| Facility clinician | Patients who have consented to share |
| County surveillance officer | County case data, aggregate analytics |
| PHEOC analyst | National case data, aggregate analytics |
| System administrator | Infrastructure only; no access to personal data |
| Auditor | Read-only access to audit logs |

All access is logged. Access to personal data requires a documented purpose.

### 17.5 Security Controls

| Control | Implementation |
|---|---|
| **Encryption at rest** | AES-256 |
| **Encryption in transit** | TLS 1.3 |
| **Key management** | Hardware-backed keystore; HSM for server keys |
| **Authentication** | Anonymous tokens for citizens; OAuth 2.0 + PKCE + MFA for staff |
| **Authorisation** | RBAC with least privilege |
| **Audit logging** | Immutable logs of all data access and sharing |
| **Vulnerability management** | Monthly scanning; quarterly penetration testing |
| **Incident response** | Documented plan; 72-hour breach notification per DPA |
| **Secure development** | SAST, DAST, dependency scanning in CI |
| **Third-party assessment** | Annual independent security audit |
| **Bug bounty** | Public programme with responsible disclosure |

### 17.6 Children's Data

- Children under 18 require guardian consent for identified profiles
- Anonymous use of Tier 1 features requires no consent
- Children's health records are controlled by the guardian
- At age 18, control transfers to the individual
- No behavioural advertising (there is none in the app)
- Extra protections for adolescent reproductive health data

### 17.7 Data Sharing Agreements

Formal agreements required with:

- Ministry of Health
- County health departments
- ADaM / ICAP
- Telco partners
- WhatsApp / Meta
- Cloud provider
- Any research partner

Each agreement specifies purpose, scope, retention, security, and audit rights.

---

## 18. Integration with Existing Systems

### 18.1 ADaM Platform

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| Case reports from CHW module | App → ADaM | Structured case reports | Real-time on sync |
| Contact monitoring summaries | App → ADaM | Daily symptom summaries (consented) | Daily |
| Case status updates | ADaM → App | Investigation status, lab results | On change |
| Contact assignments | ADaM → App | New contacts to monitor | On assignment |
| Case definitions | ADaM → App | Updated clinical criteria | On change |

**Technical:** REST API with mutual TLS, field-level encryption for PII, audit logging on both sides.

---

### 18.2 JALI Chatbot

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| User launch | App → JALI | Deep link with context | On demand |
| Misinformation corrections | JALI → App | Correction content | On publish |
| Symptom assessment sharing | App → JALI | Assessment summary (consented) | On request |
| Health worker review | JALI → App | Clinician response | On review |

---

### 18.3 PHEOC Dashboards

| Data feed | Direction | Granularity | Frequency |
|---|---|---|---|
| Aggregated symptom reports | App → PHEOC | Sub-county | Hourly |
| Case reports | App → PHEOC | Facility | Real-time |
| Geofence entry/exit events | App → PHEOC | Aggregated, min cell 10 | Hourly |
| Misinformation flags | App → PHEOC | Topic and county | Hourly |
| Early warning signals | AI → PHEOC | Sub-county | Daily |
| Resource deployment recommendations | AI → PHEOC | County | Daily |

---

### 18.4 719 Hotline

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| One-tap call | App → 719 | Call initiation | On demand |
| Auto-call on fall detection | App → 719 | Call + location | On event |
| Callback request | App → 719 | Phone number + reason | On request |
| SMS follow-up | 719 → App | Follow-up message | On case action |
| Call outcome | 719 → App | Outcome code (where consented) | On close |

---

### 18.5 Kenya Master Health Facility List

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| Facility data | MoHF → App | Facility list, services, location | Weekly |
| Facility status updates | App → MoHF | Crowdsourced corrections | On report |
| Facility verification | MoHF → App | Verified status | Weekly |

---

### 18.6 SHA / NHIF

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| Cover verification | App → SHA | Member number, cover status | On request |
| Facility acceptance list | SHA → App | Facilities accepting SHA | Weekly |
| Benefit information | SHA → App | Covered services | On change |

---

### 18.7 Pharmacy and Poisons Board

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| Medicine registry | PPB → App | Registered products, status | Daily |
| Recalls | PPB → App | Recall notices | On issue |
| Suspicious medicine reports | App → PPB | Report with photo | On report |

---

### 18.8 Telco Gateways

| Integration point | Direction | Data | Frequency |
|---|---|---|---|
| SMS outbound | App → Telco | Alert messages | On trigger |
| SMS inbound | Telco → App | Reports, requests | Real-time |
| USSD sessions | Telco ↔ App | Menu interactions | Real-time |
| Zero-rating configuration | Telco → App | Billing rules | On change |
| Airtime incentives | App → Telco | Disbursement requests | Weekly |

---

## 19. AI, Analytics, and Prediction

### 19.1 On-Device AI Models

| Model | Purpose | Size | Framework |
|---|---|---|---|
| Triage classifier | Symptom → risk classification | <1 MB | TFLite |
| Cough detection | Audio → cough event | <2 MB | TFLite |
| Cough classification | Cough → type | <1 MB | TFLite |
| Fall detection | IMU → fall event | <1 MB | TFLite |
| Respiration estimation | LiDAR → respiratory rate | <3 MB | TFLite |
| Speech recognition | Voice → text (local languages) | <20 MB | TFLite / Whisper-tiny |
| Image quality | Photo → quality score | <1 MB | TFLite |

**Total on-device model footprint:** ~30 MB (loaded as needed, not all at once).

---

### 19.2 Server-Side AI

| Model | Purpose | Inputs | Outputs |
|---|---|---|---|
| Outbreak early warning | Detect anomalous patterns | Aggregated symptom, search, and encounter data | Signal + confidence |
| Hotspot prediction | Predict next-case locations | Aggregated case and mobility data | Probability map |
| Misinformation detection | Identify emerging rumours | Text and voice submissions | Topic cluster + velocity |
| Content recommendation | Personalise health education | Engagement history | Content items |
| Stockout prediction | Predict medicine stockouts | Crowdsourced reports + facility data | Probability by facility |

---

### 19.3 AI Ethics and Governance

| Principle | Implementation |
|---|---|
| **Explainability** | Every AI output includes a plain-language reason |
| **Fairness** | Models validated across gender, age, region, and skin tone; bias audits before deployment |
| **Human in the loop** | Clinical decisions always involve a human; AI assists, never decides |
| **Transparency** | Model cards published; limitations disclosed |
| **Accountability** | Named owner for each model; review board for high-risk models |
| **Privacy** | On-device where possible; aggregated and anonymised where not |
| **Consent** | Research use requires separate, explicit consent |
| **Redress** | Users can challenge AI-driven outcomes |

---

### 19.4 Analytics for Public Health

**Dashboards:**

- Real-time symptom surveillance by county
- Triage volume and risk distribution
- Case report pipeline and status
- Contact monitoring adherence
- Proximity encounter density
- Content engagement
- Misinformation velocity
- Facility and drug availability
- Alert reach and response

**Access:** PHEOC, county health teams, MoH. Role-based. Audit logged.

---

# PART V — GO-TO-MARKET AND OPERATIONS

---

## 20. Distribution, Partnerships, and Growth Strategy

### 20.1 The Adoption Problem

With one reported case in a country of 50 million, fear will not drive downloads at scale. Fear-based downloads also churn the moment the news cycle moves on. If the product is "the Ebola app," it will be downloaded by a few hundred thousand people, opened twice, and deleted.

**Therefore:** Adoption must come from genuine utility, trusted intermediaries, and zero-friction access.

---

### 20.2 The Six Growth Levers

| # | Lever | Why it matters | Action |
|---|---|---|---|
| 1 | **Zero-rated data** | The single largest barrier to app use in Kenya | Negotiate with Safaricom, Airtel, Telkom before launch |
| 2 | **Utility in 60 seconds** | Value before commitment | Tier 1 designed for immediate payoff |
| 3 | **Trust** | Government-only branding limits adoption | Co-brand with Kenya Red Cross, AMREF, WHO, faith networks; open-source client |
| 4 | **Social proof** | CHWs, chemists, faith leaders drive adoption, not app stores | Structured intermediary programme (CHAN-5) |
| 5 | **Friction removal** | Under 15 MB; no account; Android Go; offline | Engineering requirements |
| 6 | **Incentive** | Airtime or data bundles for health profile completion | Telco partnership; short-term boost |

**What does not work:** fear, unrequested push notifications, a 60 MB app, a login wall, and a name with "Ebola" in it.

---

### 20.3 Channel-by-Channel Acquisition

| Channel | Primary acquisition role | Tactics |
|---|---|---|
| Radio | Mass awareness | Daily segments, call-ins, drama vignettes |
| SMS | Opt-in list building | Zero-rated alerts with opt-in keyword |
| USSD | Non-smartphone reach | Menu with "download app" option via SMS link |
| WhatsApp | Primary conversion | Forwardable cards with download links; bot → app handoff |
| Social media | Youth reach | TikTok myth-busting, Instagram explainers, X threads |
| Human intermediaries | Trust transfer | CHWs, chemists, faith leaders, boda SACCOs |
| App stores | Discovery | ASO, ratings, reviews |

---

### 20.4 Partnership Map

| Partner type | Specific partners | Role |
|---|---|---|
| **Telcos** | Safaricom, Airtel Kenya, Telkom Kenya | Zero-rating, SMS/USSD gateway, airtime incentives, distribution |
| **Health NGOs** | Kenya Red Cross, AMREF Health Africa, Living Goods, Medic, Dimagi | CHW networks, field validation, credibility |
| **Government** | MoH, PHEOC, county health teams, PPB, SHA | Data, authority, integration |
| **Faith networks** | NCCK, SUPKEM, Catholic Secretariat, evangelical associations | Trust, distribution, burial guidance |
| **Transport** | Boda boda SACCOs, matatu SACCOs, long-distance operators | Mobility, distribution, trusted voices |
| **Retail** | Pharmacy chains, chemists, supermarkets, kiosks | Medicine verification, distribution, stock reporting |
| **Education** | Universities, TVETs, secondary schools | Student adoption, peer spread |
| **Media** | KBC, Royal Media, Radio Africa, Standard Group, Nation Media | Awareness, credibility |
| **International** | WHO, UNICEF, CDC, Africa CDC | Technical guidance, funding, legitimacy |
| **Tech** | Google, Meta, Safaricom Spark | Platform support, zero-rating, technical resources |

---

### 20.5 Launch Sequence

**Phase 0 — Pre-launch (2 weeks before):**
- Finalise telco zero-rating agreements
- Brief county health teams and CHWs
- Pre-load content in all languages
- Set up 719 integration and referral pathways
- Test with 500 pilot users in two counties
- Train 200 CHWs as launch champions

**Launch week:**
- Radio blitz across partner stations
- WhatsApp bot goes live
- SMS opt-in campaign
- Social media campaign
- CHW door-to-door in high-risk areas
- App store launch
- Press conference with MoH and partners

**Weeks 2–4:**
- Scale CHW training to 2,000
- Expand radio to all counties
- First misinformation response cycle
- Weekly user feedback sessions
- Iterate on onboarding based on drop-off data

---

### 20.6 Retention Strategy

Acquisition is easy compared to retention. Key mechanisms:

| Mechanism | Feature | Frequency |
|---|---|---|
| Immunisation reminders | MON-001 | Monthly per child |
| Medication reminders | MON-004 | Daily |
| ANC reminders | MON-002 | Monthly |
| Community alerts | ALT-001 | Weekly |
| Health tips | INF-008 | Weekly |
| Facility finder | FND-001 | As needed |
| Medicine verifier | MED-001 | As needed |
| Family wallet | REC-002 | As needed |
| Drug stock reports | MED-004 | As needed |

**The key insight:** A parent with a child under 5 has a reason to open the app every month for years. A person on chronic medication has a reason to open it every day. These users will still have the app installed when the next outbreak comes.

---

## 21. Rollout and Phasing

### 21.1 Phase Overview

| Phase | Timeline | Objective | Channels | Tiers |
|---|---|---|---|---|
| **0 — Foundation** | Weeks -8 to 0 | Build, partner, prepare | — | — |
| **1 — Information First** | Weeks 0–4 | Maximum reach, minimum friction | CHAN-0,1,2,3,4,5 | Info only |
| **2 — Utility Launch** | Weeks 2–8 | App launch with Tier 1 | + CHAN-6 | Tier 1 |
| **3 — Retention Build** | Months 2–6 | Tier 2 features, CHW scale | All | Tier 1–2 |
| **4 — Daily Habit** | Months 4–12 | Tier 3 features | All | Tier 1–3 |
| **5 — Outbreak Ready** | Months 6–12 | Tier 4 build and test | All | Tier 1–4 |
| **6 — Scale and Sustain** | Month 12+ | Multi-disease, national integration | All | All |

---

### 21.2 Phase 1 — Information First (Weeks 0–4)

**Objective:** Reach millions without requiring a download.

**Deliverables:**
- Community radio partnership live in 20+ stations
- Zero-rated SMS alerts operational
- USSD menu live
- WhatsApp bot live with triage, Q&A, myth-busting
- Social media campaign
- 200 CHWs trained as information intermediaries
- Content in 6 languages minimum

**Success criteria:** 500,000 SMS opt-ins; 100,000 WhatsApp users; 50 stations broadcasting.

**Why this phase first:** It delivers the mission — protecting people — without waiting for app development. It builds the audience the app will later convert.

---

### 21.3 Phase 2 — Utility Launch (Weeks 2–8)

**Objective:** Launch the app with features that earn a permanent place on the home screen.

**Deliverables:**
- App live on Google Play and App Store
- Tier 1 features complete
- Zero-rated app data
- 2,000 CHWs trained
- Facility data loaded for all 47 counties
- Medicine registry cached
- Emergency SOS live
- 719 integration live

**Success criteria:** 300,000 installs; 4.0+ rating; 40% D30 retention; 50,000 triages.

---

### 21.4 Phase 3 — Retention Build (Months 2–6)

**Deliverables:**
- Child immunisation tracker
- Pregnancy and ANC tracker
- Chronic disease log
- Medication reminders
- Family health wallet (basic)
- Drug stock crowdsourcing
- Appointment booking pilot
- Service status feed

**Success criteria:** 1M installs; 25% DAU/MAU; 100,000 children tracked; 200,000 medication reminders active.

---

### 21.5 Phase 4 — Daily Habit (Months 4–12)

**Deliverables:**
- Full family health wallet with cloud backup
- Growth and development tracker
- Mental health support
- Blood donor matching
- Water quality alerts
- Air quality index
- Community reporting
- First aid guide
- Nutrition guidance
- Safe and dignified burial guidance

**Success criteria:** 2M installs; 35% DAU/MAU; 20% of users open the app daily.

---

### 21.6 Phase 5 — Outbreak Ready (Months 6–12)

**Deliverables:**
- 21-day contact monitoring
- CHW case reporting module
- Bluetooth proximity logging
- GPS location history for contact tracing
- QR/NFC check-in
- LiDAR respiration monitoring
- Acoustic cough monitoring
- Fall detection (enhanced)
- Wearable integration
- AI risk prediction
- Early warning signal
- Full PHEOC integration

**Testing:** Tabletop exercises with PHEOC; simulated outbreak activation; red team review of privacy controls.

**Success criteria:** Tier 4 activation in under 60 minutes; <5% daily battery impact; full offline operation verified.

---

### 21.7 Phase 6 — Scale and Sustain (Month 12+)

**Deliverables:**
- Multi-disease support (cholera, Rift Valley fever, mpox, measles)
- Integration into national health information system
- Sustainable funding model
- Regional expansion (Uganda, Tanzania, DRC, South Sudan)
- Continuous improvement based on user feedback

---

## 22. Success Metrics and Evaluation

### 22.1 North Star Metrics

| Metric | Definition | Target (12 months) |
|---|---|---|
| **People reached** | Unique individuals receiving health information through any channel | 15 million |
| **People protected** | Individuals who completed a triage and received actionable guidance | 3 million |
| **Lives saved (estimated)** | Cases detected earlier than they would have been otherwise | Measured via modelling |
| **Retention** | DAU/MAU ratio | 35% |

---

### 22.2 Reach Metrics

| KPI | Target | Measurement |
|---|---|---|
| App downloads | 2 million | App stores |
| WhatsApp bot users | 2 million | Meta Business API |
| SMS opt-ins | 3 million | Gateway |
| USSD sessions per month | 500,000 | Telco |
| Radio reach (weekly) | 10 million | Station surveys |
| Social media reach | 20 million | Platform analytics |
| CHWs onboarded | 5,000 | Registry |

---

### 22.3 Engagement Metrics

| KPI | Target | Measurement |
|---|---|---|
| DAU | 500,000 | App analytics |
| MAU | 1.5 million | App analytics |
| DAU/MAU | 35% | Derived |
| Triages per month | 200,000 | Backend |
| Symptom assessments completed | 85% | Funnel |
| Average session duration | 2 minutes | App analytics |
| Push notification opt-in | 60% | App analytics |

---

### 22.4 Health Outcome Metrics

| KPI | Target | Measurement |
|---|---|---|
| Contacts monitored to completion | 90% | MON-009 data |
| Median time from symptom to care-seeking | <24 hours | Triage data + follow-up |
| Exposure notifications delivered <24h | 95% | Backend |
| Misinformation corrections published <24h | 90% | Comms log |
| Malaria tests prompted | 100,000 | Triage referrals |
| Immunisation doses on schedule | 80% of tracked children | MON-001 |
| Medication adherence | 70% | MON-004 |

---

### 22.5 Technical Metrics

| KPI | Target |
|---|---|
| API p95 latency | <300 ms |
| Uptime | 99.9% |
| Crash-free sessions | 99.5% |
| Sync success rate | 98% |
| Offline feature availability | 100% of core features |
| Battery impact (all sensors) | <5% per day |
| APK base size | <15 MB |

---

### 22.6 Privacy and Trust Metrics

| KPI | Target |
|---|---|
| Users who review privacy dashboard | 30% |
| Consent revocation rate | <2% |
| Data subject access requests fulfilled <30 days | 100% |
| Security incidents | 0 major |
| Privacy complaints | <0.01% of users |
| Independent audit findings closed | 100% |

---

### 22.7 Equity Metrics

| KPI | Target |
|---|---|
| Female users | ≥50% |
| Users outside Nairobi | ≥70% |
| Users on Android Go devices | ≥30% |
| Users on feature phones reached | ≥5 million |
| Local language usage | ≥60% |
| Users over 50 | ≥15% |

---

### 22.8 Evaluation Framework

| Level | Method | Frequency |
|---|---|---|
| **Process** | Feature usage, funnel analysis, technical performance | Monthly |
| **Outcome** | Early detection rates, care-seeking behaviour, contact tracing completeness | Quarterly |
| **Impact** | Contribution to outbreak control, health system strengthening, cost-effectiveness | Annually |
| **Equity** | Disaggregated analysis by gender, geography, age, device | Quarterly |
| **Privacy** | DPIA review, audit findings, user trust survey | Semi-annually |

---

## 23. Risks and Mitigations

### 23.1 Strategic Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Low adoption due to data cost | High | High | Zero-rating agreements before launch; multi-channel strategy |
| Branded as "Ebola app" and abandoned post-outbreak | High | High | Position as health companion; Tier 1–3 features |
| Government change of priorities | Medium | High | Multi-stakeholder ownership; institutional embedding |
| Funding ends after outbreak | High | High | Sustainable funding model; integration into national budget |
| Competitor or parallel initiative | Medium | Medium | Coordination with MoH; avoid duplication |

### 23.2 Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CHW capacity constraints | High | Medium | Simple tools; training; incentives; supervision |
| Content not updated | Medium | High | Content governance; SLAs; automated staleness alerts |
| Facility data inaccurate | High | Medium | Crowdsourced corrections; regular MoHF sync |
| Misinformation overwhelms response | High | Medium | Pre-drafted corrections; rapid response protocol |
| Panic from alerts | Medium | High | Verify before publishing; calm tone; community testing |
| Stigma from exposure notification | Medium | High | Anonymity; non-stigmatising language; community engagement |
| Alert fatigue | High | Medium | Granular preferences; critical-only defaults |

### 23.3 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Telco zero-rating not secured | Medium | High | Multi-telco negotiation; fallback to USSD/SMS |
| Device fragmentation | High | Medium | Flutter; graceful degradation; Android Go support |
| Battery drain complaints | Medium | Medium | Adaptive sampling; user controls; <5% target |
| Sync failures in low connectivity | High | Medium | Robust queue; exponential backoff; user-visible status |
| Backend scalability | Low | High | Load testing; auto-scaling; CDN |
| Integration failures with ADaM/PHEOC | Medium | High | Early technical engagement; fallback manual processes |
| Security breach | Low | Very High | Encryption; audits; bug bounty; incident response |
| LiDAR accuracy issues | Medium | Low | Confidence indicators; fallback to acoustic/manual |
| Acoustic model false positives | High | Medium | Baseline personalisation; threshold tuning; user feedback loop |

### 23.4 Privacy and Ethical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Location data misuse | Low | Very High | On-device processing; geohashing; consent; audit |
| Proximity data deanonymisation | Low | Very High | PET architecture; trusted proxy; min cell size |
| AI bias (skin tone, gender, region) | Medium | High | Diverse validation; bias audits; published model cards |
| Surveillance creep | Medium | Very High | Legal constraints; DPIA; transparency reports; oversight board |
| Contact tracing data retained too long | Medium | High | Automatic deletion; retention schedule; audit |
| Children's data misuse | Low | High | Guardian consent; age-appropriate design; extra protections |
| Misuse by authorities | Low | Very High | Legal agreements; audit; independent oversight; open source |

### 23.5 Reputational Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Perceived as government surveillance | Medium | High | Open source; transparency reports; privacy by design |
| Failure during outbreak | Medium | Very High | Load testing; red team; disaster recovery; manual fallback |
| False reassurance from triage | Medium | High | Clear disclaimers; conservative thresholds; clinical review |
| Stigmatising a community | Medium | High | Non-stigmatising language; community engagement; rapid correction |
| Media misrepresentation | Medium | Medium | Proactive comms; media training; transparency |

---

## 24. Operational Considerations

### 24.1 Governance

| Body | Composition | Role |
|---|---|---|
| **Steering Committee** | MoH, PHEOC, implementing partner, telcos, NGO partners | Strategic direction, funding, escalation |
| **Clinical Advisory Group** | Clinicians, epidemiologists, WHO, CDC | Clinical content, triage logic, case definitions |
| **Technical Working Group** | Engineers, architects, security, data | Architecture, integration, security |
| **Privacy and Ethics Board** | DPO, legal, ethicists, civil society, community reps | DPIA, AI ethics, consent, oversight |
| **Community Advisory Panel** | CHWs, faith leaders, youth reps, women's reps | Usability, cultural appropriateness, feedback |
| **Operations Cell** | Programme manager, content lead, support lead, data lead | Day-to-day operations |

### 24.2 Content Operations

| Function | Owner | Cadence |
|---|---|---|
| Content drafting | Content lead | Continuous |
| Clinical review | Clinical advisory group | Weekly (outbreak) / Monthly (steady) |
| Translation | Localisation team | As needed |
| Community validation | Community advisory panel | Monthly |
| Publishing | Content lead | Daily (outbreak) / Weekly (steady) |
| Staleness audit | Content lead | Monthly |
| Misinformation response | Comms lead | On trigger |

### 24.3 Support Operations

| Channel | Coverage | Staffing |
|---|---|---|
| In-app help | 24/7 (self-service) | — |
| WhatsApp support | 8am–8pm, 7 days | 5 agents |
| Phone support | 8am–8pm, 7 days | 3 agents |
| CHW escalation | 24/7 | Roving |
| Technical incidents | 24/7 | On-call engineer |

**Response SLAs:**
- Critical (system down): 15 minutes
- High (feature broken): 2 hours
- Medium (usability issue): 24 hours
- Low (enhancement request): 1 week

### 24.4 Training

| Audience | Content | Format | Duration |
|---|---|---|---|
| CHWs | App use, case reporting, triage, referral | In-person + e-learning | 2 days |
| Facility staff | App integration, referral handling | In-person | 4 hours |
| County health teams | Dashboards, alerting, data use | In-person | 1 day |
| PHEOC analysts | Analytics, AI outputs, escalation | In-person | 2 days |
| Support agents | All features, escalation paths | In-person + shadowing | 3 days |
| Community leaders | Awareness, referral | Community session | 2 hours |
| Radio partners | Messaging, verification | Briefing pack | 1 hour |

**Refresher:** Quarterly. **New feature training:** On release.

### 24.5 Funding Model

| Phase | Primary funding | Sustainability |
|---|---|---|
| Phase 0–1 (emergency) | Government emergency funds, donor grants | — |
| Phase 2–3 (build) | Donor grants, PPP | — |
| Phase 4–5 (scale) | Donor grants + government budget line | Begin integration into MoH budget |
| Phase 6+ (sustain) | Government budget + telco CSR + foundation grants | Fully integrated into national health budget |

**Cost drivers:** Engineering, content, translation, cloud, SMS/WhatsApp, support, training, evaluation.

**Cost mitigation:**
- Zero-rating reduces user cost but may require telco CSR commitment
- Open-source reduces licensing
- Shared infrastructure with MoH
- Volunteer CHW network (with incentives)
- Grant funding for outbreak-specific work

### 24.6 Sustainability Beyond the Outbreak

The critical risk is that funding and attention evaporate when the outbreak ends. Mitigations:

1. **Position as permanent health infrastructure**, not an outbreak tool
2. **Tier 1–3 features are useful year-round** — this is the retention engine
3. **Integrate into MoH budget** by Phase 6
4. **Multi-disease scope** justifies ongoing investment
5. **Measurable health impact** in non-outbreak periods (immunisation, medication adherence, malaria)
6. **Telco partnership** provides ongoing distribution and zero-rating
7. **Open-source community** reduces maintenance cost
8. **Regional expansion** shares cost across countries

### 24.7 Legal and Regulatory Operations

| Requirement | Owner | Cadence |
|---|---|---|
| DPIA update | DPO | Before each Tier 4 activation |
| Data sharing agreement review | Legal | Annually |
| Security audit | CISO | Annually |
| Privacy policy review | DPO + Legal | Annually |
| ODPC registration | DPO | On change |
| MoH registration | Programme manager | On change |
| Telco agreement review | Legal | Annually |
| Content legal review | Legal | On publish (sensitive content) |

### 24.8 Incident Response

| Incident type | Severity | Response |
|---|---|---|
| Data breach | Critical | Isolate, assess, notify ODPC within 72h, notify affected users, remediate |
| System outage | Critical | Failover, status page, comms, root cause analysis |
| False alert published | High | Immediate correction on all channels, investigation, process fix |
| Misinformation spike | High | Rapid response protocol |
| Content error (clinical) | Critical | Immediate correction, clinical review, user notification |
| Privacy complaint | Medium | Investigate, respond within 30 days, remediate |
| Security vulnerability | High | Patch, disclose responsibly, audit for exploitation |

**Incident response team:** On-call engineer, DPO, comms lead, programme manager.

**Post-incident:** Root cause analysis within 5 days. Public report for major incidents.

---

# PART VI — APPENDICES

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **ADaM** | ICAP's case investigation and contact tracing platform |
| **ANC** | Antenatal Care |
| **AVADAR** | Auto-Visual AFP Detection and Reporting |
| **BLE** | Bluetooth Low Energy |
| **CHW** | Community Health Worker |
| **CHP** | Community Health Promoter |
| **DPIA** | Data Protection Impact Assessment |
| **DPO** | Data Protection Officer |
| **DPA** | Data Protection Act (Kenya, 2019) |
| **EBID** | Ephemeral Bluetooth Identifier |
| **EPI** | Expanded Programme on Immunisation |
| **EVD** | Ebola Virus Disease |
| **GBV** | Gender-Based Violence |
| **GPS** | Global Positioning System |
| **GNSS** | Global Navigation Satellite System |
| **HRV** | Heart Rate Variability |
| **IDSR** | Integrated Disease Surveillance and Response |
| **IMCI** | Integrated Management of Childhood Illness |
| **IMU** | Inertial Measurement Unit (accelerometer + gyroscope) |
| **JALI** | Kenya MoH WhatsApp chatbot |
| **LiDAR** | Light Detection and Ranging |
| **MAU** | Monthly Active Users |
| **DAU** | Daily Active Users |
| **MoHF** | Kenya Master Health Facility List |
| **MoH** | Ministry of Health |
| **MUAC** | Mid-Upper Arm Circumference |
| **NFC** | Near Field Communication |
| **ODPC** | Office of the Data Protection Commissioner |
| **ORS** | Oral Rehydration Solution |
| **PET** | Private Encounter Token |
| **PHEOC** | Public Health Emergency Operations Centre |
| **PHQ-9** | Patient Health Questionnaire-9 (depression screening) |
| **GAD-7** | Generalised Anxiety Disorder-7 (anxiety screening) |
| **PMTCT** | Prevention of Mother-to-Child Transmission |
| **PPB** | Pharmacy and Poisons Board |
| **PPE** | Personal Protective Equipment |
| **PPG** | Photoplethysmography |
| **RBAC** | Role-Based Access Control |
| **RDT** | Rapid Diagnostic Test |
| **SHA** | Social Health Authority |
| **SpO₂** | Peripheral Oxygen Saturation |
| **TB** | Tuberculosis |
| **TFLite** | TensorFlow Lite |
| **USSD** | Unstructured Supplementary Service Data |
| **WHO** | World Health Organization |

---

## Appendix B: Feature Index by ID

### Channel Features
| ID | Name | Section |
|---|---|---|
| CHAN-000 | Community Radio | 5.3 |
| CHAN-001 | SMS (Zero-Rated) | 5.3 |
| CHAN-002 | USSD | 5.3 |
| CHAN-003 | WhatsApp Bot | 5.3 |
| CHAN-004 | Social Media | 5.3 |
| CHAN-005 | Human Intermediaries | 5.3 |
| CHAN-006 | Native Application | 5.3 |

### Information
| ID | Name | Tier |
|---|---|---|
| INF-001 | County Risk Dashboard | 1 |
| INF-002 | "What Should I Do?" Decision Tree | 1 |
| INF-003 | Ebola Information Library | 1 |
| INF-004 | Myth-Busting Library | 1 |
| INF-005 | Travel Advisory | 1 |
| INF-006 | Hotline and Contact Directory | 1 |
| INF-007 | Service Status Feed | 2 |
| INF-008 | Health Tips and Education | 3 |
| INF-009 | First Aid Guide | 3 |
| INF-010 | Safe and Dignified Burial Guidance | 3/4 |

### Triage
| ID | Name | Tier |
|---|---|---|
| TRI-001 | Broad Febrile-Illness Triage | 1 |
| TRI-002 | Symptom Diary and Follow-Up | 1 |
| TRI-003 | Ebola-Specific Triage | 4 |

### Facility
| ID | Name | Tier |
|---|---|---|
| FND-001 | Facility Finder | 1 |
| FND-002 | Emergency Department Status | 1 |
| FND-003 | Testing Site Locator | 1/4 |
| FND-004 | Pharmacy and Chemist Finder | 1 |
| FND-005 | Vaccination Point Finder | 1 |
| FND-006 | Appointment Booking and Queue Management | 2 |

### Medicine
| ID | Name | Tier |
|---|---|---|
| MED-001 | Medicine Verifier | 1 |
| MED-002 | Drug Interaction and Safety Checker | 1 |
| MED-003 | Dosage Calculator | 1 |
| MED-004 | Drug Stock Crowdsourcing | 2 |

### Emergency
| ID | Name | Tier |
|---|---|---|
| EMG-001 | Emergency SOS | 1 |
| EMG-002 | Fall Detection and Auto-Alert | 1 |
| EMG-003 | Offline Emergency Card | 1 |

### Records
| ID | Name | Tier |
|---|---|---|
| REC-001 | Family Health Wallet (Basic) | 2 |
| REC-002 | Family Health Wallet (Full) | 3 |
## Appendix B (continued): Features by ID — Tier 4 / Sensors

| ID | Name | Tier |
|---|---|---|
| REC-003 | Growth Monitoring Chart | 3 |
| LOC-001 | Geofenced Risk Alerts | 4 |
| SENS-001 | LiDAR Respiration Monitoring | 4 |
| SENS-002 | Acoustic Cough Detection | 4 |
| SENS-003 | Fall Detection (see EMG-002) | 1 |
| SENS-004 | Camera-Based Symptom Capture | 4 |
| SENS-005 | Screen/Camera PPG Health Monitoring | 2 |
| SENS-006 | Wearable Integration | 2 |
| SENS-007 | Sleep and Activity Monitoring | 2 |
| SENS-008 | Environmental and Ambient Sensing | 4 |

> This appendix was reconstructed on 2026-10-08 from the document's own §14 headings and §11 tier model; the original file was truncated mid-table. Tier assignments follow §11 (dormant outbreak capabilities) except SENS-003/EMG-002, which is a year-round Tier 1 feature.

## Appendix C: References

> ⚠️ Derived solely from in-text mentions (§2.3 and body); none independently confirmed. Validate before external publication.

1. AVADAR (Auto-Visual AFP Detection and Reporting) — polio surveillance across ten African countries (§2.3).
2. LiBre and successor LiDAR respiration monitoring literature (§2.3).
3. DESIRE architecture — combined centralised/decentralised COVID-19 exposure notification using Ephemeral Bluetooth Identifiers and Private Encounter Tokens (§2.3).
4. Kenya Data Protection Act 2019 (DPA 2019), Office of the Data Protection Commissioner (§17).
5. Kenya Digital Health Act 2023 (§17).
6. Kenya Master Health Facility List / MoH (§18.5).
7. ACM MobiSys-class literature on offline-first modular mHealth platforms (§2.3).

## Appendix D: Open Questions and Decisions Required

> ⚠️ Reconstructed 2026-10-08 from the document's open flags; additions belong to the product owner.

| # | Question | Blocks |
|---|---|---|
| 1 | Product owner entity (MoH Digital Health Agency vs implementing partner) — listed TBD | governance, contracting |
| 2 | Official hotline codes/platform names/case counts require MoH/PHEOC validation (see Verification Note) | content, USSD menus, INF-006 |
| 3 | Tier-4 activation protocol: who holds PHEOC authorization + flag authority + DPIA sign-off? | surveillance gate |
| 4 | Cloud provider + data residency final selection (AWS Africa vs Azure South Africa vs on-prem) | §15.3, DPIA |
| 5 | Unleash instance vs internal feature flags for Tier-4 control | §15.2 |
| 6 | Telco zero-rating agreements for CHAN-001 | distribution |
| 7 | Retention policy per data type needs ODPC sign-off (24-month cap assumed in code) | privacy service |
