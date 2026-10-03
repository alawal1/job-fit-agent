"""Offline tests for fetch_job_posting. Run: python -m unittest discover tests"""

import unittest
from unittest.mock import MagicMock, patch

from skills.fetch_job import FetchError, fetch_job_posting

DESCRIPTION = "We are looking for an analyst to join our team in Stockholm. " * 10


def fake_response(json_data=None, text=""):
    response = MagicMock()
    response.json.return_value = json_data
    response.text = text
    return response


class FetchJobPostingTest(unittest.TestCase):
    @patch("skills.fetch_job.get")
    def test_ashby_uses_posting_api_and_picks_job_by_id(self, mock_get):
        job_id = "3c75574c-f213-4e41-a172-ac08c85ed68e"
        mock_get.return_value = fake_response({"jobs": [
            {"id": "00000000-0000-0000-0000-000000000000", "title": "Other", "descriptionPlain": "wrong job"},
            {"id": job_id, "title": "Analyst", "location": "Stockholm", "descriptionPlain": DESCRIPTION},
        ]})

        text = fetch_job_posting(f"https://jobs.ashbyhq.com/legora/{job_id}")

        mock_get.assert_called_once_with("https://api.ashbyhq.com/posting-api/job-board/legora", timeout=10)
        self.assertIn("Analyst", text)
        self.assertIn("join our team", text)
        self.assertNotIn("wrong job", text)

    @patch("skills.fetch_job.get")
    def test_greenhouse_uses_boards_api_and_strips_html(self, mock_get):
        escaped_html = "&lt;p&gt;" + DESCRIPTION + "&lt;/p&gt;"
        mock_get.return_value = fake_response({"title": "Analyst", "location": {"name": "Berlin"}, "content": escaped_html})

        text = fetch_job_posting("https://job-boards.eu.greenhouse.io/acme/jobs/4567")

        mock_get.assert_called_once_with("https://boards-api.greenhouse.io/v1/boards/acme/jobs/4567", timeout=10)
        self.assertIn("join our team", text)
        self.assertNotIn("<p>", text)

    @patch("skills.fetch_job.get")
    def test_javascript_only_page_fails_clearly(self, mock_get):
        mock_get.return_value = fake_response(
            text="<html><body><noscript>You need to enable JavaScript to run this app.</noscript></body></html>"
        )

        with self.assertRaises(FetchError) as ctx:
            fetch_job_posting("https://careers.example.com/job/123")
        self.assertIn("--text", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
