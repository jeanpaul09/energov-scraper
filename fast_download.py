#!/usr/bin/env python3
"""
Fast EnerGov Attachment Downloader

Uses direct download URLs from API for parallel downloads.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

OUTPUT_DIR = Path("./downloads")
PARALLEL = 10


async def fast_download(case_id: str, output_dir: Path = OUTPUT_DIR) -> dict:
    """Download all attachments using direct URLs."""
    start = datetime.now()
    
    plan_dir = output_dir / case_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"⚡ Fast Download: {case_id}")
    print(f"{'='*60}")
    
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
        print(f"🌐 Loading...")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)
        
        pdf_attachments = [a for a in attachments if a.get("FileName", "").lower().endswith(".pdf")]
        # Dedupe by filename
        seen = set()
        unique_pdfs = []
        for a in pdf_attachments:
            fn = a.get("FileName")
            if fn not in seen:
                seen.add(fn)
                unique_pdfs.append(a)
        
        print(f"📎 Found {len(unique_pdfs)} unique PDFs")
        
        if not unique_pdfs:
            await browser.close()
            return {"error": "No attachments"}
        
        # Get plan number
        plan_number = None
        for a in unique_pdfs:
            match = re.search(r'Z\d{10}', a.get("FileName", ""))
            if match:
                plan_number = match.group(0)
                break
        
        if plan_number:
            new_dir = output_dir / plan_number
            if new_dir != plan_dir and not new_dir.exists():
                plan_dir.rename(new_dir)
                plan_dir = new_dir
        
        print(f"📂 Output: {plan_dir}")
        
        # Try to download via ThumbnailUrl (direct URL)
        print(f"⬇️  Testing direct download URLs...")
        
        # Test first URL
        test_att = unique_pdfs[0]
        thumb_url = test_att.get("ThumbnailUrl", "")
        
        if thumb_url:
            print(f"   Testing: {thumb_url[:60]}...")
            try:
                test_page = await context.new_page()
                resp = await test_page.goto(thumb_url, wait_until="commit", timeout=10000)
                
                if resp and resp.status == 200:
                    print(f"   ✓ Direct URLs work! Using parallel download...")
                    
                    # Download all using direct URLs in parallel
                    async def download_direct(att, idx):
                        fn = att.get("FileName", "")
                        safe_name = re.sub(r'[^\w\-_\. ]', '_', fn)
                        local_path = plan_dir / safe_name
                        
                        if local_path.exists():
                            return True
                        
                        url = att.get("ThumbnailUrl", "")
                        if not url:
                            return False
                        
                        try:
                            dl_page = await context.new_page()
                            response = await dl_page.goto(url, timeout=30000)
                            if response and response.status == 200:
                                body = await response.body()
                                if len(body) > 100:
                                    local_path.write_bytes(body)
                                    print(f"  ✓ [{idx+1}/{len(unique_pdfs)}] {safe_name[:45]}")
                                    await dl_page.close()
                                    return True
                            await dl_page.close()
                        except Exception as e:
                            pass
                        return False
                    
                    await test_page.close()
                    
                    # Parallel download with semaphore
                    sem = asyncio.Semaphore(PARALLEL)
                    
                    async def bounded_download(att, idx):
                        async with sem:
                            return await download_direct(att, idx)
                    
                    tasks = [bounded_download(a, i) for i, a in enumerate(unique_pdfs)]
                    results = await asyncio.gather(*tasks)
                    downloaded = sum(1 for r in results if r)
                    
                else:
                    print(f"   ✗ Direct URLs blocked (status: {resp.status if resp else 'None'})")
                    downloaded = 0
                    
                await test_page.close()
                
            except Exception as e:
                print(f"   ✗ Direct URLs failed: {e}")
                downloaded = 0
        else:
            downloaded = 0
        
        # Fallback to click-download if direct failed
        if downloaded == 0:
            print(f"⬇️  Using click-to-download (sequential)...")
            downloaded = 0
            
            for i, att in enumerate(unique_pdfs):
                fn = att.get("FileName", "")
                safe_name = re.sub(r'[^\w\-_\. ]', '_', fn)
                local_path = plan_dir / safe_name
                
                if local_path.exists():
                    downloaded += 1
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
                    print(f"  ✓ [{i+1}/{len(unique_pdfs)}] {safe_name[:45]}")
                except:
                    print(f"  ⚠ [{i+1}/{len(unique_pdfs)}] {safe_name[:45]}")
        
        await browser.close()
    
    duration = (datetime.now() - start).total_seconds()
    
    metadata = {
        "case_id": case_id,
        "plan_number": plan_number,
        "downloaded_at": datetime.now().isoformat(),
        "duration_seconds": round(duration, 1),
        "total": len(unique_pdfs),
        "downloaded": downloaded,
        "files": [a.get("FileName") for a in unique_pdfs]
    }
    
    with open(plan_dir / "_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ {downloaded}/{len(unique_pdfs)} PDFs in {duration:.1f}s")
    print(f"📂 {plan_dir}")
    print(f"{'='*60}\n")
    
    return metadata


if __name__ == "__main__":
    import sys
    case_id = sys.argv[1] if len(sys.argv) > 1 else "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d"
    asyncio.run(fast_download(case_id))
