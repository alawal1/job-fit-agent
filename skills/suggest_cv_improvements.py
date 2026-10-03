"""
CV improvement suggestions tool.

Given job signals, assess_fit reasoning, the CV and the profile files in data/,
returns line-level edits to cv.md: keep / rewrite / remove / add, plus a
tailored summary line. Suggestions that don't quote cv.md exactly, or don't
name a data/ file as evidence, are dropped and listed under "dropped".
"""
import json

EVIDENCE_FILES = ["experience.md", "projects.md", "skills.md", "education.md"]
LIMITS = {"keep": 5, "rewrite": 5, "remove": 3, "add": 3}


def _norm(line: str) -> str:
    """Compare CV lines ignoring bullet dashes, curly quotes and whitespace."""
    return " ".join(line.replace("’", "'").split()).strip("–- ")


def _validate(result: dict, cv_text: str) -> dict:
    cv_lines = {_norm(line) for line in cv_text.splitlines() if line.lstrip().startswith("–")}
    dropped = []
    for key, limit in LIMITS.items():
        kept = []
        for item in result.get(key) or []:
            if key != "add" and _norm(item.get("cv_line", "")) not in cv_lines:
                dropped.append({**item, "list": key, "problem": "cv_line not found in cv.md"})
            elif key in ("rewrite", "add") and not any(f in item.get("evidence", "") for f in EVIDENCE_FILES):
                dropped.append({**item, "list": key, "problem": "no data/ file named as evidence"})
            else:
                kept.append(item)
        result[key] = kept[:limit]
    result["dropped"] = dropped
    result["readable"] = (
        [f"SUMMARY: {result.get('summary_line', '')}"]
        + [f"REWRITE: {i['cv_line']} → {i.get('new_line', '')}" for i in result["rewrite"]]
        + [f"ADD ({i.get('section', '')}): {i.get('new_line', '')} [evidence: {i['evidence']}]" for i in result["add"]]
        + [f"REMOVE: {i['cv_line']} ({i.get('why', '')})" for i in result["remove"]]
        + [f"KEEP: {i['cv_line']}" for i in result["keep"]]
    )
    return result


def suggest_cv_improvements(signals: dict, assess_fit_reasoning: dict, cv_path: str = "data/cv.md") -> dict:
    """
    Generate line-level CV edits for a specific job.

    Args:
        signals: Job signals from extract_job_signals
        assess_fit_reasoning: The reasoning dict from assess_fit (strengths, gaps, open_questions)
        cv_path: Path to CV markdown file

    Returns:
        {"keep", "rewrite", "remove", "add", "summary_line", "dropped", "readable"}
    """
    try:
        with open(cv_path, "r", encoding="utf-8") as f:
            cv_text = f.read()
    except FileNotFoundError:
        return {"error": f"CV file not found at {cv_path}"}

    evidence_text = ""
    for filename in EVIDENCE_FILES:
        try:
            with open(f"data/{filename}", "r", encoding="utf-8") as f:
                evidence_text += f"\n## {filename}\n{f.read()}\n"
        except FileNotFoundError:
            continue

    prompt = f"""You are a CV coach. Suggest concrete, line-level edits to the candidate's CV for this specific job.

Job signals:
{json.dumps(signals, indent=2)}

Fit assessment (already done):
Strengths: {assess_fit_reasoning.get('strengths', [])}
Gaps: {assess_fit_reasoning.get('gaps', [])}
Open questions: {assess_fit_reasoning.get('open_questions', [])}

Candidate's CV (cv.md):
---
{cv_text}
---

Evidence files (the ONLY facts you may use for new or rewritten lines):
---
{evidence_text}
---

Rules:
- "cv_line" must quote one existing CV bullet (a line starting with "–") EXACTLY, character for character, without the leading dash. Job titles, headings and skills rows are not bullets.
- Never invent experience, numbers, tools or claims (e.g. do not call something "AI-driven" unless the evidence says so). Every rewritten or added line must be backed by an evidence file; name the file where that fact is actually stated in "evidence" (e.g. "skills.md").
- Use the posting's own vocabulary (the job signals' role_vocabulary) ONLY where it describes the same activity the evidence describes (e.g. a knowledge platform the candidate maintained may be called a "knowledge base"). Never attach the employer's products, systems or responsibilities to the candidate's past work.
- Look through ALL evidence files, including projects the candidate is currently building, for the strongest matches to the job's requirements.
- Every new line starts with a strong verb, states a concrete result or scope where the evidence supports it, and stays under 25 words.
- At most 5 rewrites, 3 removals, 3 additions and 5 keeps, each list ranked by impact for this job.
- remove = lines that are irrelevant or dilute focus for this role.

Return ONLY valid JSON with no preamble:
{{
  "keep": [{{"cv_line": "...", "why": "..."}}],
  "rewrite": [{{"cv_line": "...", "new_line": "...", "job_requirement_addressed": "...", "evidence": "...", "why": "..."}}],
  "remove": [{{"cv_line": "...", "why": "..."}}],
  "add": [{{"section": "Experience|Projects|Skills|...", "new_line": "...", "evidence": "...", "job_requirement_addressed": "..."}}],
  "summary_line": "Tailored 1-2 sentence profile summary for this job"
}}
"""

    # Use same OpenAI client pattern as other tools
    from openai import OpenAI
    client = OpenAI()

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return _validate(json.loads(response.choices[0].message.content), cv_text)
    finally:
        client.close()
