# 🏗️ Technical Architecture & System Design
## **Car AI Doctor — Multilingual Voice & Agentic Vehicle Diagnostic Assistant**

This document details the software architecture, data flow pipelines, API integration specs, and failure handling mechanisms for **Car AI Doctor**.

---

## 1. System Architecture Diagram

```mermaid
graph TD
    subgraph Client ["Frontend Layer (Browser / HMI Touchscreen)"]
        UI[Automotive HMI UI - HTML5/CSS3]
        JS[Client Engine - app.js]
        REC[Web Audio API / MediaRecorder]
        TTS_AUDIO[HTML5 Audio Player]
    end

    subgraph Backend ["Backend Layer (FastAPI Application)"]
        API[FastAPI Router - main.py]
        SESS[Session History Manager]
        BOOK[Booking & Dispatch Engine]
        STORE[(In-Memory Session & Booking DB)]
    end

    subgraph Sarvam ["Sarvam AI Cloud Stack"]
        STT["Sarvam STT API (saaras:v3)"]
        LLM["Sarvam LLM API (sarvam-105b)"]
        TTS["Sarvam TTS API (bulbul:v3)"]
    end

    %% Flow interactions
    UI -->|1. Click / Record Audio| REC
    REC -->|2. Send speech.webm| JS
    JS -->|3. POST /api/voice-transcribe| API

    API -->|4. Speech-to-Text Request| STT
    STT -->|5. Transcript Output| API

    API -->|6. Conversation History + Prompt| LLM
    LLM -->|7. Structured Diagnostic Output| API

    API -->|8. Batched Sentences/Steps| TTS
    TTS -->|9. Concatenated WAV Audio Base64| API

    API -->|10. JSON Response| JS
    JS -->|11. Render LED Checklist & Play Audio| UI
    JS -->|12. Auto-Play Spoken Diagnosis| TTS_AUDIO

    UI -->|13. Click 'Schedule Expert Call'| JS
    JS -->|14. POST /api/book-expert| API
    API -->|15. Store Booking & Gen Reference ID| BOOK
    BOOK -->|16. Persist REF-XXXXXX| STORE
    BOOK -->|17. Synthesize Confirmation Voice| TTS
    API -->|18. Return Confirmation + Ref ID| JS
    JS -->|19. Render Booking Card with Ref Badge| UI
```

---

## 2. Component Specifications

### 2.1 Backend Layer (`main.py`)
* **Framework:** FastAPI (Python 3.9+)
* **Session Storage:** In-memory session store mapping `session_id` to conversational turns.
* **Booking Engine:** Generates unique Customer Reference IDs (`REF-XXXXXX`), assigns Master Technicians, and formats confirmation messages.

### 2.2 Sarvam AI Service Layer (`sarvam_service.py`)
Encapsulates all communication with Sarvam AI REST endpoints:

* **Speech-to-Text (`saaras:v3`):**
  * **Endpoint:** `POST https://api.sarvam.ai/speech-to-text`
  * **Header:** `api-subscription-key: <SARVAM_API_KEY>`
  * **Payload:** `multipart/form-data` with `file`, `model="saaras:v3"`, `language_code`.

* **Diagnostic LLM (`sarvam-105b`):**
  * **Endpoint:** `POST https://api.sarvam.ai/v1/chat/completions`
  * **Header:** `Authorization: Bearer <SARVAM_API_KEY>` *(Note: Bearer token auth required for 105b)*
  * **Payload:** `model="sarvam-105b"`, `messages`, `temperature=0.1`, `max_tokens=2000`.
  * **Timeout:** 60.0 seconds (handles deep reasoning passes).

* **Text-to-Speech (`bulbul:v3`):**
  * **Endpoint:** `POST https://api.sarvam.ai/text-to-speech`
  * **Header:** `api-subscription-key: <SARVAM_API_KEY>`
  * **Payload:** `model="bulbul:v3"`, `inputs` (max 3 inputs per request), `speaker`, `target_language_code`.
  * **Multi-Chunk Merge:** Batches input lines into groups of 3, executes parallel/sequential requests, strips 44-byte WAV headers, concatenates raw PCM bytes, and re-encodes a single valid WAV file in base64.

---

## 3. Sequence Diagram — Voice Triage & Expert Dispatch

```mermaid
sequenceDiagram
    autonumber
    actor Driver
    participant HMI as Frontend (HMI Dashboard)
    participant Server as FastAPI Server (main.py)
    participant SarvamSTT as Sarvam STT (saaras:v3)
    participant SarvamLLM as Sarvam LLM (sarvam-105b)
    participant SarvamTTS as Sarvam TTS (bulbul:v3)
    participant DB as Booking Store

    Driver->>HMI: Press Microphone Gauge & Speak Symptoms
    HMI->>Server: POST /api/voice-transcribe (audio.webm, lang, speaker)
    Server->>SarvamSTT: Transcribe Audio (saaras:v3)
    SarvamSTT-->>Server: Transcribed Text (e.g. "मेरी कार के इंजन से आवाज आ रही है")

    Server->>SarvamLLM: Process Chat History + System Prompt (sarvam-105b)
    SarvamLLM-->>Server: Raw Output (Urgency, Confidence, Hindi Steps)

    Server->>SarvamTTS: Synthesize Diagnostic Steps (bulbul:v3 - Batched max 3)
    SarvamTTS-->>Server: Base64 WAV Audio
    Server-->>HMI: JSON (Urgency, Confidence Score, Steps, Summary, Audio Base64)

    HMI->>Driver: Render HMI Diagnostic Card + Auto-play Spoken Audio

    Driver->>HMI: Click "Schedule Master Mechanic Call"
    HMI->>Server: POST /api/book-expert (Name, Phone, Preferred Slot)
    Server->>DB: Store Booking & Generate `REF-849204`
    Server->>SarvamTTS: Synthesize Confirmation Speech (bulbul:v3)
    SarvamTTS-->>Server: Confirmation Audio Base64
    Server-->>HMI: JSON (Status: Booked, Reference ID: REF-849204, Audio Base64)

    HMI->>Driver: Render Confirmation Card with Reference ID & Speak Confirmation
```

---

## 4. Failure & Resilience Handling

| Potential Failure Point | Mitigation Strategy |
|---|---|
| **LLM Timeout (>20s)** | Extended `httpx` async client timeout to **60.0 seconds** to accommodate deep multi-language reasoning passes. |
| **TTS Input Limit Exceeded (>3 items)** | `sarvam_service.py` automatically batches inputs into groups of 3, executes multiple requests, and concatenates raw PCM audio chunks into one seamless base64 WAV. |
| **Non-Standard LLM Output** | Dual-pass regex parser: matches `Step N:` / `चरण N:` patterns first, falls back to markdown bullet lists, and then Devanagari character block extraction. |
| **Missing API Key** | App status endpoint `/api/health` detects configuration state and provides clear diagnostic messages in logs. |
| **Microphone Denial** | Graceful UI fallback allows typed diagnostic inputs with full access to STT/LLM/TTS and Expert Dispatch workflows. |
