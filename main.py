import os
import json
import re
import uuid
import base64
import logging
import asyncio
from datetime import date, timedelta
from typing import Literal
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from sarvam_service import sarvam_service, logger
from database import (
    TIME_SLOTS,
    cancel_test_drive_booking,
    create_test_drive_booking,
    database_stats,
    get_availability,
    get_sales_concierge_context,
    get_test_drive_booking,
    initialize_database,
    list_dealerships,
    list_models,
)

initialize_database()

SARVAM_QUOTA_MESSAGE = (
    "Sarvam AI credits are exhausted. Add credits to the configured Sarvam "
    "account, then tap the orb to reconnect."
)


def is_sarvam_quota_error(error: Exception) -> bool:
    normalized = str(error).casefold()
    return (
        "no credits available" in normalized
        or "insufficient_quota_error" in normalized
        or "insufficient quota" in normalized
    )


app = FastAPI(
    title="Car AI Doctor",
    description="Multi-lingual Automotive Diagnostic Assistant powered by Sarvam AI",
    version="1.0.0"
)

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage for multi-turn conversations
sessions: Dict[str, List[Dict[str, str]]] = {}
tts_audio_cache: Dict[str, bytes] = {}
auto_booked_sessions: Dict[str, str] = {}


def _extract_conversational_test_drive_payload(
    history: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Build a booking payload from the deterministic sales conversation."""
    context = get_sales_concierge_context()
    assistant_turns = [
        str(turn.get("content", ""))
        for turn in history
        if str(turn.get("role", "")).lower() == "assistant"
    ]

    selected_model = None
    for turn_text in reversed(assistant_turns):
        matches = [
            model
            for model in context.get("all_models_ready_for_test_drive", [])
            if str(model.get("name", "")).casefold() in turn_text.casefold()
        ]
        if len(matches) == 1:
            selected_model = matches[0]
            break

    selected_dealer = None
    for turn_text in reversed(assistant_turns):
        if not any(
            marker in turn_text.casefold()
            for marker in ("चुन ली गई", "selected")
        ):
            continue
        matches = [
            dealer
            for dealer in context.get("dealerships", [])
            if str(dealer.get("name", "")).casefold() in turn_text.casefold()
        ]
        if len(matches) == 1:
            selected_dealer = matches[0]
            break

    selected_date = None
    selected_time = None
    selected_location = None
    customer_name = None
    customer_mobile = None
    for turn_text in reversed(assistant_turns):
        folded = turn_text.casefold()
        if selected_date is None and any(
            marker in folded
            for marker in ("तारीख चुन", "समय चुन", "date selected", "time selected")
        ):
            selected_date = sarvam_service._parse_booking_date(turn_text)
        if selected_time is None and any(
            marker in folded for marker in ("समय चुन", "time selected")
        ):
            selected_time = sarvam_service._parse_booking_time(turn_text)
        if selected_location is None:
            if "घर पर टेस्ट ड्राइव चुन" in folded:
                selected_location = "HOME"
            elif "डीलरशिप पर टेस्ट ड्राइव चुन" in folded:
                selected_location = "DEALERSHIP"
        if customer_name is None:
            name_match = re.search(
                r"ग्राहक का नाम (.+?) दर्ज कर लिया गया है",
                turn_text,
                flags=re.IGNORECASE,
            )
            if name_match:
                customer_name = name_match.group(1).strip()
        if customer_mobile is None:
            mobile_match = re.search(
                r"मोबाइल नंबर ([6-9]\d{9}) दर्ज कर लिया गया है",
                turn_text,
            )
            if mobile_match:
                customer_mobile = mobile_match.group(1)

    address = None
    for index in range(len(history) - 1, -1, -1):
        turn = history[index]
        if str(turn.get("role", "")).lower() != "user":
            continue
        previous = history[index - 1] if index else {}
        previous_text = str(previous.get("content", "")).casefold()
        if any(
            marker in previous_text
            for marker in (
                "पूरा पता बताइए",
                "पता पूरा नहीं मिला",
                "पिनकोड सहित पूरा पता",
                "complete address",
                "address with the six-digit pincode",
            )
        ):
            address = str(turn.get("content", "")).strip(" \t\r\n।")
            break

    normalized_address = sarvam_service._normalize_spoken_digits(address or "")
    pincode_matches = re.findall(r"(?<!\d)([1-9]\d{5})(?!\d)", normalized_address)
    pincode = pincode_matches[-1] if pincode_matches else None

    required = (
        selected_model,
        selected_dealer,
        selected_date,
        selected_time,
        selected_location,
        customer_name,
        customer_mobile,
        address,
        pincode,
    )
    if not all(required):
        return None

    return {
        "full_name": customer_name,
        "mobile": customer_mobile,
        "email": None,
        "address_line": address,
        "city": selected_dealer.get("city") or "New Delhi",
        "state": "Delhi",
        "pincode": pincode,
        "dealership_id": int(selected_dealer["id"]),
        "car_model_id": int(selected_model["id"]),
        "booking_date": selected_date.isoformat(),
        "time_slot": selected_time,
        "location_type": selected_location,
        "customer_notes": None,
        "consent_given": True,
    }


def _auto_finalize_test_drive(
    session_id: str,
    history: List[Dict[str, str]],
    diagnostic_result: Dict[str, Any],
    language_code: str,
) -> Optional[Dict[str, Any]]:
    """Create the booking immediately after the address turn."""
    summary = str(diagnostic_result.get("summary", ""))
    address_completed = (
        "पता दर्ज कर लिया गया है" in summary
        or "address has been recorded" in summary.casefold()
    )
    if not address_completed:
        return None

    existing_reference = auto_booked_sessions.get(session_id)
    if existing_reference:
        try:
            booking = get_test_drive_booking(existing_reference)
        except LookupError:
            auto_booked_sessions.pop(session_id, None)
        else:
            diagnostic_result["test_drive_booking"] = booking
            return booking

    payload = _extract_conversational_test_drive_payload(history)
    if payload is None:
        diagnostic_result["summary"] = (
            "पता पूरा नहीं मिला। कृपया छह अंकों के पिनकोड सहित पूरा पता फिर से बताइए?"
            if language_code.lower().startswith("hi")
            else "I could not capture the complete address. Please repeat it with the six-digit pincode."
        )
        diagnostic_result["full_text"] = diagnostic_result["summary"]
        return None

    try:
        booking = create_test_drive_booking(payload)
    except (LookupError, RuntimeError, ValueError) as exc:
        logger.warning("⚠️ [AUTO TEST-DRIVE BOOKING] %s", exc)
        diagnostic_result["summary"] = (
            "यह समय अब उपलब्ध नहीं है। कृपया कोई दूसरा उपलब्ध समय बताइए?"
            if language_code.lower().startswith("hi")
            else "That slot is no longer available. Please choose another available time."
        )
        diagnostic_result["full_text"] = diagnostic_result["summary"]
        return None

    auto_booked_sessions[session_id] = booking["reference_id"]
    confirmation = (
        f"आपकी टेस्ट ड्राइव बुकिंग आईडी {booking['reference_id']} है। "
        "यही बुकिंग जानकारी आपको आपके रजिस्टर्ड मोबाइल नंबर पर एस एम एस "
        "के माध्यम से भी मिलेगी।"
        if language_code.lower().startswith("hi")
        else (
            f"Your test-drive booking ID is {booking['reference_id']}. "
            "You will also receive the booking details by SMS on your registered mobile number."
        )
    )
    booking["confirmation_message"] = confirmation
    diagnostic_result.update({
        "summary": confirmation,
        "full_text": confirmation,
        "steps": [],
        "test_drive_booking": booking,
        "booking_complete": True,
    })
    return booking


def _validate_conversational_test_drive_slot(
    history: List[Dict[str, str]],
    diagnostic_result: Dict[str, Any],
    language_code: str,
) -> bool:
    """Validate the selected slot before collecting customer details."""
    summary = str(diagnostic_result.get("summary", ""))
    if not any(
        marker in summary.casefold()
        for marker in ("समय चुन लिया गया", "time selected")
    ):
        return True

    selected_date = sarvam_service._parse_booking_date(summary)
    selected_time = sarvam_service._parse_booking_time(summary)
    if selected_date is None or selected_time is None:
        return True

    context = get_sales_concierge_context()
    assistant_turns = [
        str(turn.get("content", ""))
        for turn in history
        if str(turn.get("role", "")).lower() == "assistant"
    ]
    selected_model = None
    for turn_text in reversed(assistant_turns):
        matches = [
            model
            for model in context.get("all_models_ready_for_test_drive", [])
            if str(model.get("name", "")).casefold() in turn_text.casefold()
        ]
        if len(matches) == 1:
            selected_model = matches[0]
            break

    selected_dealer = None
    for turn_text in reversed(assistant_turns):
        if not any(
            marker in turn_text.casefold()
            for marker in ("चुन ली गई", "selected")
        ):
            continue
        matches = [
            dealer
            for dealer in context.get("dealerships", [])
            if str(dealer.get("name", "")).casefold() in turn_text.casefold()
        ]
        if len(matches) == 1:
            selected_dealer = matches[0]
            break

    if selected_model is None or selected_dealer is None:
        return True

    slots = get_availability(
        int(selected_dealer["id"]),
        int(selected_model["id"]),
        selected_date.isoformat(),
    )
    selected_slot = next(
        (slot for slot in slots if slot["time_slot"] == selected_time),
        None,
    )
    if selected_slot and selected_slot["available_quantity"] > 0:
        return True

    available_times = [
        slot["time_slot"]
        for slot in slots
        if slot["available_quantity"] > 0
    ]
    formatted_date = sarvam_service._format_booking_date(
        selected_date,
        language_code,
    )
    if language_code.lower().startswith("hi"):
        if available_times:
            choices = " या ".join(available_times)
            message = (
                f"{formatted_date} की तारीख चुन ली गई है, लेकिन {selected_time} "
                f"अब उपलब्ध नहीं है। {choices} उपलब्ध हैं। आप कौन सा समय चुनेंगे?"
            )
        else:
            message = (
                f"{formatted_date} को कोई समय उपलब्ध नहीं है। "
                "कृपया कोई दूसरी तारीख बताइए?"
            )
    else:
        if available_times:
            choices = " or ".join(available_times)
            message = (
                f"{formatted_date} is selected, but {selected_time} is unavailable. "
                f"{choices} is available. Which time would you prefer?"
            )
        else:
            message = (
                f"No slots are available on {formatted_date}. "
                "Please choose another date."
            )
    diagnostic_result["summary"] = message
    diagnostic_result["full_text"] = message
    diagnostic_result["steps"] = []
    return False


def cache_tts_audio(audio_b64: Optional[str]) -> Optional[str]:
    """Cache generated WAV bytes and return a Safari-friendly same-origin URL."""
    if not audio_b64:
        return None
    try:
        audio_bytes = base64.b64decode(audio_b64, validate=True)
    except (ValueError, TypeError):
        logger.warning("⚠️ [TTS CACHE WARNING] Could not decode generated audio.")
        return None
    if not audio_bytes.startswith(b"RIFF") or len(audio_bytes) < 44:
        logger.warning("⚠️ [TTS CACHE WARNING] Generated audio is not a valid WAV.")
        return None

    audio_id = uuid.uuid4().hex
    tts_audio_cache[audio_id] = audio_bytes
    while len(tts_audio_cache) > 50:
        tts_audio_cache.pop(next(iter(tts_audio_cache)))
    return f"/api/audio/{audio_id}.wav"


@app.get("/api/audio/{audio_id}.wav")
async def stream_tts_audio(
    audio_id: str,
    range_header: Optional[str] = Header(None, alias="Range"),
):
    """Serve generated TTS with byte-range support required by Safari media playback."""
    audio_bytes = tts_audio_cache.get(audio_id)
    if audio_bytes is None:
        raise HTTPException(status_code=404, detail="Audio has expired. Generate the reply again.")

    total = len(audio_bytes)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=600",
    }
    if range_header and range_header.startswith("bytes="):
        try:
            range_value = range_header.removeprefix("bytes=").split(",", 1)[0]
            start_text, end_text = range_value.split("-", 1)
            start = int(start_text) if start_text else 0
            end = int(end_text) if end_text else total - 1
            end = min(end, total - 1)
            if start < 0 or start > end:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{total}"},
            )
        chunk = audio_bytes[start:end + 1]
        headers.update({
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(len(chunk)),
        })
        return Response(
            content=chunk,
            status_code=206,
            media_type="audio/wav",
            headers=headers,
        )

    headers["Content-Length"] = str(total)
    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers=headers,
    )

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    language_code: str = "hi-IN"
    speaker: str = "ShubhMale"
    assistant_mode: Literal["DIAGNOSTIC", "TEST_DRIVE"] = "DIAGNOSTIC"

class TTSRequest(BaseModel):
    text: str
    language_code: str = "hi-IN"
    speaker: str = "ShubhMale"

class ResetSessionRequest(BaseModel):
    session_id: str

class BookExpertRequest(BaseModel):
    session_id: Optional[str] = None
    customer_name: str
    customer_phone: str
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None
    issue_summary: Optional[str] = None
    language_code: str = "hi-IN"
    speaker: str = "ShubhMale"

class TestDriveBookingRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    mobile: str
    email: Optional[str] = Field(default=None, max_length=150)
    address_line: str = Field(min_length=5, max_length=250)
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=80)
    pincode: str
    dealership_id: int = Field(gt=0)
    car_model_id: int = Field(gt=0)
    booking_date: date
    time_slot: str
    location_type: Literal["HOME", "DEALERSHIP"]
    customer_notes: Optional[str] = Field(default=None, max_length=500)
    consent_given: bool

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) != 10 or digits[0] not in "6789":
            raise ValueError("Enter a valid 10-digit Indian mobile number.")
        return digits

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) != 6:
            raise ValueError("Enter a valid 6-digit Indian pincode.")
        return digits

    @field_validator("time_slot")
    @classmethod
    def validate_time_slot(cls, value: str) -> str:
        if value not in TIME_SLOTS:
            raise ValueError("Select an available test-drive time slot.")
        return value

    @field_validator("booking_date")
    @classmethod
    def validate_booking_date(cls, value: date) -> date:
        if value < date.today() or value > date.today() + timedelta(days=30):
            raise ValueError("Test-drive date must be between today and 30 days from today.")
        return value

    @model_validator(mode="after")
    def validate_consent(self):
        if not self.consent_given:
            raise ValueError("Consent is required to create a test-drive booking.")
        return self

# In-memory booking storage
bookings: Dict[str, Dict[str, Any]] = {}

def diagnostic_spoken_parts(diagnostic_result: Dict[str, Any]) -> List[str]:
    """Return every visible diagnostic line in the order it should be spoken."""
    parts = [
        diagnostic_result.get("summary", ""),
        *diagnostic_result.get("steps", [])
    ]
    return [str(part).strip() for part in parts if str(part).strip()]

async def synthesize_reply_audio(
    diagnostic_result: Dict[str, Any],
    language_code: str,
    speaker: str,
) -> Optional[str]:
    """Retry one transient Sarvam TTS failure before returning a silent reply."""
    for attempt in range(2):
        try:
            return await sarvam_service.text_to_speech(
                steps=diagnostic_spoken_parts(diagnostic_result),
                language_code=language_code,
                speaker=speaker,
            )
        except Exception:
            if attempt == 1:
                raise
            logger.warning("⚠️ [SARVAM TTS RETRY] First attempt failed; retrying once.")
            await asyncio.sleep(0.2)
    return None

@app.get("/api/health")
async def health_check():
    status = sarvam_service.check_status()
    return {
        "status": "online",
        "sarvam_ai": status,
        "active_bookings_count": len(bookings),
        "database": database_stats(),
    }

@app.get("/api/dealerships")
async def dealership_list(city: Optional[str] = None):
    return {
        "dealerships": list_dealerships(city),
        "inventory_scope": "Seeded New Delhi dealer demo",
    }

@app.get("/api/assistant/welcome")
async def assistant_welcome(
    assistant_mode: Literal["DIAGNOSTIC", "TEST_DRIVE"] = "DIAGNOSTIC",
    language_code: str = "hi-IN",
    speaker: str = "ShubhMale",
):
    if assistant_mode == "TEST_DRIVE":
        if language_code.startswith("hi"):
            role_word = "सकती" if "female" in speaker.lower() else "सकता"
            message = (
                "मारुति सुज़ुकी में आपका स्वागत है। "
                "मैं आपकी नई कार चुनने और टेस्ट ड्राइव बुक करने में मदद "
                f"कर {role_word} हूँ। मैं आपकी क्या मदद करूँ?"
            )
        else:
            message = (
                "Welcome to Maruti Suzuki. I can help you choose a new car "
                "and book a test drive. How may I help you?"
            )
    else:
        message = (
            "नमस्ते। अपनी कार की समस्या बताइए, मैं आपकी मदद करूँगा।"
            if language_code.startswith("hi")
            else "Hello. Tell me what is happening with your car and I will help."
        )

    audio_b64 = None
    try:
        audio_b64 = await sarvam_service.text_to_speech(
            text=message,
            language_code=language_code,
            speaker=speaker,
        )
    except Exception as exc:
        logger.warning(f"⚠️ [WELCOME TTS WARNING] {exc}")
    audio_url = cache_tts_audio(audio_b64)
    return {
        "assistant_mode": assistant_mode,
        "message": message,
        "audio_b64": audio_b64,
        "audio_url": audio_url,
    }

@app.get("/api/cars")
async def car_list(dealership_id: Optional[int] = None):
    return {
        "cars": list_models(dealership_id),
        "inventory_is_demo": True,
        "price_disclaimer": "Prices are indicative ex-showroom starting prices and can change. Confirm the final price and live stock with the selected dealer.",
    }

@app.get("/api/test-drive/availability")
async def test_drive_availability(
    dealership_id: int,
    car_model_id: int,
    booking_date: date,
):
    try:
        slots = get_availability(dealership_id, car_model_id, booking_date.isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "booking_date": booking_date.isoformat(),
        "slots": slots,
    }

@app.post("/api/test-drive/bookings", status_code=201)
async def create_test_drive(req: TestDriveBookingRequest):
    try:
        booking = create_test_drive_booking(req.model_dump(mode="json"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    booking["confirmation_message"] = (
        f"Your test-drive booking ID is {booking['reference_id']}. "
        "You will also receive the booking details by SMS on your registered "
        "mobile number."
    )
    return booking

@app.get("/api/test-drive/bookings/{reference_id}")
async def test_drive_booking_lookup(reference_id: str):
    try:
        return get_test_drive_booking(reference_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/test-drive/bookings/{reference_id}/cancel")
async def cancel_test_drive(reference_id: str):
    try:
        return cancel_test_drive_booking(reference_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = []

    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message content cannot be empty.")

    logger.info(f"📩 [API /api/chat] Incoming request for session {session_id[:8]}... (Lang: {req.language_code})")

    # Append user turn
    sessions[session_id].append({"role": "user", "content": user_msg})

    # Call Sarvam AI LLM diagnostic reasoning (Real API call)
    try:
        business_context = None
        if req.assistant_mode == "TEST_DRIVE":
            business_context = json.dumps(
                get_sales_concierge_context(),
                ensure_ascii=False,
            )
        diagnostic_result = await sarvam_service.get_diagnostic_response(
            conversation_history=sessions[session_id],
            language_code=req.language_code,
            assistant_mode=req.assistant_mode,
            business_context=business_context,
        )
        if req.assistant_mode == "TEST_DRIVE":
            slot_is_available = _validate_conversational_test_drive_slot(
                sessions[session_id],
                diagnostic_result,
                req.language_code,
            )
            if slot_is_available:
                _auto_finalize_test_drive(
                    session_id,
                    sessions[session_id],
                    diagnostic_result,
                    req.language_code,
                )
    except Exception as e:
        # Do not keep a failed turn in memory; otherwise retrying duplicates it.
        if sessions[session_id] and sessions[session_id][-1].get("content") == user_msg:
            sessions[session_id].pop()
        logger.error(f"❌ [API /api/chat ERROR] {e}")
        if is_sarvam_quota_error(e):
            raise HTTPException(status_code=402, detail=SARVAM_QUOTA_MESSAGE)
        raise HTTPException(status_code=502, detail=str(e))

    # Append assistant turn
    sessions[session_id].append({
        "role": "assistant",
        "content": diagnostic_result.get("summary", "")
    })

    # Generate TTS audio for the reply using Sarvam TTS (Real API call)
    audio_b64 = None
    try:
        audio_b64 = await synthesize_reply_audio(
            diagnostic_result,
            req.language_code,
            req.speaker,
        )
    except Exception as tts_err:
        logger.warning(f"⚠️ [API /api/chat TTS WARNING] Could not generate TTS: {tts_err}")
    audio_url = cache_tts_audio(audio_b64)

    return {
        "session_id": session_id,
        "user_message": user_msg,
        "urgency": diagnostic_result.get("urgency", "CAUTION"),
        "confidence": diagnostic_result.get("confidence", "HIGH"),
        "steps": diagnostic_result.get("steps", []),
        "summary": diagnostic_result.get("summary", ""),
        "full_text": diagnostic_result.get("full_text", diagnostic_result.get("summary", "")),
        "audio_b64": audio_b64,
        "audio_url": audio_url,
        "assistant_mode": req.assistant_mode,
        "test_drive_booking": diagnostic_result.get("test_drive_booking"),
        "booking_complete": diagnostic_result.get("booking_complete", False),
        "is_live_api": sarvam_service.is_live,
        "history": sessions[session_id]
    }

@app.post("/api/voice-transcribe")
async def voice_transcribe(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language_code: str = Form("hi-IN"),
    speaker: str = Form("ShubhMale"),
    assistant_mode: str = Form("DIAGNOSTIC"),
):
    actual_session_id = session_id or str(uuid.uuid4())
    if actual_session_id not in sessions:
        sessions[actual_session_id] = []

    logger.info(f"🎙️ [API /api/voice-transcribe] Incoming voice upload (Lang: {language_code}, Speaker: {speaker})")

    try:
        audio_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read audio file: {e}")

    # 1. Transcribe audio using Sarvam STT (saaras:v3)
    try:
        transcribed_text = await sarvam_service.transcribe_audio(
            audio_bytes=audio_bytes,
            language_code=language_code,
            filename=file.filename or "audio.wav",
            content_type=file.content_type
        )
    except Exception as stt_err:
        logger.error(f"❌ [API /api/voice-transcribe STT ERROR] {stt_err}")
        if is_sarvam_quota_error(stt_err):
            raise HTTPException(status_code=402, detail=SARVAM_QUOTA_MESSAGE)
        raise HTTPException(status_code=500, detail=f"Sarvam STT error: {stt_err}")

    if not transcribed_text or not transcribed_text.strip():
        transcribed_text = "Vehicle diagnostic check request"

    # 2. Append turn to session history
    sessions[actual_session_id].append({"role": "user", "content": transcribed_text.strip()})

    # 3. Obtain LLM Diagnostic response
    try:
        normalized_mode = assistant_mode.upper().strip()
        if normalized_mode not in {"DIAGNOSTIC", "TEST_DRIVE"}:
            raise ValueError("Unsupported assistant mode.")
        business_context = None
        if normalized_mode == "TEST_DRIVE":
            business_context = json.dumps(
                get_sales_concierge_context(),
                ensure_ascii=False,
            )
        diagnostic_result = await sarvam_service.get_diagnostic_response(
            conversation_history=sessions[actual_session_id],
            language_code=language_code,
            assistant_mode=normalized_mode,
            business_context=business_context,
        )
        if normalized_mode == "TEST_DRIVE":
            slot_is_available = _validate_conversational_test_drive_slot(
                sessions[actual_session_id],
                diagnostic_result,
                language_code,
            )
            if slot_is_available:
                _auto_finalize_test_drive(
                    actual_session_id,
                    sessions[actual_session_id],
                    diagnostic_result,
                    language_code,
                )
    except Exception as llm_err:
        if (
            sessions[actual_session_id]
            and sessions[actual_session_id][-1].get("content") == transcribed_text.strip()
        ):
            sessions[actual_session_id].pop()
        logger.error(f"❌ [API /api/voice-transcribe LLM ERROR] {llm_err}")
        if is_sarvam_quota_error(llm_err):
            raise HTTPException(status_code=402, detail=SARVAM_QUOTA_MESSAGE)
        raise HTTPException(status_code=502, detail=f"Sarvam LLM error: {llm_err}")

    sessions[actual_session_id].append({
        "role": "assistant",
        "content": diagnostic_result.get("summary", "")
    })

    # 4. Synthesize voice response using Sarvam TTS (bulbul:v3)
    audio_b64 = None
    try:
        audio_b64 = await synthesize_reply_audio(
            diagnostic_result,
            language_code,
            speaker,
        )
    except Exception as tts_err:
        logger.warning(f"⚠️ [API /api/voice-transcribe TTS WARNING] Could not generate TTS: {tts_err}")
    audio_url = cache_tts_audio(audio_b64)

    return {
        "session_id": actual_session_id,
        "transcription": transcribed_text,
        "urgency": diagnostic_result.get("urgency", "CAUTION"),
        "confidence": diagnostic_result.get("confidence", "HIGH"),
        "steps": diagnostic_result.get("steps", []),
        "summary": diagnostic_result.get("summary", ""),
        "full_text": diagnostic_result.get("full_text", diagnostic_result.get("summary", "")),
        "audio_b64": audio_b64,
        "audio_url": audio_url,
        "assistant_mode": normalized_mode,
        "test_drive_booking": diagnostic_result.get("test_drive_booking"),
        "booking_complete": diagnostic_result.get("booking_complete", False),
        "is_live_api": sarvam_service.is_live,
        "history": sessions[actual_session_id]
    }

@app.post("/api/book-expert")
async def book_expert(req: BookExpertRequest):
    if not req.customer_name.strip() or not req.customer_phone.strip():
        raise HTTPException(status_code=400, detail="Customer name and phone number are required.")

    # Generate Customer Reference ID: e.g. REF-849204
    ref_number = str(uuid.uuid4().int)[:6]
    reference_id = f"REF-{ref_number}"

    slot_date = req.preferred_date or "Today"
    slot_time = req.preferred_time or "Within 30 minutes"
    scheduled_slot = f"{slot_date}, {slot_time}"

    assigned_expert = "Master Tech Rajesh Kumar (Senior Automotive Specialist)"

    # Confirmation text in English and Hindi
    if req.language_code.startswith("hi"):
        confirmation_msg = f"आपका विशेषज्ञ कॉल सत्र सफलतापूर्वक बुक हो गया है। आपका संदर्भ आईडी {reference_id} है। हमारे मैकेनिक {slot_time} पर आपसे संपर्क करेंगे।"
    else:
        confirmation_msg = f"Your expert session is confirmed. Customer Reference ID: {reference_id}. Our master technician will call you at {slot_time}."

    booking_data = {
        "reference_id": reference_id,
        "session_id": req.session_id,
        "customer_name": req.customer_name.strip(),
        "customer_phone": req.customer_phone.strip(),
        "assigned_expert": assigned_expert,
        "scheduled_slot": scheduled_slot,
        "issue_summary": req.issue_summary or "Vehicle Diagnostic Inspection",
        "status": "CONFIRMED",
        "language_code": req.language_code,
        "created_at": sarvam_service.get_diagnostic_response.__name__ # just log timestamp
    }

    import datetime
    booking_data["created_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    bookings[reference_id] = booking_data
    logger.info(f"📅 [API /api/book-expert] Booking Created! Ref ID: {reference_id} for {req.customer_name} ({req.customer_phone})")

    # Generate TTS audio confirmation
    audio_b64 = None
    try:
        audio_b64 = await sarvam_service.text_to_speech(
            text=confirmation_msg,
            language_code=req.language_code,
            speaker=req.speaker
        )
    except Exception as tts_err:
        logger.warning(f"⚠️ [API /api/book-expert TTS WARNING] Could not generate confirmation audio: {tts_err}")
    audio_url = cache_tts_audio(audio_b64)

    return {
        "status": "booked",
        "reference_id": reference_id,
        "customer_name": req.customer_name.strip(),
        "customer_phone": req.customer_phone.strip(),
        "assigned_expert": assigned_expert,
        "scheduled_slot": scheduled_slot,
        "confirmation_message": confirmation_msg,
        "audio_b64": audio_b64,
        "audio_url": audio_url,
        "booking_details": booking_data
    }

@app.get("/api/booking/{reference_id}")
async def get_booking(reference_id: str):
    ref = reference_id.upper().strip()
    if ref not in bookings:
        raise HTTPException(status_code=404, detail=f"Booking reference ID '{ref}' not found.")
    return bookings[ref]

@app.get("/api/bookings")
async def list_bookings():
    return {
        "total_bookings": len(bookings),
        "bookings": list(bookings.values())
    }

@app.post("/api/tts")
async def generate_tts(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    try:
        audio_b64 = await sarvam_service.text_to_speech(
            text=req.text,
            language_code=req.language_code,
            speaker=req.speaker
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    audio_url = cache_tts_audio(audio_b64)

    return {
        "audio_b64": audio_b64,
        "audio_url": audio_url,
        "is_live_api": sarvam_service.is_live
    }

@app.post("/api/reset-session")
async def reset_session(req: ResetSessionRequest):
    if req.session_id in sessions:
        sessions[req.session_id] = []
    auto_booked_sessions.pop(req.session_id, None)
    logger.info(f"🔄 [API /api/reset-session] Reset conversation for session {req.session_id[:8]}...")
    return {"status": "reset", "session_id": req.session_id}

# Mount static folder
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_home():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
