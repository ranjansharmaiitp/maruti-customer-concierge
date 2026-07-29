# 🚗 Maruti Customer Concierge — Powered by Sarvam AI

> **Voice-enabled Maruti sales and test-drive booking, plus multilingual vehicle diagnostics, powered by Sarvam AI.**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Sarvam AI](https://img.shields.io/badge/Sarvam_AI-sarvam--30b-orange)](https://sarvam.ai)

---

## 📋 Overview

**Maruti Customer Concierge** is a full-stack voice application demonstrating
Sarvam speech-to-text, language-aware responses and text-to-speech in an
automotive customer journey. Customers can discover available Maruti models,
choose a dealer and slot, and complete a test-drive booking entirely through
conversation. The project also retains its multilingual vehicle diagnostic and
expert-callback mode.

The UI is inspired by real automotive **HMI (Human-Machine Interface)** systems like Mahindra AdrenoX and Audi MMI — featuring a carbon fiber aesthetic, amber instrument cluster accents, and gauge-style controls.

## 🎬 Demo

[Watch the end-to-end voice booking demo](./demo/demo.mov)

---

## 📦 Assignment Deliverables Summary

| Deliverable | Location | Description |
|---|---|---|
| **Working Solution** | `main.py`, `sarvam_service.py`, `database.py`, `static/` | Full-stack FastAPI application with Sarvam STT/TTS, deterministic orchestration and transactional booking |
| **Business Write-Up** | [`BUSINESS_WRITEUP.md`](./docs/BUSINESS_WRITEUP.md) · [`PDF`](./docs/Maruti_Customer_Concierge_Business_Writeup.pdf) | Customer-ready CTO/VP Operations proposal covering problem, Sarvam fit, ROI assumptions, limitations and rollout |
| **Executive Deck** | [`PPTX`](./docs/Maruti_Customer_Concierge_PreSales_Deck.pptx) · [`PDF`](./docs/Maruti_Customer_Concierge_PreSales_Deck.pdf) | Eight-slide pre-sales presentation with speaker-note sources |
| **Architecture Diagram** | [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md) · [`PNG`](./docs/architecture.png) | System context, sequence, data model, API surface and production path |
| **API Setup & Docs** | `README.md` & `.env.example` | Installation guide, environment configuration, and API reference |

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎙️ **Voice Input (STT)** | Record vehicle symptoms via microphone; transcribed using Sarvam `saaras:v3` |
| 🧠 **AI Diagnostics (LLM)** | Fault analysis and step-by-step checklist via `sarvam-30b` |
| 🔊 **Voice Reply (TTS)** | Spoken diagnostic response & booking confirmation via Sarvam `bulbul:v3` |
| 📅 **Master Mechanic Call Booking** | Schedule calls with Master Techs & get a unique **Customer Reference ID** |
| 🔍 **Reference ID Lookup** | Search any Reference ID (`REF-XXXXXX`) to inspect booking status |
| 🌐 **10 Indian Languages** | Hindi, English, Tamil, Telugu, Kannada, Marathi, Bengali, Gujarati, Malayalam, Punjabi |
| 👤 **Voice Gender Toggle** | Male (Shubh) or Female (Shreya) TTS voice |
| 📊 **Confidence Score** | AI-reported HIGH / MEDIUM / LOW with 9-segment LED bar indicator |
| 🚨 **Urgency Badge** | PULL OVER IMMEDIATELY / CAUTION / SAFE TO DRIVE classification |
| ✅ **Clickable Checklist** | Step-by-step LED diagnostic items you can tick off |
| 💬 **Multi-turn Memory** | Full session history — the AI remembers prior symptoms |
| 🏎️ **Automotive HMI UI** | Carbon fiber, amber glow, Orbitron/Rajdhani fonts |
| 🔑 **Maruti Test Drives** | End-to-end voice booking with no form or confirmation click |
| 🗣️ **Deterministic Sales Workflow** | Reliable Hindi slot progression with Sarvam STT and TTS |
| 🗃️ **SQLite Dealership Data** | Generated dealer catalog, inventory, fleet capacity and transactional bookings |

---

## 🏗️ Tech Stack

### Backend
* **Framework:** FastAPI (Python 3.9+) + Uvicorn
* **HTTP Client:** Async `httpx`
* **Config:** `python-dotenv`
* **Validation:** Pydantic v2

### Sarvam AI Cloud APIs
* **Speech-to-Text:** `saaras:v3` (transcribes voice recordings across 10+ languages)
* **Diagnostic LLM:** `sarvam-30b` (automotive fault analysis & step generation)
* **Text-to-Speech:** `bulbul:v3` (speaks diagnostic reply & booking confirmation)

### Frontend
* **UI Shell:** Vanilla HTML5 / CSS3 (Automotive HMI styling)
* **Client Engine:** Vanilla JavaScript (Web Audio API, MediaRecorder)
* **Design Tokens:** Carbon fiber texture, amber LED accent (`#FF9500`), red alert (`#FF2D2D`)

---

## 📁 Repository Structure

```
Car Ai/
├── main.py                   # FastAPI app — routes, sessions, expert booking engine
├── database.py               # SQLite schema, catalog seed, inventory and transactional test-drive booking
├── data/car_company.db       # Generated locally at startup; never committed
├── sarvam_service.py         # Sarvam AI STT / LLM / TTS service layer
├── requirements.txt          # Python dependencies
├── .env.example              # Template for .env setup
├── README.md                 # Project Overview & Setup Guide
├── docs/
│   ├── BUSINESS_WRITEUP.md   # Executive proposal for CTO / VP Operations
│   ├── ARCHITECTURE.md       # Technical architecture and Mermaid diagrams
│   ├── architecture.png      # Rendered architecture summary
│   ├── Maruti_Customer_Concierge_Business_Writeup.pdf
│   ├── Maruti_Customer_Concierge_PreSales_Deck.pptx
│   └── Maruti_Customer_Concierge_PreSales_Deck.pdf
└── static/
    ├── index.html            # Automotive HMI frontend with Booking Modals
    ├── css/
    │   └── style.css         # HMI design system (carbon, amber, LED, modal styles)
    └── js/
        └── app.js            # Client logic — recording, API calls, booking dispatch
```

---

## ⚡ Quick Start

### 1. Clone & Navigate

```bash
git clone https://github.com/ranjansharmaiitp/maruti-customer-concierge.git
cd maruti-customer-concierge
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Key

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your Sarvam AI key:

```env
SARVAM_API_KEY=your_sarvam_api_key_here
```

### 4. Run the Server

```bash
python3 main.py
```

Open your browser at **http://localhost:8000**

---

## 🌐 API Reference

### `POST /api/book-expert`
Schedule a session with a Master Mechanic and generate a Customer Reference ID.

**Request:**
```json
{
  "session_id": "session_123",
  "customer_name": "Rajesh Kumar",
  "customer_phone": "+91 9876543210",
  "preferred_date": "Today",
  "preferred_time": "Within 30 Minutes",
  "issue_summary": "Engine knocking at idle",
  "language_code": "hi-IN",
  "speaker": "ShubhMale"
}
```

**Response:**
```json
{
  "status": "booked",
  "reference_id": "REF-849204",
  "customer_name": "Rajesh Kumar",
  "customer_phone": "+91 9876543210",
  "assigned_expert": "Master Tech Rajesh Kumar (Senior Automotive Specialist)",
  "scheduled_slot": "Today, Within 30 Minutes",
  "confirmation_message": "आपका विशेषज्ञ कॉल सत्र सफलतापूर्वक बुक हो गया है। आपका संदर्भ आईडी REF-849204 है।",
  "audio_b64": "<base64-encoded-wav>",
  "booking_details": { ... }
}
```

---

### `GET /api/booking/{reference_id}`
Lookup an active booking by its Customer Reference ID (e.g., `REF-849204`).

---

### `POST /api/chat`
Submit a text-based diagnostic query.

---

### `POST /api/voice-transcribe`
Submit a voice recording for the full STT → LLM → TTS pipeline.

---

### Maruti Test-Drive and Dealer APIs

| Endpoint | Purpose |
|---|---|
| `GET /api/dealerships` | List configured Arena and NEXA dealerships |
| `GET /api/cars?dealership_id=<id>` | Dealerwise Maruti catalog, sale stock and test-drive fleet |
| `GET /api/test-drive/availability` | Datewise time-slot quantity for a dealer and model |
| `POST /api/test-drive/bookings` | Reserve an available slot transactionally |
| `GET /api/test-drive/bookings/{reference_id}` | Retrieve a test-drive booking |
| `POST /api/test-drive/bookings/{reference_id}/cancel` | Cancel and return capacity to the slot |

The catalog is seeded from the current official Arena and NEXA ranges, with
prices dated `2026-07-29`. Dealer stock quantities are illustrative local demo
data because live inventory is not publicly exposed. Customers are reminded to
carry their original driving licence and original Aadhaar or PAN for both
dealership and home test drives. Document numbers are not collected or stored.

Selecting **Book Maruti Test Drive** switches the complete voice pipeline into
sales mode. The orb speaks a welcome before listening. Hindi booking stages use
a deterministic state machine grounded in SQLite, while Sarvam provides speech
recognition and voice output. “Newly launched” is calculated from each model's
stored launch date, and “ready for test drive” requires active fleet capacity
and an available slot.

The final conversation turn creates the booking automatically and speaks its
reference ID. The SMS message is currently a customer-facing simulation; a
production deployment must connect an SMS provider to deliver it.

---

## ⚙️ Sarvam API Authentication Notes

Sarvam accepts the `api-subscription-key` header on all API endpoints. The
OpenAI-compatible Chat Completions endpoint also accepts
`Authorization: Bearer <KEY>`, which this application uses for the LLM call.

| API Endpoint | Auth Header |
|---|---|
| `POST /v1/chat/completions` (LLM) | `Authorization: Bearer <KEY>` or `api-subscription-key: <KEY>` |
| `POST /speech-to-text` (STT) | `api-subscription-key: <KEY>` |
| `POST /text-to-speech` (TTS) | `api-subscription-key: <KEY>` |

The LLM defaults to `sarvam-30b`, which is recommended for lower-latency voice
agents. Set `SARVAM_LLM_MODEL=sarvam-105b` in `.env` if you prefer the larger
model. The app explicitly disables reasoning mode for short voice replies so
reasoning tokens cannot consume the output budget and leave the visible answer
empty.

---

## 📝 Document Links

* 📄 **[Executive Business Write-Up](./docs/BUSINESS_WRITEUP.md)** · **[PDF](./docs/Maruti_Customer_Concierge_Business_Writeup.pdf)**
* 📊 **[Pre-Sales Deck (PPTX)](./docs/Maruti_Customer_Concierge_PreSales_Deck.pptx)** · **[PDF](./docs/Maruti_Customer_Concierge_PreSales_Deck.pdf)**
* 🏗️ **[System Architecture](./docs/ARCHITECTURE.md)** · **[Rendered Diagram](./docs/architecture.png)**

---

## 🙏 Credits

- **[Sarvam AI](https://sarvam.ai)** — Indian language STT, LLM, and TTS APIs
- **[FastAPI](https://fastapi.tiangolo.com)** — High-performance Python web framework
- **[Font Awesome](https://fontawesome.com)** — Icon library
- **[Google Fonts](https://fonts.google.com)** — Orbitron, Rajdhani, Share Tech Mono
