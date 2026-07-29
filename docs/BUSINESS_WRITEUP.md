# Maruti Customer Concierge

## A Hinglish voice-to-booking proof of concept for automotive retail

### Executive proposition

Customers who are ready to explore a new car often arrive through calls, web forms or dealer enquiries, but the journey still depends on an employee asking the same qualification questions, checking a separate availability system and creating a booking. The Maruti Customer Concierge demonstrates a more direct path: a customer speaks naturally in Hinglish, hears grounded model and dealership options, chooses a slot and location, provides contact details, and receives a confirmed test-drive booking ID without touching a form.

The proof of concept combines Sarvam AI’s India-first voice stack with deterministic booking orchestration. Saaras v3 transcribes the conversation, Bulbul v3 speaks the response, FastAPI controls the workflow, and SQLite stores the dealer catalogue, fleet capacity, customers and confirmed bookings. The result is not just a talking bot; it is a voice interface connected to a transactional process.

## 1. The operational problem

Automotive pre-sales operations must turn high-intent enquiries into scheduled showroom or home test drives. The current journey can create four avoidable points of friction:

1. **Language and code-mixing:** customers may express intent more naturally in Hindi mixed with English model, location and time terms.
2. **Repeated qualification:** model, dealership, date, time, location and contact details are often captured manually across multiple interactions.
3. **Disconnected availability:** an agent may need to check a separate dealer or fleet system before committing a slot.
4. **Weak closure:** if the interaction ends without a reference ID, both the customer and operations team lack a clear next step.

The end user may be comfortable speaking but less willing to complete a long form. A voice-first assistant reduces interface effort while preserving an auditable booking record.

## 2. Why an AI voice workflow

A traditional IVR is reliable but forces customers through rigid menus. A general chatbot is flexible but can invent stock, skip mandatory fields or repeat questions. This proof of concept uses a hybrid:

- Voice recognition accepts natural Hinglish rather than keypad navigation.
- The customer can say “कल दोपहर दो बजे,” “द्वारका सेक्टर 12,” or a model alias in one turn.
- A deterministic state machine decides what information is still missing and asks only the next relevant question.
- Dealer, model and slot responses are grounded in the database.
- Booking is committed transactionally only after validation.

This approach provides the accessibility of conversation with the operational control expected from an enterprise workflow.

## 3. Why Sarvam AI

Sarvam is central to the experience rather than an add-on:

| Requirement | Sarvam role | Enterprise relevance |
|---|---|---|
| Hinglish customer speech | Saaras v3 STT | Captures Indian language and English automotive terms in one interaction |
| Natural spoken reply | Bulbul v3 TTS with the Shubh voice | Makes the workflow usable as a phone-call experience, not only a chat UI |
| Open-ended assistance | Sarvam Chat Completions as the flexible response layer | Supports future product questions and exception handling while transactions stay deterministic |
| Language expansion | Sarvam’s India-language stack | Creates a path to regional deployment using the same orchestration contract |

The architectural advantage is the combination of India-focused speech capability and a single vendor path for STT, TTS, translation and LLM services. In production discovery, Sarvam latency, accuracy, deployment options, data handling and commercial terms should be validated against the customer’s security and scale requirements.

## 4. What the proof of concept demonstrates

The Hinglish demo completes one deep enterprise journey:

```text
Customer intent
→ model discovery and selection
→ dealer matching
→ date/time and home/dealership choice
→ name, mobile and address capture
→ live slot revalidation
→ transactional booking
→ spoken TD-XXXXXXXX reference ID
```

The local database contains dealerwise Maruti models, sales inventory, test-drive fleet records and datewise capacity. The workflow automatically books after the address is captured; the customer does not need to click a confirmation form. It also reminds the customer to keep the original driving licence and original Aadhaar or PAN available, without collecting document numbers in the conversation.

## 5. Illustrative business case

The following model is an **illustrative discovery hypothesis**, not a claimed Maruti baseline. Replace the inputs with contact-centre, dealer and Sarvam commercial data before an investment decision.

| Assumption | Illustrative value |
|---|---:|
| Inbound pre-sales interactions | 10,000 per month |
| Share eligible for automated test-drive flow | 60% |
| Fully loaded assisted interaction cost | ₹60 |
| Voice-AI interaction cost | ₹12 |
| Direct saving per automated interaction | ₹48 |

**Monthly direct saving**

`10,000 × 60% × (₹60 − ₹12) = ₹2.88 lakh`

**Annualised direct saving**

`₹2.88 lakh × 12 = ₹34.56 lakh`

This excludes potential upside from extended operating hours, faster response and higher test-drive completion. A one-percentage-point improvement at 10,000 enquiries would create 100 additional test-drive opportunities per month; the revenue value should be calculated using the customer’s test-drive-to-sale conversion and contribution margin.

The pilot should measure:

- booking completion rate;
- cost per confirmed booking;
- median time from intent to booking;
- STT correction and repeated-question rate;
- slot conflict and failure rate;
- human handoff rate;
- test-drive attendance and downstream retail conversion.

## 6. Limitations and production gaps

The current build is a proof of concept:

- The demonstrated experience is Hinglish in a browser; telephony is not yet connected.
- Dealer, model and availability data are seeded for the demo rather than sourced from a live DMS.
- Session state is stored in process memory and transactional data in SQLite.
- SMS delivery is simulated in the customer message.
- Production consent, authentication, PII retention, analytics and monitoring controls are not implemented.
- Free-form LLM responses require additional evaluation and guardrails before handling commercial commitments.

## 7. Recommended 90-day rollout

### Days 0–30 — Validate and integrate

- Agree the priority customer journey, success metrics and handoff policy.
- Connect one source of truth for dealerships, models, fleet and slots.
- Validate Sarvam STT/TTS quality on real consented Hinglish call samples.
- Define security, PII, retention, audit and consent requirements.
- Replace the SMS simulation with a sandboxed provider integration.

### Days 31–60 — Harden the workflow

- Move to managed Postgres and Redis.
- Add telephony, CRM/DMS updates, delivery receipts and agent handoff.
- Implement observability for latency, accuracy, state retries and booking outcomes.
- Add controlled exception handling and regression tests for production utterances.
- Validate one additional Indian language without changing the booking transaction.

### Days 61–90 — Run a measured pilot

- Launch with two dealerships and a bounded traffic cohort.
- Compare voice automation with the current enquiry-to-booking funnel.
- Review failed transcripts and workflow drop-offs weekly.
- Tune prompts, alias dictionaries, VAD thresholds and staffing handoffs.
- Make the scale decision against agreed cost, completion, quality and compliance gates.

## Recommendation

Proceed with a two-dealer pilot focused on the single metric that matters first: **confirmed test-drive bookings completed through voice without human re-entry**. The proof of concept already demonstrates the core technical path. The next investment should be in live-system integration, measurement and operational controls rather than additional demo breadth.

---

**Prepared for:** CTO / VP Operations review

**Use case:** Maruti customer pre-sales and test-drive booking

**Demo scope:** Hinglish browser voice interaction

**Implementation:** Sarvam Saaras v3 + Bulbul v3, FastAPI, deterministic workflow and SQLite
