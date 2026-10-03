"""Offline tests for skill sorting and CV line validation. The LLM is mocked."""

import json
import unittest
from unittest.mock import MagicMock, patch

from skills.extract_signals import extract_job_signals
from skills.suggest_cv_improvements import _norm, suggest_cv_improvements

POSTING = """Product Experience Specialist, Stockholm
What we're looking for
Recently graduated: You have completed a bachelor's or master's degree.
You must have strong written English and be a clear communicator.
Bonus: Experience in B2C SaaS support using tools like Intercom.
Bonus
: Hands-on experience with Lovable, Claude and similar AI tools.
"""


def fake_client(payload: dict):
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content=json.dumps(payload)))]
    return client


class ExtractSignalsTest(unittest.TestCase):
    def test_bonus_skills_land_in_preferred(self):
        # The LLM puts everything in required_skills (the original bug); the code must fix it.
        client = fake_client({
            "required_skills": ["Recently graduated", "Written English", "B2C SaaS support", "Intercom", "Claude", "Lovable"],
            "preferred_skills": [],
        })

        signals = extract_job_signals(POSTING, client)

        for bonus in ["B2C SaaS support", "Intercom", "Claude", "Lovable"]:
            self.assertIn(bonus, signals["preferred_skills"])
            self.assertNotIn(bonus, signals["required_skills"])
        self.assertEqual(signals["required_skills"], ["Recently graduated", "Written English"])


class CvLineTest(unittest.TestCase):
    @patch("openai.OpenAI")
    def test_every_cv_line_exists_in_cv(self, mock_openai):
        real = "Coordinated audio production and advised editorial teams on technical production issues"
        mock_openai.return_value = fake_client({
            "keep": [{"cv_line": "Synthesized policy studies and research findings into briefing materials and presentations for stakeholder meetings", "why": "x"}],
            "rewrite": [
                {"cv_line": real, "new_line": "Resolved live production issues", "evidence": "experience.md"},
                {"cv_line": "Led a team of 40 support agents", "new_line": "invented", "evidence": "experience.md"},
            ],
            "remove": [{"cv_line": "Advanced courses: English, Educational Science", "why": "x"}],
            "add": [{"section": "Projects", "new_line": "Built an AI agent", "evidence": "my imagination"}],
            "summary_line": "x",
        })

        result = suggest_cv_improvements({}, {})

        with open("data/cv.md", encoding="utf-8") as f:
            cv_lines = {_norm(line) for line in f}
        for key in ["keep", "rewrite", "remove"]:
            for item in result[key]:
                self.assertIn(_norm(item["cv_line"]), cv_lines)
        self.assertEqual(len(result["rewrite"]), 1)
        self.assertEqual(result["add"], [])  # no data/ file named as evidence
        self.assertEqual(len(result["dropped"]), 2)
        self.assertIn(f"REWRITE: {real} → Resolved live production issues", result["readable"])


if __name__ == "__main__":
    unittest.main()
