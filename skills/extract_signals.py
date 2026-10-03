# skills/extract_signals.py
"""
Extracts triage-relevant signals from a job posting.

This is an LLM-backed tool — it makes one OpenAI call with a tight prompt
to pull out only the fields needed for triage decisions (not the full
requirements list).
"""
import json
import re

PREFERRED_CUES = re.compile(r"\b(bonus|nice to have|plus|preferred|ideally|meriterande|wünschenswert|von vorteil)\b", re.I)
MANDATORY_CUES = re.compile(r"\b(must|required|you have|you bring)\b", re.I)


EXTRACTION_PROMPT = """You are extracting triage-relevant signals from a job posting.

Extract ONLY the following fields. Do not extract the full requirements list.

Return a JSON object with these exact keys:
- job_title: string
- company_name: string
- location: string (as written in the posting, e.g. "Stockholm, Sweden (Hybrid)")
- required_languages: array of objects with keys {language, level, required_or_preferred}
    - level must be one of: "basic", "conversational", "fluent", "native", "unspecified"
    - required_or_preferred must be one of: "required", "preferred"
    - Only include languages EXPLICITLY mentioned. Do not assume English.
    - Always use the English name for the language (e.g. "German" not "Deutsch", "French" not "Français", "Swedish" not "Svenska").
    - If level is not stated, use "unspecified".
    - "must have", "required" → required; "nice to have", "preferred", "plus" → preferred
- seniority_indicators: object with keys {title_level, years_experience_required, role_context_snippet}
    - title_level: the seniority word in the title (e.g. "Junior", "Senior", "Associate"), or "unspecified"
    - years_experience_required: as written (e.g. "3+ years", "unspecified")
    - role_context_snippet: 1-2 sentences from the posting describing role seniority context
- Sorting rule for requirements: go through every requirement the posting lists.
  If it carries an optional cue (see preferred_skills) → preferred_skills.
  Otherwise → required_skills. Traits are requirements too.
- required_skills: array of strings, up to 8. Things the posting makes MANDATORY,
  using clearly mandatory wording: "must", "required", "you have", "you bring",
  or a "What we're looking for" profile. Include specific tools, domain experience
  or credentials stated this way, AND core-profile traits the posting frames as who
  it is looking for (e.g. "recently graduated", "analytical problem solver",
  "clear communicator"). Every item in a "What we're looking for" / "About you" /
  "Requirements" list WITHOUT an optional cue is required. A tool merely named in a
  tech-stack description is NOT required.
- preferred_skills: array of strings, up to 6. Anything marked as optional:
  "bonus", "nice to have", "a plus", "a big plus", "preferred", "ideally",
  "familiarity with", "exposure to", "meriterande" (Swedish), "wünschenswert" or
  "von Vorteil" (German). These NEVER go in required_skills, even if they name
  specific tools.
- soft_skills: array of strings, up to 6. Interpersonal or working-style traits
  named in the posting. Examples: "communication", "presentation", "teaching",
  "mentoring", "collaboration", "organization", "ownership". Core-profile traits
  that are already in required_skills may be repeated here.
- role_vocabulary: array of up to 8 short phrases quoted verbatim from the posting
  that describe a general activity the person will do or own (not the company's
  own product, system or tool names) (e.g. "stakeholder reporting",
  "own the onboarding process"). Used to tailor the CV in the posting's own words.
- extraction_confidence: "high" | "medium" | "low"
    - Set to "low" if the posting was vague, fragmentary, or missing key triage info.

Return ONLY the JSON object. No preamble, no code fences, no commentary.

Job posting text:

"""


def extract_job_signals(job_text: str, client) -> dict:
    """
    Extract triage-relevant signals from job posting text.

    Args:
        job_text: Full text of the job posting, as returned by fetch_job_posting.
        client: OpenAI client instance.

    Returns:
        dict with keys: job_title, company_name, location, required_languages,
        seniority_indicators, key_skills_mentioned, extraction_confidence.

    Raises:
        ValueError: If the LLM response cannot be parsed as JSON.
    """
    if not job_text or len(job_text.strip()) < 150:
        # Don't spend an LLM call on text that's clearly insufficient.
        return {
            "job_title": "",
            "company_name": "",
            "location": "",
            "required_languages": [],
            "seniority_indicators": {
                "title_level": "unspecified",
                "years_experience_required": "unspecified",
                "role_context_snippet": "",
            },
            "required_skills": [],
            "preferred_skills": [],
            "soft_skills": [],
            "extraction_confidence": "low",
        }
    # print("[EXTRACT] calling LLM", flush=True)
    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT + "\n\nJob posting text:\n---\n" + job_text + "\n---"}],
        response_format={"type": "json_object"},
    )
    # print("[EXTRACT] LLM returned", flush=True)

    content = response.choices[0].message.content
    try:
        signals = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"extract_job_signals: could not parse LLM response as JSON: {e}\nResponse: {content}")
    return _demote_preferred(signals, job_text)


def _segments(job_text: str, cue: re.Pattern) -> list[str]:
    """Posting snippets carrying a cue. A short label line ("Bonus", "Nice to have:") also covers the next line."""
    # ponytail: covers "Bonus: X" and "Bonus\n: X" layouts; a multi-item list under one "Nice to have:" header is left to the prompt
    lines = [l.strip() for l in job_text.splitlines() if l.strip()]
    return [
        line + (" " + lines[i + 1] if len(line.split()) <= 3 and i + 1 < len(lines) else "")
        for i, line in enumerate(lines) if cue.search(line)
    ]


def _mentions(segment: str, skill: str) -> bool:
    words = [w for w in re.findall(r"\w+", skill.lower()) if len(w) > 2]
    return bool(words) and sum(w in segment.lower() for w in words) / len(words) >= 0.6


def _demote_preferred(signals: dict, job_text: str) -> dict:
    """Move required skills that the posting only mentions next to bonus wording into preferred_skills."""
    preferred = _segments(job_text, PREFERRED_CUES)
    mandatory = [s for s in _segments(job_text, MANDATORY_CUES) if not PREFERRED_CUES.search(s)]
    required = signals.get("required_skills") or []
    demoted = [
        skill for skill in required
        if any(_mentions(s, skill) for s in preferred) and not any(_mentions(s, skill) for s in mandatory)
    ]
    signals["required_skills"] = [s for s in required if s not in demoted]
    signals["preferred_skills"] = (signals.get("preferred_skills") or []) + demoted
    return signals