import json
import unittest

from database import get_sales_concierge_context
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


if __name__ == "__main__":
    unittest.main()
