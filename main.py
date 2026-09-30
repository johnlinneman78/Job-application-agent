"""
Main Orchestrator - Job Application Agent

Entry point for the guarded job application system.
"""
import asyncio
import yaml
import json
import logging
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt

from playwright.async_api import async_playwright
from src.models import Resume, Job, Application, ApplicationStatus
from src.resume_analyzer import ResumeAnalyzer
from src.job_scraper import GuardedJobScraper
from src.job_ranker import JobRanker
from src.application_guard import ApplicationGuard
from src.executor import ApplicationExecutor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Fix for Windows console UnicodeEncodeError
import sys
import os
if sys.platform == "win32":
    import io
    # Ensure stdout/stderr use utf-8 and don't crash on problematic chars
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # Environment variable fallback
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Initialize Console (Auto-detects encoding, sys.stdout wrapper handles the rest)
console = Console(force_terminal=True)


class JobApplicationAgent:
    """
    Main orchestrator for guarded job application automation.
    
    Workflow:
    1. Parse resume (auto)
    2. Discover jobs (auto)
    3. Run guard checks (auto)
    4. Rank jobs (auto)
    5. Generate dry-run report (auto)
    6. REQUEST PERMISSION
    7. Submit applications (guarded)
    """
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Try config.local.yaml first, fall back to config.yaml
            base_dir = Path(__file__).parent
            local_path = base_dir / "config.local.yaml"
            default_path = base_dir / "config.yaml"
            if local_path.exists():
                config_path = str(local_path)
            elif default_path.exists():
                config_path = str(default_path)
            elif Path("config.local.yaml").exists():
                config_path = "config.local.yaml"
            else:
                config_path = "config.yaml"
        
        # Load config
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.resume: Resume = None
        self.jobs_discovered: List[Job] = []
        self.jobs_ranked: List[Job] = []
        self.applications_prepared: List[Application] = []
        
        # Initialize components
        self.analyzer = ResumeAnalyzer()
        self.guard = ApplicationGuard(self.config)
    
    async def run(self, resume_path: str, dry_run: bool = False):
        """
        Run the full job application workflow.
        """
        console.print("\n[bold cyan]Job Application Agent Started[/bold cyan]\n")
        
        # Phase 1: Parse Resume
        console.print("[yellow]Phase 1:[/yellow] Parsing resume...")
        self.resume = self.analyzer.parse_resume(resume_path)
        console.print(f"Resume parsed: {self.resume.name}")
        console.print(f"  Skills: {', '.join(self.resume.technical_skills[:5])}...")
        console.print(f"  Experience: {self.resume.years_of_experience} years\n")
        
        # Generate role fit matrix
        role_fits = self.analyzer.generate_role_fit_matrix(self.resume)
        console.print("[yellow]Role Fit Matrix:[/yellow]")
        for role, score in role_fits.items():
            console.print(f"  {role}: {score * 100:.0f}% match")
        console.print()
        
        if dry_run:
            await self._run_dry_run(resume_path)
        else:
            await self._run_real_application(resume_path)

    async def _run_dry_run(self, resume_path: str):
        """Run discovery and guarding in headless mode without applying."""
        console.print("[yellow]Phase 2:[/yellow] Discovering jobs (Dry-Run)...")
        search_config = self.config.get("search", {})
        titles = search_config.get("keywords", [])
        locations = search_config.get("locations", [])
        days_ago = search_config.get("posted_within_days", 14)
        
        scraper = GuardedJobScraper(self.config, self.guard)
        self.jobs_discovered = await scraper.discover_and_guard_check_jobs(
            titles=titles,
            locations=locations,
            days_ago=days_ago
        )
        
        self.jobs_ranked = JobRanker(self.resume).rank_jobs(
            self.jobs_discovered, 
            limit=search_config.get("max_applications", 50)
        )
        
        self._show_dry_run_report(self.jobs_ranked)
        console.print("\n[bold green]Dry-run complete![/bold green]")

    async def _run_real_application(self, resume_path: str):
        """Headful application flow: Login -> Discover -> Guard -> Apply."""
        # Phase 2: Initializing Persistent Session
        console.print("[bold yellow]Phase 2:[/bold yellow] Initializing Persistent Session...")
        
        executor = ApplicationExecutor(self.config, self.guard)
        
        # Merge resume info into personal_info for enhanced field filling
        if self.resume:
            if "personal_info" not in self.config:
                self.config["personal_info"] = {}
            self.config["personal_info"]["email"] = self.resume.email
            self.config["personal_info"]["phone"] = self.resume.phone
            self.config["personal_info"]["name"] = self.resume.name
            
        search_config = self.config.get("search", {})
        user_data_dir = Path("data/browser_context").absolute()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        
        async with async_playwright() as p:
            # Launch with persistent context (saves login!)
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Step 1: Check login or Login
            if "linkedin.com" not in page.url or "feed" not in page.url:
                console.print("[cyan]Opening browser... Please log into LinkedIn when window appears.[/cyan]")
                await executor.login_to_linkedin(page)
            # await executor.login_to_indeed(page) # Optional, can add as needed
            
            # Step 2: In-Session Discovery (using the SAME context for cookies)
            console.print(f"\n[yellow]Phase 3:[/yellow] Discovering Portland/Remote Jobs (Logged In)...")
            scraper = GuardedJobScraper(self.config, self.guard)
            all_discovered_jobs = await scraper.discover_jobs(
                titles=search_config.get("keywords", []),
                locations=search_config.get("locations", ["Portland, OR", "Remote"]),
                days_ago=search_config.get("posted_within_days", 14),
                context=context
            )
            
            if not all_discovered_jobs:
                console.print("[red]No jobs found for the selected criteria.[/red]")
                await context.close()
                return

            # Step 3: Rank based on discovery data (Title/Company/Location)
            ranker = JobRanker(self.resume)
            self.jobs_ranked = ranker.rank_jobs(all_discovered_jobs, limit=100) # Pre-rank top 100
            
            # Step 4: Perform Guard Checks on ONLY the top matches to save time
            console.print(f"[yellow]Phase 4:[/yellow] Running guard checks on top {len(self.jobs_ranked)} matches...")
            safe_jobs = []
            await scraper._run_guard_checks(self.jobs_ranked, context, safe_jobs)
            
            if not safe_jobs:
                console.print("[red]No safe, resume-only jobs found among the top matches.[/red]")
                await context.close()
                return
            
            self.jobs_ranked = safe_jobs[:search_config.get("max_applications", 50)]
            self._show_dry_run_report(self.jobs_ranked)
            
            # Step 4: Final Permission
            proceed = Confirm.ask("\nProceed with submitting these applications?")
            if not proceed:
                console.print("[yellow]Cancelled.[/yellow]")
                await context.close()
                return
            
            # Step 5: Execute
            console.print("\n[yellow]Phase 6:[/yellow] Submitting applications (Mainting Session)...\n")
            executor.page = page  # Keep using the page we logged in on
            executor.resume = self.resume # Pass resume for field filling logic
            
            applications = await executor.apply_to_jobs(
                jobs=self.jobs_ranked,
                resume_path=resume_path,
                context=context
            )
            
            # Save and Finalize
            self._save_applications(applications, "data/applications_submitted.json")
            
            await context.close()
            console.print("\n[bold green]Done![/bold green] Check data/applications_submitted.json for results.")

    
    def _show_dry_run_report(self, jobs: List[Job]):
        """Display dry-run report table."""
        table = Table(title="Top Job Matches (Resume-Only)")
        
        table.add_column("#", style="cyan", width=4)
        table.add_column("Company", style="magenta", width=20)
        table.add_column("Title", style="green", width=30)
        table.add_column("Platform", width=10)
        table.add_column("Location", width=15)
        table.add_column("Match", style="yellow", width=8)
        
        for i, job in enumerate(jobs[:20], 1):  # Show top 20
            table.add_row(
                str(i),
                job.company[:20],
                job.title[:30],
                job.platform.value,
                job.location[:15],
                f"{job.match_score * 100:.0f}%"
            )
        
        console.print(table)
        
        if len(jobs) > 20:
            console.print(f"\n... and {len(jobs) - 20} more jobs")
    
    def _save_jobs(self, jobs: List[Job], filepath: str):
        """Save jobs to JSON file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        jobs_data = [job.model_dump(mode='json') for job in jobs]
        
        with open(filepath, 'w') as f:
            json.dump(jobs_data, f, indent=2, default=str)
        
        logger.info(f"Saved {len(jobs)} jobs to {filepath}")
    
    def _save_applications(self, applications: List[Application], filepath: str):
        """Save applications to JSON file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        apps_data = [app.model_dump(mode='json') for app in applications]
        
        with open(filepath, 'w') as f:
            json.dump(apps_data, f, indent=2, default=str)
        
        logger.info(f"Saved {len(applications)} applications to {filepath}")


async def main():
    """Main entry point."""
    import sys
    
    # Simple CLI
    if len(sys.argv) < 2:
        console.print("[red]Usage: python main.py <resume_path> [--dry-run][/red]")
        sys.exit(1)
    
    resume_path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    
    if not Path(resume_path).exists():
        console.print(f"[red]Error: Resume not found at {resume_path}[/red]")
        sys.exit(1)
    
    agent = JobApplicationAgent()
    await agent.run(resume_path, dry_run=dry_run)


if __name__ == "__main__":
    asyncio.run(main())
