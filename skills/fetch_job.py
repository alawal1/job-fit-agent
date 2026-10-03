"""Fetch utilities for job postings.

Job boards with a public posting API are read through that API (the HTML
pages render with JavaScript). Everything else falls back to fetching the
HTML and extracting the visible text. A fetch that yields no usable posting
raises FetchError instead of returning junk text.
"""

import html
import re

from bs4 import BeautifulSoup
from requests import RequestException, get

MIN_CHARS = 300
FAILURE_PHRASES = ["enable javascript", "javascript is required", "javascript must be enabled"]


class FetchError(RuntimeError):
    """The posting text could not be retrieved."""


def _html_to_text(markup: str) -> str:
    return BeautifulSoup(markup, "html.parser").get_text(separator="\n", strip=True)


def _ashby(data: dict, m: re.Match) -> str:
    for job in data.get("jobs", []):
        if job.get("id") == m["id"]:
            return f"{job.get('title', '')}\n{job.get('location', '')}\n\n{job.get('descriptionPlain', '')}"
    raise FetchError(f"Job {m['id']} not found on the Ashby board '{m['company']}' (filled or unlisted?)")


def _greenhouse(data: dict, m: re.Match) -> str:
    location = (data.get("location") or {}).get("name", "")
    return f"{data.get('title', '')}\n{location}\n\n{_html_to_text(html.unescape(data.get('content', '')))}"


def _lever(data: dict, m: re.Match) -> str:
    parts = [data.get("text", ""), (data.get("categories") or {}).get("location", ""), data.get("descriptionPlain", "")]
    for section in data.get("lists", []):
        parts += [section.get("text", ""), _html_to_text(section.get("content", ""))]
    parts.append(data.get("additionalPlain", ""))
    return "\n\n".join(p for p in parts if p)


# Job boards with public posting APIs: (posting URL pattern, API URL template, text extractor).
# To support another board, add one line here.
JOB_BOARD_APIS = [
    (r"jobs\.ashbyhq\.com/(?P<company>[^/?#]+)/(?P<id>[0-9a-f-]{36})",
     "https://api.ashbyhq.com/posting-api/job-board/{company}", _ashby),
    (r"job-boards(?:\.eu)?\.greenhouse\.io/(?P<company>[^/?#]+)/jobs/(?P<id>\d+)",
     "https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}", _greenhouse),
    (r"jobs\.lever\.co/(?P<company>[^/?#]+)/(?P<id>[0-9a-f-]{36})",
     "https://api.lever.co/v0/postings/{company}/{id}", _lever),
]


def _get(url: str):
    try:
        response = get(url, timeout=10)
        response.raise_for_status()
        return response
    except RequestException as exc:
        raise FetchError(f"Failed to fetch {url}: {exc}") from exc


def _fetch_text(url: str) -> str:
    for pattern, api_template, extract in JOB_BOARD_APIS:
        m = re.search(pattern, url)
        if m:
            return extract(_get(api_template.format(**m.groupdict())).json(), m)

    soup = BeautifulSoup(_get(url).text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def fetch_job_posting(url: str) -> str:
    """Return the posting text (max 6000 chars) or raise FetchError."""
    text = _fetch_text(url).strip()
    lowered = text.lower()
    if len(text) < MIN_CHARS or any(p in lowered for p in FAILURE_PHRASES):
        raise FetchError(
            f"Could not read a job posting from {url} (got {len(text)} chars: {text[:80]!r}). "
            "The page probably needs JavaScript or blocks automated access. "
            "Paste the posting text instead: python agent.py --text posting.txt --url <link>"
        )
    return text[:6000]
