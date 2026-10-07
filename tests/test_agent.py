"""Offline test: tools get the real extracted signals/reasoning, not the model's retyped copies."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")  # agent.py creates an OpenAI client at import

import agent

REAL = {"required_skills": ["SQL"], "preferred_skills": ["Intercom"]}
RETYPED = {"required_skills": ["SQL", "Intercom"]}  # model moved a bonus skill into required


class ExecuteToolTest(unittest.TestCase):
    def test_real_outputs_beat_retyped_args(self):
        run = {"posting_text": "posting"}
        with patch.object(agent, "extract_job_signals", return_value=REAL) as extract, \
             patch.object(agent, "assess_fit", return_value={"verdict": "apply", "reasoning": {"gaps": []}}) as assess, \
             patch.object(agent, "suggest_cv_improvements", return_value={"rewrite": []}) as suggest:
            agent._execute_tool("extract_job_signals", {"job_text": "retyped"}, run)
            agent._execute_tool("assess_fit", {"signals": RETYPED}, run)
            agent._execute_tool("suggest_cv_improvements", {"signals": RETYPED, "assess_fit_reasoning": {"gaps": ["made up"]}}, run)

        extract.assert_called_once_with("posting", agent.client)
        self.assertEqual(assess.call_args.args[0], REAL)
        self.assertEqual(assess.call_args.kwargs["posting_text"], "posting")
        suggest.assert_called_once_with(REAL, {"gaps": []})


if __name__ == "__main__":
    unittest.main()
