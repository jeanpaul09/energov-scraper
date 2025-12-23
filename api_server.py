#!/usr/bin/env python3
"""
EnerGov Attachment API Server

RESTful API for downloading attachments from Miami-Dade EnerGov.
Supports batch downloads and async processing.

Usage:
    python api_server.py

Endpoints:
    GET  /download/{case_id}     - Download all PDFs for a case
    POST /batch                   - Queue multiple case IDs
    GET  /status/{job_id}        - Check batch job status
"""

import asyncio
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn

from playwright.async_api import async_playwright

# Configuration
OUTPUT_DIR = Path("./downloads")
OUTPUT_DIR.mkdir(exist_ok=True)

# Job tracking
jobs: dict[str, dict] = {}


class BatchRequest(BaseModel):
    case_ids: list[str]


class DownloadResult(BaseModel):
    case_id: str
    plan_number: Optional[str]
    total_files: int
    downloaded: int
    duration_seconds: float
    output_path: str
    files: list[str]


async def download_attachments(case_id: str) -> dict:
    """Download all PDF attachments for a case."""
    start = datetime.now()
    
    plan_dir = OUTPUT_DIR / case_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Capture attachments from API
        attachments = []
        async def handle_response(response):
            nonlocal attachments
            if "entityattachments" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    attachments = data.get("Result", {}).get("Attachments", []) or []
                except:
                    pass
        
        page.on("response", handle_response)
        
        url = f"https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/plan/{case_id}?tab=attachments"
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)
        
        # Filter PDFs and dedupe
        pdf_attachments = [a for a in attachments if a.get("FileName", "").lower().endswith(".pdf")]
        seen = set()
        unique_pdfs = []
        for a in pdf_attachments:
            fn = a.get("FileName")
            if fn not in seen:
                seen.add(fn)
                unique_pdfs.append(a)
        
        if not unique_pdfs:
            await browser.close()
            return {"error": "No PDF attachments found", "case_id": case_id}
        
        # Get plan number
        plan_number = None
        for a in unique_pdfs:
            match = re.search(r'Z\d{10}', a.get("FileName", ""))
            if match:
                plan_number = match.group(0)
                break
        
        if plan_number:
            new_dir = OUTPUT_DIR / plan_number
            if new_dir != plan_dir and not new_dir.exists():
                plan_dir.rename(new_dir)
                plan_dir = new_dir
        
        # Download all PDFs
        downloaded = 0
        file_list = []
        
        for att in unique_pdfs:
            fn = att.get("FileName", "")
            safe_name = re.sub(r'[^\w\-_\. ]', '_', fn)
            local_path = plan_dir / safe_name
            
            if local_path.exists():
                downloaded += 1
                file_list.append(safe_name)
                continue
            
            try:
                async with page.expect_download(timeout=10000) as dl_info:
                    escaped = fn.replace('"', '\\"').replace("'", "\\'")
                    await page.evaluate(f'''() => {{
                        for (const a of document.querySelectorAll('a')) {{
                            if (a.textContent.trim() === "{escaped}") {{ a.click(); return; }}
                        }}
                    }}''')
                
                download = await dl_info.value
                await download.save_as(local_path)
                downloaded += 1
                file_list.append(safe_name)
            except:
                pass
        
        await browser.close()
    
    duration = (datetime.now() - start).total_seconds()
    
    result = {
        "case_id": case_id,
        "plan_number": plan_number,
        "total_files": len(unique_pdfs),
        "downloaded": downloaded,
        "duration_seconds": round(duration, 1),
        "output_path": str(plan_dir),
        "files": file_list,
    }
    
    # Save metadata
    with open(plan_dir / "_metadata.json", "w") as f:
        json.dump(result, f, indent=2)
    
    return result


async def process_batch(job_id: str, case_ids: list[str]):
    """Process batch download job."""
    jobs[job_id]["status"] = "processing"
    jobs[job_id]["started_at"] = datetime.now().isoformat()
    
    results = []
    for i, case_id in enumerate(case_ids):
        jobs[job_id]["progress"] = f"{i}/{len(case_ids)}"
        jobs[job_id]["current"] = case_id
        
        try:
            result = await download_attachments(case_id)
            results.append(result)
        except Exception as e:
            results.append({"case_id": case_id, "error": str(e)})
    
    jobs[job_id]["status"] = "completed"
    jobs[job_id]["completed_at"] = datetime.now().isoformat()
    jobs[job_id]["results"] = results
    jobs[job_id]["progress"] = f"{len(case_ids)}/{len(case_ids)}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    print("🚀 EnerGov API Server starting...")
    yield
    print("👋 Server shutting down...")


app = FastAPI(
    title="EnerGov Attachment Downloader API",
    description="Download PDF attachments from Miami-Dade EnerGov plans",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """API info."""
    return {
        "name": "EnerGov Attachment Downloader",
        "version": "1.0.0",
        "endpoints": {
            "GET /download/{case_id}": "Download all PDFs for a case",
            "POST /batch": "Queue multiple case IDs for download",
            "GET /status/{job_id}": "Check batch job status",
            "GET /files/{plan_number}": "List downloaded files",
        }
    }


@app.get("/download/{case_id}")
async def download_case(case_id: str):
    """Download all PDF attachments for a single case."""
    try:
        result = await download_attachments(case_id)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch")
async def create_batch_job(request: BatchRequest, background_tasks: BackgroundTasks):
    """Create a batch download job."""
    job_id = str(uuid.uuid4())[:8]
    
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "case_ids": request.case_ids,
        "total": len(request.case_ids),
        "progress": "0/{}".format(len(request.case_ids)),
    }
    
    background_tasks.add_task(process_batch, job_id, request.case_ids)
    
    return {
        "job_id": job_id,
        "status": "queued",
        "total": len(request.case_ids),
        "check_status": f"/status/{job_id}"
    }


@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get batch job status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/files/{plan_number}")
async def list_files(plan_number: str):
    """List downloaded files for a plan."""
    plan_dir = OUTPUT_DIR / plan_number
    
    if not plan_dir.exists():
        raise HTTPException(status_code=404, detail="Plan not found")
    
    files = [f.name for f in plan_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    
    return {
        "plan_number": plan_number,
        "path": str(plan_dir),
        "file_count": len(files),
        "files": files
    }


@app.get("/files/{plan_number}/{filename}")
async def get_file(plan_number: str, filename: str):
    """Download a specific file."""
    file_path = OUTPUT_DIR / plan_number / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path, filename=filename)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

