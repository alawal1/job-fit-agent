# skills/assess_fit.py
"""
Soft-judgment tool: apply / borderline / skip + confidence + structured reasoning.

Called only after check_hard_filters returns passed=true.
Can be called twice per analysis: once without company_context, once with (if borderline).
"""
import json

ASSESS_PROMPT = """You are evaluating whether a job posting is a good fit for a candidate.
Your job is to be honest, not encouraging. A false "apply" wastes the candidate's time.

Return a verdict: apply, borderline, or skip.

Decision rules — apply these in order:

1. Identify the MUST-HAVES: the job signals' required_skills plus years of
   experience, seniority level, language and location. The job signals'
   preferred_skills are NICE-TO-HAVES: they can NEVER be must-haves or hard
   blockers. A missing nice-to-have may lower confidence or turn apply into
   borderline, but never causes skip on its own.

2. For each must-have, state whether the candidate meets it based on evidence
   ANYWHERE in the profile: CV, experience, projects, skills (including
   "Currently Building"), education and positioning. Read all of it before
   calling something missing (e.g. building AI agents IS hands-on experience
   with AI tools). "Coursework" or "in progress" is NOT the same as
   "experience with." If a requirement is probably met but just not stated
   in the profile (e.g. a common trait or tool), put it in open_questions,
   not gaps. gaps are only for things the profile shows are missing.

3. verdict = apply ONLY IF:
   - The candidate meets every must-have, OR
   - The candidate misses at most one must-have AND has an unusually strong
     compensating strength that the posting explicitly values.

4. verdict = skip IF (and only if one of these holds — nice-to-haves never count):
   - The candidate misses two or more must-haves, OR
   - Any single must-have is a hard blocker (wrong seniority, wrong domain,
     required years far exceed candidate's, a required tool/domain experience
     entirely absent), OR
   - The role's core function is something the candidate has no evidence of doing.

5. verdict = borderline ONLY IF you can name specific open_questions whose
   answers would flip apply↔skip. Do not use it as a hedge.

Seniority check: compare the posting's expected seniority to the candidate's
actual experience. If the role expects the candidate to advise, lead, or
out-level people more senior than them, that is a must-have miss.
"""

ASSESS_PROMPT_TAIL = """

RETURN JSON with this exact shape:
{
  "verdict": "apply" | "borderline" | "skip",
  "confidence": "high" | "medium" | "low",
  "reasoning": {
    "strengths": ["2-5 concrete matches between posting and profile"],
    "gaps": ["0-5 REQUIRED items the profile shows are missing (prefix nice-to-haves with 'Nice-to-have:')"],
    "open_questions": ["Empty if verdict is high-confidence apply/skip. Non-empty for borderline."],
    "reason": "A brief explanation for the verdict, especially why a skip recommendation was made."
  }
}

Return ONLY the JSON object. No preamble."""
def assess_fit(signals: dict, profile: dict, client, company_context: dict | None = None) -> dict:
    """
    Evaluate fit. Returns verdict + confidence + reasoning + enrichment_used flag.
    """
    # Load detailed profile context
    profile_context = ""
    profile_files = ["cv.md", "experience.md", "projects.md", "skills.md", "education.md", "positioning.md"]
    
    for filename in profile_files:
        filepath = f"data/{filename}"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                profile_context += f"\n## {filename.replace('.md', '').title()}\n"
                profile_context += f.read()
                profile_context += "\n"
        except FileNotFoundError:
            continue
    
    if not profile_context:
        profile_context = "(No detailed profile files found)"
    
    prompt = (
        ASSESS_PROMPT
        + json.dumps(profile, indent=2)
        + "\n\nDETAILED CANDIDATE PROFILE:\n---"
        + profile_context
        + "---"
        + "\n\nJOB SIGNALS:\n"
        + json.dumps(signals, indent=2)
    )

    if company_context is not None:
        prompt += "\n\nCOMPANY CONTEXT (from prior search):\n" + json.dumps(company_context, indent=2)

    prompt += ASSESS_PROMPT_TAIL

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    try:
        result = json.loads(response.choices[0].message.content)
        result["enrichment_used"] = company_context is not None
        return result
    except json.JSONDecodeError as e:
        return {
            "verdict": "skip",
            "confidence": "low",
            "reasoning": {"strengths": [], "gaps": [], "open_questions": []},
            "enrichment_used": company_context is not None,
            "error": f"Failed to parse LLM response: {e}",
        }