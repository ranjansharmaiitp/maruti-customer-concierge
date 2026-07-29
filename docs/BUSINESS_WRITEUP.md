# 📄 Enterprise Business Proposal & Executive Write-Up
## **Car AI Doctor: Multilingual Voice & Agentic Vehicle Diagnostic Assistant**

**Target Audience:** CTO, VP of Customer Experience, VP of Service Operations (Automotive OEMs, NBFC Auto Finance, Roadside Assistance & Service Chains)
**Author:** Pre-Sales Engineer, Sarvam AI Stack Integration
**Date:** July 2026

---

### Executive Summary

India has over **300 Million registered vehicles**, with over **30 Million emergency roadside assistance calls, service inquiries, and break-down diagnostic queries** logged annually.

**Car AI Doctor** is an enterprise-grade, multilingual voice bot and agentic dispatch solution built on the **Sarvam AI Stack** (`saaras:v3`, `sarvam-105b`, `bulbul:v3`). It enables automotive manufacturers (OEMs), insurance providers, and service networks to automate Tier-1 automotive triage, accurately assess fault urgency, provide immediate step-by-step diagnostic checklists in regional Indian languages, and seamlessly schedule appointments with certified Master Technicians with an instant **Customer Reference ID**.

---

### 1. The Problem

Automotive OEMs and service networks in India face four major operational bottlenecks:

1. **High Call Center Costs:**
   Inbound helpline calls cost between **₹70 – ₹120 per call** with human agents. A OEM handling 500,000 monthly service & emergency breakdown calls incurs over **₹4.5 Crore/month** in support overheads.
2. **Language & Digital Literacy Barriers:**
   Over 70% of vehicle owners and commercial drivers across Tier-2, Tier-3, and rural India prefer communicating in regional languages (Hindi, Tamil, Telugu, Marathi, etc.) or code-mixed Hinglish. Traditional key-press IVRs have a **65% drop-off rate**.
3. **Safety Risks & Misdiagnosis:**
   Drivers frequently ignore critical dashboard warning lights (e.g., oil pressure, engine overheating) due to a lack of immediate understanding, leading to catastrophic engine damage and roadside accidents.
4. **Friction in Service Booking:**
   Converting a breakdown inquiry into a scheduled garage service currently requires multi-touch manual dispatch, leading to lost service revenue for dealerships.

---

### 2. Why AI?

A **Voice-First AI Agent + Agentic Workflow** is uniquely suited for automotive customer support:

* **Zero Friction for Drivers:** Drivers do not need to read complex manuals or navigate apps while stranded. They press a button and speak naturally in their native language.
* **Instant Automated Triage:** The AI classifies fault severity into **PULL OVER IMMEDIATELY**, **CAUTION**, or **SAFE TO DRIVE** within seconds, ensuring driver safety.
* **Autonomous Downstream Actions:** The agent doesn't just answer questions; it executes agentic workflows — generating a unique **Customer Reference ID** (`REF-XXXXXX`), assigning certified Master Technicians, and updating service queue databases automatically.

---

### 3. Why Sarvam AI?

Generic global AI platforms (OpenAI, ElevenLabs, Whisper) fall short in the Indian automotive context due to language nuances, latency, and high cost. **Sarvam AI provides unmatched competitive advantages:**

| Requirement | Generic Global AI (OpenAI / Whisper) | **Sarvam AI Stack** | Business Impact |
|---|---|---|---|
| **Regional Speech Recognition** | Poor accuracy on Indian accents, road background noise, and regional dialects | **Sarvam `saaras:v3`** — Native ASR across 10+ Indian languages + Hinglish | 94%+ transcription accuracy in noisy environments |
| **Reasoning & Diagnostic LLM** | Expensive API costs, high latency for long prompts | **Sarvam `sarvam-105b`** — Optimized for Indian regional reasoning & automotive context | Sub-second diagnostic reasoning, 80% lower API cost |
| **Natural Voice Synthesis** | Robotic Hindi/Tamil voices, un-natural cadence | **Sarvam `bulbul:v3`** — Expressive regional voices (Shubh & Shreya presets) | High customer trust and brand alignment |
| **Data Sovereignty & Latency** | Servers in US/EU, data privacy concerns, high network RTT | **MeitY Compliant** — India-hosted infrastructure, ultra-low latency | Regulatory compliance for Indian enterprises |

---

### 4. Architecture Summary

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                              DRIVER / USER                             │
 │    Speaks vehicle symptoms via HMI Infotainment Touchscreen / Mobile   │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                     VOICE PIPELINE (Sarvam STT)                        │
 │  `saaras:v3` Transcribes speech audio in Hindi/Tamil/Telugu/Hinglish   │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                  DIAGNOSTIC REASONING ENGINE (Sarvam LLM)               │
 │  `sarvam-105b` Analyzes symptoms against automotive knowledge base:    │
 │   • Categorizes Urgency (PULL OVER / CAUTION / SAFE)                   │
 │   • Generates 9-Segment LED Confidence Score                        │
 │   • Builds 4-Step Actionable Checklist                                 │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                  AGENTIC DISPATCH & WORKFLOW ENGINE                   │
 │  • Generates Unique Customer Reference ID (`REF-849204`)              │
 │  • Assigns Master Technician & Scheduled Call Time                     │
 │  • Saves booking record to Enterprise Database                        │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                     VOICE SYNTHESIS (Sarvam TTS)                       │
 │  `bulbul:v3` Batched synthesis reads diagnostic checklist & booking    │
 │   confirmation aloud in driver's native language                       │
 └────────────────────────────────────────────────────────────────────────┘
```

---

### 5. ROI & Business Case

#### Operational Assumptions:
* **Target Enterprise:** Mid-sized Automotive OEM or Service Network.
* **Monthly Volume:** 100,000 inbound customer diagnostic & breakdown calls.
* **Baseline Human Cost:** ₹80 per call center interaction.
* **AI Automation Target:** 75% Tier-1 call deflection without human intervention.

#### Financial Projection:

| Metric | Current (Human Call Center) | Proposed (Car AI Doctor + Sarvam) | Impact |
|---|---|---|---|
| **Monthly Inbound Calls** | 100,000 | 100,000 | — |
| **Deflected by AI (75%)** | 0 | 75,000 calls | **75% Deflection** |
| **Cost per Deflected Call** | ₹80 | ₹12 (Sarvam API + Infra) | **85% Cost Reduction** |
| **Monthly Spend (75k calls)** | ₹60,000,000 (₹60 Lakhs) | ₹9,00,000 (₹9 Lakhs) | **₹51 Lakhs Saved / Month** |
| **Annualized Savings** | — | — | **₹6.12 Crore / Year** |
| **Service Booking Conversion** | 18% (manual callbacks) | 34% (instant Ref ID dispatch) | **+88% Booking Uplift** |

---

### 6. Limitations & 90-Day Production Roadmap

#### Current PoC Scope & Limitations:
* In-memory session and booking storage (to be replaced with PostgreSQL / Redis).
* Microphone audio capture via web browser MediaRecorder (to be extended to telephony IVR).

#### 90-Day Enterprise Production Rollout Plan:

```
  DAYS 1–30: INTEGRATION & TELEPHONY
  ├── Connect Exotel / Plivo / Twilio SIP Trunking for PSTN Phone Calls
  ├── Replace in-memory database with PostgreSQL + Redis session store
  └── Fine-tune Sarvam-105b prompt on OEM-specific vehicle DTC codes

  DAYS 31–60: ENTERPRISE CRM & DMS BINDING
  ├── Two-way sync with Salesforce / SAP Dealer Management Systems (DMS)
  ├── Automatic SMS & WhatsApp dispatch of Reference IDs with GPS location
  └── Integration with OBD-II Bluetooth telemetry streams

  DAYS 61–90: PILOT LAUNCH & SCALING
  ├── Pilot rollout across 50 dealerships in Maharashtra, Delhi-NCR & Tamil Nadu
  ├── Real-time agent escalation for Critical PULL OVER emergencies
  └── Full production deployment across nationwide roadside assistance fleet
```
