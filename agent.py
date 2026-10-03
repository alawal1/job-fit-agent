import json
import sys
from openai import OpenAI
from dotenv import load_dotenv

from skills.fetch_job import FetchError, fetch_job_posting
from skills.extract_signals import extract_job_signals
from skills.check_filters import check_hard_filters
from skills.assess_fit import assess_fit
from skills.suggest_cv_improvements import suggest_cv_improvements

load_dotenv()
client = OpenAI()
with open("data/profile.json") as f:
    PROFILE = json.load(f)

MAX_ITERATIONS = 8
MODEL = "gpt-4o"


def calculate_composite_score(result: dict) -> float:
    """
    Generates a composite score (0-100) from verdict, confidence, strengths, and gaps.
    Used for ranking multiple jobs.
    """
    verdict = result.get("verdict", "skip").lower()
    confidence = result.get("confidence", "low").lower()
    reasoning = result.get("reasoning") or {}

    verdict_map = {"apply": 10, "borderline": 5, "skip": 0}
    confidence_map = {"high": 1.0, "medium": 0.67, "low": 0.33}

    verdict_score = verdict_map.get(verdict, 0) * 30
    confidence_score = confidence_map.get(confidence, 0.33) * 20
    strengths_bonus = len(reasoning.get("strengths", [])) * 5
    gaps_penalty = len(reasoning.get("gaps", [])) * 3

    raw_score = verdict_score + confidence_score + strengths_bonus - gaps_penalty
    normalized = max(0, min(100, (raw_score + 50) / 4.5))

    return round(normalized, 1)

# Tool schemas shown to the LLM.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_job_posting",
            "description": (
                "Fetches the text content of a job posting from a URL. "
                "Call this first whenever you are given a URL. Returns plain text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the job posting"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_job_signals",
            "description": (
                "Extracts the specific fields needed to triage a job posting from its full text. "
                "Call this after fetch_job_posting has returned the posting text. "
                "Do not call if the text is under ~150 words, appears truncated, or is mostly "
                "boilerplate (company description, benefits list) without actual role content. "
                "Returns a structured signals object. This tool focuses only on triage-relevant "
                "fields; it does NOT extract the full requirements list."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_text": {
                        "type": "string",
                        "description": "The full text of the job posting, as returned by fetch_job_posting.",
                    },
                },
                "required": ["job_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_hard_filters",
            "description": (
                "Checks whether a job passes the candidate's hard filters (language and seniority). "
                "Call this after extract_job_signals has returned successfully. "
                "You MUST pass the full signals object returned by extract_job_signals as the 'signals' argument. "
                "Do not call this tool without the signals argument. "
                "If this returns passed=false, the triage is complete — return a skip verdict immediately. "
                "Do not call assess_fit when hard filters fail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "signals": {
                        "type": "object",
                        "description": "The signals object returned by extract_job_signals.",
                    },
                },
                "required": ["signals"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assess_fit",
            "description": (
                "Evaluates how well a job matches the candidate's profile. "
                "Call only after check_hard_filters has returned passed=true. "
                "You MUST pass the full signals object as the 'signals' argument. "
                "Returns a verdict (apply/borderline/skip) with confidence and structured reasoning. "
                "If verdict is 'borderline' with non-empty open_questions, you may call this tool "
                "a second time later with a 'company_context' argument (not yet supported — only call once for now)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "signals": {
                        "type": "object",
                        "description": "The signals object returned by extract_job_signals.",
                    },
                },
                "required": ["signals"],
            },
        },
    },{
        "type": "function",
        "function": {
            "name": "suggest_cv_improvements",
            "description": (
                "Suggests CV improvements tailored to a specific job. "
                "Call this ONLY when assess_fit returns verdict='apply' or 'borderline'. "
                "Requires signals object and assess_fit reasoning as arguments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "signals": {
                        "type": "object",
                        "description": "Job signals from extract_job_signals",
                    },
                    "assess_fit_reasoning": {
                        "type": "object",
                        "description": "The reasoning dict from assess_fit output",
                    },
                },
                "required": ["signals", "assess_fit_reasoning"],
            },
        },
    },
]


# Runtime implementations. Tools that need the OpenAI client get it passed in.
def _execute_tool(name: str, args: dict) -> dict:
    print(f"[TOOL CALLED] name={name} args_keys={list(args.keys())}", flush=True)

    if name == "fetch_job_posting":
        text = fetch_job_posting(args["url"])
        result = {"text": text, "length_chars": len(text)}
    elif name == "extract_job_signals":
        result = extract_job_signals(args["job_text"], client)
    elif name == "check_hard_filters":
        if "signals" not in args:
            result = {"error": "Missing 'signals' argument. You must pass the signals object from extract_job_signals."}
        else:
            result = check_hard_filters(args["signals"], PROFILE, client)
    elif name == "assess_fit":
        if "signals" not in args:
            result = {"error": "Missing 'signals' argument. You must pass the signals object from extract_job_signals."}
        else:
            result = assess_fit(args["signals"], PROFILE, client)
    elif name == "suggest_cv_improvements":
        if "signals" not in args or "assess_fit_reasoning" not in args:
            result = {"error": "Missing required arguments. Pass signals and assess_fit_reasoning."}
        else:
            result = suggest_cv_improvements(args["signals"], args["assess_fit_reasoning"])
    else:
        result = {"error": f"Unknown tool: {name}"}

    print(f"[TOOL RESULT] {name} → {json.dumps(result, ensure_ascii=False)[:3000]}", flush=True)
    return result

SYSTEM_PROMPT = """You are a job triage agent. You decide whether a job posting is worth the user applying to: apply, borderline, or skip.

Required workflow:
1. Call fetch_job_posting to get the text.
2. Call extract_job_signals on the text — unless it's a dead link or boilerplate page.
3. Call check_hard_filters on the signals.
4. If check_hard_filters returns passed=false, return verdict SKIP with the failure reasons. Do not call more tools.
5. If check_hard_filters returns passed=true, CALL assess_fit and use its output.
6. If assess_fit returns verdict='apply' or 'borderline', CALL suggest_cv_improvements to provide tailored CV guidance.
7. Return the assess_fit verdict, confidence, reasoning, and CV recommendations (if available) as your final answer.

Do not produce a final answer on a live posting without calling extract_job_signals, check_hard_filters, and assess_fit when filters pass.
After calling suggest_cv_improvements, produce a brief final message and stop."""

def run_agent_v2(url: str) -> dict:
    """
    Run the v2 triage agent on a single job URL.
    Returns structured verdict + reasoning from assess_fit if available.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze this job posting: {url}"},
    ]

    tool_calls_made = 0
    assess_fit_result = None  # Track the last assess_fit output
    last_check_filters_result = None
    cv_recommendations_result = None

    for iteration in range(MAX_ITERATIONS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0,
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message)
        
        if choice.finish_reason == "stop":
            if assess_fit_result:
                return {
                    **assess_fit_result,
                    "cv_recommendations": cv_recommendations_result,  
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                }
            
            # No assess_fit ran — synthesize structured output from final_message
            msg = (message.content or "").strip()
            reason = msg
            if last_check_filters_result is not None and not last_check_filters_result.get("passed", True):
                filter_reasons = [fr.get("reason", "") for fr in last_check_filters_result.get("filter_results", []) if fr.get("reason")]
                if filter_reasons:
                    reason = " ".join(filter_reasons)
            verdict = "skip"  # default
            msg_lower = msg.lower()
            if "apply" in msg_lower and "skip" not in msg_lower:
                verdict = "apply"
            elif "borderline" in msg_lower:
                verdict = "borderline"
            
            return {
                "verdict": verdict,
                "confidence": "high" if any(token in msg_lower for token in ["dead", "filled", "no longer available"]) else "medium",
                "reasoning": {
                    "strengths": [],
                    "gaps": [],
                    "open_questions": [],
                    "reason": reason or "No structured reasoning was available."
                },
                "final_message": message.content,
                "tool_calls_made": tool_calls_made,
                "iterations": iteration + 1,
            }

        if choice.finish_reason == "tool_calls":
            for tool_call in message.tool_calls:
                tool_calls_made += 1
                args = json.loads(tool_call.function.arguments)
                try:
                    result = _execute_tool(tool_call.function.name, args)
                    if tool_call.function.name == "assess_fit" and "verdict" in result:
                        assess_fit_result = result
                    if tool_call.function.name == "check_hard_filters" and "passed" in result:
                        last_check_filters_result = result
                    # Capture CV recommendations  
                    if tool_call.function.name == "suggest_cv_improvements" and "recommendations" in result:
                        cv_recommendations_result = result
                except FetchError:
                    raise  # no posting text → nothing to judge; caller reports the error
                except Exception as e:
                    print(f"[TOOL ERROR] {tool_call.function.name}: {type(e).__name__}: {e}", flush=True)
                    result = {"error": f"{type(e).__name__}: {e}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            continue

        return {
            "final_message": message.content or "",
            "tool_calls_made": tool_calls_made,
            "iterations": iteration + 1,
            "error": f"Unexpected finish_reason: {choice.finish_reason}",
        }

    return {
        "final_message": "",
        "tool_calls_made": tool_calls_made,
        "iterations": MAX_ITERATIONS,
        "error": "Max iterations reached.",
    }
    
def run_agent_v2_from_text(job_text: str) -> dict:
    """
    Run v2 triage agent when job text is provided directly (manual paste).
    Skips fetch_job_posting, starts with extract_job_signals.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"The user provided this job description directly. Analyze it:\n\n{job_text}"},
    ]
    
    tool_calls_made = 0
    assess_fit_result = None
    last_check_filters_result = None
    cv_recommendations_result = None 
    
    for iteration in range(MAX_ITERATIONS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            temperature=0,
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message)
        
        if choice.finish_reason == "stop":
            if assess_fit_result:
                return {
                    **assess_fit_result,
                    "cv_recommendations": cv_recommendations_result,
                    "tool_calls_made": tool_calls_made,
                    "iterations": iteration + 1,
                }
            
            msg = (message.content or "").strip()
            reason = msg
            if last_check_filters_result is not None and not last_check_filters_result.get("passed", True):
                filter_reasons = [fr.get("reason", "") for fr in last_check_filters_result.get("filter_results", []) if fr.get("reason")]
                if filter_reasons:
                    reason = " ".join(filter_reasons)
            verdict = "skip"
            msg_lower = msg.lower()
            if "apply" in msg_lower and "skip" not in msg_lower:
                verdict = "apply"
            elif "borderline" in msg_lower:
                verdict = "borderline"
            
            return {
                "verdict": verdict,
                "confidence": "high" if any(token in msg_lower for token in ["dead", "filled", "no longer available"]) else "medium",
                "reasoning": {
                    "strengths": [],
                    "gaps": [],
                    "open_questions": [],
                    "reason": reason or "No structured reasoning was available."
                },
                "final_message": message.content,
                "tool_calls_made": tool_calls_made,
                "iterations": iteration + 1,
            }
        
        if choice.finish_reason == "tool_calls":
            for tool_call in message.tool_calls:
                tool_calls_made += 1
                
                if tool_call.function.name == "fetch_job_posting":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"error": "Job text already provided by user, no URL to fetch."})
                    })
                    continue
                
                args = json.loads(tool_call.function.arguments)
                try:
                    result = _execute_tool(tool_call.function.name, args)
                    if tool_call.function.name == "assess_fit" and "verdict" in result:
                        assess_fit_result = result
                    if tool_call.function.name == "check_hard_filters" and "passed" in result:
                        last_check_filters_result = result
                    if tool_call.function.name == "suggest_cv_improvements" and "recommendations" in result:
                        cv_recommendations_result = result
                except Exception as e:
                    print(f"[TOOL ERROR] {tool_call.function.name}: {type(e).__name__}: {e}", flush=True)
                    result = {"error": f"{type(e).__name__}: {e}"}
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            continue
        
        return {
            "final_message": message.content or "",
            "tool_calls_made": tool_calls_made,
            "iterations": iteration + 1,
            "error": f"Unexpected finish_reason: {choice.finish_reason}",
        }
    
    return {
        "final_message": "",
        "tool_calls_made": tool_calls_made,
        "iterations": MAX_ITERATIONS,
        "error": "Max iterations reached without natural termination.",
    }
    
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Triage a job posting: apply / borderline / skip.")
    parser.add_argument("url", nargs="?", help="Job posting URL")
    parser.add_argument("--url", dest="link", help="Link to the posting (with --text: only shown, not fetched)")
    parser.add_argument("--text", help="File with the posting text; used instead of fetching the URL")
    args = parser.parse_args()
    url = args.link or args.url
    if not (args.text or url):
        parser.error("give a job URL or --text <file>")

    try:
        if args.text:
            with open(args.text, encoding="utf-8") as f:
                result = run_agent_v2_from_text(f.read().strip())
            if url:
                result["url"] = url
        else:
            result = run_agent_v2(url)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except FetchError as exc:
        print(json.dumps({"error": str(exc), "url": url}, indent=2, ensure_ascii=False))
        sys.exit(1)
    finally:
        client.close()
