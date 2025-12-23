#!/usr/bin/env python3
"""
Property Analyzer - Unified PropertyReach + EnerGov Integration

Flow:
1. PropertyReach API → Get property data (address, owner, parcel, value)
2. Mapbox → Geocode/verify address
3. EnerGov → Search for zoning plans by address/parcel
4. Download PDFs → Extract key data
5. Combine → Return comprehensive property analysis

Usage:
    analyzer = PropertyAnalyzer(
        propertyreach_key="test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr",
        mapbox_token="your_mapbox_token"
    )
    result = await analyzer.analyze_property("24000 SW 124th Avenue, Miami, FL")
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, asdict

import httpx
from playwright.async_api import async_playwright

# =============================================================================
# Configuration
# =============================================================================

PROPERTYREACH_BASE = "https://api.propertyreach.com/v1"
MAPBOX_GEOCODING = "https://api.mapbox.com/geocoding/v5/mapbox.places"
ENERGOV_SEARCH = "https://energov.miamidade.gov/energov_prod/selfservice/api"

OUTPUT_DIR = Path("./analysis_output")
OUTPUT_DIR.mkdir(exist_ok=True)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class PropertyData:
    """Property information from PropertyReach."""
    address: str
    city: str
    state: str
    zip_code: str
    parcel_id: Optional[str] = None
    owner_name: Optional[str] = None
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
    raw_data: Optional[dict] = None


@dataclass
class ZoningPlan:
    """Zoning plan from EnerGov."""
    case_id: str
    plan_number: str
    description: Optional[str] = None
    status: Optional[str] = None
    opened_date: Optional[str] = None
    address: Optional[str] = None
    plan_type: Optional[str] = None
    attachments: list = None
    
    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []


@dataclass
class AnalysisResult:
    """Complete property analysis result."""
    query: str
    property_data: Optional[PropertyData] = None
    geocoded_address: Optional[dict] = None
    zoning_plans: list = None
    downloaded_pdfs: list = None
    analysis_timestamp: str = None
    errors: list = None
    
    def __post_init__(self):
        if self.zoning_plans is None:
            self.zoning_plans = []
        if self.downloaded_pdfs is None:
            self.downloaded_pdfs = []
        if self.errors is None:
            self.errors = []
        if self.analysis_timestamp is None:
            self.analysis_timestamp = datetime.now().isoformat()


# =============================================================================
# PropertyReach API Client
# =============================================================================

class PropertyReachClient:
    """Client for PropertyReach API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    
    async def search_by_address(self, address: str) -> Optional[PropertyData]:
        """Search for property by address."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # PropertyReach address search endpoint
                url = f"{PROPERTYREACH_BASE}/properties/search"
                params = {"address": address}
                
                resp = await client.get(url, headers=self.headers, params=params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_property(data)
                elif resp.status_code == 401:
                    print(f"⚠️ PropertyReach: Invalid API key")
                else:
                    print(f"⚠️ PropertyReach: {resp.status_code} - {resp.text[:100]}")
                    
            except Exception as e:
                print(f"⚠️ PropertyReach error: {e}")
        
        return None
    
    async def get_property_by_parcel(self, parcel_id: str, county: str = "miami-dade") -> Optional[PropertyData]:
        """Get property by parcel ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                url = f"{PROPERTYREACH_BASE}/properties/parcel/{parcel_id}"
                params = {"county": county}
                
                resp = await client.get(url, headers=self.headers, params=params)
                
                if resp.status_code == 200:
                    return self._parse_property(resp.json())
                    
            except Exception as e:
                print(f"⚠️ PropertyReach parcel lookup error: {e}")
        
        return None
    
    async def autocomplete(self, query: str, limit: int = 5) -> list[dict]:
        """Get address suggestions."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                url = f"{PROPERTYREACH_BASE}/addresses/autocomplete"
                params = {"q": query, "limit": limit}
                
                resp = await client.get(url, headers=self.headers, params=params)
                
                if resp.status_code == 200:
                    return resp.json().get("suggestions", [])
                    
            except Exception as e:
                print(f"⚠️ Autocomplete error: {e}")
        
        return []
    
    def _parse_property(self, data: dict) -> PropertyData:
        """Parse API response into PropertyData."""
        # Handle nested response
        prop = data.get("property", data.get("result", data))
        if isinstance(prop, list) and prop:
            prop = prop[0]
        
        return PropertyData(
            address=prop.get("address", {}).get("full", "") or prop.get("address", ""),
            city=prop.get("address", {}).get("city", "") or prop.get("city", ""),
            state=prop.get("address", {}).get("state", "") or prop.get("state", ""),
            zip_code=prop.get("address", {}).get("zip", "") or prop.get("zip", ""),
            parcel_id=prop.get("parcelId") or prop.get("apn"),
            owner_name=prop.get("owner", {}).get("name") or prop.get("ownerName"),
            owner_type=prop.get("owner", {}).get("type") or prop.get("ownerType"),
            property_type=prop.get("propertyType") or prop.get("type"),
            bedrooms=prop.get("bedrooms"),
            bathrooms=prop.get("bathrooms"),
            sqft=prop.get("sqft") or prop.get("livingArea"),
            lot_size=prop.get("lotSize") or prop.get("lotSqft"),
            year_built=prop.get("yearBuilt"),
            assessed_value=prop.get("assessedValue") or prop.get("taxAssessment"),
            market_value=prop.get("marketValue") or prop.get("estimatedValue"),
            last_sale_date=prop.get("lastSaleDate"),
            last_sale_price=prop.get("lastSalePrice"),
            latitude=prop.get("latitude") or prop.get("location", {}).get("lat"),
            longitude=prop.get("longitude") or prop.get("location", {}).get("lng"),
            raw_data=data,
        )


# =============================================================================
# Mapbox Geocoding Client  
# =============================================================================

class MapboxClient:
    """Client for Mapbox Geocoding API."""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
    
    async def geocode(self, address: str) -> Optional[dict]:
        """Geocode an address to coordinates."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # URL encode the address
                encoded = address.replace(" ", "%20")
                url = f"{MAPBOX_GEOCODING}/{encoded}.json"
                params = {
                    "access_token": self.access_token,
                    "country": "US",
                    "types": "address",
                    "limit": 1,
                }
                
                resp = await client.get(url, params=params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    
                    if features:
                        feature = features[0]
                        coords = feature.get("geometry", {}).get("coordinates", [])
                        
                        return {
                            "formatted_address": feature.get("place_name"),
                            "longitude": coords[0] if len(coords) > 0 else None,
                            "latitude": coords[1] if len(coords) > 1 else None,
                            "confidence": feature.get("relevance"),
                            "address_components": feature.get("context", []),
                        }
                        
            except Exception as e:
                print(f"⚠️ Mapbox geocoding error: {e}")
        
        return None
    
    async def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        """Convert coordinates to address."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                url = f"{MAPBOX_GEOCODING}/{lng},{lat}.json"
                params = {
                    "access_token": self.access_token,
                    "types": "address",
                    "limit": 1,
                }
                
                resp = await client.get(url, params=params)
                
                if resp.status_code == 200:
                    data = resp.json()
                    features = data.get("features", [])
                    if features:
                        return features[0].get("place_name")
                        
            except Exception as e:
                print(f"⚠️ Reverse geocoding error: {e}")
        
        return None


# =============================================================================
# EnerGov Integration (using existing fast_download)
# =============================================================================

class EnerGovClient:
    """Client for EnerGov zoning data."""
    
    async def search_by_address(self, address: str) -> list[ZoningPlan]:
        """Search for zoning plans by address."""
        plans = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Search on EnerGov
            search_url = "https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/search"
            await page.goto(search_url, wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Try to search for the address
            try:
                # Type in search box
                search_input = await page.query_selector('input[type="search"], input[placeholder*="Search"], #searchInput')
                if search_input:
                    await search_input.fill(address)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(3)
                    
                    # Extract results
                    results = await page.evaluate('''() => {
                        const items = [];
                        document.querySelectorAll('tr.result-row, div.search-result, a[href*="/plan/"]').forEach(el => {
                            const href = el.getAttribute('href') || el.querySelector('a')?.getAttribute('href') || '';
                            const caseMatch = href.match(/plan\\/([a-f0-9-]+)/i);
                            if (caseMatch) {
                                items.push({
                                    caseId: caseMatch[1],
                                    text: el.textContent.trim().slice(0, 200)
                                });
                            }
                        });
                        return items;
                    }''')
                    
                    for r in results:
                        plan_match = re.search(r'Z\d{10}', r.get('text', ''))
                        plans.append(ZoningPlan(
                            case_id=r['caseId'],
                            plan_number=plan_match.group(0) if plan_match else None,
                            description=r.get('text', '')[:100],
                        ))
                        
            except Exception as e:
                print(f"⚠️ EnerGov search error: {e}")
            
            await browser.close()
        
        return plans
    
    async def get_plan_details(self, case_id: str) -> Optional[ZoningPlan]:
        """Get details for a specific plan."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            attachments = []
            plan_data = {}
            
            async def handle_response(response):
                nonlocal attachments, plan_data
                url = response.url
                
                if "entityattachments" in url and response.status == 200:
                    try:
                        data = await response.json()
                        attachments = data.get("Result", {}).get("Attachments", []) or []
                    except:
                        pass
            
            page.on("response", handle_response)
            
            url = f"https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/plan/{case_id}?tab=attachments"
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(2)
            
            # Extract plan info from page
            plan_data = await page.evaluate('''() => {
                const title = document.querySelector('h1, .plan-title, .case-number')?.textContent || '';
                const status = document.querySelector('.status, .plan-status')?.textContent || '';
                return { title, status };
            }''')
            
            await browser.close()
            
            plan_number = None
            match = re.search(r'Z\d{10}', plan_data.get('title', ''))
            if match:
                plan_number = match.group(0)
            
            pdf_attachments = [
                {"name": a.get("FileName"), "id": a.get("AttachmentID"), "category": a.get("AttachmentGroupName")}
                for a in attachments 
                if a.get("FileName", "").lower().endswith(".pdf")
            ]
            
            return ZoningPlan(
                case_id=case_id,
                plan_number=plan_number,
                status=plan_data.get('status'),
                attachments=pdf_attachments,
            )
    
    async def download_plan_pdfs(self, case_id: str, output_dir: Path) -> list[str]:
        """Download all PDFs for a plan."""
        # Use the fast_download logic
        from fast_download import fast_download
        
        result = await fast_download(case_id, output_dir)
        return result.get("files", [])


# =============================================================================
# Main Property Analyzer
# =============================================================================

class PropertyAnalyzer:
    """
    Unified property analysis combining PropertyReach, Mapbox, and EnerGov.
    """
    
    def __init__(
        self,
        propertyreach_key: str,
        mapbox_token: str = None,
        output_dir: Path = OUTPUT_DIR
    ):
        self.propertyreach = PropertyReachClient(propertyreach_key)
        self.mapbox = MapboxClient(mapbox_token) if mapbox_token else None
        self.energov = EnerGovClient()
        self.output_dir = output_dir
    
    async def analyze_property(
        self,
        address: str = None,
        parcel_id: str = None,
        case_id: str = None,
        download_pdfs: bool = True
    ) -> AnalysisResult:
        """
        Perform comprehensive property analysis.
        
        Args:
            address: Street address to analyze
            parcel_id: Parcel ID (APN) to look up
            case_id: Direct EnerGov case ID
            download_pdfs: Whether to download PDF attachments
            
        Returns:
            AnalysisResult with all data combined
        """
        result = AnalysisResult(query=address or parcel_id or case_id)
        
        print(f"\n{'='*60}")
        print(f"🔍 Property Analysis: {result.query}")
        print(f"{'='*60}")
        
        # Step 1: Get property data from PropertyReach
        print("\n📊 Step 1: PropertyReach lookup...")
        if address:
            result.property_data = await self.propertyreach.search_by_address(address)
        elif parcel_id:
            result.property_data = await self.propertyreach.get_property_by_parcel(parcel_id)
        
        if result.property_data:
            print(f"   ✓ Found: {result.property_data.address}")
            print(f"   ✓ Owner: {result.property_data.owner_name}")
            print(f"   ✓ Parcel: {result.property_data.parcel_id}")
        else:
            print("   ⚠️ No property data found")
            result.errors.append("PropertyReach: No data found")
        
        # Step 2: Geocode with Mapbox (if available)
        if self.mapbox and address:
            print("\n🗺️  Step 2: Mapbox geocoding...")
            result.geocoded_address = await self.mapbox.geocode(address)
            if result.geocoded_address:
                print(f"   ✓ Geocoded: {result.geocoded_address.get('formatted_address')}")
                print(f"   ✓ Coords: {result.geocoded_address.get('latitude')}, {result.geocoded_address.get('longitude')}")
        
        # Step 3: Search EnerGov for zoning plans
        print("\n📋 Step 3: EnerGov search...")
        
        if case_id:
            # Direct case lookup
            plan = await self.energov.get_plan_details(case_id)
            if plan:
                result.zoning_plans.append(plan)
        elif address:
            # Search by address
            plans = await self.energov.search_by_address(address)
            result.zoning_plans = plans
        
        print(f"   ✓ Found {len(result.zoning_plans)} zoning plan(s)")
        
        # Step 4: Download PDFs if requested
        if download_pdfs and result.zoning_plans:
            print("\n📥 Step 4: Downloading PDFs...")
            
            for plan in result.zoning_plans:
                if plan.case_id:
                    try:
                        files = await self.energov.download_plan_pdfs(
                            plan.case_id,
                            self.output_dir
                        )
                        result.downloaded_pdfs.extend(files)
                        print(f"   ✓ Downloaded {len(files)} PDFs for {plan.plan_number or plan.case_id}")
                    except Exception as e:
                        result.errors.append(f"PDF download error: {e}")
        
        # Save analysis result
        output_file = self.output_dir / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self._save_result(result, output_file)
        
        print(f"\n{'='*60}")
        print(f"✅ Analysis complete!")
        print(f"   📁 Output: {output_file}")
        print(f"   📄 PDFs: {len(result.downloaded_pdfs)}")
        print(f"{'='*60}\n")
        
        return result
    
    def _save_result(self, result: AnalysisResult, path: Path):
        """Save analysis result to JSON."""
        def to_dict(obj):
            if hasattr(obj, '__dict__'):
                return {k: to_dict(v) for k, v in obj.__dict__.items() if not k.startswith('_')}
            elif isinstance(obj, list):
                return [to_dict(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: to_dict(v) for k, v in obj.items()}
            return obj
        
        with open(path, 'w') as f:
            json.dump(to_dict(result), f, indent=2, default=str)


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Property Analyzer")
    parser.add_argument("--address", "-a", help="Property address")
    parser.add_argument("--parcel", "-p", help="Parcel ID")
    parser.add_argument("--case-id", "-c", help="EnerGov case ID")
    parser.add_argument("--propertyreach-key", default="test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr")
    parser.add_argument("--mapbox-token", help="Mapbox access token")
    parser.add_argument("--no-download", action="store_true", help="Skip PDF downloads")
    
    args = parser.parse_args()
    
    analyzer = PropertyAnalyzer(
        propertyreach_key=args.propertyreach_key,
        mapbox_token=args.mapbox_token,
    )
    
    await analyzer.analyze_property(
        address=args.address,
        parcel_id=args.parcel,
        case_id=args.case_id,
        download_pdfs=not args.no_download,
    )


if __name__ == "__main__":
    asyncio.run(main())

