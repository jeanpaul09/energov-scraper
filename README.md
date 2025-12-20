# Miami-Dade EnerGov Portal Scraper

A comprehensive Python scraper for extracting plan data, attachments (PDFs), and document content from the Miami-Dade County EnerGov permit portal.

## Features

- 🔍 **Search by Plan Number** - Automatically converts plan numbers to case IDs
- 📎 **Attachment Scraping** - Downloads all PDF attachments from plans
- 📖 **PDF Text Extraction** - Extracts text and tables from downloaded PDFs
- 📊 **JSON Output** - Structured data export for further processing
- 🔄 **Batch Processing** - Scrape multiple plans with progress tracking
- 🔧 **Resumable** - Can resume interrupted batch scrapes

## Installation

```bash
# Clone or navigate to the project directory
cd CDV

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## URL Encoding

The EnerGov portal uses UUIDs (Case IDs) to identify plans:

- **Plan Number**: `Z2024000202` (human-readable identifier)
- **Case ID**: `c75ba542-3e32-48f5-8f7b-418d3f8c1b6d` (UUID in URL)

The scraper handles this conversion automatically.

**Example URL:**
```
https://energov.miamidade.gov/EnerGov_Prod/SelfService/#/plan/c75ba542-3e32-48f5-8f7b-418d3f8c1b6d?tab=attachments
```

## Usage

### Single Plan Scraping

```bash
# Scrape by case ID (UUID)
python energov_scraper.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d

# Scrape by plan number (auto-resolves to case ID)
python energov_scraper.py --plan-number Z2024000202

# With visible browser (for debugging)
python energov_scraper.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d --visible

# Custom output directory
python energov_scraper.py --plan-number Z2024000202 --output-dir ./my_output
```

### Batch Scraping

```bash
# Scrape multiple plans
python batch_scraper.py Z2024000202 Z2024000201 Z2024000200

# From CSV file
python batch_scraper.py --csv plans.csv --column plan_number

# Resume interrupted scrape
python batch_scraper.py --resume

# Reset progress
python batch_scraper.py --reset

# With custom delay between scrapes
python batch_scraper.py --delay 5 Z2024000202 Z2024000201
```

### API Client (Direct API Access)

```bash
# Search for plans
python energov_api.py --search "Z2024000202"

# Get plan data
python energov_api.py --plan-number Z2024000202 -o plan_data.json

# Get data by case ID
python energov_api.py --case-id c75ba542-3e32-48f5-8f7b-418d3f8c1b6d
```

### Python API

```python
import asyncio
from energov_scraper import EnerGovScraper
from energov_api import EnerGovAPIClient

# Using the full scraper
async def scrape_plan():
    async with EnerGovScraper(headless=True) as scraper:
        result = await scraper.scrape_plan(plan_number="Z2024000202")
        print(f"Downloaded {result['downloaded_count']} attachments")

asyncio.run(scrape_plan())

# Using the API client directly
async def api_access():
    async with EnerGovAPIClient() as client:
        # Search
        results = await client.search_plans("Z2024000202")
        
        # Get details
        plan = await client.get_plan("c75ba542-3e32-48f5-8f7b-418d3f8c1b6d")
        
        # Get attachments
        attachments = await client.get_attachments("c75ba542-3e32-48f5-8f7b-418d3f8c1b6d")

asyncio.run(api_access())
```

## Output Structure

```
output/
├── {case_id}.json          # Complete scraped data
├── pdfs/
│   └── {case_id}/
│       ├── document1.pdf
│       ├── document2.pdf
│       └── ...
├── batch_summary_{timestamp}.json  # Batch scrape summary
└── .scrape_progress.json   # Progress tracking for resumption
```

### JSON Output Format

```json
{
  "case_id": "c75ba542-3e32-48f5-8f7b-418d3f8c1b6d",
  "plan_number": "Z2024000202",
  "scrape_timestamp": "2024-12-20T05:30:00.000Z",
  "plan_url": "https://energov.miamidade.gov/...",
  "plan_details": {
    "PlanNumber": "Z2024000202",
    "PlanType": "Zoning Hearings",
    "Status": "Completed",
    "Description": "...",
    "AppliedDate": "09/16/2024",
    "CompletionDate": "08/12/2025",
    "District": "Commission District 8",
    "AssignedTo": "..."
  },
  "attachments_metadata": [...],
  "attachments_count": 15,
  "downloaded_count": 15,
  "pdf_extractions": [
    {
      "file_name": "document.pdf",
      "text": "Extracted text content...",
      "tables": [...],
      "metadata": {
        "page_count": 5
      }
    }
  ]
}
```

## API Endpoints (Discovered)

The scraper uses these API endpoints from the EnerGov portal:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/energov/plans/{caseId}` | GET | Plan details |
| `/api/energov/entity/attachments/search/entityattachments/{caseId}/2/true` | GET | Attachments list |
| `/api/energov/entity/contacts/search/search` | POST | Contacts |
| `/api/energov/entity/inspections/search/search` | POST | Inspections |
| `/api/energov/entity/fees/search` | POST | Fees |
| `/api/energov/workflow/summary/activities/2/{caseId}` | GET | Review workflow |

## CSV Input Format

For batch scraping with `--csv`, your CSV should have a column with plan identifiers:

```csv
plan_number,notes
Z2024000202,First plan
Z2024000201,Second plan
```

## Dependencies

- **playwright** - Browser automation
- **lxml** - HTML/XML parsing
- **pdfplumber** - PDF text extraction
- **PyMuPDF** - PDF handling
- **pandas** - Data processing
- **httpx** - Async HTTP client
- **pydantic** - Data validation

## Troubleshooting

### Browser Issues
```bash
# Reinstall Playwright browsers
playwright install chromium
```

### Rate Limiting
The server may rate limit requests. Use `--delay` to increase time between scrapes:
```bash
python batch_scraper.py --delay 5 ...
```

### Session Issues
If scraping fails, try with visible browser to debug:
```bash
python energov_scraper.py --visible --plan-number Z2024000202
```

## Legal Notice

This scraper is designed for accessing publicly available permit information from the Miami-Dade County EnerGov portal. Users are responsible for complying with all applicable terms of service and data usage policies.

## License

MIT License - See LICENSE file for details.

