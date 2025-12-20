#!/usr/bin/env python3
"""
EnerGov API Client for Miami-Dade County

This module provides a clean API interface for interacting with the
Miami-Dade EnerGov portal, handling:
- Plan searches and lookups
- Attachment retrieval
- File downloads

The API structure was reverse-engineered from the EnerGov portal network traffic.
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, quote

import httpx

# =============================================================================
# Constants
# =============================================================================

BASE_URL = "https://energov.miamidade.gov/EnerGov_Prod/SelfService"
API_BASE = "https://energov.miamidade.gov/energov_prod/selfservice/api"

# Entity types used in EnerGov
ENTITY_TYPES = {
    "PERMIT": 1,
    "PLAN": 2,
    "CODE_CASE": 3,
    "CODE_CASE_HEARING": 4,
    "BUSINESS_LICENSE": 5,
    "PROJECT": 6,
    "PROFESSIONAL_LICENSE": 7,
}

# =============================================================================
# API Client
# =============================================================================


class EnerGovAPIClient:
    """
    Async API client for Miami-Dade EnerGov portal.
    
    Usage:
        async with EnerGovAPIClient() as client:
            # Search for a plan
            results = await client.search_plans("Z2024000202")
            
            # Get plan details
            plan = await client.get_plan(case_id)
            
            # Get attachments
            attachments = await client.get_attachments(case_id)
    """
    
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
        self._session_cookies: dict = {}
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Referer": BASE_URL,
                "Origin": "https://energov.miamidade.gov",
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    def _build_url(self, endpoint: str) -> str:
        """Build full API URL."""
        if endpoint.startswith("http"):
            return endpoint
        return urljoin(API_BASE + "/", endpoint.lstrip("/"))
    
    async def _get(self, endpoint: str, params: dict = None) -> Any:
        """Make GET request."""
        url = self._build_url(endpoint)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def _post(self, endpoint: str, json: dict = None) -> Any:
        """Make POST request."""
        url = self._build_url(endpoint)
        response = await self.client.post(url, json=json)
        response.raise_for_status()
        return response.json()
    
    # -------------------------------------------------------------------------
    # Plan APIs
    # -------------------------------------------------------------------------
    
    async def search_plans(
        self,
        search_text: str,
        page_size: int = 20,
        page_number: int = 1
    ) -> dict:
        """
        Search for plans by text (plan number, address, etc).
        
        Args:
            search_text: Search query
            page_size: Results per page
            page_number: Page number (1-indexed)
            
        Returns:
            Search results dictionary
        """
        payload = {
            "SearchText": search_text,
            "ModuleName": "Plan",
            "TypeName": "",
            "SortColumn": "OpenedDate",
            "SortDirection": "desc",
            "PageSize": page_size,
            "PageNumber": page_number,
        }
        
        try:
            # Try the main search endpoint
            return await self._post("energov/search", payload)
        except httpx.HTTPStatusError:
            pass
        
        # Alternative endpoints to try
        try:
            return await self._post("energov/plans/search", payload)
        except httpx.HTTPStatusError:
            pass
        
        try:
            return await self._post("caps/plan/search", payload)
        except httpx.HTTPStatusError:
            pass
        
        return {"Result": [], "TotalCount": 0}
    
    async def get_plan(self, case_id: str) -> dict:
        """
        Get plan details by case ID.
        
        Args:
            case_id: The plan's case ID (UUID)
            
        Returns:
            Plan details dictionary
        """
        return await self._get(f"energov/plans/{case_id}")
    
    async def get_plan_workflow(self, case_id: str) -> dict:
        """Get workflow/review status for a plan."""
        return await self._get(f"energov/workflow/summary/activities/2/{case_id}")
    
    async def get_plan_fees(self, case_id: str) -> dict:
        """Get fees for a plan."""
        payload = {
            "EntityId": case_id,
            "EntityType": ENTITY_TYPES["PLAN"],
        }
        return await self._post("energov/entity/fees/search", payload)
    
    # -------------------------------------------------------------------------
    # Attachment APIs
    # -------------------------------------------------------------------------
    
    async def get_attachments(
        self,
        case_id: str,
        entity_type: int = ENTITY_TYPES["PLAN"],
        include_all: bool = True
    ) -> list[dict]:
        """
        Get attachments for a case.
        
        Args:
            case_id: The case ID (UUID)
            entity_type: Entity type (default: Plan = 2)
            include_all: Include all attachment types
            
        Returns:
            List of attachment dictionaries
        """
        endpoint = f"energov/entity/attachments/search/entityattachments/{case_id}/{entity_type}/{str(include_all).lower()}"
        result = await self._get(endpoint)
        
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get("Result", [])
        return []
    
    async def get_attachment_download_url(self, attachment_id: str) -> str:
        """
        Get the download URL for an attachment.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            Download URL
        """
        return f"{API_BASE}/energov/entity/attachments/download/{attachment_id}"
    
    async def download_attachment(self, attachment_id: str) -> bytes:
        """
        Download an attachment.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            File bytes
        """
        url = await self.get_attachment_download_url(attachment_id)
        response = await self.client.get(url)
        response.raise_for_status()
        return response.content
    
    # -------------------------------------------------------------------------
    # Contact APIs
    # -------------------------------------------------------------------------
    
    async def get_contacts(self, case_id: str, entity_type: int = ENTITY_TYPES["PLAN"]) -> list[dict]:
        """Get contacts associated with a case."""
        payload = {
            "EntityId": case_id,
            "EntityType": entity_type,
        }
        result = await self._post("energov/entity/contacts/search/search", payload)
        
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get("Result", [])
        return []
    
    # -------------------------------------------------------------------------
    # Inspection APIs
    # -------------------------------------------------------------------------
    
    async def get_inspections(self, case_id: str, entity_type: int = ENTITY_TYPES["PLAN"]) -> list[dict]:
        """Get inspections for a case."""
        payload = {
            "EntityId": case_id,
            "EntityType": entity_type,
        }
        result = await self._post("energov/entity/inspections/search/search", payload)
        
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get("Result", [])
        return []
    
    # -------------------------------------------------------------------------
    # Location APIs
    # -------------------------------------------------------------------------
    
    async def get_location_data(self, case_id: str) -> dict:
        """Get location/address data for a case."""
        payload = {"CAPId": case_id}
        return await self._post("energov/address/locationData", payload)
    
    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    
    async def plan_number_to_case_id(self, plan_number: str) -> Optional[str]:
        """
        Convert a plan number to its case ID.
        
        Args:
            plan_number: The plan number (e.g., "Z2024000202")
            
        Returns:
            Case ID (UUID) or None if not found
        """
        results = await self.search_plans(plan_number)
        
        # Parse results based on structure
        items = []
        if isinstance(results, list):
            items = results
        elif isinstance(results, dict):
            items = results.get("Result", []) or results.get("Results", [])
        
        # Find exact match
        for item in items:
            item_number = (
                item.get("PlanNumber") or 
                item.get("CAPNumber") or 
                item.get("Number") or 
                ""
            )
            if item_number.upper() == plan_number.upper():
                return (
                    item.get("PlanId") or 
                    item.get("CAPId") or 
                    item.get("CaseId") or 
                    item.get("Id")
                )
        
        # Return first result if no exact match
        if items:
            return (
                items[0].get("PlanId") or 
                items[0].get("CAPId") or 
                items[0].get("CaseId") or 
                items[0].get("Id")
            )
        
        return None
    
    def build_plan_url(self, case_id: str, tab: str = None) -> str:
        """
        Build the portal URL for a plan.
        
        Args:
            case_id: Case ID (UUID)
            tab: Optional tab name (summary, locations, fees, reviews, inspections, attachments, contacts, sub-records, meetings, more-info)
            
        Returns:
            Full portal URL
        """
        url = f"{BASE_URL}/#/plan/{case_id}"
        if tab:
            url += f"?tab={tab}"
        return url


# =============================================================================
# Standalone Functions
# =============================================================================


async def fetch_plan_with_attachments(
    case_id: str = None,
    plan_number: str = None
) -> dict:
    """
    Fetch complete plan data including attachments.
    
    Args:
        case_id: Case ID (UUID), or
        plan_number: Plan number to search
        
    Returns:
        Complete plan data dictionary
    """
    async with EnerGovAPIClient() as client:
        # Resolve case_id
        if not case_id and plan_number:
            case_id = await client.plan_number_to_case_id(plan_number)
            if not case_id:
                raise ValueError(f"Plan not found: {plan_number}")
        
        if not case_id:
            raise ValueError("Either case_id or plan_number required")
        
        # Fetch all data
        plan = await client.get_plan(case_id)
        attachments = await client.get_attachments(case_id)
        contacts = await client.get_contacts(case_id)
        inspections = await client.get_inspections(case_id)
        
        return {
            "case_id": case_id,
            "plan_number": plan_number,
            "url": client.build_plan_url(case_id),
            "plan_details": plan,
            "attachments": attachments,
            "contacts": contacts,
            "inspections": inspections,
            "fetched_at": datetime.now().isoformat(),
        }


# =============================================================================
# CLI
# =============================================================================


async def main():
    """CLI entry point."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="EnerGov API Client")
    parser.add_argument("--case-id", help="Case ID (UUID)")
    parser.add_argument("--plan-number", help="Plan number to lookup")
    parser.add_argument("--search", help="Search text")
    parser.add_argument("--output", "-o", help="Output file (JSON)")
    
    args = parser.parse_args()
    
    async with EnerGovAPIClient() as client:
        result = None
        
        if args.search:
            result = await client.search_plans(args.search)
            print(f"Found {len(result.get('Result', []))} results")
        
        elif args.case_id or args.plan_number:
            case_id = args.case_id
            if not case_id and args.plan_number:
                case_id = await client.plan_number_to_case_id(args.plan_number)
                print(f"Resolved plan {args.plan_number} -> {case_id}")
            
            if case_id:
                result = await fetch_plan_with_attachments(case_id=case_id)
        
        if result:
            output = json.dumps(result, indent=2, default=str)
            if args.output:
                with open(args.output, "w") as f:
                    f.write(output)
                print(f"Saved to {args.output}")
            else:
                print(output)


if __name__ == "__main__":
    asyncio.run(main())

