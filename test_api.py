#!/usr/bin/env python3
"""Test EnerGov API endpoints to find the best approach."""

import asyncio
import json
import httpx

API_BASE = "https://energov.miamidade.gov/energov_prod/selfservice/api"
CASE_ID = "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Origin": "https://energov.miamidade.gov",
    "Referer": "https://energov.miamidade.gov/EnerGov_Prod/SelfService/",
}


async def test_endpoints():
    """Test various API endpoints."""
    
    endpoints = [
        # Attachments endpoints
        f"/energov/entity/attachments/search/entityattachments/{CASE_ID}/2/true",
        f"/energov/entity/attachments/{CASE_ID}",
        f"/energov/attachments/{CASE_ID}",
        f"/energov/plans/{CASE_ID}/attachments",
        f"/energov/plans/{CASE_ID}",
        # Document endpoints
        f"/energov/entity/documents/{CASE_ID}/2",
        f"/energov/documents/{CASE_ID}",
        # Cap endpoints
        f"/caps/plan/{CASE_ID}",
        f"/caps/{CASE_ID}/attachments",
    ]
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        for endpoint in endpoints:
            url = f"{API_BASE}{endpoint}"
            print(f"\n{'='*60}")
            print(f"Testing: {endpoint}")
            print(f"{'='*60}")
            
            try:
                resp = await client.get(url)
                print(f"Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        
                        # Pretty print structure
                        if isinstance(data, dict):
                            print(f"Type: dict, Keys: {list(data.keys())}")
                            
                            # Check for attachments in various locations
                            for key in ["Attachments", "Result", "Documents", "Files"]:
                                if key in data:
                                    val = data[key]
                                    print(f"  {key}: type={type(val).__name__}", end="")
                                    if isinstance(val, list):
                                        print(f", len={len(val)}")
                                        if val and len(val) > 0:
                                            first = val[0]
                                            if isinstance(first, dict):
                                                print(f"    First item keys: {list(first.keys())[:10]}")
                                            else:
                                                print(f"    First item: {str(first)[:100]}")
                                    elif isinstance(val, dict):
                                        print(f", keys={list(val.keys())[:5]}")
                                    else:
                                        print(f", value={str(val)[:100]}")
                            
                            # Check Result.Attachments
                            if "Result" in data and isinstance(data["Result"], dict):
                                result = data["Result"]
                                print(f"  Result keys: {list(result.keys())[:10]}")
                                if "Attachments" in result:
                                    att = result["Attachments"]
                                    print(f"    Result.Attachments: type={type(att).__name__}")
                                    if isinstance(att, list) and att:
                                        print(f"      len={len(att)}, first={att[0] if att else 'empty'}")
                        
                        elif isinstance(data, list):
                            print(f"Type: list, Length: {len(data)}")
                            if data:
                                first = data[0]
                                if isinstance(first, dict):
                                    print(f"  First item keys: {list(first.keys())[:10]}")
                                else:
                                    print(f"  First item: {str(first)[:100]}")
                        
                        # Save full response for analysis
                        safe_name = endpoint.replace("/", "_").replace("?", "_")
                        with open(f"api_test_{safe_name}.json", "w") as f:
                            json.dump(data, f, indent=2, default=str)
                            
                    except json.JSONDecodeError:
                        print(f"Response (not JSON): {resp.text[:200]}")
                else:
                    print(f"Error: {resp.text[:200]}")
                    
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_endpoints())

