# Job Fit Agent (v2)

An agentic job-posting tool. Given a job URL, it decides whether the role is worth applying to — returning `apply`, `borderline`, or `skip` with structured reasoning.

Built as a portfolio project to demonstrate agent design: tool definition, orchestration via tool descriptions, and evaluation against manual ground truth.

## What it does

1. Fetches a job posting from a URL
2. Extracts triage-relevant signals (title, company, location, languages, seniority)
3. Applies hard filters (language match + LLM-judged seniority fit)
4. If filters pass, assesses overall fit against the candidate profile
5. Returns: verdict (apply/borderline/skip), confidence (high/medium/low) strengths, gaps

The agent decides the tool sequence itself — it skips extraction on dead postings, short-circuits on failed filters, and returns early when a decision is clear.

## Architecture

Standard OpenAI tool-calling loop. Max 8 iterations. No framework (no LangChain etc.) — pure Python + OpenAI SDK.

**Four tools:**
- `fetch_job_posting` — HTTP fetch + HTML cleanup
- `extract_job_signals` — LLM extraction of triage-relevant fields
- `check_hard_filters` — deterministic language check + LLM seniority judgment
- `assess_fit` — LLM soft judgment, returns structured verdict + reasoning


See `DESIGN.md` for full design rationale.

## Stack

Python, FastAPI, OpenAI API (tool use + JSON mode), vanilla JS frontend.

## How to run

pip install fastapi uvicorn openai python-dotenv requests beautifulsoup4
echo "OPENAI_API_KEY=sk-..." > .env
uvicorn backend:app --reload


Then open `http://localhost:8000`.

CLI usage:

python agent.py "https://example.com/job-posting"


If a posting can't be fetched (JavaScript-only page, blocked site), save its text to a file and pass it directly:

python agent.py --text posting.txt --url "https://example.com/job-posting"

With `--text`, the file is what gets judged; `--url` is optional and only included in the output as the link. A failed fetch never produces a verdict — the agent exits with an error telling you to use `--text`.

Batch mode — judge every job in a queue file:

python agent.py --queue jobs/queue.md

Tests (offline, no API key needed):

python -m unittest discover tests

## Evaluation
python eval_runner.py

## Project structure

├── agent.py              # Main loop + tool definitions
├── backend.py            # FastAPI server
├── index.html            # Web UI
├── skills/               # Tool implementations
│   ├── fetch_job.py
│   ├── extract_signals.py
│   ├── check_filters.py
│   └── assess_fit.py
├── data/
│   ├── profile.json      # Candidate profile (hard filters + soft signals)
│   └── eval_set.csv      # Ground-truth verdicts for evaluation
└── eval_runner.py        # Eval against manual scoring


## Evaluation

Agent evaluated against manually-scored job postings. Primary metric: agreement with my decisions.

## Known limitations

- Workday, LinkedIn, some careers portals block automated fetching → UI supports manual paste fallback
- Company context uses training knowledge (no web search) with eval-triggered upgrade path planned

