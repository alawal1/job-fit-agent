# skills/extract_signals.py
"""
Extracts triage-relevant signals from a job posting.

This is an LLM-backed tool — it makes one OpenAI call with a tight prompt
to pull out only the fields needed for triage decisions (not the full
requirements list).
"""
import json


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
- required_skills: array of strings, up to 8. HARD requirements only — specific
  tools, technologies, named platforms, domain experience, or credentials the
  posting treats as essential. Examples: "BigQuery", "Snowflake", "dbt", "SQL",
  "5+ years in analytics", "Python". Signals: "must have", "required", "you have
  experience with", "proven track record", or a tool named as core to the role.
  EXCLUDE anything interpersonal or behavioral, even if it is framed as required.
- preferred_skills: array of strings, up to 6. Hard skills the posting would like
  but does not require. Signals: "nice to have", "a plus", "bonus", "familiarity
  with", "exposure to". EXCLUDE soft skills.
- soft_skills: array of strings, up to 6. Interpersonal or working-style traits
  named in the posting. Examples: "communication", "presentation", "teaching",
  "mentoring", "collaboration", "organization", "ownership". If the posting
  describes a behavior or interpersonal expectation, it goes here — even if the
  posting frames it as essential.
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
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"extract_job_signals: could not parse LLM response as JSON: {e}\nResponse: {content}")