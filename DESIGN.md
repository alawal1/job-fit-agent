# Job Triage Agent — Design Overview

## Goal
Triage agent: decides apply / borderline / skip for job postings.

## Architecture
Standard OpenAI tool-calling loop. Max 8 iterations.
5 tools, agent chooses sequence:
- fetch_job_posting — existing
- extract_job_signals — LLM extraction
- check_hard_filters — hybrid (deterministic languages + LLM seniority)
- assess_fit — LLM judgment, returns verdict + confidence + structured reasoning
- search_company_context — LLM-only, called only on borderline cases

## Key design principles
- Tool descriptions encode orchestration (when to call, when NOT to call)
- Deterministic where rules are clear, LLM where language understanding matters
- State flows through tools as structured data, not agent memory
- `borderline` verdict must carry open_questions (prevents hedging)

## Debugging log
Four bug categories hit during v2 build:
1. Shell backgrounding URLs with `&` → always quote URLs
2. Agent skipping tool → system prompt too loose, tightened to required workflow
3. Silent exception swallower in _execute_tool wrapper → added [TOOL ERROR] logging
4. Unescaped `{...}` in prompt template broke .format() → switched to string concat

## Fetching: API first, then HTML, never empty
Many job boards (Ashby, Greenhouse, Lever) render postings with JavaScript, so a plain HTTP fetch returns a shell page ("You need to enable JavaScript to run this app.") and the agent ended up judging an empty posting with a confident-looking skip. These boards also publish public, unauthenticated posting APIs that return the same description as structured data, so `fetch_job_posting` checks the URL against one table of board patterns (`JOB_BOARD_APIS`) and calls the API when one matches. This is more reliable than scraping HTML, needs no headless browser, and reads only what the board publishes for job aggregators. For every other site it falls back to HTML. Either way, text under 300 characters or containing "enable JavaScript" raises `FetchError`. The run stops with that error instead of producing a verdict, and the user can supply the text with `--text`.

## Known limitations

- **Workday and LinkedIn URLs cannot be fetched programmatically.** These sites render job content via JavaScript and block simple HTTP fetching. `fetch_job_posting` raises `FetchError` for them instead of passing on empty text, and the run ends with an error rather than a verdict. Workaround: paste the posting text in the UI, or run `python agent.py --text posting.txt --url <link>`.
