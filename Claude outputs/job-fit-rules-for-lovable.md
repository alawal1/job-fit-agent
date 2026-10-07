# Job Fit Agent — fit rules (extracted from the Python code)

Source: `job-fit-agent` repo (read-only, nothing changed). Files: `data/profile.json`, `skills/check_filters.py`, `skills/assess_fit.py`, `skills/extract_signals.py`, `skills/fetch_job.py`, `agent.py`.

## 1. Pipeline (agent.py)
1. Fetch the posting.
2. Extract signals (skip if dead link / boilerplate).
3. Hard filters. If any fails → **SKIP**, stop.
4. Assess fit → apply / borderline / skip.
5. If apply or borderline → CV improvement suggestions.

## 2. Fetching (fetch_job.py)
- Ashby, Greenhouse and Lever URLs → use their public posting APIs instead of scraping HTML:
  - `jobs.ashbyhq.com/{company}/{id}` → `https://api.ashbyhq.com/posting-api/job-board/{company}`
  - `job-boards(.eu).greenhouse.io/{company}/jobs/{id}` → `https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{id}`
  - `jobs.lever.co/{company}/{id}` → `https://api.lever.co/v0/postings/{company}/{id}`
- Anything else → fetch HTML, drop script/style/nav/footer, keep text.
- Text under 300 characters or containing "enable JavaScript" → fetch failed. **Never give a verdict on a failed fetch**; ask for pasted text instead.
- Workday and LinkedIn can't be fetched → paste text.
- Cap posting text at 6,000 characters.

## 3. Signal extraction (extract_signals.py)
Extract: job title, company, location, required languages (language in English, level basic/conversational/fluent/native/unspecified, required vs preferred), seniority (title level, years required, 1–2 sentence context), required skills (≤8), preferred skills (≤6), soft skills (≤6), role vocabulary (≤8 verbatim phrases), extraction confidence.
- Only languages explicitly named. Never assume English.
- Optional cues → preferred, never required: "bonus", "nice to have", "a plus", "preferred", "ideally", "familiarity with", "exposure to", "meriterande", "wünschenswert", "von Vorteil".
- Mandatory cues → required: "must", "required", "you have", "you bring", or any item in a "What we're looking for" / "About you" / "Requirements" list without an optional cue. Traits count as requirements.
- A tool merely named in a tech-stack description is NOT required.
- Under 150 characters of text → don't extract, confidence low.

## 4. Hard filters (check_filters.py + profile.json)
**Languages (deterministic):** English fluent, German native, Swedish conversational.
- Only *required* languages gate; preferred are ignored.
- "Unspecified" level counts as fluent.
- Rank: basic < conversational < fluent < native. Candidate level must be ≥ job level, for every required language.
- Language fails → SKIP, don't check seniority.

**Seniority (AI judgment)** against: "Early-career: graduated from a Master's in Strategic Information Systems Management from Stockholm University in July 2026, targeting internships, entry-level, junior, and associate positions. Open to 'Associate Consultant' at consulting firms (typically entry-level). Not open to 'Senior', 'Lead', 'Principal', 'Staff', or 'Manager' roles, or positions requiring 3+ years of post-graduate experience."

## 5. Soft profile (profile.json)
- Work: open to early-career roles across data, AI, consulting, product and project management, and adjacent fields. Strong interest in data/business analysis and insights, AI automation and agent design, digital transformation, consulting, knowledge management, project coordination and management. Also open to communications, PR and creative operations roles using media production and international cooperation background. Prefers a mix of technical and communication/strategic work. Not interested in pure sales, pure design, or deep engineering (production ML / distributed systems).
- Technical skills — intermediate: Python, JavaScript, HTML/CSS, Git, Azure DevOps, Jira, Confluence. Basic: SQL, pandas. Learning: AI agents, LLM tool use, n8n/Zapier, prompt engineering.
- Domain experience: ESG/CSRD reporting; Data & AI consulting (internship); knowledge management; broadcasting/media production; international development / PR.
- Work authorization: EU.
- Locations: Stockholm, Remote-EU, Köln/Cologne, Frankfurt, Germany, Lund, Malmö, Göteborg, Copenhagen, Belgium, Amsterdam, Rotterdam, Brussels. Work model: hybrid, remote, on-site.

## 6. Fit decision (assess_fit.py)
Be honest, not encouraging. A false "apply" wastes time. Apply in order:
1. **Must-haves** = required skills + years of experience + seniority + language + location. Preferred skills are nice-to-haves: never must-haves, never blockers. A missing nice-to-have can lower confidence or turn apply into borderline, never cause skip on its own.
2. For each must-have, look for evidence **anywhere** in the profile (CV, experience, projects, skills incl. "Currently Building", education, positioning). Building AI agents counts as hands-on AI tool experience. "Coursework" / "in progress" ≠ "experience with". Probably met but unstated → open question, not a gap. Check against the full posting wording, not just the short label. Every gap names the requirement as the posting states it + what the profile shows instead ("Required: 3+ years B2B sales; profile shows none."). No contrast to state = not a gap.
3. **APPLY** only if every must-have is met, OR at most one is missed AND there is an unusually strong compensating strength the posting explicitly values.
4. **SKIP** only if: two or more must-haves missed, OR any single hard blocker (wrong seniority, wrong domain, required years far above the candidate's, required tool/domain entirely absent), OR the core function of the role is something with no evidence at all.
5. **BORDERLINE** only if you can name specific open questions whose answers would flip apply ↔ skip. Never a hedge.
- Seniority: if the role expects advising, leading or out-levelling people more senior than the candidate, that's a must-have miss.

**Output:** verdict (apply/borderline/skip), confidence (high/medium/low), strengths (2–5 concrete matches), gaps (0–5 required items missing; nice-to-haves prefixed "Nice-to-have:"), open_questions (empty for high-confidence apply/skip, required for borderline), reason (brief; especially why skip).

## 7. Translated from code to wording
- The 300 / 150 / 6,000 character thresholds and the language ranking are code rules. In Lovable they belong in the server function code, not in the AI prompt.
- Model in the original: gpt-4o, temperature 0, JSON mode. Lovable will use its own AI models; keep the same JSON shapes.
