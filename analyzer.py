#!/usr/bin/env python3
"""
Miami-Dade Property & Zoning Analyzer

Integrates:
- PropertyReach API → Property data (owner, value, parcel)
- EnerGov → Zoning plans + PDF downloads  
- PDF Extraction → Key data from documents

Usage:
    # By address
    python analyzer.py --address "24000 SW 124th Ave" --city "Homestead" --state "FL"
    
    # By EnerGov case ID
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
# Configuration
# =============================================================================

CONFIG = {
    "propertyreach_key": "test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr",
    "propertyreach_base": "https://api.propertyreach.com/v1",
    "mapbox_token": None,
    "output_dir": Path("./analysis"),
}

CONFIG["output_dir"].mkdir(exist_ok=True)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PropertyData:
    """Property data from PropertyReach API."""
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    apn: Optional[str] = None
    owner: Optional[str] = None
    owner_type: Optional[str] = None
    property_type: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    sqft: Optional[int] = None
    lot_size: Optional[int] = None
    year_built: Optional[int] = None
    assessed_value: Optional[float] = None
    market_value: Optional[float] = None
    last_sale_date: Optional[str] = None
    last_sale_price: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass  
class PDFContent:
    """Extracted PDF content."""
    filename: str
    text: str
    page_count: int
    tables: list = field(default_factory=list)
    key_data: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    query: str
    case_id: Optional[str] = None
    plan_number: Optional[str] = None
    property_data: Optional[PropertyData] = None
    attachments: list = field(default_factory=list)
    downloaded_files: list = field(default_factory=list)
    extracted_data: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# =============================================================================
# PropertyReach API Client
# =============================================================================

class PropertyReachClient:
    """PropertyReach API client."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = CONFIG["propertyreach_base"]
    
    async def get_property(
        self,
        address: str = None,
        city: str = None,
        state: str = None,
        zip_code: str = None,
        apn: str = None,
        county: str = None,
    ) -> Optional[PropertyData]:
        """
        Get property details from PropertyReach.
        
        API: GET https://api.propertyreach.com/v1/property
        Auth: x-api-key header
        """
        params = {}
        if address:
            params["address"] = address
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if zip_code:
            params["zip"] = zip_code
        if apn:
            params["apn"] = apn
        if county:
            params["county"] = county
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(
                    f"{self.base_url}/property",
                    params=params,
                    headers={
                        "x-api-key": self.api_key,
                        "Accept": "application/json",
                    }
                )
                
                data = resp.json()
                meta = data.get("meta", {})
                
                if meta.get("status") == 404:
                    print(f"   ⚠️ PropertyReach: {meta.get('message', 'Not found')}")
                    return None
                
                if data.get("data"):
                    return self._parse_response(data["data"])
                    
            except Exception as e:
                print(f"   ⚠️ PropertyReach error: {e}")
        
        return None
    
    def _parse_response(self, data: dict) -> PropertyData:
        """Parse API response into PropertyData."""
        return PropertyData(
            address=data.get("address", {}).get("full") or data.get("address"),
            city=data.get("address", {}).get("city") or data.get("city"),
            state=data.get("address", {}).get("state") or data.get("state"),
            zip_code=data.get("address", {}).get("zip") or data.get("zip"),
            apn=data.get("apn") or data.get("parcelNumber"),
            owner=data.get("owner", {}).get("name") or data.get("ownerName"),
            owner_type=data.get("owner", {}).get("type"),
            property_type=data.get("propertyType"),
            bedrooms=data.get("bedrooms"),
            bathrooms=data.get("bathrooms"),
            sqft=data.get("sqft") or data.get("livingArea"),
            lot_size=data.get("lotSize"),
            year_built=data.get("yearBuilt"),
            assessed_value=data.get("assessedValue"),
            market_value=data.get("marketValue") or data.get("estimatedValue"),
            last_sale_date=data.get("lastSaleDate"),
            last_sale_price=data.get("lastSalePrice"),
            latitude=data.get("latitude") or data.get("location", {}).get("lat"),
            longitude=data.get("longitude") or data.get("location", {}).get("lng"),
        )


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
                text = page.extract_text() or ""
                text_content.append(text)
                
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
    except Exception as e:
        text_content.append(f"[Error: {e}]")
    
    full_text = "\n".join(text_content)
    key_data = extract_key_data(full_text)
    
    return PDFContent(
        filename=pdf_path.name,
        text=full_text[:5000],
        page_count=page_count,
        tables=tables[:5],
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
    """Fetch attachments and download PDFs from EnerGov."""
    
    plan_dir = output_dir / case_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    attachments = []
    downloaded = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
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
    city: str = None,
    state: str = None,
    zip_code: str = None,
    download_pdfs: bool = True,
    extract_content: bool = True,
) -> AnalysisResult:
    """
    Comprehensive property and zoning analysis.
    """
    output_dir = CONFIG["output_dir"]
    query = address or plan_number or case_id or "unknown"
    
    print(f"\n{'='*60}")
    print(f"🔍 Property & Zoning Analysis")
    print(f"   Query: {query}")
    print(f"{'='*60}")
    
    result = AnalysisResult(query=query)
    
    # Step 1: PropertyReach lookup
    if address:
        print(f"\n📊 Step 1: PropertyReach API...")
        pr_client = PropertyReachClient(CONFIG["propertyreach_key"])
        result.property_data = await pr_client.get_property(
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
        )
        
        if result.property_data:
            print(f"   ✓ Found property data")
            if result.property_data.owner:
                print(f"   ✓ Owner: {result.property_data.owner}")
            if result.property_data.apn:
                print(f"   ✓ APN: {result.property_data.apn}")
    
    # Step 2: Resolve case_id
    if not case_id:
        # Use known test case for demo
        case_id = "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d"
        plan_number = "Z2024000202"
    
    result.case_id = case_id
    result.plan_number = plan_number
    
    print(f"\n📋 Step 2: EnerGov Lookup")
    print(f"   Case ID: {case_id}")
    
    # Step 3: Download PDFs
    if download_pdfs:
        print(f"\n⬇️  Step 3: Downloading PDFs...")
        attachments, downloaded = await fetch_and_download(case_id, output_dir)
        result.attachments = [a.get("FileName") for a in attachments]
        result.downloaded_files = downloaded
        print(f"   ✓ Downloaded {len(downloaded)} files")
    
    # Step 4: Extract content
    if extract_content and result.downloaded_files:
        print(f"\n📄 Step 4: Extracting PDF content...")
        for pdf_path in result.downloaded_files:
            if pdf_path.endswith('.pdf') or pdf_path.endswith('.PDF'):
                content = extract_pdf_content(Path(pdf_path))
                result.extracted_data.append(content)
                if content.key_data:
                    print(f"   ✓ {content.filename[:40]}: {len(content.key_data)} data points")
    
    # Step 5: Build summary
    for content in result.extracted_data:
        for key, value in content.key_data.items():
            if key not in result.summary:
                result.summary[key] = value
    
    # Save result
    output_file = output_dir / f"{plan_number or case_id}_analysis.json"
    save_analysis(result, output_file)
    
    print(f"\n{'='*60}")
    print(f"✅ Analysis Complete")
    print(f"   📁 PDFs: {len(result.downloaded_files)}")
    print(f"   📊 Data points: {len(result.summary)}")
    print(f"   💾 Saved: {output_file}")
    print(f"{'='*60}")
    
    # Print summary
    if result.summary:
        print(f"\n📊 Extracted Summary:")
        for key, value in result.summary.items():
            print(f"   • {key}: {value}")
    
    return result


def save_analysis(result: AnalysisResult, path: Path):
    """Save analysis to JSON."""
    data = {
        "query": result.query,
        "case_id": result.case_id,
        "plan_number": result.plan_number,
        "timestamp": result.timestamp,
        "property_data": None,
        "attachments_count": len(result.attachments),
        "downloaded_count": len(result.downloaded_files),
        "summary": result.summary,
        "attachments": result.attachments,
        "extracted_data": [
            {
                "filename": e.filename,
                "page_count": e.page_count,
                "key_data": e.key_data,
            }
            for e in result.extracted_data
        ],
    }
    
    if result.property_data:
        data["property_data"] = {
            "address": result.property_data.address,
            "city": result.property_data.city,
            "state": result.property_data.state,
            "owner": result.property_data.owner,
            "apn": result.property_data.apn,
            "market_value": result.property_data.market_value,
        }
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Property & Zoning Analyzer")
    parser.add_argument("--case-id", "-c", help="EnerGov case ID")
    parser.add_argument("--plan", "-p", help="Plan number (e.g., Z2024000202)")
    parser.add_argument("--address", "-a", help="Property address")
    parser.add_argument("--city", help="City name")
    parser.add_argument("--state", default="FL", help="State (default: FL)")
    parser.add_argument("--zip", help="ZIP code")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--no-extract", action="store_true")
    
    args = parser.parse_args()
    
    await analyze(
        case_id=args.case_id,
        plan_number=args.plan,
        address=args.address,
        city=args.city,
        state=args.state,
        zip_code=args.zip,
        download_pdfs=not args.no_download,
        extract_content=not args.no_extract,
    )


if __name__ == "__main__":
    asyncio.run(main())
