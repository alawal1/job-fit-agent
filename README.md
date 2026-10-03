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

```bash
pip install fastapi uvicorn openai python-dotenv requests beautifulsoup4
echo "OPENAI_API_KEY=sk-..." > .env
uvicorn backend:app --reload
```

Then open `http://localhost:8000`.

CLI usage:
```bash
python agent.py "https://example.com/job-posting"
```

If a posting can't be fetched (JavaScript-only page, blocked site), save its text to a file and pass it directly:
```bash
python agent.py --text posting.txt --url "https://example.com/job-posting"
```
With `--text`, the file is what gets judged; `--url` is optional and only included in the output as the link. A failed fetch never produces a verdict — the agent exits with an error telling you to use `--text`.

Batch mode — judge every job in a queue file:
```bash
python agent.py --queue jobs/queue.md
```
Queue format, one block per job (`text` is optional, relative to the queue file; if given it is used instead of fetching the url):
```markdown
## Legora — Legal Engineering Operations Associate
- url: https://jobs.ashbyhq.com/legora/3c75574c-...
- text: postings/legora.txt
```
Results go to `<queue-name>-results.md` next to the queue (e.g. `jobs/queue-results.md`): a summary line at the top (`2 apply · 1 borderline · 3 skip · 1 failed`), then one block per job with url, verdict, confidence, strengths, gaps, open questions and reason. One failing job doesn't stop the batch. Re-running skips jobs already in the results file (matched by url); a failed job is retried once on the next run and then left as failed. When done, a macOS notification shows "Job-fit: x apply, y borderline".

Tests (offline, no API key needed):
```bash
python -m unittest discover tests
```

Evaluation:
```bash
python eval_runner.py
```
## Project structure

```
v2/
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
├── batch.py              # --queue batch mode
└── eval_runner.py        # Eval against manual scoring
```

## Evaluation

Agent evaluated against manually-scored job postings. Primary metric: agreement with my triage decisions.

**Current:** 80% agreement on 5 fetchable URLs (small eval set, v2 alpha).

Disagreements traced to profile miscalibration (overly optimistic manual scoring vs. stated hard filters). Agent held to stricter-but-principled verdicts.

## Known limitations

- Ashby, Greenhouse and Lever postings are read through their public posting APIs (see `JOB_BOARD_APIS` in `skills/fetch_job.py` to add more boards)
- Workday, LinkedIn, some careers portals block automated fetching → use `--text` on the CLI or the paste fallback in the UI
- Company context uses training knowledge (no web search) with eval-triggered upgrade path planned

