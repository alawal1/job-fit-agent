"""Batch mode: judge every job in a queue file and write <queue-name>-results.md next to it.

Queue format (one block per job):
    ## <company> — <title>
    - url: <link>
    - text: <path to .txt with the posting text, relative to the queue file>   (optional)

Jobs already in the results file are skipped. A failed job is retried once on
the next run; if it fails again it stays failed.
"""

import re
import subprocess
import sys
from pathlib import Path

import agent

VERDICTS = ["apply", "borderline", "skip", "failed"]
MAX_ATTEMPTS = 2  # first try + one retry on the next run


def _blocks(markdown: str):
    """Yield (heading, fields, raw_block) for each '## ' block."""
    for raw in re.split(r"^(?=## )", markdown, flags=re.M):
        if raw.startswith("## "):
            heading = raw.splitlines()[0][3:].strip()
            fields = {k: v.strip() for k, v in re.findall(r"^- ([\w ]+): (.*)$", raw, flags=re.M)}
            yield heading, fields, raw.rstrip()


def _one_line(value) -> str:
    return " ".join(str(value).split())


def _judge(fields: dict, base_dir: Path) -> dict:
    if fields.get("text"):
        text = (base_dir / fields["text"]).read_text(encoding="utf-8").strip()
        result = agent.run_agent_v2_from_text(text)
    elif fields.get("url"):
        result = agent.run_agent_v2(fields["url"])
    else:
        raise ValueError("job has neither url nor text")
    if result.get("verdict") not in ("apply", "borderline", "skip"):
        raise RuntimeError(result.get("error") or "agent returned no verdict")
    return result


def _format(heading: str, url, result=None, error=None, attempts=1) -> str:
    lines = [f"## {heading}", f"- url: {url or ''}"]
    if error:
        return "\n".join(lines + ["- verdict: failed", f"- attempts: {attempts}", f"- error: {_one_line(error)}"])
    reasoning = result.get("reasoning") or {}
    lines += [f"- verdict: {result['verdict']}", f"- confidence: {result.get('confidence', '')}"]
    for label, key in [("strengths", "strengths"), ("gaps", "gaps"), ("open questions", "open_questions")]:
        lines.append(f"- {label}:")
        lines += [f"  - {_one_line(item)}" for item in reasoning.get(key, [])]
    lines.append(f"- reason: {_one_line(reasoning.get('reason', ''))}")
    return "\n".join(lines)


def _notify(message: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{message}"'], check=False)


def run_queue(queue_path: str) -> dict:
    queue = Path(queue_path)
    out = queue.with_name(f"{queue.stem}-results.md")

    previous = {}
    if out.exists():
        for heading, fields, raw in _blocks(out.read_text(encoding="utf-8")):
            previous[fields.get("url") or heading] = (fields, raw)

    blocks = []
    for heading, fields, _ in _blocks(queue.read_text(encoding="utf-8")):
        old_fields, old_raw = previous.pop(fields.get("url") or heading, ({}, None))
        attempts = int(old_fields.get("attempts", 0))
        if old_raw and (old_fields.get("verdict") != "failed" or attempts >= MAX_ATTEMPTS):
            blocks.append(old_raw)
            continue
        print(f"[BATCH] judging: {heading}", flush=True)
        try:
            blocks.append(_format(heading, fields.get("url"), _judge(fields, queue.parent)))
        except Exception as exc:
            print(f"[BATCH] failed: {heading}: {exc}", flush=True)
            blocks.append(_format(heading, fields.get("url"), error=f"{type(exc).__name__}: {exc}", attempts=attempts + 1))
    blocks += [raw for _, raw in previous.values()]  # keep results for jobs no longer in the queue

    counts = {v: 0 for v in VERDICTS}
    for block in blocks:
        m = re.search(r"^- verdict: (\w+)", block, flags=re.M)
        if m and m[1] in counts:
            counts[m[1]] += 1
    summary = " · ".join(f"{counts[v]} {v}" for v in VERDICTS)
    out.write_text(f"# Job-fit results\n\n{summary}\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")

    print(f"[BATCH] {summary} → {out}", flush=True)
    _notify(f"Job-fit: {counts['apply']} apply, {counts['borderline']} borderline")
    return counts
