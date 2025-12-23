#!/usr/bin/env python3
"""Intercept network requests to discover how attachments are loaded."""

import asyncio
import json
from playwright.async_api import async_playwright

CASE_ID = "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d"
URL = f"https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/plan/{CASE_ID}?tab=attachments"


async def intercept():
    """Intercept all network requests."""
    
    api_calls = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Intercept all requests
        async def handle_request(request):
            if "api" in request.url.lower() or "attachment" in request.url.lower():
                api_calls.append({
                    "method": request.method,
                    "url": request.url,
                    "headers": dict(request.headers),
                })
        
        async def handle_response(response):
            url = response.url
            if "attachment" in url.lower() or "document" in url.lower():
                try:
                    body = await response.json()
                    print(f"\n{'='*60}")
                    print(f"📡 {response.request.method} {url}")
                    print(f"Status: {response.status}")
                    
                    # Analyze response
                    if isinstance(body, dict):
                        print(f"Keys: {list(body.keys())}")
                        if "Result" in body:
                            result = body["Result"]
                            if isinstance(result, dict):
                                print(f"Result keys: {list(result.keys())}")
                                for k, v in result.items():
                                    if v is not None:
                                        vtype = type(v).__name__
                                        if isinstance(v, list):
                                            print(f"  {k}: list[{len(v)}]")
                                            if v:
                                                print(f"    Sample: {json.dumps(v[0], default=str)[:200]}")
                                        elif isinstance(v, dict):
                                            print(f"  {k}: dict{list(v.keys())[:5]}")
                                        else:
                                            print(f"  {k}: {vtype} = {str(v)[:100]}")
                    elif isinstance(body, list):
                        print(f"Array length: {len(body)}")
                        if body:
                            print(f"First item: {json.dumps(body[0], default=str)[:300]}")
                    
                    # Save full response
                    safe = url.split("/")[-1].split("?")[0][:50]
                    with open(f"network_{safe}.json", "w") as f:
                        json.dump(body, f, indent=2, default=str)
                        
                except:
                    pass
        
        page.on("request", handle_request)
        page.on("response", handle_response)
        
        print(f"🌐 Loading: {URL}")
        await page.goto(URL, wait_until="networkidle")
        await asyncio.sleep(5)  # Wait for all data to load
        
        # Also check what's in the page's Angular scope
        print("\n" + "="*60)
        print("🔍 Checking page data...")
        print("="*60)
        
        # Extract attachment data from page
        data = await page.evaluate("""
            () => {
                const result = {
                    attachments: [],
                    downloadUrls: []
                };
                
                // Find all links with PDF references
                document.querySelectorAll('a').forEach(a => {
                    const text = a.textContent.trim();
                    const href = a.href;
                    const onclick = a.getAttribute('ng-click') || a.getAttribute('onclick') || '';
                    
                    if (text.toLowerCase().endsWith('.pdf')) {
                        result.attachments.push({
                            name: text,
                            href: href,
                            onclick: onclick,
                            // Get data attributes
                            dataId: a.getAttribute('data-id') || a.getAttribute('data-attachment-id'),
                        });
                    }
                });
                
                // Try to get attachment IDs from Angular scope
                if (window.angular) {
                    try {
                        const elem = document.querySelector('[ng-controller*="Attachment"], .attachment-list, [class*="attachment"]');
                        if (elem) {
                            const scope = angular.element(elem).scope();
                            if (scope) {
                                // Look for attachment data
                                const checkScope = (s, depth = 0) => {
                                    if (depth > 3) return;
                                    for (const key of Object.keys(s)) {
                                        if (key.startsWith('$')) continue;
                                        const val = s[key];
                                        if (Array.isArray(val) && val.length > 0) {
                                            const first = val[0];
                                            if (first && (first.AttachmentId || first.DocumentId || first.FileName)) {
                                                result.angularData = val.map(v => ({
                                                    AttachmentId: v.AttachmentId || v.Id || v.DocumentId,
                                                    FileName: v.FileName || v.Name,
                                                    Category: v.Category,
                                                    CreatedDate: v.CreatedDate
                                                }));
                                            }
                                        }
                                    }
                                    if (s.$parent) checkScope(s.$parent, depth + 1);
                                };
                                checkScope(scope);
                            }
                        }
                    } catch(e) {
                        result.angularError = e.message;
                    }
                }
                
                return result;
            }
        """)
        
        print(f"\nFound {len(data['attachments'])} PDF links on page")
        if data.get('angularData'):
            print(f"Angular data: {len(data['angularData'])} attachments with IDs")
            print(f"Sample: {json.dumps(data['angularData'][0], default=str)}")
        
        # Save all data
        with open("page_attachments.json", "w") as f:
            json.dump(data, f, indent=2, default=str)
        
        await browser.close()
    
    print(f"\n📊 Captured {len(api_calls)} API calls")
    with open("api_calls.json", "w") as f:
        json.dump(api_calls, f, indent=2)


if __name__ == "__main__":
    asyncio.run(intercept())

