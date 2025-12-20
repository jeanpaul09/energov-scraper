#!/usr/bin/env python3
"""
Miami-Dade EnerGov Portal Scraper

Scrapes plan attachments (PDFs) from the Miami-Dade County EnerGov portal
and extracts data from them.

URL Pattern: https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/plan/{case_id}?tab=attachments
API Base: https://energov.miamidade.gov/energov_prod/selfservice/api

Usage:
    python energov_scraper.py --plan-number Z2024000202
    python energov_scraper.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
import pandas as pd
import pdfplumber
from playwright.async_api import async_playwright, Page, Browser
from pydantic import BaseModel, Field
from tqdm import tqdm

# =============================================================================
# Configuration
# =============================================================================

BASE_URL = "https://energov.miamidade.gov/EnerGov_Prod/SelfService"
API_BASE = "https://energov.miamidade.gov/energov_prod/selfservice/api"

# Headers to mimic browser requests
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
    "Origin": "https://energov.miamidade.gov",
}

OUTPUT_DIR = Path("./output")
PDF_DIR = OUTPUT_DIR / "pdfs"

# =============================================================================
# Data Models
# =============================================================================


class Attachment(BaseModel):
    """Model for an attachment from the EnerGov portal."""
    attachment_id: str = Field(alias="AttachmentId", default="")
    file_name: str = Field(alias="FileName", default="")
    file_type: str = Field(alias="FileType", default="")
    category: str = Field(alias="Category", default="")
    description: str = Field(alias="Description", default="")
    created_date: Optional[str] = Field(alias="CreatedDate", default=None)
    file_size: Optional[int] = Field(alias="FileSize", default=None)
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    extracted_text: Optional[str] = None

    class Config:
        populate_by_name = True


class PlanDetails(BaseModel):
    """Model for plan details from the EnerGov portal."""
    plan_id: str = Field(alias="PlanId", default="")
    plan_number: str = Field(alias="PlanNumber", default="")
    plan_type: str = Field(alias="PlanType", default="")
    status: str = Field(alias="Status", default="")
    description: str = Field(alias="Description", default="")
    applied_date: Optional[str] = Field(alias="AppliedDate", default=None)
    completion_date: Optional[str] = Field(alias="CompletionDate", default=None)
    expiration_date: Optional[str] = Field(alias="ExpirationDate", default=None)
    district: str = Field(alias="District", default="")
    assigned_to: str = Field(alias="AssignedTo", default="")
    address: str = Field(alias="Address", default="")
    attachments: list[Attachment] = []

    class Config:
        populate_by_name = True


class SearchResult(BaseModel):
    """Model for search results."""
    case_id: str
    plan_number: str
    plan_type: str
    status: str


# =============================================================================
# Core Scraper Class
# =============================================================================


class EnerGovScraper:
    """
    Scraper for Miami-Dade EnerGov Portal.
    
    This scraper can:
    1. Search for plans by plan number
    2. Convert plan numbers to case IDs
    3. Fetch plan details and attachments
    4. Download PDF attachments
    5. Extract text from PDFs
    6. Export data as JSON
    """

    def __init__(self, headless: bool = True, output_dir: Path = OUTPUT_DIR):
        self.headless = headless
        self.output_dir = output_dir
        self.pdf_dir = output_dir / "pdfs"
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def initialize(self):
        """Initialize browser and HTTP client."""
        # Start Playwright browser
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=DEFAULT_HEADERS["User-Agent"],
        )
        self.page = await context.new_page()
        
        # Initialize HTTP client for API requests
        self.http_client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=60.0,
            follow_redirects=True,
        )
        
        print("✓ Browser and HTTP client initialized")

    async def close(self):
        """Close browser and HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
        if self.browser:
            await self.browser.close()
        print("✓ Resources cleaned up")

    async def search_plan_number(self, plan_number: str) -> Optional[str]:
        """
        Search for a plan by plan number and return its case ID.
        
        The EnerGov portal uses a search API to find plans.
        
        Args:
            plan_number: The plan number (e.g., "Z2024000202")
            
        Returns:
            The case ID (UUID) if found, None otherwise
        """
        print(f"🔍 Searching for plan number: {plan_number}")
        
        # Navigate to the search page first to get cookies
        search_url = f"{BASE_URL}/#/search"
        await self.page.goto(search_url, wait_until="networkidle")
        await asyncio.sleep(2)  # Wait for Angular app to load
        
        # Try the search API endpoint
        search_endpoints = [
            f"{API_BASE}/energov/search/plan",
            f"{API_BASE}/energov/plans/search",
            f"{API_BASE}/caps/search",
        ]
        
        search_payload = {
            "SearchText": plan_number,
            "SearchType": "Plan",
            "ModuleName": "Plan",
            "SortColumn": "PlanNumber",
            "SortDirection": "asc",
            "PageSize": 10,
            "PageNumber": 1,
        }
        
        # Try different search approaches
        for endpoint in search_endpoints:
            try:
                response = await self.http_client.post(
                    endpoint,
                    json=search_payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    # Parse response to find case ID
                    if isinstance(data, list) and len(data) > 0:
                        return data[0].get("PlanId") or data[0].get("CaseId")
                    elif isinstance(data, dict):
                        results = data.get("Result") or data.get("Results") or data.get("Data") or []
                        if results and len(results) > 0:
                            return results[0].get("PlanId") or results[0].get("CaseId")
            except Exception as e:
                print(f"  ⚠ Endpoint {endpoint} failed: {e}")
                continue
        
        # Alternative: Use browser to navigate and extract from URL redirect
        print("  → Trying browser navigation approach...")
        try:
            # Navigate directly with plan number in search
            await self.page.goto(
                f"{BASE_URL}/#/search?searchText={plan_number}&module=Plan",
                wait_until="networkidle"
            )
            await asyncio.sleep(3)
            
            # Look for the plan in search results and click it
            plan_link = await self.page.query_selector(f'text="{plan_number}"')
            if plan_link:
                await plan_link.click()
                await asyncio.sleep(2)
                
                # Extract case ID from URL
                current_url = self.page.url
                match = re.search(r'/plan/([a-f0-9-]+)', current_url)
                if match:
                    return match.group(1)
        except Exception as e:
            print(f"  ⚠ Browser approach failed: {e}")
        
        return None

    async def get_plan_details(self, case_id: str) -> Optional[dict]:
        """
        Fetch plan details from the API.
        
        Args:
            case_id: The case ID (UUID)
            
        Returns:
            Plan details dictionary
        """
        print(f"📋 Fetching plan details for case: {case_id}")
        
        # First navigate to the plan page to establish session
        plan_url = f"{BASE_URL}/#/plan/{case_id}"
        await self.page.goto(plan_url, wait_until="networkidle")
        await asyncio.sleep(3)  # Wait for Angular to load data
        
        # Get cookies from browser
        cookies = await self.page.context.cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        
        # Update headers with cookies
        headers = {**DEFAULT_HEADERS, "Cookie": cookie_header}
        
        # Fetch from API
        endpoint = f"{API_BASE}/energov/plans/{case_id}"
        try:
            response = await self.http_client.get(endpoint, headers=headers)
            if response.status_code == 200:
                data = response.json()
                print(f"  ✓ Plan details retrieved")
                return data
        except Exception as e:
            print(f"  ⚠ API request failed: {e}")
        
        # Fallback: Extract from page DOM
        print("  → Extracting from page DOM...")
        try:
            plan_data = await self._extract_plan_from_dom()
            return plan_data
        except Exception as e:
            print(f"  ⚠ DOM extraction failed: {e}")
        
        return None

    async def _extract_plan_from_dom(self) -> dict:
        """Extract plan details from the page DOM."""
        data = {}
        
        # Extract plan number from title
        title = await self.page.title()
        data["PlanNumber"] = title
        
        # Define selectors for common fields
        field_selectors = {
            "Type": "Type",
            "Status": "Status",
            "Description": "Description",
            "AppliedDate": "Applied Date",
            "CompletionDate": "Completion Date",
            "ExpirationDate": "Expiration Date",
            "District": "District",
            "AssignedTo": "Assigned To",
            "IVRNumber": "IVR Number",
        }
        
        for key, label in field_selectors.items():
            try:
                # Look for label and get adjacent value
                label_elem = await self.page.query_selector(f'text="{label}:"')
                if label_elem:
                    parent = await label_elem.evaluate_handle("el => el.parentElement")
                    text = await parent.inner_text()
                    # Extract value after the label
                    value = text.replace(f"{label}:", "").strip()
                    data[key] = value
            except:
                pass
        
        return data

    async def get_attachments(self, case_id: str) -> list[dict]:
        """
        Fetch attachment list for a plan.
        
        Args:
            case_id: The case ID (UUID)
            
        Returns:
            List of attachment dictionaries
        """
        print(f"📎 Fetching attachments for case: {case_id}")
        
        # Navigate to attachments tab
        attachments_url = f"{BASE_URL}/#/plan/{case_id}?tab=attachments"
        await self.page.goto(attachments_url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Get cookies from browser
        cookies = await self.page.context.cookies()
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        headers = {**DEFAULT_HEADERS, "Cookie": cookie_header}
        
        # API endpoint for attachments (discovered from network traffic)
        # Pattern: /api/energov/entity/attachments/search/entityattachments/{caseId}/{entityType}/true
        # entityType 2 = Plan
        endpoint = f"{API_BASE}/energov/entity/attachments/search/entityattachments/{case_id}/2/true"
        
        try:
            response = await self.http_client.get(endpoint, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # Debug: print response structure
                print(f"  [DEBUG] API response type: {type(data)}")
                if isinstance(data, dict):
                    print(f"  [DEBUG] Keys: {list(data.keys())[:10]}")
                    if "Result" in data:
                        result = data["Result"]
                        print(f"  [DEBUG] Result type: {type(result)}")
                        if isinstance(result, list):
                            print(f"  [DEBUG] Result items: {len(result)}")
                            if result:
                                print(f"  [DEBUG] First result item keys: {list(result[0].keys()) if isinstance(result[0], dict) else type(result[0])}")
                        elif isinstance(result, dict):
                            print(f"  [DEBUG] Result keys: {list(result.keys())[:10]}")
                
                # Handle various response formats from EnerGov API
                attachments = []
                if isinstance(data, list):
                    attachments = data
                elif isinstance(data, dict):
                    # Check if Result contains nested Attachments
                    result = data.get("Result", data)
                    if isinstance(result, dict):
                        # Attachments is inside Result
                        attachments_data = result.get("Attachments", [])
                        print(f"  [DEBUG] Attachments type: {type(attachments_data)}")
                        if isinstance(attachments_data, list):
                            attachments = attachments_data
                            if attachments:
                                print(f"  [DEBUG] First attachment: {attachments[0]}")
                        elif isinstance(attachments_data, dict):
                            # Could be a dict with more nesting
                            for key in ["Items", "Result", "Data", "List"]:
                                if key in attachments_data and isinstance(attachments_data[key], list):
                                    attachments = attachments_data[key]
                                    break
                    elif isinstance(result, list):
                        attachments = result
                
                # Ensure each item is a dict with required fields
                valid_attachments = []
                for att in attachments:
                    if isinstance(att, dict):
                        # Only include if it has file-related fields
                        if att.get("AttachmentId") or att.get("FileName") or att.get("DocumentId") or att.get("FileType"):
                            valid_attachments.append(att)
                    elif isinstance(att, str) and not att.startswith("{"):
                        # If it's just a filename string
                        valid_attachments.append({"FileName": att})
                
                print(f"  ✓ Found {len(valid_attachments)} attachments from API")
                if valid_attachments:
                    print(f"  [DEBUG] First attachment: {valid_attachments[0]}")
                    return valid_attachments
                # If API returned empty, fall through to DOM extraction
        except Exception as e:
            print(f"  ⚠ API request failed: {e}")
        
        # Fallback: Extract from DOM
        print("  → Extracting attachments from DOM (API returned no data)...")
        return await self._extract_attachments_from_dom()

    async def _extract_attachments_from_dom(self) -> list[dict]:
        """Extract attachment info from the page DOM using JavaScript."""
        attachments = []
        
        try:
            # Wait for attachments section to fully load
            await asyncio.sleep(3)
            
            # Execute JavaScript to extract attachment data directly from the rendered page
            js_data = await self.page.evaluate("""
                () => {
                    const attachments = [];
                    
                    // Method 1: Find all links that contain PDF file extensions
                    const pdfLinks = document.querySelectorAll('a[href*=".pdf"], a[href*=".PDF"]');
                    pdfLinks.forEach(link => {
                        const text = link.textContent.trim();
                        const href = link.href;
                        if (text && text.length > 0 && !text.toLowerCase().startsWith('http')) {
                            attachments.push({
                                FileName: text,
                                DownloadUrl: href,
                                FileType: 'PDF'
                            });
                        }
                    });
                    
                    // Method 2: Find attachment cards - look for divs/sections containing PDF info
                    // EnerGov uses a card layout with file names as links
                    const cards = document.querySelectorAll('[class*="card"], [class*="tile"], section, .md-card');
                    cards.forEach(card => {
                        // Look for PDF-related text in the card
                        const text = card.innerText || '';
                        if (text.toLowerCase().includes('.pdf')) {
                            // Find the filename link within this card
                            const fileLink = card.querySelector('a');
                            if (fileLink) {
                                const fileName = fileLink.textContent.trim();
                                if (fileName && fileName.toLowerCase().includes('.pdf')) {
                                    // Check for duplicate
                                    if (!attachments.some(a => a.FileName === fileName)) {
                                        // Extract other metadata
                                        const uploadedMatch = text.match(/Uploaded:\\s*([\\d\\/]+)/);
                                        const notesMatch = text.match(/Notes:\\s*(.+?)(?:\\n|$)/);
                                        
                                        attachments.push({
                                            FileName: fileName,
                                            DownloadUrl: fileLink.href,
                                            FileType: 'PDF',
                                            UploadedDate: uploadedMatch ? uploadedMatch[1] : null,
                                            Notes: notesMatch ? notesMatch[1].trim() : null
                                        });
                                    }
                                }
                            }
                        }
                    });
                    
                    // Method 3: Try AngularJS scope if available
                    if (window.angular) {
                        try {
                            // Find attachment container element
                            const attachmentContainer = document.querySelector('[ng-controller*="attachment"], [class*="attachment-list"]');
                            if (attachmentContainer) {
                                const scope = angular.element(attachmentContainer).scope();
                                if (scope) {
                                    // Look for attachments in various scope paths
                                    const scopeData = scope.attachments || scope.vm?.attachments || 
                                                     scope.$parent?.attachments || scope.$parent?.vm?.attachments ||
                                                     scope.files || scope.vm?.files;
                                    if (Array.isArray(scopeData)) {
                                        scopeData.forEach(item => {
                                            if (item && (item.FileName || item.Name || item.fileName)) {
                                                attachments.push({
                                                    AttachmentId: item.AttachmentId || item.Id || item.DocumentId,
                                                    FileName: item.FileName || item.Name || item.fileName,
                                                    FileType: item.FileType || item.Type || 'Unknown',
                                                    Category: item.Category || item.CategoryName,
                                                    Description: item.Description || item.Notes,
                                                    CreatedDate: item.CreatedDate || item.UploadDate,
                                                    DownloadUrl: item.DownloadUrl || item.Url
                                                });
                                            }
                                        });
                                    }
                                }
                            }
                        } catch (e) {
                            console.log('Angular scope extraction error:', e);
                        }
                    }
                    
                    // Method 4: Find any element with text ending in .pdf
                    if (attachments.length === 0) {
                        const allElements = document.querySelectorAll('*');
                        allElements.forEach(el => {
                            // Only check leaf text nodes
                            if (el.children.length === 0) {
                                const text = el.textContent.trim();
                                if (text.toLowerCase().endsWith('.pdf') && text.length < 200) {
                                    // This might be a filename
                                    if (!attachments.some(a => a.FileName === text)) {
                                        // Try to find parent link
                                        let link = el.closest('a');
                                        attachments.push({
                                            FileName: text,
                                            DownloadUrl: link ? link.href : null,
                                            FileType: 'PDF'
                                        });
                                    }
                                }
                            }
                        });
                    }
                    
                    return attachments;
                }
            """)
            
            if js_data:
                print(f"  ✓ Found {len(js_data)} attachments from DOM")
                for att in js_data:
                    print(f"    - {att.get('FileName', 'Unknown')}")
                attachments.extend(js_data)
                        
        except Exception as e:
            print(f"  ⚠ DOM extraction error: {e}")
        
        print(f"  [DEBUG] Total attachments from DOM: {len(attachments)}")
        return attachments

    async def download_attachment(self, attachment: dict, case_id: str) -> Optional[Path]:
        """
        Download a single attachment using Playwright click-to-download.
        
        Args:
            attachment: Attachment dictionary
            case_id: The case ID
            
        Returns:
            Path to downloaded file
        """
        # Handle case where attachment might not be a dict
        if not isinstance(attachment, dict):
            print(f"  ⚠ Invalid attachment format: {type(attachment)}")
            return None
        
        attachment_id = attachment.get("AttachmentId") or attachment.get("Id") or attachment.get("DocumentId") or ""
        file_name = attachment.get("FileName") or attachment.get("Name") or attachment.get("Description") or f"attachment_{attachment_id}"
        
        # Sanitize filename
        safe_name = re.sub(r'[^\w\-_\. ]', '_', file_name)
        file_path = self.pdf_dir / case_id / safe_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Skip if already downloaded
        if file_path.exists():
            print(f"  ⏭ Already exists: {safe_name}")
            return file_path
        
        # Method 1: Try direct download URL if available
        download_url = attachment.get("DownloadUrl") or attachment.get("Url")
        
        if download_url and download_url.startswith("http"):
            # Get cookies
            cookies = await self.page.context.cookies()
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            headers = {**DEFAULT_HEADERS, "Cookie": cookie_header}
            
            try:
                response = await self.http_client.get(download_url, headers=headers)
                if response.status_code == 200 and len(response.content) > 100:
                    file_path.write_bytes(response.content)
                    print(f"  ✓ Downloaded: {safe_name}")
                    return file_path
            except Exception as e:
                print(f"  [DEBUG] Direct URL failed: {e}")
        
        # Method 2: Click-to-download via browser
        try:
            # Escape special characters in filename for CSS selector
            escaped_name = file_name.replace('"', '\\"')
            
            # Try to find and click the file link
            async with self.page.expect_download(timeout=15000) as download_info:
                # Try multiple selectors
                clicked = False
                for selector in [
                    f'a:has-text("{escaped_name}")',
                    f'text="{escaped_name}"',
                    f'[title*="{escaped_name}"]',
                ]:
                    try:
                        elem = await self.page.query_selector(selector)
                        if elem:
                            await elem.click()
                            clicked = True
                            break
                    except:
                        continue
                
                if not clicked:
                    # Try JavaScript click
                    await self.page.evaluate(f'''
                        () => {{
                            const links = document.querySelectorAll('a');
                            for (const link of links) {{
                                if (link.textContent.includes("{escaped_name}")) {{
                                    link.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    ''')
            
            download = await download_info.value
            await download.save_as(file_path)
            print(f"  ✓ Downloaded: {safe_name}")
            return file_path
            
        except Exception as e:
            # Download might not have triggered (no download expected)
            pass
        
        # Method 3: Construct download URL based on attachment ID
        if attachment_id:
            download_endpoints = [
                f"{API_BASE}/energov/entity/attachments/download/{attachment_id}",
                f"{API_BASE}/energov/attachments/{attachment_id}/download",
                f"{API_BASE}/document/{attachment_id}",
            ]
            
            cookies = await self.page.context.cookies()
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            headers = {**DEFAULT_HEADERS, "Cookie": cookie_header}
            
            for endpoint in download_endpoints:
                try:
                    response = await self.http_client.get(endpoint, headers=headers)
                    if response.status_code == 200 and len(response.content) > 100:
                        file_path.write_bytes(response.content)
                        print(f"  ✓ Downloaded: {safe_name}")
                        return file_path
                except:
                    continue
        
        print(f"  ⚠ Could not download: {file_name}")
        return None

    async def download_all_attachments(self, attachments: list[dict], case_id: str) -> list[Path]:
        """
        Download all attachments for a plan.
        
        Args:
            attachments: List of attachment dictionaries
            case_id: The case ID
            
        Returns:
            List of paths to downloaded files
        """
        print(f"⬇️  Downloading {len(attachments)} attachments...")
        downloaded = []
        
        for attachment in tqdm(attachments, desc="Downloading"):
            path = await self.download_attachment(attachment, case_id)
            if path:
                downloaded.append(path)
        
        print(f"  ✓ Downloaded {len(downloaded)}/{len(attachments)} files")
        return downloaded

    def extract_pdf_text(self, pdf_path: Path) -> str:
        """
        Extract text from a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Extracted text
        """
        if not pdf_path.exists():
            return ""
        
        if pdf_path.suffix.lower() != ".pdf":
            return ""
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    
                    # Also extract tables if present
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            # Convert table to text
                            table_text = "\n".join(
                                ["\t".join([str(cell) if cell else "" for cell in row]) for row in table]
                            )
                            text_parts.append(f"\n[TABLE]\n{table_text}\n[/TABLE]\n")
                
                return "\n\n".join(text_parts)
        except Exception as e:
            print(f"  ⚠ PDF extraction error for {pdf_path.name}: {e}")
            return ""

    def extract_pdf_data(self, pdf_path: Path) -> dict:
        """
        Extract structured data from a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dictionary with extracted data
        """
        data = {
            "file_name": pdf_path.name,
            "file_path": str(pdf_path),
            "file_size": pdf_path.stat().st_size if pdf_path.exists() else 0,
            "text": "",
            "tables": [],
            "metadata": {},
        }
        
        if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
            return data
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                data["metadata"] = {
                    "page_count": len(pdf.pages),
                    "pdf_info": pdf.metadata or {},
                }
                
                all_text = []
                all_tables = []
                
                for i, page in enumerate(pdf.pages):
                    # Extract text
                    page_text = page.extract_text()
                    if page_text:
                        all_text.append(page_text)
                    
                    # Extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        if table and len(table) > 0:
                            # Convert to list of dicts if possible
                            if len(table) > 1:
                                headers = [str(h) if h else f"col_{i}" for i, h in enumerate(table[0])]
                                rows = []
                                for row in table[1:]:
                                    row_dict = {}
                                    for j, cell in enumerate(row):
                                        key = headers[j] if j < len(headers) else f"col_{j}"
                                        row_dict[key] = str(cell) if cell else ""
                                    rows.append(row_dict)
                                all_tables.append({
                                    "page": i + 1,
                                    "headers": headers,
                                    "rows": rows,
                                })
                            else:
                                all_tables.append({
                                    "page": i + 1,
                                    "data": table,
                                })
                
                data["text"] = "\n\n".join(all_text)
                data["tables"] = all_tables
                
        except Exception as e:
            print(f"  ⚠ PDF extraction error for {pdf_path.name}: {e}")
        
        return data

    async def scrape_plan(self, case_id: str = None, plan_number: str = None) -> dict:
        """
        Scrape a complete plan with all attachments.
        
        Args:
            case_id: The case ID (UUID), or
            plan_number: The plan number to search for
            
        Returns:
            Complete plan data dictionary
        """
        # Resolve case_id from plan_number if needed
        if not case_id and plan_number:
            case_id = await self.search_plan_number(plan_number)
            if not case_id:
                raise ValueError(f"Could not find case ID for plan number: {plan_number}")
        
        if not case_id:
            raise ValueError("Either case_id or plan_number must be provided")
        
        print(f"\n{'='*60}")
        print(f"📄 SCRAPING PLAN: {case_id}")
        print(f"{'='*60}\n")
        
        # Get plan details
        plan_details = await self.get_plan_details(case_id)
        
        # Get attachments
        attachments = await self.get_attachments(case_id)
        
        # Download attachments
        downloaded_paths = await self.download_all_attachments(attachments, case_id)
        
        # Extract PDF data
        print("\n📖 Extracting PDF data...")
        pdf_data = []
        for path in tqdm(downloaded_paths, desc="Extracting"):
            extracted = self.extract_pdf_data(path)
            pdf_data.append(extracted)
        
        # Compile results
        result = {
            "case_id": case_id,
            "plan_number": plan_number,
            "scrape_timestamp": datetime.now().isoformat(),
            "plan_url": f"{BASE_URL}/#/plan/{case_id}",
            "plan_details": plan_details,
            "attachments_metadata": attachments,
            "attachments_count": len(attachments),
            "downloaded_count": len(downloaded_paths),
            "pdf_extractions": pdf_data,
        }
        
        # Save to JSON
        output_file = self.output_dir / f"{case_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n✅ Results saved to: {output_file}")
        
        return result


# =============================================================================
# CLI Interface
# =============================================================================


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Miami-Dade EnerGov Portal Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scrape by case ID
    python energov_scraper.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d
    
    # Scrape by plan number
    python energov_scraper.py --plan-number Z2024000202
    
    # Scrape with visible browser (for debugging)
    python energov_scraper.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d --visible
        """
    )
    
    parser.add_argument(
        "--case-id",
        help="Case ID (UUID) to scrape"
    )
    parser.add_argument(
        "--plan-number",
        help="Plan number to search and scrape"
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    
    args = parser.parse_args()
    
    if not args.case_id and not args.plan_number:
        parser.error("Either --case-id or --plan-number must be provided")
    
    # Run scraper
    async with EnerGovScraper(
        headless=not args.visible,
        output_dir=Path(args.output_dir)
    ) as scraper:
        result = await scraper.scrape_plan(
            case_id=args.case_id,
            plan_number=args.plan_number
        )
        
        # Print summary
        print("\n" + "="*60)
        print("📊 SCRAPE SUMMARY")
        print("="*60)
        print(f"Case ID: {result['case_id']}")
        print(f"Plan Number: {result.get('plan_number', 'N/A')}")
        print(f"Attachments Found: {result['attachments_count']}")
        print(f"Files Downloaded: {result['downloaded_count']}")
        print(f"PDFs Extracted: {len(result['pdf_extractions'])}")
        print(f"Output: {args.output_dir}/{result['case_id']}.json")


if __name__ == "__main__":
    asyncio.run(main())

