#!/usr/bin/env python3
"""
Batch Scraper for Miami-Dade EnerGov Portal

Process multiple plan numbers at once, with support for:
- CSV input files
- Command line plan lists
- Progress tracking and resumption
- Rate limiting to avoid overloading the server

Usage:
    # From command line
    python batch_scraper.py Z2024000202 Z2024000201 Z2024000200
    
    # From CSV file
    python batch_scraper.py --csv plans.csv --column plan_number
    
    # Resume interrupted scrape
    python batch_scraper.py --resume
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm import tqdm

from energov_scraper import EnerGovScraper

# =============================================================================
# Configuration
# =============================================================================

OUTPUT_DIR = Path("./output")
PROGRESS_FILE = OUTPUT_DIR / ".scrape_progress.json"
DEFAULT_DELAY = 2.0  # Seconds between scrapes


# =============================================================================
# Progress Tracker
# =============================================================================


class ProgressTracker:
    """Track scraping progress for resumption."""
    
    def __init__(self, progress_file: Path = PROGRESS_FILE):
        self.progress_file = progress_file
        self.data = self._load()
    
    def _load(self) -> dict:
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                return json.load(f)
        return {
            "completed": [],
            "failed": [],
            "pending": [],
            "last_updated": None,
        }
    
    def _save(self):
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.data["last_updated"] = datetime.now().isoformat()
        with open(self.progress_file, "w") as f:
            json.dump(self.data, f, indent=2)
    
    def set_pending(self, plan_ids: list[str]):
        """Set list of pending plans."""
        self.data["pending"] = plan_ids
        self._save()
    
    def mark_completed(self, plan_id: str):
        """Mark a plan as completed."""
        if plan_id in self.data["pending"]:
            self.data["pending"].remove(plan_id)
        if plan_id not in self.data["completed"]:
            self.data["completed"].append(plan_id)
        if plan_id in self.data["failed"]:
            self.data["failed"].remove(plan_id)
        self._save()
    
    def mark_failed(self, plan_id: str, error: str):
        """Mark a plan as failed."""
        if plan_id in self.data["pending"]:
            self.data["pending"].remove(plan_id)
        if plan_id not in self.data["failed"]:
            self.data["failed"].append(plan_id)
        self._save()
    
    def get_remaining(self) -> list[str]:
        """Get remaining plans to scrape."""
        return self.data["pending"]
    
    def reset(self):
        """Reset progress."""
        self.data = {
            "completed": [],
            "failed": [],
            "pending": [],
            "last_updated": None,
        }
        self._save()


# =============================================================================
# Batch Scraper
# =============================================================================


async def scrape_batch(
    plan_identifiers: list[str],
    output_dir: Path = OUTPUT_DIR,
    delay: float = DEFAULT_DELAY,
    headless: bool = True,
    resume: bool = False,
) -> dict:
    """
    Scrape multiple plans.
    
    Args:
        plan_identifiers: List of plan numbers or case IDs
        output_dir: Output directory
        delay: Delay between scrapes (seconds)
        headless: Run browser in headless mode
        resume: Resume from previous progress
        
    Returns:
        Summary dictionary
    """
    tracker = ProgressTracker(output_dir / ".scrape_progress.json")
    
    if resume:
        remaining = tracker.get_remaining()
        if remaining:
            print(f"📋 Resuming: {len(remaining)} plans remaining")
            plan_identifiers = remaining
        else:
            print("⚠️  No progress file found or all complete")
    else:
        tracker.set_pending(plan_identifiers)
    
    results = {
        "started_at": datetime.now().isoformat(),
        "total": len(plan_identifiers),
        "completed": [],
        "failed": [],
    }
    
    print(f"\n{'='*60}")
    print(f"🚀 BATCH SCRAPING {len(plan_identifiers)} PLANS")
    print(f"{'='*60}\n")
    
    async with EnerGovScraper(headless=headless, output_dir=output_dir) as scraper:
        for i, identifier in enumerate(tqdm(plan_identifiers, desc="Scraping")):
            print(f"\n[{i+1}/{len(plan_identifiers)}] Processing: {identifier}")
            
            try:
                # Determine if it's a case ID (UUID) or plan number
                is_uuid = len(identifier) == 36 and identifier.count("-") == 4
                
                if is_uuid:
                    await scraper.scrape_plan(case_id=identifier)
                else:
                    await scraper.scrape_plan(plan_number=identifier)
                
                tracker.mark_completed(identifier)
                results["completed"].append(identifier)
                
            except Exception as e:
                error_msg = str(e)
                print(f"  ❌ Failed: {error_msg}")
                tracker.mark_failed(identifier, error_msg)
                results["failed"].append({"id": identifier, "error": error_msg})
            
            # Rate limiting
            if i < len(plan_identifiers) - 1:
                await asyncio.sleep(delay)
    
    results["finished_at"] = datetime.now().isoformat()
    
    # Save summary
    summary_file = output_dir / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print(f"\n{'='*60}")
    print("📊 BATCH SUMMARY")
    print(f"{'='*60}")
    print(f"Total: {results['total']}")
    print(f"Completed: {len(results['completed'])}")
    print(f"Failed: {len(results['failed'])}")
    print(f"Summary saved: {summary_file}")
    
    return results


def load_plans_from_csv(
    csv_path: str,
    column: str = "plan_number"
) -> list[str]:
    """
    Load plan identifiers from CSV file.
    
    Args:
        csv_path: Path to CSV file
        column: Column name containing plan identifiers
        
    Returns:
        List of plan identifiers
    """
    df = pd.read_csv(csv_path)
    
    # Try to find the column
    if column in df.columns:
        return df[column].dropna().astype(str).tolist()
    
    # Try case-insensitive match
    col_lower = column.lower()
    for col in df.columns:
        if col.lower() == col_lower:
            return df[col].dropna().astype(str).tolist()
    
    # Try common column names
    for try_col in ["plan_number", "planNumber", "PlanNumber", "case_id", "caseId", "CaseId", "id", "ID"]:
        if try_col in df.columns:
            print(f"⚠️  Using column: {try_col}")
            return df[try_col].dropna().astype(str).tolist()
    
    raise ValueError(f"Column '{column}' not found. Available: {list(df.columns)}")


# =============================================================================
# CLI
# =============================================================================


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Batch scraper for Miami-Dade EnerGov Portal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scrape specific plans
    python batch_scraper.py Z2024000202 Z2024000201
    
    # From CSV file
    python batch_scraper.py --csv plans.csv --column plan_number
    
    # Resume interrupted scrape
    python batch_scraper.py --resume
    
    # With visible browser
    python batch_scraper.py --visible Z2024000202
        """
    )
    
    parser.add_argument(
        "plans",
        nargs="*",
        help="Plan numbers or case IDs to scrape"
    )
    parser.add_argument(
        "--csv",
        help="CSV file with plan identifiers"
    )
    parser.add_argument(
        "--column",
        default="plan_number",
        help="Column name in CSV (default: plan_number)"
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory (default: ./output)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay between scrapes in seconds (default: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous progress"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset progress and start fresh"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    
    # Reset progress if requested
    if args.reset:
        tracker = ProgressTracker(output_dir / ".scrape_progress.json")
        tracker.reset()
        print("✓ Progress reset")
        return
    
    # Get plans to scrape
    plans = []
    
    if args.csv:
        plans = load_plans_from_csv(args.csv, args.column)
        print(f"📂 Loaded {len(plans)} plans from {args.csv}")
    elif args.plans:
        plans = args.plans
    elif not args.resume:
        parser.error("Provide plan numbers, --csv file, or --resume")
    
    # Run batch scraper
    await scrape_batch(
        plan_identifiers=plans,
        output_dir=output_dir,
        delay=args.delay,
        headless=not args.visible,
        resume=args.resume,
    )


if __name__ == "__main__":
    asyncio.run(main())

