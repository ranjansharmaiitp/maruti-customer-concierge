import os
import re
import json
import logging
import asyncio
import httpx
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Clean logger setup for terminal observation
logger = logging.getLogger("car_ai_doctor")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('\033[36m[%(asctime)s]\033[0m \033[1m%(message)s\033[0m', '%H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_LLM_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_TRANSLATE_URL = "https://api.sarvam.ai/translate"

LANGUAGE_NAMES = {
    "hi-IN": "Hindi (हिन्दी)",
    "en-IN": "English",
    "ta-IN": "Tamil (தமிழ்)",
    "te-IN": "Telugu (తెలుగు)",
    "kn-IN": "Kannada (கன்னட)",
    "mr-IN": "Marathi (मराठी)",
    "bn-IN": "Bengali (বাংলা)",
    "gu-IN": "Gujarati (ગુજરાતી)",
    "ml-IN": "Malayalam (മലയാളം)",
    "pa-IN": "Punjabi (ਪੰਜਾਬੀ)"
}

SPEAKER_MAP = {
    "ShubhMale": "shubh",
    "ShreyaFemale": "shreya",
    "shubh": "shubh",
    "shreya": "shreya",
    "abhilash": "shubh",
    "anushka": "shreya"
}

class SarvamAIService:
    def __init__(self):
        self.reload_config()

    def reload_config(self):
        load_dotenv(override=True)
        self.api_key = os.getenv("SARVAM_API_KEY", "").strip()
        self.is_live = bool(self.api_key and len(self.api_key) > 8 and self.api_key != "your_sarvam_api_key_here")
        configured_model = os.getenv("SARVAM_LLM_MODEL", "sarvam-30b").strip()
        self.llm_model = configured_model if configured_model in {"sarvam-30b", "sarvam-105b"} else "sarvam-30b"

    def check_status(self) -> Dict[str, Any]:
        self.reload_config()
        return {
            "configured": bool(self.api_key),
            "is_live": self.is_live,
            "stt_model": "saaras:v3",
            "llm_model": self.llm_model,
            "tts_model": "bulbul:v3"
        }

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language_code: str = "hi-IN",
        filename: str = "audio.wav",
        content_type: Optional[str] = None
    ) -> str:
        """
        Transcribes speech audio using Sarvam AI STT API (saaras:v3). Real API calls only.
        """
        self.reload_config()

        if not self.is_live:
            err_msg = "[SARVAM STT ERROR] SARVAM_API_KEY is not set or invalid in .env! Cannot perform real speech transcription."
            logger.error(err_msg)
            raise ValueError(err_msg)

        if not audio_bytes or len(audio_bytes) < 100:
            err_msg = "[SARVAM STT ERROR] Audio buffer is empty or corrupted."
            logger.error(err_msg)
            raise ValueError(err_msg)

        print("\n" + "="*80)
        logger.info(f"🎤 [SARVAM STT REQUEST] Transcribing audio with saaras:v3")
        logger.info(f"   Language Code : {language_code} ({LANGUAGE_NAMES.get(language_code, 'Unknown')})")
        extension = os.path.splitext(filename.lower())[1]
        # Browsers commonly include codec parameters such as
        # "audio/webm; codecs=opus". Sarvam validates against exact media types,
        # so send only the base MIME value.
        mime_type = content_type.split(";", 1)[0].strip().lower() if content_type else None
        if not mime_type or mime_type == "application/octet-stream":
            mime_type = {
                ".webm": "audio/webm",
                ".m4a": "audio/mp4",
                ".mp4": "audio/mp4",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".ogg": "audio/ogg",
            }.get(extension, "application/octet-stream")

        logger.info(f"   Audio Filename: {filename} ({len(audio_bytes)} bytes, {mime_type})")
        print("="*80)

        headers = {
            "api-subscription-key": self.api_key
        }
        files = {
            "file": (filename, audio_bytes, mime_type)
        }
        data = {
            "model": "saaras:v3",
            "language_code": language_code,
            "with_timestamps": "false"
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(SARVAM_STT_URL, headers=headers, files=files, data=data)
                logger.info(f"📡 [SARVAM STT RESPONSE] Status Code: {response.status_code}")

                if response.status_code == 200:
                    res_json = response.json()
                    transcript = res_json.get("transcript", "") or res_json.get("text", "")
                    logger.info(f"✅ [SARVAM STT SUCCESS] Transcribed Text: \"{transcript}\"")
                    print("="*80 + "\n")
                    return transcript
                else:
                    err_msg = f"[SARVAM STT API FAILED] HTTP {response.status_code}: {response.text}"
                    logger.error(err_msg)
                    raise RuntimeError(err_msg)

        except Exception as e:
            logger.error(f"❌ [SARVAM STT EXCEPTION] {e}")
            print("="*80 + "\n")
            raise RuntimeError(f"Sarvam STT API call failed: {e}")

    async def translate_text(self, text: str, target_language_code: str) -> str:
        """Translate a short reply into the selected language using Sarvam Mayura."""
        self.reload_config()
        if not self.is_live:
            raise ValueError("[SARVAM TRANSLATE ERROR] SARVAM_API_KEY is missing or invalid.")

        payload = {
            "input": (text or "").strip()[:1000],
            "source_language_code": "auto",
            "target_language_code": target_language_code,
            "speaker_gender": "Male",
            "mode": "modern-colloquial",
            "model": "mayura:v1",
            "output_script": "spoken-form-in-native",
        }
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                SARVAM_TRANSLATE_URL,
                headers=headers,
                json=payload,
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"[SARVAM TRANSLATE FAILED] HTTP {response.status_code}: {response.text}"
            )
        translated = str(response.json().get("translated_text", "")).strip()
        if not translated:
            raise RuntimeError("[SARVAM TRANSLATE FAILED] Empty translated_text.")
        return translated

    async def get_diagnostic_response(
        self,
        conversation_history: List[Dict[str, str]],
        language_code: str = "hi-IN",
        assistant_mode: str = "DIAGNOSTIC",
        business_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends conversation history to Sarvam's OpenAI-compatible Chat Completions
        REST endpoint. Reasoning is disabled because this voice application needs a
        short answer; otherwise reasoning tokens can exhaust max_tokens and leave
        message.content empty.
        """
        self.reload_config()

        if not self.is_live:
            err_msg = "[SARVAM LLM ERROR] SARVAM_API_KEY is missing or invalid in .env! Cannot perform real LLM diagnosis."
            logger.error(err_msg)
            raise ValueError(err_msg)

        user_msg = conversation_history[-1]["content"] if conversation_history else ""
        lang_name = LANGUAGE_NAMES.get(language_code, "Hindi (हिन्दी)")
        normalized_mode = assistant_mode.upper().strip()
        translated_user_cache: Optional[str] = None

        async def translated_user_for_fallback() -> str:
            nonlocal translated_user_cache
            if translated_user_cache is not None:
                return translated_user_cache
            if language_code.lower().startswith("en"):
                translated_user_cache = user_msg
                return translated_user_cache
            try:
                translated_user_cache = await self.translate_text(user_msg, "en-IN")
            except Exception as translate_error:
                logger.warning(
                    "⚠️ [SARVAM QUERY TRANSLATE WARNING] %s",
                    translate_error,
                )
                translated_user_cache = ""
            return translated_user_cache

        schedule_markers = (
            "किस तारीख",
            "किस समय",
            "तारीख चुन ली गई",
            "समय चुन लिया गया",
            "घर पर लेना चाहेंगे या डीलरशिप पर",
            "बुकिंग किस नाम से करनी है",
            "मोबाइल नंबर बताइए",
            "पूरा पता बताइए",
            "which date",
            "which time",
            "date selected",
            "time selected",
            "home or dealership",
            "booking name",
            "mobile number",
            "complete address",
        )
        last_assistant_text = next(
            (
                str(turn.get("content", "")).casefold()
                for turn in reversed(conversation_history)
                if str(turn.get("role", "")).lower() == "assistant"
            ),
            "",
        )
        is_schedule_turn = any(
            str(turn.get("role", "")).lower() == "assistant"
            and any(
                marker in str(turn.get("content", "")).casefold()
                for marker in schedule_markers
            )
            for turn in conversation_history
        )
        if (
            normalized_mode == "TEST_DRIVE"
            and language_code.lower().startswith("hi")
        ):
            fallback = self._sales_language_fallback(
                user_message=user_msg,
                raw_reply="",
                business_context=business_context,
                language_code=language_code,
                conversation_history=conversation_history,
            )
            return {
                "urgency": "SAFE TO DRIVE",
                "confidence": "HIGH",
                "summary": fallback,
                "steps": [],
                "full_text": fallback,
            }

        print("\n" + "="*80)
        logger.info(f"🧠 [SARVAM LLM REQUEST] Sending prompt to Sarvam AI LLM")
        logger.info(f"   Assistant Mode  : {normalized_mode}")
        logger.info(f"   Target Language : {lang_name} ({language_code})")
        logger.info(f"   User Message    : \"{user_msg}\"")
        logger.info(f"   History Turns   : {len(conversation_history)}")
        print("="*80)

        if normalized_mode == "TEST_DRIVE":
            system_prompt = f"""You are the Maruti Suzuki Customer Concierge in a live sales and test-drive conversation.

Reply only in natural {lang_name}. Match the language used by the customer.
Never switch to English unless the selected language is English.
Write the actual customer-facing reply. Never describe your plan, intentions, or what you will ask next.
Be welcoming, helpful, and conversational.
The DATABASE CONTEXT below is generated from the app's SQLite database for this exact request.
Use it as the only source for model names, launch recency, prices, dealerships, sale stock, and test-drive readiness.
Never invent a model, price, dealer, launch status, or availability.
When asked for newly launched cars ready for a test drive, answer from recent_models_ready_for_test_drive.
When asked for all choices, answer from all_models_ready_for_test_drive.
Mention that prices are indicative and stock is local demo inventory when price or quantity is discussed.
Do not tell the customer to visit another website. This app can complete the test-drive booking.
The booking sequence is model, dealership, date, time, home or dealership, customer details, then required documents.
Infer which booking fields the customer has already supplied from the conversation.
Ask for exactly one missing booking field per reply, following that sequence.
Never combine several booking questions in one reply and never ask for details already provided.
If the customer wants a test drive but has not chosen a model, mention at most four relevant models and ask which one they prefer.
Never list the full catalogue unless the customer explicitly asks to see every available model.
Once a model is chosen, acknowledge it briefly and ask only for the preferred dealership or locality.
Keep the complete reply to 2 to 4 short, natural spoken sentences and under 320 characters where practical.
Do not use numbered instructions, bullet points, headings, labels, or checklist language.
Put the complete conversational reply in summary and always return steps as an empty array.
For this sales workflow always use urgency SAFE TO DRIVE.
Every user-facing word other than proper model or dealership names must be in {lang_name}.

DATABASE CONTEXT:
{business_context or '{"error": "No dealership context was provided."}'}"""
        else:
            system_prompt = f"""You are Car AI Doctor, a warm and careful automotive assistant in a live voice conversation.

Reply in natural {lang_name}. Always answer the user's message directly, including greetings and follow-up questions.
For a vehicle symptom, prioritize immediate safety, explain uncertainty honestly, and give short practical checks.
Never claim that a remote chat is a definitive mechanical inspection.
Keep summary to 1 to 3 short spoken sentences with no markdown.
For an automotive issue, provide 1 to 5 concise steps. For a casual message that needs no steps, use an empty list.
Use PULL OVER IMMEDIATELY only for a credible immediate safety risk, CAUTION for an issue needing attention, and SAFE TO DRIVE when no immediate vehicle danger is described.
All user-facing strings must be in {lang_name}."""

        # Sanitize messages to ensure non-empty content
        clean_history = []
        for item in conversation_history:
            role = item.get("role", "user")
            content = (item.get("content") or "").strip()
            if not content:
                content = "Vehicle diagnostic check requested."
            clean_history.append({"role": role, "content": content})

        messages = [{"role": "system", "content": system_prompt}] + clean_history[-20:]
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "vehicle_diagnosis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "urgency": {
                            "type": "string",
                            "enum": ["PULL OVER IMMEDIATELY", "CAUTION", "SAFE TO DRIVE"]
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW"]
                        },
                        "summary": {
                            "type": "string",
                            "maxLength": 320 if normalized_mode == "TEST_DRIVE" else 1000
                        },
                        "steps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 0 if normalized_mode == "TEST_DRIVE" else 5
                        }
                    },
                    "required": ["urgency", "confidence", "summary", "steps"],
                    "additionalProperties": False
                }
            }
        }
        payload = {
            "model": self.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1000,
            # JSON null explicitly disables thinking mode in Sarvam Chat Completion.
            "reasoning_effort": None,
            "response_format": response_format
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        logger.info(f"⚡ [SARVAM LLM CALL] Invoking Model: {self.llm_model} via REST Chat Completions...")

        try:
            async def request_structured_reply(request_messages: List[Dict[str, str]]) -> tuple[str, Dict[str, Any]]:
                request_payload = {**payload, "messages": request_messages}
                async with httpx.AsyncClient(timeout=45.0) as client:
                    response = await client.post(
                        SARVAM_LLM_URL,
                        headers=headers,
                        json=request_payload,
                    )

                logger.info(f"📡 [SARVAM LLM RESPONSE] Status Code: {response.status_code}")
                if response.status_code != 200:
                    try:
                        error_body = response.json()
                        api_detail = error_body.get("detail") or error_body.get("message") or error_body
                    except ValueError:
                        api_detail = response.text
                    raise RuntimeError(f"HTTP {response.status_code}: {api_detail}")

                response_data = response.json()
                choices = response_data.get("choices") or []
                if not choices:
                    raise RuntimeError("Sarvam returned no completion choices.")

                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message") or {}
                raw_text = (message.get("content") or "").strip()
                logger.info(f"   Finish Reason : {finish_reason}")
                logger.info(f"   Content       : {repr(raw_text)[:300]}")

                if not raw_text:
                    raise RuntimeError(
                        f"Sarvam returned empty message.content (finish_reason={finish_reason!r})."
                    )

                try:
                    structured = json.loads(raw_text)
                    return raw_text, self._validate_structured_diagnostic(structured)
                except json.JSONDecodeError as parse_error:
                    if normalized_mode != "TEST_DRIVE":
                        raise
                    logger.warning(
                        "⚠️ [SARVAM LLM JSON FALLBACK] Truncated or malformed response "
                        "(finish_reason=%s): %s",
                        finish_reason,
                        parse_error,
                    )
                    fallback = self._sales_language_fallback(
                        user_message=user_msg,
                        raw_reply=raw_text,
                        business_context=business_context,
                        language_code=language_code,
                        translated_user=await translated_user_for_fallback(),
                        conversation_history=conversation_history,
                    )
                    return raw_text, {
                        "urgency": "SAFE TO DRIVE",
                        "confidence": "MEDIUM",
                        "summary": fallback,
                        "steps": [],
                        "full_text": fallback,
                    }

            raw_text, parsed = await request_structured_reply(messages)

            if normalized_mode == "TEST_DRIVE":
                parsed["steps"] = []
                parsed["full_text"] = parsed["summary"]

            if (
                not self._uses_expected_script(parsed["summary"], language_code)
                and not self._looks_like_internal_plan(parsed["summary"])
            ):
                try:
                    translated = await self.translate_text(
                        parsed["summary"],
                        language_code,
                    )
                    if self._uses_expected_script(translated, language_code):
                        parsed["summary"] = translated
                        parsed["full_text"] = translated
                except Exception as translate_error:
                    logger.warning(
                        "⚠️ [SARVAM TRANSLATE WARNING] %s",
                        translate_error,
                    )

            if not self._uses_expected_script(parsed["summary"], language_code):
                logger.warning(
                    "⚠️ [SARVAM LLM LANGUAGE RETRY] Reply did not match %s; retrying once.",
                    language_code,
                )
                correction_prompt = (
                    f"LANGUAGE CORRECTION: Return the customer-facing answer only in {lang_name}. "
                    "Do not explain your plan. Use 2 to 4 short conversational sentences, "
                    "ask only one next question, and return steps as an empty array."
                )
                raw_text, parsed = await request_structured_reply(
                    messages + [{"role": "system", "content": correction_prompt}]
                )
                if normalized_mode == "TEST_DRIVE":
                    parsed["steps"] = []
                    parsed["full_text"] = parsed["summary"]

                if (
                    not self._uses_expected_script(parsed["summary"], language_code)
                    and not self._looks_like_internal_plan(parsed["summary"])
                ):
                    try:
                        translated = await self.translate_text(
                            parsed["summary"],
                            language_code,
                        )
                        if self._uses_expected_script(translated, language_code):
                            parsed["summary"] = translated
                            parsed["full_text"] = translated
                    except Exception as translate_error:
                        logger.warning(
                            "⚠️ [SARVAM TRANSLATE WARNING] %s",
                            translate_error,
                        )

                if not self._uses_expected_script(parsed["summary"], language_code):
                    if normalized_mode != "TEST_DRIVE":
                        raise ValueError(
                            f"Sarvam reply did not use the selected language ({language_code})."
                        )
                    fallback = self._sales_language_fallback(
                        user_message=user_msg,
                        raw_reply=raw_text,
                        business_context=business_context,
                        language_code=language_code,
                        translated_user=await translated_user_for_fallback(),
                        conversation_history=conversation_history,
                    )
                    parsed["summary"] = fallback
                    parsed["steps"] = []
                    parsed["full_text"] = fallback

            translated_current_user = (
                await translated_user_for_fallback()
                if normalized_mode == "TEST_DRIVE"
                else ""
            )
            if (
                normalized_mode == "TEST_DRIVE"
                and (
                    self._message_has_dealer_intent(
                        user_msg,
                        translated_current_user,
                    )
                    or self._message_has_booking_date(
                        user_msg,
                        translated_current_user,
                    )
                    or self._message_has_booking_time(
                        user_msg,
                        translated_current_user,
                    )
                    or self._sales_reply_needs_fallback(
                        parsed["summary"],
                        business_context,
                    )
                )
            ):
                fallback = self._sales_language_fallback(
                    user_message=user_msg,
                    raw_reply=raw_text,
                    business_context=business_context,
                    language_code=language_code,
                    translated_user=translated_current_user,
                    conversation_history=conversation_history,
                )
                parsed["summary"] = fallback
                parsed["steps"] = []
                parsed["full_text"] = fallback

            logger.info("✅ [SARVAM LLM DIAGNOSTIC PARSED SUCCESS]")
            logger.info(f"   Urgency Rating: {parsed['urgency']}")
            logger.info(f"   Steps Count   : {len(parsed['steps'])}")
            logger.info(f"   Summary       : {parsed['summary']}")
            print("="*80 + "\n")
            return parsed

        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            err_final = f"[SARVAM LLM FAILURE] Chat completion failed: {e}"
            logger.error(err_final)
            print("="*80 + "\n")
            raise RuntimeError(err_final) from e
        except RuntimeError as e:
            err_final = f"[SARVAM LLM FAILURE] Chat completion failed: {e}"
            logger.error(err_final)
            print("="*80 + "\n")
            raise RuntimeError(err_final) from e

    @staticmethod
    def _uses_expected_script(text: str, language_code: str) -> bool:
        """Check that non-English replies contain enough characters from the selected script."""
        script_ranges = {
            "hi": "\u0900-\u097F",
            "mr": "\u0900-\u097F",
            "bn": "\u0980-\u09FF",
            "pa": "\u0A00-\u0A7F",
            "gu": "\u0A80-\u0AFF",
            "ta": "\u0B80-\u0BFF",
            "te": "\u0C00-\u0C7F",
            "kn": "\u0C80-\u0CFF",
            "ml": "\u0D00-\u0D7F",
        }
        language = language_code.lower().split("-", 1)[0]
        if language == "en" or language not in script_ranges:
            return True
        return len(re.findall(f"[{script_ranges[language]}]", text or "")) >= 8

    @staticmethod
    def _looks_like_internal_plan(text: str) -> bool:
        normalized = (text or "").casefold()
        planning_phrases = (
            "the customer wants",
            "i will provide",
            "i will ask",
            "i need to ask",
            "as per the workflow",
            "confirm the customer",
            "provide the available",
        )
        return any(phrase in normalized for phrase in planning_phrases)

    @staticmethod
    def _message_has_dealer_intent(text: str, translated_text: str = "") -> bool:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        terms = (
            "dealer", "dealership", "locality", "location", "area", "near",
            "dwarka", "delhi", "डीलर", "जगह", "इलाका", "दिल्ली",
            "द्वारका", "द्वारिका",
        )
        return any(term in normalized for term in terms)

    @staticmethod
    def _message_has_booking_date(text: str, translated_text: str = "") -> bool:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        date_terms = (
            "आज", "कल", "परसों", "तारीख", "डेट",
            "today", "tomorrow", "date",
            "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
            "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        )
        return (
            any(term in normalized for term in date_terms)
            or bool(
                re.search(
                    r"\b\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?\b",
                    normalized,
                )
            )
        )

    @staticmethod
    def _normalize_spoken_digits(text: str) -> str:
        """Convert Hindi/English spoken digit words into compact digit sequences."""
        normalized = (text or "").translate(
            str.maketrans("०१२३४५६७८९", "0123456789")
        )
        spoken_digits = {
            "ज़ीरो": "0", "जीरो": "0", "शून्य": "0", "zero": "0",
            "वन": "1", "एक": "1", "one": "1",
            "टू": "2", "दो": "2", "two": "2",
            "थ्री": "3", "तीन": "3", "three": "3",
            "फोर": "4", "चार": "4", "four": "4",
            "फाइव": "5", "पाँच": "5", "पांच": "5", "five": "5",
            "सिक्स": "6", "छह": "6", "छः": "6", "six": "6",
            "सेवन": "7", "सात": "7", "seven": "7",
            "एट": "8", "आठ": "8", "eight": "8",
            "नाइन": "9", "नौ": "9", "nine": "9",
        }
        for word, digit in sorted(
            spoken_digits.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            normalized = re.sub(
                rf"(?<![\w]){re.escape(word)}(?![\w])",
                digit,
                normalized,
                flags=re.IGNORECASE,
            )
        return re.sub(r"(?<=\d)[\s,.-]+(?=\d)", "", normalized)

    @staticmethod
    def _parse_booking_date(text: str, translated_text: str = "") -> Optional[date]:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        normalized = SarvamAIService._normalize_spoken_digits(normalized)
        today = date.today()

        if "परसों" in normalized or "day after tomorrow" in normalized:
            return today + timedelta(days=2)
        if "कल" in normalized or "tomorrow" in normalized:
            return today + timedelta(days=1)
        if "आज" in normalized or re.search(r"\btoday\b", normalized):
            return today

        iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", normalized)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                return None

        numeric_match = re.search(
            r"\b(\d{1,2})[-/.](\d{1,2})(?:[-/.](\d{2,4}))?\b",
            normalized,
        )
        if numeric_match:
            year = int(numeric_match.group(3) or today.year)
            if year < 100:
                year += 2000
            try:
                return date(
                    year,
                    int(numeric_match.group(2)),
                    int(numeric_match.group(1)),
                )
            except ValueError:
                return None

        month_numbers = {
            "जनवरी": 1, "january": 1, "jan": 1,
            "फरवरी": 2, "february": 2, "feb": 2,
            "मार्च": 3, "march": 3, "mar": 3,
            "अप्रैल": 4, "april": 4, "apr": 4,
            "मई": 5, "may": 5,
            "जून": 6, "june": 6, "jun": 6,
            "जुलाई": 7, "july": 7, "jul": 7,
            "अगस्त": 8, "august": 8, "aug": 8,
            "सितंबर": 9, "september": 9, "sep": 9,
            "अक्टूबर": 10, "october": 10, "oct": 10,
            "नवंबर": 11, "november": 11, "nov": 11,
            "दिसंबर": 12, "december": 12, "dec": 12,
        }
        month_pattern = "|".join(
            re.escape(month_name)
            for month_name in sorted(month_numbers, key=len, reverse=True)
        )
        named_match = re.search(
            rf"\b(\d{{1,2}})\s*({month_pattern})(?:\s*(20\d{{2}}))?\b",
            normalized,
        )
        if named_match:
            try:
                return date(
                    int(named_match.group(3) or today.year),
                    month_numbers[named_match.group(2)],
                    int(named_match.group(1)),
                )
            except ValueError:
                return None
        return None

    @staticmethod
    def _format_booking_date(value: date, language_code: str) -> str:
        if language_code.lower().startswith("hi"):
            hindi_months = (
                "", "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून",
                "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
            )
            return f"{value.day} {hindi_months[value.month]} {value.year}"
        return value.strftime("%d %B %Y")

    @staticmethod
    def _message_has_booking_time(text: str, translated_text: str = "") -> bool:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        time_terms = (
            "बजे", "समय", "टाइम", "सुबह", "दोपहर", "शाम",
            "am", "pm", "a.m.", "p.m.", "time", "morning",
            "afternoon", "evening", "noon",
        )
        return (
            any(term in normalized for term in time_terms)
            or bool(re.search(r"\b(?:10|12|0?2|0?4)(?::00)?\b", normalized))
        )

    @staticmethod
    def _parse_booking_time(text: str, translated_text: str = "") -> Optional[str]:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        normalized = SarvamAIService._normalize_spoken_digits(normalized)

        hindi_spoken_slots = (
            ("बारह", "12:00 PM"),
            ("दस", "10:00 AM"),
            ("चार", "04:00 PM"),
            ("दो", "02:00 PM"),
        )
        for term, slot in hindi_spoken_slots:
            if re.search(rf"{term}\s*बजे", normalized):
                return slot

        numeric_slots = (
            (r"\b12(?::00)?\s*(?:pm|p\.m\.)?\b", "12:00 PM"),
            (r"\b10(?::00)?\s*(?:am|a\.m\.)?\b", "10:00 AM"),
            (r"\b0?4(?::00)?\s*(?:pm|p\.m\.)?\b", "04:00 PM"),
            (r"\b0?2(?::00)?\s*(?:pm|p\.m\.)?\b", "02:00 PM"),
        )
        for pattern, slot in numeric_slots:
            if re.search(pattern, normalized):
                return slot

        english_spoken_slots = (
            (r"\b(?:twelve|noon)\b", "12:00 PM"),
            (r"\bten\b", "10:00 AM"),
            (r"\bfour\b", "04:00 PM"),
            (r"\btwo\b", "02:00 PM"),
        )
        for pattern, slot in english_spoken_slots:
            if re.search(pattern, normalized):
                return slot
        return None

    @staticmethod
    def _parse_test_drive_location(
        text: str,
        translated_text: str = "",
    ) -> Optional[str]:
        normalized = f"{text or ''} {translated_text or ''}".casefold()
        if any(term in normalized for term in ("घर", "home", "मेरे पते", "my address")):
            return "HOME"
        if any(
            term in normalized
            for term in ("डीलरशिप", "शोरूम", "showroom", "at the dealer")
        ):
            return "DEALERSHIP"
        return None

    @classmethod
    def _sales_reply_needs_fallback(
        cls,
        text: str,
        business_context: Optional[str],
    ) -> bool:
        """Reject long, plan-like, multi-question, or non-progressing sales replies."""
        reply = (text or "").strip()
        if not reply or len(reply) > 320 or cls._looks_like_internal_plan(reply):
            return True
        if reply.count("?") + reply.count("？") != 1:
            return True

        try:
            context = json.loads(business_context or "{}")
        except (TypeError, json.JSONDecodeError):
            return False
        model_rows = context.get("all_models_ready_for_test_drive") or []
        mentioned_models = {
            str(item.get("name", "")).strip().casefold()
            for item in model_rows
            if str(item.get("name", "")).strip()
            and str(item.get("name", "")).strip().casefold() in reply.casefold()
        }
        return len(mentioned_models) > 4

    @staticmethod
    def _sales_language_fallback(
        user_message: str,
        raw_reply: str,
        business_context: Optional[str],
        language_code: str,
        translated_user: str = "",
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Return a short DB-grounded sales prompt if the LLM twice ignores language."""
        try:
            context = json.loads(business_context or "{}")
        except (TypeError, json.JSONDecodeError):
            context = {}

        recent_models = context.get("recent_models_ready_for_test_drive") or []
        all_models = context.get("all_models_ready_for_test_drive") or []
        model_rows = all_models or recent_models
        model_names = [
            str(item.get("name", "")).strip()
            for item in model_rows
            if str(item.get("name", "")).strip()
        ]

        selected_model = None
        user_casefold = (user_message or "").casefold()
        translated_user_casefold = (translated_user or "").casefold()
        raw_casefold = (raw_reply or "").casefold()
        current_customer_text = re.sub(
            r"\s+",
            " ",
            f"{user_casefold} {translated_user_casefold}",
        ).strip()
        spoken_model_aliases = {
            "e vitara": (
                "ई विटारा", "ईवी विटारा", "ई वी विटारा",
                "ईवी टारा", "ई वी टारा", "ईवी टेरा", "ई वी टेरा",
                "ईवी टायर", "ई वी टायर", "इवी टारा", "इवी टेरा",
                "इवी टायर", "ev vitara", "evitara",
            ),
            "victoris": (
                "विक्टोरिस", "विक्टोरियस", "विक्टोरिस्", "victorious",
            ),
            "dzire": ("डिजायर", "डिज़ायर", "डिजाइर", "desire"),
            "swift": ("स्विफ्ट", "सिविफ्ट"),
        }
        for model_name in model_names:
            aliases = spoken_model_aliases.get(model_name.casefold(), ())
            if any(alias in current_customer_text for alias in aliases):
                selected_model = model_name
                break

        # "विटारा" by itself can refer to e VITARA or Grand Vitara. Resolve it
        # from the most recent choices shown to the customer instead of making
        # a global, ambiguous alias. The current new-model prompt offers only
        # e VITARA from the Vitara family.
        if (
            not selected_model
            and any(
                alias in current_customer_text
                for alias in ("विटारा", "vitara")
            )
        ):
            offered_vitara_models = []
            for turn in reversed(conversation_history or []):
                if str(turn.get("role", "")).lower() != "assistant":
                    continue
                turn_text = str(turn.get("content", "")).casefold()
                offered_vitara_models = [
                    model_name
                    for model_name in model_names
                    if "vitara" in model_name.casefold()
                    and model_name.casefold() in turn_text
                ]
                if offered_vitara_models:
                    break
            if len(offered_vitara_models) == 1:
                selected_model = offered_vitara_models[0]
            else:
                recent_vitara_models = [
                    str(model.get("name", "")).strip()
                    for model in recent_models
                    if "vitara" in str(model.get("name", "")).casefold()
                ]
                if len(recent_vitara_models) == 1:
                    selected_model = recent_vitara_models[0]

        raw_model_mentions = [
            model_name
            for model_name in model_names
            if model_name.casefold() in raw_casefold
        ]
        if not selected_model:
            for model_name in model_names:
                if (
                    model_name.casefold() in user_casefold
                    or model_name.casefold() in translated_user_casefold
                ):
                    selected_model = model_name
                    break
                selected_pattern = rf"\bfor (?:the )?{re.escape(model_name.casefold())}\b"
                if re.search(selected_pattern, raw_casefold):
                    selected_model = model_name
                    break
        if not selected_model and len(raw_model_mentions) == 1:
            selected_model = raw_model_mentions[0]
        if not selected_model and translated_user_casefold:
            words = re.findall(r"[a-z0-9]+", translated_user_casefold)
            phrases = words + [
                f"{words[index]} {words[index + 1]}"
                for index in range(len(words) - 1)
            ]
            best_score = 0.0
            best_model = None
            for model_name in model_names:
                normalized_model = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    model_name.casefold(),
                ).strip()
                for phrase in phrases:
                    score = SequenceMatcher(None, normalized_model, phrase).ratio()
                    if score > best_score:
                        best_score = score
                        best_model = model_name
            if best_score >= 0.70:
                selected_model = best_model

        if not selected_model:
            for turn in reversed(conversation_history or []):
                turn_text = str(turn.get("content", "")).casefold()
                turn_mentions = [
                    model_name
                    for model_name in model_names
                    if model_name.casefold() in turn_text
                ]
                if len(turn_mentions) == 1:
                    selected_model = turn_mentions[0]
                    break

        dealers = context.get("dealerships") or []
        eligible_dealers = []
        if selected_model:
            eligible_dealers = [
                dealer for dealer in dealers
                if selected_model.casefold()
                in str(dealer.get("test_drive_models", "")).casefold()
            ]

        location_search = " ".join(
            (user_casefold, translated_user_casefold, raw_casefold)
        )
        dealer_intent_terms = (
            "dealer",
            "dealership",
            "locality",
            "location",
            "area",
            "near",
            "dwarka",
            "delhi",
            "डीलर",
            "जगह",
            "इलाका",
            "दिल्ली",
            "द्वारका",
            "द्वारिका",
        )
        asks_for_dealer = any(term in location_search for term in dealer_intent_terms)
        location_stopwords = {
            "available", "availability", "book", "booking", "car", "dealer",
            "dealership", "delhi", "drive", "here", "locality", "location",
            "model", "near", "new", "test", "the", "this", "want",
        }
        location_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", translated_user_casefold)
            if len(token) >= 4 and token not in location_stopwords
        }
        normalized_location_input = SarvamAIService._normalize_spoken_digits(
            user_casefold
        )
        if "द्वारका" in normalized_location_input or "द्वारिका" in normalized_location_input:
            location_tokens.add("dwarka")
        if "दिल्ली" in normalized_location_input:
            location_tokens.add("delhi")
        sector_match = re.search(
            r"(?:सेक्टर|sector)\s*(\d{1,3})",
            normalized_location_input,
        )
        if sector_match:
            location_tokens.add(f"sector {sector_match.group(1)}")
        pincode_match = re.search(r"(?<!\d)([1-9]\d{5})(?!\d)", normalized_location_input)
        if pincode_match:
            location_tokens.add(pincode_match.group(1))

        scored_localities = []
        for dealer in eligible_dealers:
            searchable = (
                f"{dealer.get('name', '')} {dealer.get('address', '')} "
                f"{dealer.get('city', '')} {dealer.get('pincode', '')}"
            ).casefold()
            score = sum(token in searchable for token in location_tokens)
            if score:
                scored_localities.append((score, dealer))
        best_locality_score = max(
            (score for score, _dealer in scored_localities),
            default=0,
        )
        locality_matches = [
            dealer
            for score, dealer in scored_localities
            if score == best_locality_score
        ]
        confirmation_text = f"{user_casefold} {translated_user_casefold}"
        confirms_dealer = any(
            phrase in confirmation_text
            for phrase in (
                "हाँ", "यही", "इसी", "चुनना है", "बुक कर दो",
                "बुक करनी है", "बुकिंग करनी है",
                "yes", "this dealership", "this one", "choose this",
                "book it", "book from here",
            )
        )
        suggested_dealer = None
        confirmed_dealer = None
        for turn in reversed(conversation_history or []):
            if str(turn.get("role", "")).lower() != "assistant":
                continue
            turn_text = str(turn.get("content", "")).casefold()
            turn_dealers = [
                dealer for dealer in eligible_dealers
                if str(dealer.get("name", "")).casefold() in turn_text
            ]
            if len(turn_dealers) != 1:
                continue
            if any(
                marker in turn_text
                for marker in ("चुन ली गई", "किस तारीख", "selected", "which date")
            ):
                confirmed_dealer = turn_dealers[0]
                break
            if suggested_dealer is None:
                suggested_dealer = turn_dealers[0]

        selected_dealer = confirmed_dealer
        if confirms_dealer:
            if len(locality_matches) == 1:
                selected_dealer = locality_matches[0]
            elif suggested_dealer is not None:
                selected_dealer = suggested_dealer

        requested_date = SarvamAIService._parse_booking_date(
            user_message,
            translated_user,
        )
        has_date_intent = SarvamAIService._message_has_booking_date(
            user_message,
            translated_user,
        )
        requested_time = SarvamAIService._parse_booking_time(
            user_message,
            translated_user,
        )
        has_time_intent = SarvamAIService._message_has_booking_time(
            user_message,
            translated_user,
        )
        requested_location = SarvamAIService._parse_test_drive_location(
            user_message,
            translated_user,
        )

        historical_date = None
        historical_time = None
        historical_location = None
        for turn in reversed(conversation_history or []):
            if str(turn.get("role", "")).lower() != "assistant":
                continue
            turn_text = str(turn.get("content", ""))
            turn_casefold = turn_text.casefold()
            if historical_date is None and any(
                marker in turn_casefold
                for marker in (
                    "तारीख चुन ली गई",
                    "समय चुन लिया गया",
                    "date selected",
                    "time selected",
                )
            ):
                historical_date = SarvamAIService._parse_booking_date(turn_text)
            if historical_time is None and any(
                marker in turn_casefold
                for marker in ("समय चुन लिया गया", "time selected")
            ):
                historical_time = SarvamAIService._parse_booking_time(turn_text)
            if historical_location is None:
                if "घर पर टेस्ट ड्राइव चुन" in turn_casefold:
                    historical_location = "HOME"
                elif "डीलरशिप पर टेस्ट ड्राइव चुन" in turn_casefold:
                    historical_location = "DEALERSHIP"

        selected_date = requested_date or historical_date
        selected_time = requested_time or historical_time
        selected_location = requested_location or historical_location

        assistant_turns = [
            str(turn.get("content", ""))
            for turn in conversation_history or []
            if str(turn.get("role", "")).lower() == "assistant"
        ]
        last_assistant = assistant_turns[-1].casefold() if assistant_turns else ""
        awaiting_name = any(
            marker in last_assistant
            for marker in ("बुकिंग किस नाम से करनी है", "booking name")
        )
        awaiting_mobile = any(
            marker in last_assistant
            for marker in ("मोबाइल नंबर बताइए", "mobile number")
        )
        awaiting_address = any(
            marker in last_assistant
            for marker in (
                "पूरा पता बताइए",
                "पता पूरा नहीं मिला",
                "पिनकोड सहित पूरा पता",
                "complete address",
                "address with the six-digit pincode",
            )
        )

        requested_name = None
        if awaiting_name:
            candidate_name = re.sub(
                r"^[\s\"'“”‘’]+|[\s।.!?,\"'“”‘’]+$",
                "",
                user_message,
            )
            if (
                2 <= len(candidate_name) <= 100
                and not re.search(r"\d", candidate_name)
            ):
                requested_name = candidate_name

        requested_mobile = None
        normalized_customer_input = SarvamAIService._normalize_spoken_digits(
            user_message
        )
        mobile_match = re.search(r"(?<!\d)([6-9]\d{9})(?!\d)", normalized_customer_input)
        if mobile_match:
            requested_mobile = mobile_match.group(1)

        requested_address = None
        if awaiting_address:
            candidate_address = user_message.strip(" \t\r\n।")
            if len(candidate_address) >= 5:
                requested_address = candidate_address

        historical_name = None
        historical_mobile = None
        address_recorded = False
        for turn_text in reversed(assistant_turns):
            if historical_name is None:
                name_match = re.search(
                    r"ग्राहक का नाम (.+?) दर्ज कर लिया गया है",
                    turn_text,
                    flags=re.IGNORECASE,
                )
                if name_match:
                    historical_name = name_match.group(1).strip()
            if historical_mobile is None:
                saved_mobile_match = re.search(
                    r"मोबाइल नंबर ([6-9]\d{9}) दर्ज कर लिया गया है",
                    turn_text,
                )
                if saved_mobile_match:
                    historical_mobile = saved_mobile_match.group(1)
            if "पता दर्ज कर लिया गया है" in turn_text:
                address_recorded = True

        selected_customer_name = requested_name or historical_name
        selected_mobile = requested_mobile or historical_mobile
        selected_address_recorded = bool(requested_address) or address_recorded

        if language_code.lower().startswith("hi"):
            if selected_model:
                if selected_dealer:
                    if selected_date:
                        formatted_date = SarvamAIService._format_booking_date(
                            selected_date,
                            language_code,
                        )
                        if selected_date < date.today():
                            return (
                                f"{formatted_date} बीत चुकी है। "
                                "कृपया आज से अगले 30 दिनों की कोई तारीख बताइए?"
                            )
                        if selected_date > date.today() + timedelta(days=30):
                            return (
                                f"{formatted_date} अभी बुकिंग सीमा से बाहर है। "
                                "कृपया आज से अगले 30 दिनों की कोई तारीख बताइए?"
                            )
                    elif has_date_intent:
                        return (
                            "मैं तारीख स्पष्ट रूप से नहीं समझ पाया। "
                            "कृपया जैसे 30 जुलाई 2026 या कल कहकर बताइए?"
                        )
                    else:
                        return (
                            f"{selected_dealer.get('name')}, "
                            f"{selected_dealer.get('address')} चुन ली गई है। "
                            "आप किस तारीख को टेस्ट ड्राइव लेना चाहेंगे?"
                        )

                    if not selected_time:
                        if has_time_intent:
                            return (
                                "मैं समय स्पष्ट रूप से नहीं समझ पाया। "
                                "उपलब्ध समय सुबह 10 बजे, दोपहर 12 बजे, "
                                "दोपहर 2 बजे या शाम 4 बजे है। आप कौन सा समय चुनेंगे?"
                            )
                        return (
                            f"{formatted_date} की तारीख चुन ली गई है। "
                            "आप किस समय टेस्ट ड्राइव लेना चाहेंगे?"
                        )

                    if not selected_location:
                        return (
                            f"{formatted_date} को {selected_time} का समय चुन लिया गया है। "
                            "आप टेस्ट ड्राइव घर पर लेना चाहेंगे या डीलरशिप पर?"
                        )

                    location_text = (
                        "घर पर" if selected_location == "HOME" else "डीलरशिप पर"
                    )
                    if not selected_customer_name:
                        if awaiting_name:
                            return (
                                "मैं नाम स्पष्ट रूप से नहीं समझ पाया। "
                                "कृपया अपना पूरा नाम बताइए?"
                            )
                        return (
                            f"{formatted_date} को {selected_time} पर {location_text} "
                            "टेस्ट ड्राइव चुन ली गई है। बुकिंग किस नाम से करनी है?"
                        )

                    if not selected_mobile:
                        if awaiting_mobile:
                            return (
                                "मोबाइल नंबर सही प्रारूप में नहीं मिला। "
                                "कृपया 6, 7, 8 या 9 से शुरू होने वाला 10 अंकों का नंबर बताइए?"
                            )
                        return (
                            f"ग्राहक का नाम {selected_customer_name} दर्ज कर लिया गया है। "
                            "कृपया 10 अंकों का मोबाइल नंबर बताइए?"
                        )

                    if not selected_address_recorded:
                        if awaiting_address:
                            return (
                                "पता अधूरा लग रहा है। कृपया मकान या फ्लैट नंबर, "
                                "इलाका, शहर और पिनकोड सहित पूरा पता बताइए?"
                            )
                        return (
                            f"मोबाइल नंबर {selected_mobile} दर्ज कर लिया गया है। "
                            "कृपया मकान या फ्लैट नंबर, इलाका, शहर और पिनकोड सहित "
                            "पूरा पता बताइए?"
                        )

                    return (
                        "पता दर्ज कर लिया गया है। आपकी टेस्ट ड्राइव बुक की जा रही है।"
                    )
                if locality_matches:
                    dealer = locality_matches[0]
                    return (
                        f"{selected_model} की टेस्ट ड्राइव "
                        f"{dealer.get('name')}, {dealer.get('address')} पर उपलब्ध है। "
                        "क्या आप यही डीलरशिप चुनना चाहेंगे?"
                    )
                if asks_for_dealer and eligible_dealers:
                    dealer_names = ", ".join(
                        f"{dealer.get('name')} ({dealer.get('address')})"
                        for dealer in eligible_dealers[:3]
                    )
                    return (
                        f"{selected_model} के लिए {dealer_names} उपलब्ध हैं। "
                        "आप कौन सी डीलरशिप चुनना चाहेंगे?"
                    )
                return (
                    f"{selected_model} की टेस्ट ड्राइव उपलब्ध है। "
                    "आप किस डीलरशिप या इलाके से बुक करना चाहेंगे?"
                )
            choices_source = recent_models or all_models
            choices = [
                str(item.get("name", "")).strip()
                for item in choices_source[:4]
                if str(item.get("name", "")).strip()
            ]
            choice_text = ", ".join(choices)
            if choice_text:
                return (
                    f"ज़रूर, मैं आपकी टेस्ट ड्राइव बुक कर सकता हूँ। "
                    f"अभी {choice_text} उपलब्ध हैं। आप कौन सा मॉडल पसंद करेंगे?"
                )
            return (
                "ज़रूर, मैं आपकी टेस्ट ड्राइव बुक कर सकता हूँ। "
                "आप कौन सा मॉडल पसंद करेंगे?"
            )

        if selected_model:
            return (
                f"A test drive is available for the {selected_model}. "
                "Which dealership or locality would you prefer?"
            )
        return "I can help book your test drive. Which model would you prefer?"

    async def text_to_speech(
        self,
        text: str = "",
        steps: Optional[List[str]] = None,
        language_code: str = "hi-IN",
        speaker: str = "ShubhMale"
    ) -> Optional[str]:
        """
        Synthesizes text to speech using Sarvam AI TTS API (bulbul:v3).
        Accepts either a `text` string or a `steps` list.
        Each step is sent as a separate TTS input (max 500 chars each).
        Multiple audio chunks are combined into one base64 WAV.
        Real API calls only.
        """
        self.reload_config()

        if not self.is_live:
            err_msg = "[SARVAM TTS ERROR] SARVAM_API_KEY is missing or invalid in .env!"
            logger.error(err_msg)
            raise ValueError(err_msg)

        # Build inputs list: prefer steps list, fall back to text string
        if steps and isinstance(steps, list):
            raw_inputs = [s.strip() for s in steps if s.strip()]
        elif text and text.strip():
            raw_inputs = [text.strip()]
        else:
            logger.warning("[SARVAM TTS WARNING] Both text and steps are empty.")
            return None

        # Split any input exceeding 500 chars into smaller chunks
        MAX_CHARS = 500
        tts_inputs = []
        for inp in raw_inputs:
            if len(inp) <= MAX_CHARS:
                tts_inputs.append(inp)
            else:
                # Split on sentence boundaries
                sentences = re.split(r'(?<=[।.!?])\s+', inp)
                chunk = ""
                for sent in sentences:
                    if len(chunk) + len(sent) + 1 <= MAX_CHARS:
                        chunk = (chunk + " " + sent).strip()
                    else:
                        if chunk:
                            tts_inputs.append(chunk)
                        chunk = sent[:MAX_CHARS]
                if chunk:
                    tts_inputs.append(chunk)

        actual_speaker = SPEAKER_MAP.get(speaker, "shubh")

        print("\n" + "="*80)
        logger.info(f"🔊 [SARVAM TTS REQUEST] Synthesizing audio with bulbul:v3")
        logger.info(f"   Language Code : {language_code} ({LANGUAGE_NAMES.get(language_code, 'Unknown')})")
        logger.info(f"   Speaker Voice : {actual_speaker} (Selected: {speaker})")
        logger.info(f"   Total Inputs  : {len(tts_inputs)} chunk(s)")
        for i, inp in enumerate(tts_inputs):
            logger.info(f"   Input {i+1} ({len(inp)} chars): \"{inp[:80]}...\"")
        print("="*80)

        import base64, struct

        def _merge_wav_b64_list(b64_list: list) -> str:
            """Merge a list of base64 WAV strings into one by concatenating PCM data."""
            if len(b64_list) == 1:
                return b64_list[0]
            pcm_parts = []
            for b64 in b64_list:
                wav = base64.b64decode(b64)
                pcm_parts.append(wav[44:])  # skip 44-byte WAV header
            combined_pcm = b"".join(pcm_parts)
            sample_rate = 22050
            header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + len(combined_pcm), b'WAVE',
                b'fmt ', 16, 1, 1,
                sample_rate, sample_rate * 2, 2, 16,
                b'data', len(combined_pcm)
            )
            return base64.b64encode(header + combined_pcm).decode('utf-8')

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }

        # Sarvam TTS allows max 3 inputs per request — batch accordingly
        MAX_INPUTS_PER_CALL = 3
        batches = [
            tts_inputs[i:i + MAX_INPUTS_PER_CALL]
            for i in range(0, len(tts_inputs), MAX_INPUTS_PER_CALL)
        ]
        logger.info(f"   Batches        : {len(batches)} API call(s) for {len(tts_inputs)} input(s)")

        async def _fetch_batch(client: httpx.AsyncClient, batch_idx: int, batch: list):
            payload = {
                "inputs": batch,
                "target_language_code": language_code,
                "speaker": actual_speaker,
                "model": "bulbul:v3",
                "pace": 1.0,
                "speech_sample_rate": 22050,
                "enable_preprocessing": True
            }
            res = await client.post(SARVAM_TTS_URL, headers=headers, json=payload)
            logger.info(f"📡 [SARVAM TTS BATCH {batch_idx+1}/{len(batches)}] Status: {res.status_code}")
            if res.status_code == 200:
                res_json = res.json()
                audios = res_json.get("audios", [])
                if not audios:
                    single = res_json.get("audio")
                    audios = [single] if single else []
                return [a for a in audios if a]
            else:
                logger.error(f"[SARVAM TTS API FAILED] Batch {batch_idx+1} HTTP {res.status_code}: {res.text}")
                return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                tasks = [_fetch_batch(client, idx, b) for idx, b in enumerate(batches)]
                results = await asyncio.gather(*tasks)

            all_audio_b64 = []
            for r in results:
                all_audio_b64.extend(r)

            if all_audio_b64:
                combined_b64 = _merge_wav_b64_list(all_audio_b64)
                logger.info(f"✅ [SARVAM TTS SUCCESS] {len(all_audio_b64)} audio chunk(s) merged → {len(combined_b64)} chars")
                print("="*80 + "\n")
                return combined_b64

            err_msg = "[SARVAM TTS ERROR] API returned no audio data."
            logger.error(err_msg)
            print("="*80 + "\n")
            raise RuntimeError(err_msg)

        except Exception as e:
            logger.error(f"❌ [SARVAM TTS EXCEPTION] {e}")
            print("="*80 + "\n")
            raise RuntimeError(f"Sarvam TTS API call failed: {e}")



    def _validate_structured_diagnostic(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize Sarvam's structured chat response for the API/UI."""
        if not isinstance(result, dict):
            raise ValueError("Structured LLM response is not an object.")

        allowed_urgencies = {"PULL OVER IMMEDIATELY", "CAUTION", "SAFE TO DRIVE"}
        allowed_confidences = {"HIGH", "MEDIUM", "LOW"}

        urgency = str(result.get("urgency", "CAUTION")).upper().strip()
        confidence = str(result.get("confidence", "MEDIUM")).upper().strip()
        summary = str(result.get("summary", "")).strip()
        raw_steps = result.get("steps", [])

        if urgency not in allowed_urgencies:
            urgency = "CAUTION"
        if confidence not in allowed_confidences:
            confidence = "MEDIUM"
        if not summary:
            raise ValueError("Structured LLM response has an empty summary.")
        if not isinstance(raw_steps, list):
            raise ValueError("Structured LLM response steps must be a list.")

        steps = []
        seen_lines = {summary.casefold()}
        for raw_step in raw_steps:
            step = str(raw_step).strip()
            normalized = step.casefold()
            if not step or normalized in seen_lines:
                continue
            seen_lines.add(normalized)
            steps.append(step)
            if len(steps) == 5:
                break
        full_text = summary
        if steps:
            full_text = f"{summary}\n" + "\n".join(steps)

        return {
            "urgency": urgency,
            "confidence": confidence,
            "steps": steps,
            "full_text": full_text,
            "summary": summary
        }

    def _parse_diagnostic_output(self, raw_text: str, user_query: str, language_code: str = "hi-IN") -> Dict[str, Any]:
        """
        Parses natural conversational spoken output into summary, diagnostic steps, and urgency badges.
        """
        if not raw_text:
            raise ValueError("Raw text from Sarvam LLM is empty.")

        # Clean markdown formatting (*, **, quotes) and any step labels
        clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', raw_text)
        clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)
        clean_text = re.sub(r'^\s*[\"\']|[\"\']\s*$', '', clean_text)
        clean_text = re.sub(r'^(?:Urgency|Confidence|Step\s*\d+|Summary|चरण\s*\d+)\s*[:\-]\s*', '', clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.strip()

        # Urgency auto-detection
        upper_text = raw_text.upper()
        urgency = "CAUTION"
        if ("PULL OVER" in upper_text or "STOP DRIVING" in upper_text or "CRITICAL" in upper_text
                or "DANGER" in upper_text or "तुरंत रोकें" in raw_text or "खतरा" in raw_text or "इमरजेंसी" in raw_text):
            urgency = "PULL OVER IMMEDIATELY"
        elif ("SAFE TO DRIVE" in upper_text or "MINOR" in upper_text or "सुरक्षित" in raw_text or "ठीक" in raw_text):
            urgency = "SAFE TO DRIVE"

        # Split conversational sentences into diagnostic step items for the UI checklist
        sentences = [s.strip() for s in re.split(r'(?<=[।.!?])\s+', clean_text) if s.strip() and len(s.strip()) > 3]
        if not sentences:
            sentences = [clean_text]

        return {
            "urgency": urgency,
            "confidence": "HIGH",
            "steps": sentences[:5],
            "full_text": clean_text,
            "summary": clean_text
        }

sarvam_service = SarvamAIService()
