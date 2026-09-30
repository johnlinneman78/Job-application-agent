import asyncio
import sys
import os
from pathlib import Path

# Fix path
sys.path.append(str(Path.cwd()))

from src.models import Job, Platform
from src.job_scraper import GuardedJobScraper
from src.application_guard import ApplicationGuard

async def test_scan():
    config = {
        "search": {
            "keywords": ["Sales Development"],
            "locations": ["Remote"],
            "posted_within_days": 14
        }
    }
    try:
        print("Starting test scan...")
        guard = ApplicationGuard(config)
        scraper = GuardedJobScraper(config, guard)
        jobs = await scraper.discover_and_guard_check_jobs(
            titles=config["search"]["keywords"],
            locations=config["search"]["locations"],
            days_ago=config["search"]["posted_within_days"]
        )
        print(f"Found {len(jobs)} jobs.")
        for j in jobs:
            print(f"- {j.title} at {j.company}")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scan())
