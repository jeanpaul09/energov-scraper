#!/usr/bin/env python3
"""
CDV Backend API Server

State-of-the-art FastAPI backend for PropertyReach integration,
permit data aggregation, and parcel intelligence.
"""

import os
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn


# ============================================
# CONFIGURATION
# ============================================

class Config:
    """Application configuration."""
    
    # PropertyReach API
    PROPERTYREACH_API_KEY = os.getenv(
        "PROPERTYREACH_API_KEY",
        "test_T9ktTlVrUgZuetmMperHBKm1i3P4jeSFamr"
    )
    PROPERTYREACH_BASE_URL = "https://api.propertyreach.com/v1"
    
    # Mapbox
    MAPBOX_ACCESS_TOKEN = os.getenv(
        "MAPBOX_ACCESS_TOKEN",
        "pk.eyJ1IjoiamVhbnBhdWwwOSIsImEiOiJjbWpqMWdmNmMxdjVvM2VxMzM5Nm92bmg3In0.2UPggL-HJqybJ3gk0smJAw"
    )
    
    # EnerGov Miami-Dade
    ENERGOV_BASE_URL = "https://energov.miamidade.gov/EnerGov_Prod/SelfService/api/energov"
    
    # Server
    HOST = "0.0.0.0"
    PORT = 8000
    DEBUG = True


# ============================================
# MODELS
# ============================================

class PropertySearchRequest(BaseModel):
    """Request model for property search."""
    city: Optional[str] = "Miami"
    state: Optional[str] = "FL"
    zip: Optional[str] = None
    county: Optional[str] = "Miami-Dade"
    limit: Optional[int] = Field(default=50, le=100)


class PropertyDetailRequest(BaseModel):
    """Request model for property details."""
    street_address: str
    city: Optional[str] = "Miami"
    state: Optional[str] = "FL"
    zip: Optional[str] = None


class GeocodingRequest(BaseModel):
    """Request for geocoding addresses."""
    query: str
    limit: Optional[int] = 5


class ParcelDimensions(BaseModel):
    """Parcel dimension data."""
    lot_sqft: Optional[float] = None
    lot_acres: Optional[float] = None
    lot_width: Optional[float] = None
    lot_depth: Optional[float] = None
    building_sqft: Optional[float] = None


class PropertyData(BaseModel):
    """Unified property data model."""
    property_id: Optional[str] = None
    address: str
    city: str = "Miami"
    state: str = "FL"
    zip: Optional[str] = None
    
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Parcel info
    folio: Optional[str] = None
    apn: Optional[str] = None
    zoning: Optional[str] = None
    land_use: Optional[str] = None
    
    # Dimensions
    dimensions: Optional[ParcelDimensions] = None
    
    # Building info
    year_built: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    stories: Optional[int] = None
    property_type: Optional[str] = None
    
    # Valuation
    land_value: Optional[float] = None
    building_value: Optional[float] = None
    total_value: Optional[float] = None
    assessed_value: Optional[float] = None
    
    # Sales history
    last_sale_price: Optional[float] = None
    last_sale_date: Optional[str] = None
    
    # Owner info
    owner_name: Optional[str] = None
    owner_mailing_address: Optional[str] = None
    
    # Metadata
    data_source: str = "propertyreach"
    fetched_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


# ============================================
# HTTP CLIENT
# ============================================

class PropertyReachClient:
    """Async client for PropertyReach API."""
    
    def __init__(self):
        self.base_url = Config.PROPERTYREACH_BASE_URL
        self.api_key = Config.PROPERTYREACH_API_KEY
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def get_property(
        self,
        street_address: str,
        city: str = "Miami",
        state: str = "FL",
        zip_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get property details by address."""
        params = {
            "streetAddress": street_address,
            "city": city,
            "state": state
        }
        if zip_code:
            params["zip"] = zip_code
        
        response = await self.client.get(
            f"{self.base_url}/property",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def search_properties(
        self,
        city: str = "Miami",
        state: str = "FL",
        county: Optional[str] = None,
        zip_code: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Search for properties in an area."""
        payload = {
            "target": {
                "city": city,
                "state": state
            },
            "limit": limit
        }
        if county:
            payload["target"]["county"] = county
        if zip_code:
            payload["target"]["zip"] = zip_code
        
        response = await self.client.post(
            f"{self.base_url}/search",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def autocomplete(
        self,
        query: str,
        state: str = "FL"
    ) -> Dict[str, Any]:
        """Autocomplete address search."""
        params = {
            "query": query,
            "state": state
        }
        response = await self.client.get(
            f"{self.base_url}/autocomplete",
            params=params
        )
        response.raise_for_status()
        return response.json()


class MapboxClient:
    """Async client for Mapbox geocoding."""
    
    def __init__(self):
        self.access_token = Config.MAPBOX_ACCESS_TOKEN
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        return self
    
    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()
    
    async def geocode(
        self,
        query: str,
        limit: int = 5,
        bbox: str = "-80.87,25.14,-80.03,25.97"  # Miami-Dade bounds
    ) -> List[Dict[str, Any]]:
        """Forward geocoding - address to coordinates."""
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json"
        params = {
            "access_token": self.access_token,
            "limit": limit,
            "bbox": bbox,
            "proximity": "-80.1918,25.7617"  # Miami center
        }
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("features", [])
    
    async def reverse_geocode(
        self,
        longitude: float,
        latitude: float
    ) -> Dict[str, Any]:
        """Reverse geocoding - coordinates to address."""
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{longitude},{latitude}.json"
        params = {"access_token": self.access_token}
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        return features[0] if features else {}


# ============================================
# APPLICATION SETUP
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    print("🚀 CDV Backend starting...")
    print(f"📍 PropertyReach API configured")
    print(f"🗺️  Mapbox configured")
    yield
    print("👋 CDV Backend shutting down...")


app = FastAPI(
    title="CDV Parcel Intelligence API",
    description="Backend API for Miami-Dade County parcel data and permit intelligence",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# API ROUTES
# ============================================

@app.get("/", response_model=APIResponse)
async def root():
    """API root endpoint."""
    return APIResponse(
        success=True,
        data={
            "name": "CDV Parcel Intelligence API",
            "version": "1.0.0",
            "status": "operational",
            "endpoints": {
                "property": "/api/property",
                "search": "/api/search",
                "autocomplete": "/api/autocomplete",
                "geocode": "/api/geocode",
                "health": "/health"
            }
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "propertyreach": "configured",
            "mapbox": "configured"
        }
    }


@app.get("/api/property", response_model=APIResponse)
async def get_property(
    address: str = Query(..., description="Street address"),
    city: str = Query("Miami", description="City name"),
    state: str = Query("FL", description="State code"),
    zip: Optional[str] = Query(None, description="ZIP code")
):
    """
    Get detailed property information by address.
    
    Uses PropertyReach API for comprehensive property data including
    dimensions, valuation, ownership, and sales history.
    """
    try:
        async with PropertyReachClient() as client:
            data = await client.get_property(
                street_address=address,
                city=city,
                state=state,
                zip_code=zip
            )
            
            # Transform to our unified model
            prop = data.get("property", data)
            
            property_data = PropertyData(
                property_id=str(prop.get("id", "")),
                address=f"{prop.get('streetAddress', address)}, {city}, {state}",
                city=city,
                state=state,
                zip=prop.get("zip", zip),
                latitude=prop.get("latitude"),
                longitude=prop.get("longitude"),
                folio=prop.get("apn") or prop.get("parcelNumber"),
                apn=prop.get("apn"),
                zoning=prop.get("zoning"),
                land_use=prop.get("propertyType") or prop.get("landUse"),
                dimensions=ParcelDimensions(
                    lot_sqft=prop.get("lotSquareFootage") or prop.get("lotSize"),
                    lot_acres=(prop.get("lotSquareFootage", 0) or 0) / 43560 if prop.get("lotSquareFootage") else None,
                    lot_width=prop.get("lotWidth"),
                    lot_depth=prop.get("lotDepth"),
                    building_sqft=prop.get("squareFootage")
                ),
                year_built=prop.get("yearBuilt"),
                bedrooms=prop.get("bedrooms"),
                bathrooms=prop.get("bathrooms"),
                stories=prop.get("stories"),
                property_type=prop.get("propertyType"),
                land_value=prop.get("landValue"),
                building_value=prop.get("improvementValue") or prop.get("buildingValue"),
                total_value=prop.get("assessedValue") or prop.get("totalValue"),
                assessed_value=prop.get("assessedValue"),
                last_sale_price=prop.get("lastSalePrice"),
                last_sale_date=prop.get("lastSaleDate"),
                owner_name=prop.get("ownerName"),
                owner_mailing_address=prop.get("ownerMailingAddress"),
                data_source="propertyreach"
            )
            
            return APIResponse(
                success=True,
                data=property_data.model_dump(),
                meta={"source": "propertyreach", "cached": False}
            )
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Property not found")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API error: {str(e)}")


@app.post("/api/search", response_model=APIResponse)
async def search_properties(request: PropertySearchRequest):
    """
    Search for properties in a geographic area.
    
    Returns a list of properties matching the search criteria.
    """
    try:
        async with PropertyReachClient() as client:
            data = await client.search_properties(
                city=request.city,
                state=request.state,
                county=request.county,
                zip_code=request.zip,
                limit=request.limit
            )
            
            return APIResponse(
                success=True,
                data=data,
                meta={
                    "source": "propertyreach",
                    "limit": request.limit,
                    "area": f"{request.city}, {request.state}"
                }
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/api/autocomplete", response_model=APIResponse)
async def autocomplete(
    q: str = Query(..., min_length=2, description="Search query"),
    state: str = Query("FL", description="State to search in")
):
    """
    Autocomplete address suggestions.
    
    Returns matching address suggestions as the user types.
    """
    try:
        async with PropertyReachClient() as client:
            data = await client.autocomplete(query=q, state=state)
            return APIResponse(
                success=True,
                data=data,
                meta={"query": q, "state": state}
            )
    except Exception as e:
        # Fallback to Mapbox geocoding
        async with MapboxClient() as mapbox:
            features = await mapbox.geocode(q, limit=5)
            suggestions = [
                {
                    "address": f.get("place_name", ""),
                    "center": f.get("center", []),
                    "relevance": f.get("relevance", 0)
                }
                for f in features
            ]
            return APIResponse(
                success=True,
                data={"suggestions": suggestions},
                meta={"query": q, "source": "mapbox_fallback"}
            )


@app.get("/api/geocode", response_model=APIResponse)
async def geocode(
    q: str = Query(..., description="Address or place to geocode"),
    limit: int = Query(5, le=10, description="Max results")
):
    """
    Geocode an address to coordinates.
    
    Uses Mapbox geocoding API focused on Miami-Dade County.
    """
    try:
        async with MapboxClient() as client:
            features = await client.geocode(q, limit=limit)
            results = [
                {
                    "place_name": f.get("place_name"),
                    "center": f.get("center"),
                    "bbox": f.get("bbox"),
                    "relevance": f.get("relevance"),
                    "place_type": f.get("place_type", [])
                }
                for f in features
            ]
            return APIResponse(
                success=True,
                data={"results": results},
                meta={"query": q, "count": len(results)}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Geocoding error: {str(e)}")


@app.get("/api/reverse-geocode", response_model=APIResponse)
async def reverse_geocode(
    lng: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude")
):
    """
    Reverse geocode coordinates to an address.
    """
    try:
        async with MapboxClient() as client:
            result = await client.reverse_geocode(lng, lat)
            return APIResponse(
                success=True,
                data=result,
                meta={"coordinates": [lng, lat]}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reverse geocoding error: {str(e)}")


# ============================================
# ERROR HANDLERS
# ============================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            error=exc.detail
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=APIResponse(
            success=False,
            error=f"Internal server error: {str(exc)}"
        ).model_dump()
    )


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║           CDV Parcel Intelligence API                 ║
    ║                   v1.0.0                              ║
    ╠═══════════════════════════════════════════════════════╣
    ║  Endpoints:                                           ║
    ║    GET  /api/property      - Property details         ║
    ║    POST /api/search        - Search properties        ║
    ║    GET  /api/autocomplete  - Address suggestions      ║
    ║    GET  /api/geocode       - Address to coordinates   ║
    ║    GET  /health            - Health check             ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host=Config.HOST,
        port=Config.PORT,
        reload=Config.DEBUG,
        log_level="info"
    )

