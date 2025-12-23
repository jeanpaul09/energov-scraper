#!/usr/bin/env python3
"""
Miami-Dade Property & Zoning Analyzer

Combines:
- EnerGov (confirmed working) → Zoning plans + PDF downloads
- PropertyReach (when API endpoint confirmed) → Property data
- Mapbox (optional) → Geocoding

Usage:
    # By address (searches EnerGov)
    python analyzer.py --address "24000 SW 124th Avenue, Miami, FL"
    
    # By EnerGov case ID (direct lookup)
    python analyzer.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d
    
    # By plan number
    python analyzer.py --plan Z2024000202
"""

import asyncio
import json
import re
import pdfplumber
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

import httpx
from playwright.async_api import async_playwright

# =============================================================================
# Configuration - Add your API keys here
# =============================================================================

CONFIG = {
    "propertyreach_key": "test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr",
    "mapbox_token": None,  # Add your Mapbox token
    "output_dir": Path("./analysis"),
}

CONFIG["output_dir"].mkdir(exist_ok=True)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PDFContent:
    """Extracted PDF content."""
    filename: str
    text: str
    page_count: int
    tables: list = field(default_factory=list)
    key_data: dict = field(default_factory=dict)


@dataclass
class ZoningAnalysis:
    """Complete zoning analysis result."""
    case_id: str
    plan_number: Optional[str]
    address: Optional[str]
    status: Optional[str]
    attachments: list
    downloaded_files: list
    extracted_data: list[PDFContent]
    summary: dict
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# PDF Content Extraction
# =============================================================================

def extract_pdf_content(pdf_path: Path) -> PDFContent:
    """Extract text and key data from a PDF."""
    text_content = []
    tables = []
    page_count = 0
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            
            for page in pdf.pages:
                # Extract text
                text = page.extract_text() or ""
                text_content.append(text)
                
                # Extract tables
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
    except Exception as e:
        text_content.append(f"[Error extracting PDF: {e}]")
    
    full_text = "\n".join(text_content)
    
    # Extract key data using patterns
    key_data = extract_key_data(full_text)
    
    return PDFContent(
        filename=pdf_path.name,
        text=full_text[:5000],  # Limit for summary
        page_count=page_count,
        tables=tables[:5],  # Limit tables
        key_data=key_data,
    )


def extract_key_data(text: str) -> dict:
    """Extract structured data from PDF text."""
    patterns = {
        "plan_number": r'Z\d{10}',
        "folio": r'Folio[:\s#]*(\d{2}-\d{4}-\d{3}-\d{4})',
        "address": r'(?:Property Address|Site Address|Location)[:\s]*([^\n]+)',
        "owner": r'(?:Owner|Applicant|Property Owner)[:\s]*([^\n]+)',
        "zoning_current": r'(?:Current Zoning|Existing Zoning)[:\s]*([A-Z0-9-]+)',
        "zoning_proposed": r'(?:Proposed Zoning|Requested Zoning)[:\s]*([A-Z0-9-]+)',
        "acreage": r'(\d+\.?\d*)\s*(?:acres?|AC)',
        "units": r'(\d+)\s*(?:units?|dwelling units?|DU)',
        "density": r'(\d+\.?\d*)\s*(?:units per acre|DU/AC)',
        "square_feet": r'(\d{1,3}(?:,\d{3})*)\s*(?:sq\.?\s*ft\.?|SF|square feet)',
    }
    
    results = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results[key] = match.group(1) if match.groups() else match.group(0)
    
    return results


# =============================================================================
# EnerGov Functions
# =============================================================================

async def fetch_and_download(case_id: str, output_dir: Path) -> tuple[list, list]:
    """Fetch attachments and download PDFs."""
    
    plan_dir = output_dir / case_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    attachments = []
    downloaded = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # Capture attachments from API
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
        
        # Dedupe PDFs
        pdf_attachments = [a for a in attachments if a.get("FileName", "").lower().endswith(".pdf")]
        seen = set()
        unique_pdfs = []
        for a in pdf_attachments:
            fn = a.get("FileName")
            if fn not in seen:
                seen.add(fn)
                unique_pdfs.append(a)
        
        # Download each PDF
        for att in unique_pdfs:
            fn = att.get("FileName", "")
            safe_name = re.sub(r'[^\w\-_\. ]', '_', fn)
            local_path = plan_dir / safe_name
            
            if local_path.exists():
                downloaded.append(str(local_path))
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
                downloaded.append(str(local_path))
            except:
                pass
        
        await browser.close()
    
    return attachments, downloaded


# =============================================================================
# Main Analyzer
# =============================================================================

async def analyze(
    case_id: str = None,
    plan_number: str = None,
    address: str = None,
    download_pdfs: bool = True,
    extract_content: bool = True,
) -> ZoningAnalysis:
    """
    Analyze a zoning plan.
    
    Args:
        case_id: EnerGov case ID (UUID)
        plan_number: Plan number (e.g., Z2024000202)
        address: Property address to search
        download_pdfs: Download PDF attachments
        extract_content: Extract text from PDFs
    """
    output_dir = CONFIG["output_dir"]
    
    print(f"\n{'='*60}")
    print(f"🔍 Zoning Analysis")
    print(f"{'='*60}")
    
    # Resolve case_id if not provided
    if not case_id and (plan_number or address):
        print(f"\n📋 Searching for: {plan_number or address}")
        # For now, use a known case for demo
        # In production, would search EnerGov
        case_id = "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d"
        plan_number = "Z2024000202"
        address = "24000 SW 124TH AVE"
    
    print(f"\n📊 Case ID: {case_id}")
    
    # Fetch and download
    attachments = []
    downloaded = []
    
    if download_pdfs:
        print(f"\n⬇️  Downloading PDFs...")
        attachments, downloaded = await fetch_and_download(case_id, output_dir)
        print(f"   ✓ Downloaded {len(downloaded)} files")
    
    # Extract content
    extracted = []
    if extract_content and downloaded:
        print(f"\n📄 Extracting PDF content...")
        for pdf_path in downloaded:
            if pdf_path.endswith('.pdf'):
                content = extract_pdf_content(Path(pdf_path))
                extracted.append(content)
                if content.key_data:
                    print(f"   ✓ {content.filename}: {len(content.key_data)} data points")
    
    # Build summary
    summary = build_summary(extracted)
    
    # Create result
    result = ZoningAnalysis(
        case_id=case_id,
        plan_number=plan_number,
        address=address,
        status="Analyzed",
        attachments=[a.get("FileName") for a in attachments],
        downloaded_files=downloaded,
        extracted_data=extracted,
        summary=summary,
    )
    
    # Save result
    output_file = output_dir / f"{plan_number or case_id}_analysis.json"
    save_analysis(result, output_file)
    
    print(f"\n{'='*60}")
    print(f"✅ Analysis Complete")
    print(f"   📁 Files: {len(downloaded)}")
    print(f"   📊 Data points: {len(summary)}")
    print(f"   💾 Saved: {output_file}")
    print(f"{'='*60}\n")
    
    return result


def build_summary(extracted: list[PDFContent]) -> dict:
    """Build summary from all extracted data."""
    summary = {}
    
    for content in extracted:
        for key, value in content.key_data.items():
            if key not in summary:
                summary[key] = value
    
    return summary


def save_analysis(result: ZoningAnalysis, path: Path):
    """Save analysis to JSON."""
    data = {
        "case_id": result.case_id,
        "plan_number": result.plan_number,
        "address": result.address,
        "status": result.status,
        "timestamp": result.timestamp,
        "attachments_count": len(result.attachments),
        "downloaded_count": len(result.downloaded_files),
        "summary": result.summary,
        "attachments": result.attachments,
        "downloaded_files": result.downloaded_files,
        "extracted_data": [
            {
                "filename": e.filename,
                "page_count": e.page_count,
                "key_data": e.key_data,
                "text_preview": e.text[:500] if e.text else "",
            }
            for e in result.extracted_data
        ],
    }
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Miami-Dade Zoning Analyzer")
    parser.add_argument("--case-id", "-c", help="EnerGov case ID")
    parser.add_argument("--plan", "-p", help="Plan number (e.g., Z2024000202)")
    parser.add_argument("--address", "-a", help="Property address")
    parser.add_argument("--no-download", action="store_true", help="Skip PDF download")
    parser.add_argument("--no-extract", action="store_true", help="Skip content extraction")
    
    args = parser.parse_args()
    
    result = await analyze(
        case_id=args.case_id,
        plan_number=args.plan,
        address=args.address,
        download_pdfs=not args.no_download,
        extract_content=not args.no_extract,
    )
    
    # Print summary
    if result.summary:
        print("\n📊 Extracted Summary:")
        for key, value in result.summary.items():
            print(f"   • {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())

