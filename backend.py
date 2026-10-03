# backend.py
import os
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from skills.fetch_job import FetchError
from agent import run_agent_v2, run_agent_v2_from_text, calculate_composite_score

app = FastAPI()

BLOCKED_DOMAINS = ["linkedin.com", "workday.com", "myworkdayjobs.com"]


def is_blocked_url(url: str) -> bool:
    return any(d in url.lower() for d in BLOCKED_DOMAINS)


@app.get("/", response_class=FileResponse)
def read_index():
    return FileResponse("index.html")


@app.post("/analyze/v2")
async def analyze_v2(request: Request):
    payload = await request.json()
    url = payload.get("url")
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail={"error": "A valid 'url' field is required."})

    url = url.strip()
    if is_blocked_url(url):
        return JSONResponse(content={"blocked": True, "message": "This site blocks automated fetching. Please paste the job description manually."})

    try:
        result = run_agent_v2(url)
        # print(f"[BACKEND] Returning: {json.dumps(result, indent=2)}", flush=True)
    except FetchError as exc:
        return JSONResponse(content={"blocked": True, "message": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    if result.get("tool_calls_made", 0) == 1 and "empty" in (result.get("final_message") or "").lower():
        return JSONResponse(content={"blocked": True, "message": "Could not fetch content. Please paste the job description manually."})

    return JSONResponse(content=result)


@app.post("/analyze/v2/text")
async def analyze_v2_text(request: Request):
    payload = await request.json()
    job_text = payload.get("job_text")
    if not job_text or not isinstance(job_text, str) or len(job_text.strip()) < 150:
        raise HTTPException(status_code=400, detail={"error": "Please paste a job description of at least 150 characters."})

    try:
        result = run_agent_v2_from_text(job_text.strip())
        # print(f"[BACKEND] Returning: {json.dumps(result, indent=2)}", flush=True)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return JSONResponse(content=result)


@app.post("/analyze/v2/batch")
async def analyze_v2_batch(request: Request):
    payload = await request.json()
    urls = payload.get("urls", [])

    if not isinstance(urls, list):
        raise HTTPException(status_code=400, detail={"error": "A 'urls' array is required."})

    urls = [u.strip() for u in urls if isinstance(u, str) and u.strip()]

    if len(urls) < 2 or len(urls) > 10:
        raise HTTPException(status_code=400, detail={"error": f"Please provide 2-10 URLs. Got {len(urls)}."})

    blocked_urls = [u for u in urls if is_blocked_url(u)]
    if blocked_urls:
        return JSONResponse(
            status_code=400,
            content={"error": f"Some URLs are from blocked domains: {blocked_urls}. Please paste job descriptions manually instead."}
        )

    results = []
    failed_urls = []

    def run_sync(url):
        try:
            return {"url": url, "result": run_agent_v2(url), "error": None}
        except Exception as e:
            return {"url": url, "result": None, "error": str(e)}

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=4) as executor:
        analysis_results = await loop.run_in_executor(
            executor,
            lambda: [run_sync(url) for url in urls]
        )

    for analysis in analysis_results:
        if analysis["error"]:
            failed_urls.append({"url": analysis["url"], "error": analysis["error"]})
        else:
            result = analysis["result"]
            if result.get("tool_calls_made", 0) == 1 and "empty" in (result.get("final_message") or "").lower():
                failed_urls.append({"url": analysis["url"], "error": "Could not fetch content"})
            else:
                result["url"] = analysis["url"]
                result["composite_score"] = calculate_composite_score(result)
                result.pop("cv_recommendations", None)
                results.append(result)

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    return JSONResponse(content={
        "jobs": results,
        "count": len(results),
        "failed_urls": failed_urls
    })


@app.get("/profile")
def profile():
    entries = []
    data_dir = "data"
    if os.path.isdir(data_dir):
        for filename in sorted(os.listdir(data_dir)):
            if filename.endswith(".md") and filename != "cv.md":
                filepath = os.path.join(data_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as file:
                        entries.append({"filename": filename, "content": file.read()})
                except OSError:
                    continue
    return JSONResponse(content={"files": entries})