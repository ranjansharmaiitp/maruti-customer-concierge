import asyncio
import json
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from database import get_sales_concierge_context
from main import (
    _auto_finalize_test_drive,
    _extract_conversational_test_drive_payload,
    auto_booked_sessions,
)
from sarvam_service import SarvamAIService


class SalesWorkflowRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = json.dumps(
            get_sales_concierge_context(),
            ensure_ascii=False,
        )
        cls.model_prompt = (
            "ज़रूर, मैं आपकी टेस्ट ड्राइव बुक कर सकता हूँ। अभी e VITARA, "
            "Victoris, Dzire, Swift उपलब्ध हैं। आप कौन सा मॉडल पसंद करेंगे?"
        )

    def reply(self, user_message, history=None):
        return SarvamAIService._sales_language_fallback(
            user_message=user_message,
            raw_reply="",
            business_context=self.context,
            language_code="hi-IN",
            conversation_history=history or [],
        )

    def advance(self, history, user_message):
        history.append({"role": "user", "content": user_message})
        reply = self.reply(user_message, history)
        history.append({"role": "assistant", "content": reply})
        return reply

    def test_e_vitara_spoken_aliases_progress_to_dealership(self):
        aliases = (
            "मैं ई विटारा की टेस्ट ड्राइव लेना चाहूँगा।",
            "मैं ईवी टायर की टेस्ट ड्राइव लेना चाहूँगा।",
            "मुझे ईवी टेरा की टेस्ट ड्राइव बुक करनी है।",
            "मुझे विटारा की बुकिंग करनी है।",
        )
        history = [
            {"role": "user", "content": "कौन सी नई गाड़ियां उपलब्ध हैं?"},
            {"role": "assistant", "content": self.model_prompt},
        ]
        for phrase in aliases:
            with self.subTest(phrase=phrase):
                reply = self.reply(phrase, history)
                self.assertTrue(reply.startswith("e VITARA की टेस्ट ड्राइव"))
                self.assertIn("किस डीलरशिप या इलाके", reply)

    def test_plain_vitara_uses_the_only_recent_vitara_model(self):
        reply = self.reply("विटारा की टेस्ट ड्राइव बुक करनी है।")
        self.assertTrue(reply.startswith("e VITARA की टेस्ट ड्राइव"))

    def test_hindi_booking_state_machine_does_not_require_llm_key(self):
        history = [
            {
                "role": "user",
                "content": "मुझे ई विटारा की टेस्ट ड्राइव बुक करनी है।",
            },
        ]
        with (
            patch("sarvam_service.load_dotenv"),
            patch.dict(os.environ, {"SARVAM_API_KEY": ""}),
        ):
            service = SarvamAIService()
            result = asyncio.run(
                service.get_diagnostic_response(
                    conversation_history=history,
                    language_code="hi-IN",
                    assistant_mode="TEST_DRIVE",
                    business_context=self.context,
                )
            )

        self.assertFalse(service.is_live)
        self.assertIn("e VITARA की टेस्ट ड्राइव उपलब्ध है", result["summary"])
        self.assertIn("किस डीलरशिप या इलाके", result["summary"])

    def test_dwarka_sector_twelve_progresses_to_date(self):
        history = [
            {"role": "user", "content": "मुझे विटारा की बुकिंग करनी है।"},
            {
                "role": "assistant",
                "content": (
                    "e VITARA की टेस्ट ड्राइव उपलब्ध है। "
                    "आप किस डीलरशिप या इलाके से बुक करना चाहेंगे?"
                ),
            },
        ]
        reply = self.reply(
            "मुझे द्वारका सेक्टर 12 न्यू दिल्ली वाले डीलर से बुक करनी है।",
            history,
        )
        self.assertIn("NEXA Dwarka Customer Experience Centre", reply)
        self.assertIn("आप किस तारीख", reply)

    def test_complete_hinglish_booking_flow_advances_every_stage(self):
        history = [
            {"role": "user", "content": "अभी कौन सी नई गाड़ियां उपलब्ध हैं?"},
            {"role": "assistant", "content": self.model_prompt},
        ]

        reply = self.advance(
            history,
            "मैं ई विटारा की टेस्ट ड्राइव लेना चाहूँगा।",
        )
        self.assertIn("किस डीलरशिप या इलाके", reply)

        reply = self.advance(
            history,
            "मुझे द्वारका सेक्टर 12 न्यू दिल्ली वाले डीलर से बुक करनी है।",
        )
        self.assertIn("NEXA Dwarka Customer Experience Centre", reply)
        self.assertIn("आप किस तारीख", reply)

        reply = self.advance(history, "कल दोपहर बारह बजे।")
        tomorrow = SarvamAIService._format_booking_date(
            date.today() + timedelta(days=1),
            "hi-IN",
        )
        self.assertIn(f"{tomorrow} को दोपहर 12 बजे", reply)
        self.assertIn("क्या आप टेस्ट ड्राइव अपने घर पर लेना चाहेंगे", reply)
        self.assertIn("NEXA Dwarka Customer Experience Centre पर आकर", reply)
        self.assertNotIn("12:00 PM", reply)

        reply = self.advance(history, "मैं अपने घर पर लेना चाहूँगा।")
        self.assertIn("बुकिंग किस नाम से करनी है", reply)

        reply = self.advance(history, "रंजन शर्मा")
        self.assertIn("ग्राहक का नाम रंजन शर्मा दर्ज कर लिया गया है", reply)
        self.assertIn("10 अंकों का मोबाइल नंबर", reply)

        reply = self.advance(history, "9097189971")
        self.assertIn("मोबाइल नंबर 9097189971 दर्ज कर लिया गया है", reply)
        self.assertIn("पूरा पता बताइए", reply)

        reply = self.advance(
            history,
            "फ्लैट 302 द्वारका ग्रीन सोसाइटी सेक्टर 14 "
            "द्वारका न्यू दिल्ली पिन कोड 110078",
        )
        self.assertEqual(
            reply,
            "पता दर्ज कर लिया गया है। आपकी टेस्ट ड्राइव बुक की जा रही है।",
        )

        payload = _extract_conversational_test_drive_payload(history)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["full_name"], "रंजन शर्मा")
        self.assertEqual(payload["mobile"], "9097189971")
        self.assertEqual(payload["booking_date"], (date.today() + timedelta(days=1)).isoformat())
        self.assertEqual(payload["time_slot"], "12:00 PM")
        self.assertEqual(payload["location_type"], "HOME")
        self.assertEqual(payload["pincode"], "110078")

    def test_complete_flow_invokes_automatic_booking_and_returns_id(self):
        history = [
            {"role": "user", "content": "अभी कौन सी नई गाड़ियां उपलब्ध हैं?"},
            {"role": "assistant", "content": self.model_prompt},
        ]
        turns = (
            "मैं ई विटारा की टेस्ट ड्राइव लेना चाहूँगा।",
            "मुझे द्वारका सेक्टर 12 न्यू दिल्ली वाले डीलर से बुक करनी है।",
            "कल दोपहर बारह बजे।",
            "घर पर।",
            "रंजन शर्मा",
            "9097189971",
            (
                "फ्लैट 302 द्वारका ग्रीन सोसाइटी सेक्टर 14 "
                "द्वारका न्यू दिल्ली पिन कोड 110078"
            ),
        )
        final_reply = ""
        for turn in turns:
            final_reply = self.advance(history, turn)

        diagnostic_result = {
            "summary": final_reply,
            "full_text": final_reply,
            "steps": [],
        }
        session_id = "workflow-auto-finalize-test"
        auto_booked_sessions.pop(session_id, None)
        fake_booking = {
            "reference_id": "TD-TEST1234",
            "customer_name": "रंजन शर्मा",
        }
        with patch("main.create_test_drive_booking", return_value=fake_booking) as create:
            booking = _auto_finalize_test_drive(
                session_id,
                history,
                diagnostic_result,
                "hi-IN",
            )

        self.assertIsNotNone(booking)
        self.assertTrue(create.called)
        self.assertTrue(diagnostic_result["booking_complete"])
        self.assertIn("TD-TEST1234", diagnostic_result["summary"])
        self.assertIn("एस एम एस", diagnostic_result["summary"])
        auto_booked_sessions.pop(session_id, None)


if __name__ == "__main__":
    unittest.main()
