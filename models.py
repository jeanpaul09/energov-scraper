#!/usr/bin/env python3
"""
Data Models for Miami-Dade EnerGov Scraper

Pydantic models for parsing and validating EnerGov API responses.
These models were reverse-engineered from actual API responses.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Attachment Models
# =============================================================================


class AttachmentMetadata(BaseModel):
    """Metadata for an attachment file."""
    attachment_id: str = Field(default="", alias="AttachmentId")
    file_name: str = Field(default="", alias="FileName")
    file_type: str = Field(default="", alias="FileType")
    mime_type: str = Field(default="", alias="MimeType")
    category: str = Field(default="", alias="Category")
    description: str = Field(default="", alias="Description")
    created_date: Optional[str] = Field(default=None, alias="CreatedDate")
    created_by: str = Field(default="", alias="CreatedBy")
    file_size: int = Field(default=0, alias="FileSize")
    is_public: bool = Field(default=True, alias="IsPublic")
    needs_action: bool = Field(default=False, alias="NeedsAction")
    document_id: str = Field(default="", alias="DocumentId")
    
    class Config:
        populate_by_name = True
        extra = "allow"


class AttachmentWithData(AttachmentMetadata):
    """Attachment with extracted content."""
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    extracted_text: Optional[str] = None
    page_count: int = 0
    tables: list[dict] = Field(default_factory=list)
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Contact Models
# =============================================================================


class Contact(BaseModel):
    """Contact associated with a plan."""
    contact_id: str = Field(default="", alias="ContactId")
    contact_type: str = Field(default="", alias="ContactType")
    first_name: str = Field(default="", alias="FirstName")
    last_name: str = Field(default="", alias="LastName")
    full_name: str = Field(default="", alias="FullName")
    company_name: str = Field(default="", alias="CompanyName")
    email: str = Field(default="", alias="Email")
    phone: str = Field(default="", alias="Phone")
    address: str = Field(default="", alias="Address")
    city: str = Field(default="", alias="City")
    state: str = Field(default="", alias="State")
    zip_code: str = Field(default="", alias="ZipCode")
    is_primary: bool = Field(default=False, alias="IsPrimary")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Location Models
# =============================================================================


class Address(BaseModel):
    """Address/location information."""
    address_id: str = Field(default="", alias="AddressId")
    street_address: str = Field(default="", alias="StreetAddress")
    city: str = Field(default="", alias="City")
    state: str = Field(default="", alias="State")
    zip_code: str = Field(default="", alias="ZipCode")
    county: str = Field(default="", alias="County")
    parcel_number: str = Field(default="", alias="ParcelNumber")
    folio_number: str = Field(default="", alias="FolioNumber")
    latitude: Optional[float] = Field(default=None, alias="Latitude")
    longitude: Optional[float] = Field(default=None, alias="Longitude")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Review/Workflow Models
# =============================================================================


class ReviewActivity(BaseModel):
    """Review activity/workflow step."""
    activity_id: str = Field(default="", alias="ActivityId")
    activity_name: str = Field(default="", alias="ActivityName")
    activity_type: str = Field(default="", alias="ActivityType")
    status: str = Field(default="", alias="Status")
    assigned_to: str = Field(default="", alias="AssignedTo")
    department: str = Field(default="", alias="Department")
    due_date: Optional[str] = Field(default=None, alias="DueDate")
    completed_date: Optional[str] = Field(default=None, alias="CompletedDate")
    comments: str = Field(default="", alias="Comments")
    result: str = Field(default="", alias="Result")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Inspection Models
# =============================================================================


class Inspection(BaseModel):
    """Inspection record."""
    inspection_id: str = Field(default="", alias="InspectionId")
    inspection_type: str = Field(default="", alias="InspectionType")
    status: str = Field(default="", alias="Status")
    result: str = Field(default="", alias="Result")
    scheduled_date: Optional[str] = Field(default=None, alias="ScheduledDate")
    completed_date: Optional[str] = Field(default=None, alias="CompletedDate")
    inspector: str = Field(default="", alias="Inspector")
    comments: str = Field(default="", alias="Comments")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Fee Models
# =============================================================================


class Fee(BaseModel):
    """Fee record."""
    fee_id: str = Field(default="", alias="FeeId")
    fee_name: str = Field(default="", alias="FeeName")
    fee_code: str = Field(default="", alias="FeeCode")
    amount: float = Field(default=0.0, alias="Amount")
    paid_amount: float = Field(default=0.0, alias="PaidAmount")
    balance: float = Field(default=0.0, alias="Balance")
    status: str = Field(default="", alias="Status")
    due_date: Optional[str] = Field(default=None, alias="DueDate")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Plan Models
# =============================================================================


class PlanSummary(BaseModel):
    """Summary of a plan (from search results)."""
    plan_id: str = Field(default="", alias="PlanId")
    plan_number: str = Field(default="", alias="PlanNumber")
    plan_type: str = Field(default="", alias="PlanType")
    plan_type_name: str = Field(default="", alias="PlanTypeName")
    status: str = Field(default="", alias="Status")
    description: str = Field(default="", alias="Description")
    address: str = Field(default="", alias="Address")
    applied_date: Optional[str] = Field(default=None, alias="AppliedDate")
    
    class Config:
        populate_by_name = True
        extra = "allow"


class PlanDetails(BaseModel):
    """Detailed plan information."""
    plan_id: str = Field(default="", alias="PlanId")
    plan_number: str = Field(default="", alias="PlanNumber")
    plan_type: str = Field(default="", alias="PlanType")
    plan_type_name: str = Field(default="", alias="PlanTypeName")
    plan_class: str = Field(default="", alias="PlanClass")
    status: str = Field(default="", alias="Status")
    description: str = Field(default="", alias="Description")
    
    # Dates
    applied_date: Optional[str] = Field(default=None, alias="AppliedDate")
    opened_date: Optional[str] = Field(default=None, alias="OpenedDate")
    issued_date: Optional[str] = Field(default=None, alias="IssuedDate")
    expiration_date: Optional[str] = Field(default=None, alias="ExpirationDate")
    completion_date: Optional[str] = Field(default=None, alias="CompletionDate")
    
    # Assignment
    assigned_to: str = Field(default="", alias="AssignedTo")
    district: str = Field(default="", alias="District")
    
    # Identifiers
    ivr_number: str = Field(default="", alias="IVRNumber")
    project_id: str = Field(default="", alias="ProjectId")
    project_name: str = Field(default="", alias="ProjectName")
    
    # Valuation
    job_value: float = Field(default=0.0, alias="JobValue")
    total_square_feet: float = Field(default=0.0, alias="TotalSquareFeet")
    
    class Config:
        populate_by_name = True
        extra = "allow"


# =============================================================================
# Complete Scrape Result
# =============================================================================


class ScrapeResult(BaseModel):
    """Complete result of scraping a plan."""
    case_id: str
    plan_number: Optional[str] = None
    plan_url: str
    scrape_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    plan_details: Optional[dict] = None
    address: Optional[Address] = None
    contacts: list[Contact] = Field(default_factory=list)
    attachments: list[AttachmentWithData] = Field(default_factory=list)
    reviews: list[ReviewActivity] = Field(default_factory=list)
    inspections: list[Inspection] = Field(default_factory=list)
    fees: list[Fee] = Field(default_factory=list)
    
    # Stats
    attachments_count: int = 0
    downloaded_count: int = 0
    
    class Config:
        populate_by_name = True
        extra = "allow"
    
    def to_dataframe(self):
        """Convert to pandas DataFrame format."""
        import pandas as pd
        
        # Flatten for main record
        main_record = {
            "case_id": self.case_id,
            "plan_number": self.plan_number,
            "plan_url": self.plan_url,
            "scrape_timestamp": self.scrape_timestamp,
            "attachments_count": self.attachments_count,
            "downloaded_count": self.downloaded_count,
        }
        
        # Add plan details
        if self.plan_details:
            for k, v in self.plan_details.items():
                if not isinstance(v, (list, dict)):
                    main_record[f"plan_{k}"] = v
        
        return main_record
    
    def get_pdf_attachments(self) -> list[AttachmentWithData]:
        """Get only PDF attachments."""
        return [a for a in self.attachments if a.file_type.lower() == "pdf" or a.file_name.lower().endswith(".pdf")]


# =============================================================================
# Export Helpers
# =============================================================================


def results_to_dataframe(results: list[ScrapeResult]):
    """Convert list of results to pandas DataFrame."""
    import pandas as pd
    
    records = [r.to_dataframe() for r in results]
    return pd.DataFrame(records)


def attachments_to_dataframe(result: ScrapeResult):
    """Convert attachments to DataFrame."""
    import pandas as pd
    
    records = []
    for att in result.attachments:
        record = att.model_dump()
        record["case_id"] = result.case_id
        record["plan_number"] = result.plan_number
        records.append(record)
    
    return pd.DataFrame(records)

