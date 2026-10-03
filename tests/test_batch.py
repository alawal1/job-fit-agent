"""Offline test for batch mode. The agent is mocked: no OpenAI calls, no live URLs."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")  # agent.py creates an OpenAI client at import

import batch

QUEUE = """# Queue

## Acme — Data Analyst
- url: https://example.com/jobs/1
- text: postings/acme.txt

## Globex — Ops Associate
- url: https://example.com/jobs/2
- text: postings/globex.txt

## Initech — Consultant
- url: https://example.com/jobs/3
- text: postings/initech.txt
"""


def fake_agent(text):
    if "Acme" in text:
        return {"verdict": "apply", "confidence": "high",
                "reasoning": {"strengths": ["SQL", "English"], "gaps": [], "open_questions": [], "reason": "Strong match."}}
    if "Globex" in text:
        return {"verdict": "borderline", "confidence": "medium",
                "reasoning": {"strengths": ["Ops"], "gaps": ["Swedish"], "open_questions": ["Is Swedish required?"], "reason": "Unclear language."}}
    raise RuntimeError("OpenAI timeout")


class BatchTest(unittest.TestCase):
    @patch("batch._notify")
    @patch("batch.agent.run_agent_v2_from_text", side_effect=fake_agent)
    def test_three_job_queue(self, mock_agent, mock_notify):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "postings").mkdir()
            for name in ["Acme", "Globex", "Initech"]:
                (tmp / "postings" / f"{name.lower()}.txt").write_text(f"{name} job posting text")
            queue = tmp / "queue.md"
            queue.write_text(QUEUE)
            results = tmp / "queue-results.md"

            # Run 1: the failing job doesn't stop the others.
            batch.run_queue(queue)
            text = results.read_text()
            self.assertIn("1 apply · 1 borderline · 0 skip · 1 failed", text)
            self.assertIn("- url: https://example.com/jobs/1", text)
            self.assertIn("  - Is Swedish required?", text)
            self.assertIn("- reason: Strong match.", text)
            self.assertIn("- attempts: 1", text)
            self.assertEqual(mock_agent.call_count, 3)
            mock_notify.assert_called_with("Job-fit: 1 apply, 1 borderline")

            # Run 2: only the failed job is retried; it fails again.
            batch.run_queue(queue)
            self.assertEqual(mock_agent.call_count, 4)
            self.assertIn("- attempts: 2", results.read_text())

            # Run 3: failed twice → done, nothing is judged.
            batch.run_queue(queue)
            self.assertEqual(mock_agent.call_count, 4)
            self.assertIn("1 apply · 1 borderline · 0 skip · 1 failed", results.read_text())


if __name__ == "__main__":
    unittest.main()
