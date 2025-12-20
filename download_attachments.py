#!/usr/bin/env python3
"""
Miami-Dade EnerGov Attachment Downloader - Optimized Version

Downloads all PDF attachments from EnerGov plans into folders by plan number.

Usage:
    python3 download_attachments.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Configuration
BASE_URL = "https://energov.miamidade.gov/EnerGov_Prod/SelfService"
OUTPUT_DIR = Path("./downloads")


async def download_plan_attachments(case_id: str, plan_number: str = None, output_dir: Path = OUTPUT_DIR):
    """Download all attachments for a plan - optimized for speed."""
    
    folder_name = plan_number or case_id
    plan_dir = output_dir / folder_name
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📁 Downloading: {folder_name}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Navigate to attachments tab
        url = f"{BASE_URL}/#/plan/{case_id}?tab=attachments"
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)  # Wait for Angular to render
        except Exception as e:
            print(f"❌ Failed to load: {e}")
            await browser.close()
            return []
        
        # Get plan number from title
        title = await page.title()
        if title and title not in ["Civic Access", "SelfService Public Site"]:
            plan_number = title
            new_dir = output_dir / plan_number
            if new_dir != plan_dir and not new_dir.exists():
                plan_dir.rename(new_dir)
                plan_dir = new_dir
        
        # Extract attachment info
        attachments = await page.evaluate("""
            () => {
                const files = [];
                const seen = new Set();
                document.querySelectorAll('a').forEach(link => {
                    const text = link.textContent.trim();
                    if (text.toLowerCase().endsWith('.pdf') && text.length < 200 && !seen.has(text)) {
                        seen.add(text);
                        files.push(text);
                    }
                });
                return files;
            }
        """)
        
        if not attachments:
            print("⚠️  No PDFs found")
            await browser.close()
            return []
        
        print(f"📎 Found {len(attachments)} unique PDFs")
        
        # Download files
        downloaded = []
        for i, file_name in enumerate(attachments):
            safe_name = re.sub(r'[^\w\-_\. ]', '_', file_name)
            file_path = plan_dir / safe_name
            
            if file_path.exists():
                downloaded.append(str(file_path))
                continue
            
            try:
                async with page.expect_download(timeout=10000) as download_info:
                    escaped = file_name.replace('"', '\\"').replace("'", "\\'")
                    await page.evaluate(f'''() => {{
                        for (const a of document.querySelectorAll('a')) {{
                            if (a.textContent.trim() === "{escaped}") {{ a.click(); return; }}
                        }}
                    }}''')
                
                download = await download_info.value
                await download.save_as(file_path)
                downloaded.append(str(file_path))
                print(f"  ✓ [{i+1}/{len(attachments)}] {safe_name}")
                
            except PlaywrightTimeout:
                print(f"  ⚠ [{i+1}/{len(attachments)}] Timeout: {file_name[:40]}")
            except Exception as e:
                print(f"  ❌ [{i+1}/{len(attachments)}] Error: {str(e)[:30]}")
        
        await browser.close()
        
        # Save metadata
        with open(plan_dir / "_metadata.json", "w") as f:
            json.dump({
                "plan_number": plan_number,
                "case_id": case_id,
                "downloaded_at": datetime.now().isoformat(),
                "files": attachments,
                "count": len(downloaded)
            }, f, indent=2)
        
        print(f"✅ Done: {len(downloaded)}/{len(attachments)} files → {plan_dir}")
        return downloaded


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Download EnerGov attachments")
    parser.add_argument("plans", nargs="*", help="Plan numbers or case IDs")
    parser.add_argument("--case-id", "-c", help="Case ID (UUID)")
    parser.add_argument("--output-dir", "-o", default="./downloads")
    
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.case_id:
        await download_plan_attachments(args.case_id, output_dir=output_dir)
    elif args.plans:
        for plan in args.plans:
            if len(plan) == 36 and plan.count("-") == 4:
                await download_plan_attachments(plan, output_dir=output_dir)
            else:
                print(f"⚠️  '{plan}' - Use case ID (UUID from URL)")
    else:
        print("Usage: python3 download_attachments.py --case-id <UUID>")
        print("Example: python3 download_attachments.py -c c75ba542-3e32-48f5-8f7b-418d3f8c1b6d")


if __name__ == "__main__":
    asyncio.run(main())
